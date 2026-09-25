# Marlowe benchmark

Run from the Python project directory (`marlowe_ai_agent/`). No default test
calls a live model.

```text
python -m pytest -q
python -m bench.validate_dataset
python -m bench.run --all --fake
python -m bench.run --all --fake --fake-wrong
python -m bench.run --smoke 5 --max-usd 50
python -m bench.run --all --resume bench/results/<smoke-directory> --max-usd 50
python -m bench.report --run bench/results/<run-directory>
```

The live run needs the agent's normal `LLM_MODEL`/`LLM_BASE_URL` and API key
configuration. Only `OpenAIReasoner` loads `.env`; the benchmark never reads or
prints it. Set `BENCH_JUDGE_MODEL` to an independent model and optionally set
`BENCH_USER_MODEL`. If the provider does not return `usage.cost`, provide
`BENCH_PRICE_IN_PER_M` and `BENCH_PRICE_OUT_PER_M` for USD per million tokens.
Without cost data, smoke stops and full run is refused. The cost guard prevents
new cases from being scheduled when the projected budget is exhausted, but
already-running requests can finish and incur additional charges. The 900s
wall-clock limit is cooperative and cannot interrupt an in-flight SDK request.

The Core V1 simulator is an intentionally limited independent instrument,
grounded in `evalValue`, `evalObservation`, `reduceContractStep`, `applyAction`,
and `computeTransaction` in the [official semantics](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/src/Language/Marlowe/Core/V1/Semantics.hs),
and in the [specification's](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/specification/marlowe-cardano-specification.md)
`When`/`Case` continuation tree. It does not support `DivValue`, merkleized
cases, ambiguous transaction intervals or protocol-level effects. It cannot
replace the official analyzer or runtime semantics.
