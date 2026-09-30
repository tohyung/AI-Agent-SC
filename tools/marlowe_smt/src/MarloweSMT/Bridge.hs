{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module MarloweSMT.Bridge
  ( Request(..)
  , parseRequest
  , ReferenceRequest(..)
  , parseReferenceRequest
  , countMerkleizedCases
  ) where

import Control.Monad (unless, when)
import Data.Aeson
import Data.Aeson.Key (Key)
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Aeson.Types (Parser)
import qualified Data.ByteString.Char8 as BS
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Data.Text as Text
import qualified Data.Text.Encoding as TextEncoding
import qualified Data.Vector as Vector
import qualified Language.Marlowe.Semantics.Types as M
import qualified Language.Marlowe.Semantics as S
import Text.Read (readMaybe)

data Request = Request
  { requestContract :: M.Contract
  , requestState :: Maybe M.State
  }

data ReferenceRequest = ReferenceRequest
  { referenceContract :: M.Contract
  , referenceState :: M.State
  , referenceTransactions :: [S.TransactionInput]
  , referenceHasMerkleizedInput :: Bool
  }

parseReferenceRequest :: Value -> Parser ReferenceRequest
parseReferenceRequest = withObject "reference request" $ \object -> do
  exact "reference request" ["contract", "state", "transactions"] object
  contract <- object .: "contract" >>= parseContract
  state <- object .: "state" >>= parseState
  transactions <- object .: "transactions" >>= parseList "transactions" parseTransaction
  let merkleized = any (any isMerkleized . S.txInputs) transactions
  pure ReferenceRequest
    { referenceContract = contract
    , referenceState = state
    , referenceTransactions = transactions
    , referenceHasMerkleizedInput = merkleized
    }
  where
    isMerkleized (M.MerkleizedInput _ _) = True
    isMerkleized _ = False

parseTransaction :: Value -> Parser S.TransactionInput
parseTransaction = withObject "TransactionInput" $ \object -> do
  exact "TransactionInput" ["interval", "inputs"] object
  interval <- object .: "interval" >>= parseInterval
  inputs <- object .: "inputs" >>= parseList "inputs" parseInput
  pure (S.TransactionInput interval inputs)

parseInterval :: Value -> Parser M.TimeInterval
parseInterval = withObject "TimeInterval" $ \object -> do
  exact "TimeInterval" ["from", "to"] object
  lower <- object .: "from" >>= parsePOSIX
  upper <- object .: "to" >>= parsePOSIX
  pure (M.TimeInterval lower upper)

parsePOSIX :: Value -> Parser M.POSIXTime
parsePOSIX value = M.POSIXTime <$> case value of
  Number _ -> parseJSON value
  String text -> maybe (fail "invalid POSIX millisecond integer") pure (readMaybe (Text.unpack text))
  _ -> fail "POSIX time must be an integer or decimal string"

parseInput :: Value -> Parser M.Input
parseInput = withObject "Input" $ \object -> do
  let merkleized = KeyMap.member "merkleized_continuation" object
      fields = if merkleized then KeyMap.delete "merkleized_continuation" object else object
  content <- parseInputContent (Object fields)
  if merkleized
    then M.MerkleizedInput content . utf8 <$> fieldText False "merkleized_continuation" object "merkleized_continuation"
    else pure (M.NormalInput content)

parseInputContent :: Value -> Parser M.InputContent
parseInputContent = withObject "InputContent" $ \object -> do
  kind <- object .: "type" :: Parser Text.Text
  case kind of
    "Deposit" -> do
      exact "Deposit input" ["type", "account", "party", "token", "amount"] object
      M.IDeposit
        <$> (object .: "account" >>= parseParty)
        <*> (object .: "party" >>= parseParty)
        <*> (object .: "token" >>= parseToken)
        <*> object .: "amount"
    "Choice" -> do
      exact "Choice input" ["type", "choice_id", "chosen"] object
      M.IChoice
        <$> (object .: "choice_id" >>= parseChoiceId)
        <*> object .: "chosen"
    "Notify" -> exact "Notify input" ["type"] object *> pure M.INotify
    _ -> fail "unsupported input type"

parseRequest :: Value -> Parser Request
parseRequest value@(Object object)
  | KeyMap.member "contract" object = do
      exactOneOf "request envelope" [["contract"], ["contract", "state"]] object
      contract <- object .: "contract" >>= parseContract
      state <- object .:? "state" >>= traverse parseState
      pure Request {requestContract = contract, requestState = state}
  | otherwise = Request <$> parseContract value <*> pure Nothing
parseRequest value = Request <$> parseContract value <*> pure Nothing

parseState :: Value -> Parser M.State
parseState = withObject "State" $ \object -> do
  exact "State" ["accounts", "choices", "boundValues", "minTime"] object
  accountEntries <- object .: "accounts" >>= parseList "accounts" parseAccountEntry
  choiceEntries <- object .: "choices" >>= parseList "choices" parseChoiceEntry
  boundEntries <- object .: "boundValues" >>= parseList "boundValues" parseBoundValueEntry
  minTime <- M.POSIXTime <$> object .: "minTime"
  unique "accounts" (fmap fst accountEntries)
  unique "choices" (fmap fst choiceEntries)
  unique "boundValues" (fmap fst boundEntries)
  pure M.State
    { M.accounts = Map.fromList accountEntries
    , M.choices = Map.fromList choiceEntries
    , M.boundValues = Map.fromList boundEntries
    , M.minTime = minTime
    }

parseAccountEntry :: Value -> Parser ((M.Party, M.Token), Integer)
parseAccountEntry = parsePair "account entry" $ \key value -> do
  (party, token) <- parsePair "account key" (\p t -> (,) <$> parseParty p <*> parseToken t) key
  amount <- parseJSON value
  pure ((party, token), amount)

parseChoiceEntry :: Value -> Parser (M.ChoiceId, Integer)
parseChoiceEntry = parsePair "choice entry" $ \key value -> (,) <$> parseChoiceId key <*> parseJSON value

parseBoundValueEntry :: Value -> Parser (M.ValueId, Integer)
parseBoundValueEntry = parsePair "bound-value entry" $ \key value -> do
  identifier <- M.ValueId <$> parseNonEmptyText "value id" key
  number <- parseJSON value
  pure (identifier, number)

parsePair :: String -> (Value -> Value -> Parser a) -> Value -> Parser a
parsePair label parser = withArray label $ \items -> do
  unless (Vector.length items == 2) (fail (label <> " must contain exactly two elements"))
  parser (items Vector.! 0) (items Vector.! 1)

parseList :: String -> (Value -> Parser a) -> Value -> Parser [a]
parseList label parser = withArray label (mapM parser . Vector.toList)

unique :: Ord a => String -> [a] -> Parser ()
unique label values =
  unless (Set.size (Set.fromList values) == length values) (fail (label <> " contains duplicate keys"))

utf8 :: Text.Text -> BS.ByteString
utf8 = TextEncoding.encodeUtf8

parseNonEmptyText :: String -> Value -> Parser Text.Text
parseNonEmptyText label = withText label $ \text -> do
  when (Text.null text) (fail (label <> " must not be empty"))
  pure text

fieldText :: Bool -> String -> Object -> Key -> Parser Text.Text
fieldText allowEmpty label object key = do
  text <- object .: key
  unless (allowEmpty || not (Text.null text)) (fail (label <> " must not be empty"))
  pure text

parseParty :: Value -> Parser M.Party
parseParty = withObject "Party" $ \object -> do
  exactOneOf "Party" [["role_token"], ["address"]] object
  if KeyMap.member "role_token" object
    then M.Role . utf8 <$> fieldText False "role_token" object "role_token"
    else M.Address . utf8 <$> fieldText False "address" object "address"

parseToken :: Value -> Parser M.Token
parseToken = withObject "Token" $ \object -> do
  exact "Token" ["currency_symbol", "token_name"] object
  M.Token
    <$> (utf8 <$> fieldText True "currency_symbol" object "currency_symbol")
    <*> (utf8 <$> fieldText True "token_name" object "token_name")

parseChoiceId :: Value -> Parser M.ChoiceId
parseChoiceId = withObject "ChoiceId" $ \object -> do
  exact "ChoiceId" ["choice_name", "choice_owner"] object
  M.ChoiceId
    <$> (utf8 <$> fieldText False "choice_name" object "choice_name")
    <*> (object .: "choice_owner" >>= parseParty)

parseBound :: Value -> Parser M.Bound
parseBound = withObject "Bound" $ \object -> do
  exact "Bound" ["from", "to"] object
  lower <- object .: "from"
  upper <- object .: "to"
  when (lower > upper) (fail "Bound.from must be <= Bound.to")
  pure (M.Bound lower upper)

parsePayee :: Value -> Parser M.Payee
parsePayee = withObject "Payee" $ \object -> do
  exactOneOf "Payee" [["party"], ["account"]] object
  if KeyMap.member "party" object
    then M.Party <$> (object .: "party" >>= parseParty)
    else M.Account <$> (object .: "account" >>= parseParty)

parseValueExpr :: Value -> Parser M.Value
parseValueExpr value@(Number _) = M.Constant <$> parseJSON value
parseValueExpr (String "time_interval_start") = pure M.TimeIntervalStart
parseValueExpr (String "time_interval_end") = pure M.TimeIntervalEnd
parseValueExpr (Object object) = do
  exactOneOf "Value"
    [ ["in_account", "amount_of_token"]
    , ["negate"]
    , ["add", "and"]
    , ["value", "minus"]
    , ["multiply", "times"]
    , ["divide", "by"]
    , ["value_of_choice"]
    , ["use_value"]
    , ["if", "then", "else"]
    ] object
  if KeyMap.member "in_account" object then M.AvailableMoney
      <$> (object .: "in_account" >>= parseParty)
      <*> (object .: "amount_of_token" >>= parseToken)
  else if KeyMap.member "negate" object then M.NegValue <$> (object .: "negate" >>= parseValueExpr)
  else if KeyMap.member "add" object then M.AddValue <$> (object .: "add" >>= parseValueExpr) <*> (object .: "and" >>= parseValueExpr)
  else if KeyMap.member "minus" object then M.SubValue <$> (object .: "value" >>= parseValueExpr) <*> (object .: "minus" >>= parseValueExpr)
  else if KeyMap.member "multiply" object then M.MulValue <$> (object .: "multiply" >>= parseValueExpr) <*> (object .: "times" >>= parseValueExpr)
  else if KeyMap.member "divide" object then M.DivValue <$> (object .: "divide" >>= parseValueExpr) <*> (object .: "by" >>= parseValueExpr)
  else if KeyMap.member "value_of_choice" object then M.ChoiceValue <$> (object .: "value_of_choice" >>= parseChoiceId)
  else if KeyMap.member "use_value" object then M.UseValue . M.ValueId <$> fieldText False "use_value" object "use_value"
  else M.Cond <$> (object .: "if" >>= parseObservation) <*> (object .: "then" >>= parseValueExpr) <*> (object .: "else" >>= parseValueExpr)
parseValueExpr _ = fail "Value must be an integer, a time literal, or a supported object"

parseObservation :: Value -> Parser M.Observation
parseObservation (Bool True) = pure M.TrueObs
parseObservation (Bool False) = pure M.FalseObs
parseObservation (Object object) = do
  exactOneOf "Observation"
    [ ["both", "and"]
    , ["either", "or"]
    , ["not"]
    , ["chose_something_for"]
    , ["value", "ge_than"]
    , ["value", "gt"]
    , ["value", "lt"]
    , ["value", "le_than"]
    , ["value", "equal_to"]
    ] object
  if KeyMap.member "both" object then M.AndObs <$> (object .: "both" >>= parseObservation) <*> (object .: "and" >>= parseObservation)
  else if KeyMap.member "either" object then M.OrObs <$> (object .: "either" >>= parseObservation) <*> (object .: "or" >>= parseObservation)
  else if KeyMap.member "not" object then M.NotObs <$> (object .: "not" >>= parseObservation)
  else if KeyMap.member "chose_something_for" object then M.ChoseSomething <$> (object .: "chose_something_for" >>= parseChoiceId)
  else if KeyMap.member "ge_than" object then M.ValueGE <$> (object .: "value" >>= parseValueExpr) <*> (object .: "ge_than" >>= parseValueExpr)
  else if KeyMap.member "gt" object then M.ValueGT <$> (object .: "value" >>= parseValueExpr) <*> (object .: "gt" >>= parseValueExpr)
  else if KeyMap.member "lt" object then M.ValueLT <$> (object .: "value" >>= parseValueExpr) <*> (object .: "lt" >>= parseValueExpr)
  else if KeyMap.member "le_than" object then M.ValueLE <$> (object .: "value" >>= parseValueExpr) <*> (object .: "le_than" >>= parseValueExpr)
  else M.ValueEQ <$> (object .: "value" >>= parseValueExpr) <*> (object .: "equal_to" >>= parseValueExpr)
parseObservation _ = fail "Observation must be a boolean or a supported object"

parseAction :: Value -> Parser M.Action
parseAction = withObject "Action" $ \object -> do
  exactOneOf "Action"
    [ ["party", "deposits", "of_token", "into_account"]
    , ["for_choice", "choose_between"]
    , ["notify_if"]
    ] object
  if KeyMap.member "deposits" object then M.Deposit
      <$> (object .: "into_account" >>= parseParty)
      <*> (object .: "party" >>= parseParty)
      <*> (object .: "of_token" >>= parseToken)
      <*> (object .: "deposits" >>= parseValueExpr)
  else if KeyMap.member "for_choice" object then do
    bounds <- object .: "choose_between" >>= parseList "choose_between" parseBound
    when (null bounds) (fail "choose_between must not be empty")
    M.Choice <$> (object .: "for_choice" >>= parseChoiceId) <*> pure bounds
  else M.Notify <$> (object .: "notify_if" >>= parseObservation)

parseCase :: Value -> Parser M.Case
parseCase = withObject "Case" $ \object -> do
  exactOneOf "Case" [["case", "then"], ["case", "merkleized_then"]] object
  action <- object .: "case" >>= parseAction
  if KeyMap.member "then" object
    then M.Case action <$> (object .: "then" >>= parseContract)
    else M.MerkleizedCase action . utf8 <$> fieldText False "merkleized_then" object "merkleized_then"

parseContract :: Value -> Parser M.Contract
parseContract (String "close") = pure M.Close
parseContract (Object object) = do
  exactOneOf "Contract"
    [ ["pay", "from_account", "to", "token", "then"]
    , ["if", "then", "else"]
    , ["when", "timeout", "timeout_continuation"]
    , ["let", "be", "then"]
    , ["assert", "then"]
    ] object
  if KeyMap.member "pay" object then M.Pay
      <$> (object .: "from_account" >>= parseParty)
      <*> (object .: "to" >>= parsePayee)
      <*> (object .: "token" >>= parseToken)
      <*> (object .: "pay" >>= parseValueExpr)
      <*> (object .: "then" >>= parseContract)
  else if KeyMap.member "if" object then M.If
      <$> (object .: "if" >>= parseObservation)
      <*> (object .: "then" >>= parseContract)
      <*> (object .: "else" >>= parseContract)
  else if KeyMap.member "when" object then do
    timeout <- object .: "timeout"
    when (timeout <= (0 :: Integer)) (fail "timeout must be a positive POSIX millisecond integer")
    M.When
      <$> (object .: "when" >>= parseList "when" parseCase)
      <*> pure (M.POSIXTime timeout)
      <*> (object .: "timeout_continuation" >>= parseContract)
  else if KeyMap.member "let" object then M.Let
      <$> (M.ValueId <$> fieldText False "let" object "let")
      <*> (object .: "be" >>= parseValueExpr)
      <*> (object .: "then" >>= parseContract)
  else M.Assert <$> (object .: "assert" >>= parseObservation) <*> (object .: "then" >>= parseContract)
parseContract _ = fail "Contract must be \"close\" or a supported object"

exact :: String -> [Key] -> Object -> Parser ()
exact label fields = exactOneOf label [fields]

exactOneOf :: String -> [[Key]] -> Object -> Parser ()
exactOneOf label alternatives object = do
  let actual = Set.fromList (KeyMap.keys object)
      expected = fmap Set.fromList alternatives
  unless (actual `elem` expected) $ fail $
    label <> " has invalid fields " <> showKeys actual <>
    "; expected one of " <> show (fmap (fmap Key.toString . Set.toList) expected)

showKeys :: Set.Set Key -> String
showKeys = show . fmap Key.toString . Set.toList

countMerkleizedCases :: M.Contract -> Int
countMerkleizedCases = \case
  M.Close -> 0
  M.Pay _ _ _ _ continuation -> countMerkleizedCases continuation
  M.If _ left right -> countMerkleizedCases left + countMerkleizedCases right
  M.When cases _ timeoutContinuation -> sum (fmap countCase cases) + countMerkleizedCases timeoutContinuation
  M.Let _ _ continuation -> countMerkleizedCases continuation
  M.Assert _ continuation -> countMerkleizedCases continuation
  where
    countCase (M.Case _ continuation) = countMerkleizedCases continuation
    countCase (M.MerkleizedCase _ _) = 1
