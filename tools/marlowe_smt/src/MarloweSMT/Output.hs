{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module MarloweSMT.Output
  ( Meta(..)
  , ThmResultLike(..)
  , renderAnalysis
  , renderInvalidInput
  , renderInternalFailure
  ) where

import Data.Aeson
import Data.Aeson.Types (Pair)
import qualified Data.Aeson.KeyMap as KeyMap
import qualified Data.ByteString as BS
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
