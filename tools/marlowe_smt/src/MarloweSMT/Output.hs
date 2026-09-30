{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module MarloweSMT.Output
  ( Meta(..)
  , ThmResultLike(..)
  , renderAnalysis
  , renderInvalidInput
  , renderInternalFailure
  , warningJSON
  , paymentJSON
  , stateJSON
  , contractJSON
  , transactionErrorJSON
  ) where

import Data.Aeson
import Data.Aeson.Types (Pair)
import qualified Data.Aeson.KeyMap as KeyMap
import qualified Data.ByteString as BS
import qualified Data.Map.Strict as Map
import qualified Data.Text as Text
import qualified Data.Text.Encoding as TextEncoding
import qualified Language.Marlowe.Semantics as S
import qualified Language.Marlowe.Semantics.Types as M

data Meta = Meta
  { metaSolver :: String
  , metaUpstreamCommit :: String
  , metaDriverVersion :: String
  }

metaJSON :: Meta -> Value
metaJSON meta = object
  [ "solver" .= metaSolver meta
  , "upstream_commit" .= metaUpstreamCommit meta
  , "driver_version" .= metaDriverVersion meta
  ]

renderAnalysis
  :: Meta
  -> [String]
  -> Either ThmResultLike (Maybe (M.POSIXTime, [S.TransactionInput], [S.TransactionWarning]))
  -> Value
renderAnalysis meta notes = \case
  Left theorem -> base "Indeterminate" [] Null notes meta
    ["solver_result" .= unThmResultLike theorem]
  Right Nothing -> base "Valid" [] Null notes meta []
  Right (Just (start, transactions, warnings)) ->
    base "Counterexample" (fmap warningJSON warnings)
      (object ["start_time" .= show start, "transactions" .= fmap transactionJSON transactions]) notes meta []

newtype ThmResultLike = ThmResultLike { unThmResultLike :: String }

renderInvalidInput :: Meta -> String -> Value
renderInvalidInput meta message = base "InvalidInput" [] Null [] meta ["error" .= message]

renderInternalFailure :: Meta -> String -> Value
renderInternalFailure meta message =
  base "Indeterminate" [] Null [] meta ["solver_result" .= message]

base :: String -> [Value] -> Value -> [String] -> Meta -> [Pair] -> Value
base status warnings counterexample notes meta extra = object $
  [ "status" .= status
  , "warnings" .= warnings
  , "counterexample" .= counterexample
  , "analysis_notes" .= notes
  , "meta" .= metaJSON meta
  ] <> extra

warningJSON :: S.TransactionWarning -> Value
warningJSON = \case
  S.TransactionNonPositiveDeposit party account amount -> object
    [ "type" .= String "TransactionNonPositiveDeposit"
    , "party" .= partyJSON party
    , "account" .= partyJSON account
    , "amount" .= amount
    ]
  S.TransactionNonPositivePay account payee amount -> object
    [ "type" .= String "TransactionNonPositivePay"
    , "account" .= partyJSON account
    , "payee" .= payeeJSON payee
    , "amount" .= amount
    ]
  S.TransactionPartialPay account payee paid expected -> object
    [ "type" .= String "TransactionPartialPay"
    , "account" .= partyJSON account
    , "payee" .= payeeJSON payee
    , "paid" .= paid
    , "expected" .= expected
    ]
  S.TransactionShadowing valueId oldValue newValue -> object
    [ "type" .= String "TransactionShadowing"
    , "value_id" .= valueIdText valueId
    , "old_value" .= oldValue
    , "new_value" .= newValue
    ]
  S.TransactionAssertionFailed -> object ["type" .= String "TransactionAssertionFailed"]

paymentJSON :: S.Payment -> Value
paymentJSON (S.Payment source payee token amount) = object
  [ "source_account" .= partyJSON source
  , "payee" .= payeeJSON payee
  , "token" .= tokenJSON token
  , "amount" .= amount
  ]

stateJSON :: M.State -> Value
stateJSON state = object
  [ "accounts" .= [[toJSON [partyJSON party, tokenJSON token], toJSON amount]
                   | ((party, token), amount) <- Map.toAscList (M.accounts state)]
  , "choices" .= [toJSON [choiceIdJSON choiceId, toJSON chosen]
                  | (choiceId, chosen) <- Map.toAscList (M.choices state)]
  , "boundValues" .= [toJSON [toJSON (valueIdText identifier), toJSON number]
                     | (identifier, number) <- Map.toAscList (M.boundValues state)]
  , "minTime" .= M.getPOSIXTime (M.minTime state)
  ]

contractJSON :: M.Contract -> Value
contractJSON = \case
  M.Close -> String "close"
  M.Pay source payee token amount continuation -> object
    [ "pay" .= valueJSON amount, "from_account" .= partyJSON source
    , "to" .= payeeJSON payee, "token" .= tokenJSON token
    , "then" .= contractJSON continuation
    ]
  M.If observation left right -> object
    [ "if" .= observationJSON observation, "then" .= contractJSON left
    , "else" .= contractJSON right
    ]
  M.When cases timeout continuation -> object
    [ "when" .= fmap caseJSON cases, "timeout" .= M.getPOSIXTime timeout
    , "timeout_continuation" .= contractJSON continuation
    ]
  M.Let identifier value continuation -> object
    [ "let" .= valueIdText identifier, "be" .= valueJSON value
    , "then" .= contractJSON continuation
    ]
  M.Assert observation continuation -> object
    [ "assert" .= observationJSON observation, "then" .= contractJSON continuation ]

caseJSON :: M.Case -> Value
caseJSON = \case
  M.Case action continuation -> object
    [ "case" .= actionJSON action, "then" .= contractJSON continuation ]
  M.MerkleizedCase action hash -> object
    [ "case" .= actionJSON action, "merkleized_then" .= bytesText hash ]

actionJSON :: M.Action -> Value
actionJSON = \case
  M.Deposit account party token amount -> object
    [ "into_account" .= partyJSON account, "party" .= partyJSON party
    , "of_token" .= tokenJSON token, "deposits" .= valueJSON amount
    ]
  M.Choice choiceId bounds -> object
    [ "for_choice" .= choiceIdJSON choiceId
    , "choose_between" .= [object ["from" .= lower, "to" .= upper]
                          | M.Bound lower upper <- bounds]
    ]
  M.Notify observation -> object ["notify_if" .= observationJSON observation]

valueJSON :: M.Value -> Value
valueJSON = \case
  M.AvailableMoney account token -> object
    ["in_account" .= partyJSON account, "amount_of_token" .= tokenJSON token]
  M.Constant number -> toJSON number
  M.NegValue value -> object ["negate" .= valueJSON value]
  M.AddValue left right -> object ["add" .= valueJSON left, "and" .= valueJSON right]
  M.SubValue left right -> object ["value" .= valueJSON left, "minus" .= valueJSON right]
  M.MulValue left right -> object ["multiply" .= valueJSON left, "times" .= valueJSON right]
  M.DivValue left right -> object ["divide" .= valueJSON left, "by" .= valueJSON right]
  M.ChoiceValue choiceId -> object ["value_of_choice" .= choiceIdJSON choiceId]
  M.TimeIntervalStart -> String "time_interval_start"
  M.TimeIntervalEnd -> String "time_interval_end"
  M.UseValue identifier -> object ["use_value" .= valueIdText identifier]
  M.Cond observation left right -> object
    ["if" .= observationJSON observation, "then" .= valueJSON left, "else" .= valueJSON right]

observationJSON :: M.Observation -> Value
observationJSON = \case
  M.AndObs left right -> object ["both" .= observationJSON left, "and" .= observationJSON right]
  M.OrObs left right -> object ["either" .= observationJSON left, "or" .= observationJSON right]
  M.NotObs value -> object ["not" .= observationJSON value]
  M.ChoseSomething choiceId -> object ["chose_something_for" .= choiceIdJSON choiceId]
  M.ValueGE left right -> compareJSON "ge_than" left right
  M.ValueGT left right -> compareJSON "gt" left right
  M.ValueLT left right -> compareJSON "lt" left right
  M.ValueLE left right -> compareJSON "le_than" left right
  M.ValueEQ left right -> compareJSON "equal_to" left right
  M.TrueObs -> Bool True
  M.FalseObs -> Bool False
  where
    compareJSON key left right = object ["value" .= valueJSON left, key .= valueJSON right]

transactionErrorJSON :: S.TransactionError -> Value
transactionErrorJSON = \case
  S.TEAmbiguousTimeIntervalError -> object ["type" .= String "TEAmbiguousTimeIntervalError"]
  S.TEApplyHashMismatch -> object ["type" .= String "TEApplyHashMismatch"]
  S.TEApplyNoMatchError -> object ["type" .= String "TEApplyNoMatchError"]
  S.TEUselessTransaction -> object ["type" .= String "TEUselessTransaction"]
  S.TEIntervalError intervalError -> object
    ["type" .= String "TEIntervalError", "detail" .= intervalErrorJSON intervalError]

intervalErrorJSON :: M.IntervalError -> Value
intervalErrorJSON = \case
  M.InvalidInterval interval -> object
    ["type" .= String "InvalidInterval", "interval" .= intervalJSON interval]
  M.IntervalInPastError minTime interval -> object
    ["type" .= String "IntervalInPastError", "min_time" .= M.getPOSIXTime minTime
    , "interval" .= intervalJSON interval]

transactionJSON :: S.TransactionInput -> Value
transactionJSON (S.TransactionInput interval inputs) = object
  [ "interval" .= intervalJSON interval
  , "inputs" .= fmap inputJSON inputs
  ]

intervalJSON :: M.TimeInterval -> Value
intervalJSON (M.TimeInterval lower upper) = object ["from" .= show lower, "to" .= show upper]

inputJSON :: M.Input -> Value
inputJSON = \case
  M.NormalInput content -> inputContentJSON content
  M.MerkleizedInput content hash -> case inputContentJSON content of
    Object fields -> Object (KeyMap.insert "merkleized_continuation" (toJSON (bytesText hash)) fields)
    impossible -> impossible

inputContentJSON :: M.InputContent -> Value
inputContentJSON = \case
  M.IDeposit account party token amount -> object
    [ "type" .= String "Deposit"
    , "account" .= partyJSON account
    , "party" .= partyJSON party
    , "token" .= tokenJSON token
    , "amount" .= amount
    ]
  M.IChoice choiceId chosen -> object
    [ "type" .= String "Choice"
    , "choice_id" .= choiceIdJSON choiceId
    , "chosen" .= chosen
    ]
  M.INotify -> object ["type" .= String "Notify"]

partyJSON :: M.Party -> Value
partyJSON = \case
  M.Address address -> object ["address" .= bytesText address]
  M.Role role -> object ["role_token" .= bytesText role]

payeeJSON :: M.Payee -> Value
payeeJSON = \case
  M.Account account -> object ["account" .= partyJSON account]
  M.Party party -> object ["party" .= partyJSON party]

tokenJSON :: M.Token -> Value
tokenJSON (M.Token currency tokenName) = object
  [ "currency_symbol" .= bytesText currency
  , "token_name" .= bytesText tokenName
  ]

choiceIdJSON :: M.ChoiceId -> Value
choiceIdJSON (M.ChoiceId name owner) = object
  [ "choice_name" .= bytesText name
  , "choice_owner" .= partyJSON owner
  ]

valueIdText :: M.ValueId -> Text.Text
valueIdText (M.ValueId value) = value

bytesText :: BS.ByteString -> Text.Text
bytesText = TextEncoding.decodeUtf8
