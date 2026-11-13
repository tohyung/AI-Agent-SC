#!/usr/bin/env bash
# E7 machine scoring for both arms at the four time tolerances, then the blind packets.
# Run from Windows Git Bash at the repo root, after all 100 cases have run on both arms.
#   bash tools/e7/score_all.sh
set -euo pipefail
OUT=runs/E7-Eval-Score
mkdir -p "$OUT/machine"
for arm in pipeline baseline; do
  for tol in 1m:1 1h:60 1d:1440 3d:4320; do
    name=${tol%%:*}; minutes=${tol##*:}
    wsl -d Ubuntu -- bash tools/e6/score_wsl.sh research.experiments.e7_score --dataset v5 \
      --arm "$arm" --cases 1-100 --pipeline-dir runs/E7-Eval-Pipeline \
      --baseline-dir runs/E7-Eval-Baseline --time-tolerance-minutes "$minutes" \
      --out "$OUT/machine/$arm-$name.json" > "$OUT/machine/$arm-$name.log"
    echo "$arm $name done"
  done
done
python -m research.experiments.e7_analysis packets --machine "$OUT/machine" --out "$OUT/blind"
