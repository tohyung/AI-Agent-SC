#!/usr/bin/env bash
# E6 pipeline arm, one call: bash tools/e6/pipe.sh N [roleplay_case args...] (from Git Bash).
N=$1; shift
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/d/code/marlowe_ai_agent/tools/e6/run_wsl.sh \
  research.experiments.roleplay_case --case-index "$N" --dataset v3 --formalization AFF \
  --provider gemini "$@" 2>&1 | grep -E "^case |Traceback|Error" ; \
  cd /d/code/marlowe_ai_agent && PYTHONIOENCODING=utf-8 python tools/e6/show.py pipe "$N"
