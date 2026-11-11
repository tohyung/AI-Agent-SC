#!/usr/bin/env bash
# E6 baseline arm, one call: bash tools/e6/base.sh N [baseline_llm args...] (from Git Bash).
N=$1; shift
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/code/marlowe_ai_agent/tools/e6/run_wsl.sh \
  research.experiments.baseline_llm --case-index "$N" "$@" 2>&1 | grep -E "Traceback|Error" ; \
  cd /d/code/marlowe_ai_agent && PYTHONIOENCODING=utf-8 python tools/e6/show.py base "$N"
