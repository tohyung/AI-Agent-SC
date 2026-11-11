#!/usr/bin/env bash
# One step of the E6 loop for case N: show the case, drive the pipeline arm, then the baseline arm
# if the pipeline arm has ended. bash tools/e6/next.sh N
cd /d/code/marlowe_ai_agent
export PYTHONIOENCODING=utf-8
N=$1
python tools/e6/show.py case "$N"
python tools/e6/auto.py pipe "$N"; rc=$?
if [ $rc -eq 2 ]; then python tools/e6/show.py pipe "$N" | grep -E "_ms|amount|draft|note|CANDIDATE|party|recipient|owner"; fi
if [ $rc -eq 0 ]; then python tools/e6/auto.py base "$N"; fi
