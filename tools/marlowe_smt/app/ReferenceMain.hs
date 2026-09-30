{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Data.Aeson
import Data.Aeson.Types (parseEither)
import qualified Data.ByteString.Lazy.Char8 as BSL
import MarloweSMT.Bridge
import MarloweSMT.Output
import qualified Language.Marlowe.Semantics as S
import qualified Language.Marlowe.Semantics.Types as M
import System.Exit (exitFailure)

upstreamCommit :: String
upstreamCommit = "7b5b1e900ec53a8eb18747992bec73470704dfcb"

driverVersion :: String
driverVersion = "0.1.0"

metaJSON :: Value
metaJSON = object
  [ "upstream_commit" .= upstreamCommit
  , "reference_driver_version" .= driverVersion
  ]

response :: String -> [Value] -> M.State -> M.Contract -> Value -> Value
response status steps state contract details = object
  [ "status" .= status
  , "meta" .= metaJSON
  , "steps" .= steps
  , "final_state" .= stateJSON state
  , "final_contract" .= contractJSON contract
  , "detail" .= details
  ]

main :: IO ()
main = do
  input <- BSL.getContents
  case eitherDecode input :: Either String Value of
    Left message -> invalid ("invalid JSON: " <> message)
    Right value -> case parseEither parseReferenceRequest value of
      Left message -> invalid ("invalid Core V1 reference request: " <> message)
      Right request -> do
        let contract = referenceContract request
            state = referenceState request
        if countMerkleizedCases contract > 0 || referenceHasMerkleizedInput request
          then emit (response "Unsupported" [] state contract
            (object ["reason" .= String "merkleized_continuation_not_supported"]))
          else emit (runTrace 0 state contract [] (referenceTransactions request))

runTrace :: Int -> M.State -> M.Contract -> [Value] -> [S.TransactionInput] -> Value
runTrace _ state contract reversed [] = response "Success" (reverse reversed) state contract Null
runTrace index state contract reversed (transaction:rest) =
  case S.computeTransaction transaction state contract of
    S.Error errorValue ->
      let step = object
            [ "index" .= index
            , "status" .= String "TransactionError"
            , "error" .= transactionErrorJSON errorValue
            ]
      in response "TransactionError" (reverse (step:reversed)) state contract Null
    S.TransactionOutput output ->
      let nextState = S.txOutState output
          nextContract = S.txOutContract output
          step = object
            [ "index" .= index
            , "status" .= String "Success"
            , "warnings" .= fmap warningJSON (S.txOutWarnings output)
            , "payments" .= fmap paymentJSON (S.txOutPayments output)
            , "state" .= stateJSON nextState
            , "contract" .= contractJSON nextContract
            ]
      in runTrace (index + 1) nextState nextContract (step:reversed) rest

invalid :: String -> IO a
invalid message = do
  emit (object
    [ "status" .= String "InvalidInput"
    , "meta" .= metaJSON
    , "steps" .= ([] :: [Value])
    , "detail" .= object ["reason" .= message]
    ])
  exitFailure

emit :: Value -> IO ()
emit = BSL.putStrLn . encode
