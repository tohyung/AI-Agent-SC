{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Control.Exception (SomeException, displayException, try)
import Data.Aeson
import Data.Aeson.Types (parseEither)
import qualified Data.ByteString.Lazy.Char8 as BSL
import qualified Data.Text as Text
import MarloweSMT.Analysis (analyzeWithTimeout)
import MarloweSMT.Bridge
import MarloweSMT.Output
import System.Environment (getArgs)
import System.Exit (exitFailure)
import System.IO (hPutStrLn, stderr)
import System.Process (readProcess)
import Text.Read (readMaybe)

upstreamCommit :: String
upstreamCommit = "7b5b1e900ec53a8eb18747992bec73470704dfcb"

driverVersion :: String
driverVersion = "0.2.0"

main :: IO ()
main = do
  meta <- loadMeta
  outcome <- try (run meta) :: IO (Either SomeException ())
  case outcome of
    Right () -> pure ()
    Left exception -> do
      let message = "internal analysis failure: " <> displayException exception
      emit (renderInternalFailure meta message)
      hPutStrLn stderr message
      exitFailure

run :: Meta -> IO ()
run meta = do
  timeoutMs <- getArgs >>= either (invalid meta) pure . parseArgs
  input <- BSL.getContents
  json <- either (invalid meta . ("invalid JSON: " <>)) pure (eitherDecode input :: Either String Value)
  Request contract initialState <- either (invalid meta . ("invalid Core V1 input: " <>)) pure (parseEither parseRequest json)
  let merkleized = countMerkleizedCases contract
      notes = if merkleized == 0 then [] else
        [ show merkleized <> " MerkleizedCase continuation(s) are hashes and were not analyzed" ]
  result <- analyzeWithTimeout timeoutMs contract initialState
  let normalized = case result of
        Left theorem -> Left (ThmResultLike (show theorem))
        Right value -> Right value
  emit (renderAnalysis meta notes normalized)

parseArgs :: [String] -> Either String (Maybe Integer)
parseArgs [] = Right Nothing
parseArgs ["--solver-timeout-ms", raw] = case readMaybe raw of
  Just value | value > 0 -> Right (Just value)
  _ -> Left "--solver-timeout-ms requires a positive integer"
parseArgs _ = Left "usage: marlowe-smt [--solver-timeout-ms N]"

invalid :: Meta -> String -> IO a
invalid meta message = do
  emit (renderInvalidInput meta message)
  hPutStrLn stderr message
  exitFailure

emit :: Value -> IO ()
emit = BSL.putStrLn . encode

loadMeta :: IO Meta
loadMeta = do
  version <- try (readProcess "z3" ["--version"] "") :: IO (Either SomeException String)
  let solver = either (const "z3 unavailable") (Text.unpack . Text.strip . Text.pack) version
  pure Meta
    { metaSolver = solver
    , metaUpstreamCommit = upstreamCommit
    , metaDriverVersion = driverVersion
    }
