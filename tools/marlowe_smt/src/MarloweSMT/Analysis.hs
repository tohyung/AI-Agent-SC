module MarloweSMT.Analysis (analyzeWithTimeout) where

import Data.SBV
import qualified Language.Marlowe.Analysis.FSSemanticsFastVerbose as FS
import Language.Marlowe.Semantics (TransactionInput, TransactionWarning)
import Language.Marlowe.Semantics.Types

analyzeWithTimeout
  :: Maybe Integer
  -> Contract
  -> Maybe State
  -> IO (Either ThmResult (Maybe (POSIXTime, [TransactionInput], [TransactionWarning])))
analyzeWithTimeout timeoutMs contract initialState = do
  theorem@(ThmResult result) <- proveWith solverConfig property
  pure $ case result of
    Unsatisfiable _ _ -> Right Nothing
    Satisfiable _ model -> Right (Just (FS.extractCounterExample model contract initialState labels))
    _ -> Left theorem
  where
    labels = FS.generateLabels (1 + FS.countWhens contract)
    property = do
      parameters <- FS.generateParameters labels
      valid <- FS.wrapper contract parameters initialState
      pure (sNot valid)
    solverConfig = case timeoutMs of
      Nothing -> z3
      Just milliseconds -> z3 { extraArgs = extraArgs z3 <> ["-t:" <> show milliseconds] }
