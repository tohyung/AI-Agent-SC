# SMT benchmark suites

`generate_contracts.py` and `stress-summary.csv` are the original Stage 0.7
control: every generated contract ends in `Assert False`, so the table measures
the `Counterexample`/SAT side only. It must not be used to size the Valid/UNSAT
timeout.

`generate_valid_contracts.py` provides deterministic F1–F5 Valid families and
the structurally matched C1 Counterexample control. `run_valid_bench.py` and
`stress-valid-summary.csv` measure the Valid side. Representative canonical
contracts are retained under `valid-corpus/`; the full generated grid remains
ignored under `results/`.

The committed Valid summary completes all 360 requested configurations through
n=64 and contains a partial n=128 extension through the first all-Timeout F3
point. `run_parallel_valid_bench.py` reproduces the N=1/2/4 process-group RSS
measurement in `parallel-valid-summary.csv`. Run `select_valid_corpus.py` to
recreate the bounded corpus and manifest from the generator and summary.
