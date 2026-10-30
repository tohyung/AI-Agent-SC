# Marlowe benchmark

The frozen 100-case dataset (`dataset/cases.jsonl`) and the offline tooling
that builds and validates it. Run from the Python project directory
(`marlowe_ai_agent/`); nothing here calls a model.

```text
python -m bench.validate_dataset
python -m pytest -q tests/bench
```

`validate_dataset` checks prompt uniqueness and banned wording, rebuilds every
reference from its template to detect drift, and requires each feasible
reference to score 100% under `evaluator.py`. The live benchmark runner for
the archived Node 1/2/3 pipeline was removed on 2026-10-30; current live
evaluation uses `research/experiments/stage2b_eval.py`.

The Core V1 simulator is an intentionally limited independent instrument,
grounded in `evalValue`, `evalObservation`, `reduceContractStep`, `applyAction`,
and `computeTransaction` in the [official semantics](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/src/Language/Marlowe/Core/V1/Semantics.hs),
and in the [specification's](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/specification/marlowe-cardano-specification.md)
`When`/`Case` continuation tree. It does not support `DivValue`, merkleized
cases, ambiguous transaction intervals or protocol-level effects. It cannot
replace the official analyzer or runtime semantics.
