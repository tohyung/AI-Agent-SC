# Dataset

`cases.jsonl` is the frozen benchmark: 100 template-generated prompts with
Core V1 reference contracts and scenario checks (dataset v2, seed 1234).

SHA-256 of `cases.jsonl`:
`e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`

Distribution: 60 Vietnamese / 40 English; difficulty L1 25, L2 30, L3 30,
L4 15; `info_mode` complete 55, missing 30, ambiguous 10, infeasible 5.

Evaluation discipline: cases 1-56 are the development set; case 57 is
excluded (its evaluator fields were read on 2026-10-27); cases 58-100 are the
closed test set. For a case that has not been run, read only `prompt`.

```text
python -m dataset.validate_dataset
python -m pytest -q tests/dataset
```

`validate_dataset` checks prompt uniqueness and banned wording, rebuilds every
reference from `templates.py` to detect drift, and requires each feasible
reference to score 100% under `evaluator.py`. Nothing here calls a model.

Do not regenerate v2 after observing live results without a version increment
and full disclosure. Dataset v1 (`bddc66e4223abbdc9278edd8972651448b9752ac4e898533bde2de69bc45226d`)
was used only for an interrupted smoke run and must not be mixed with v2.

Limits: difficulty labels are stratification metadata, not calibrated
difficulty; prompt phrasing is template-derived and not a sample of real
users. Reference deadlines use an unstated 12:00 UTC time, and GOLD uses the
placeholder currency symbol `"benchmark"`.

`marlowe_sim.py` is an intentionally limited independent Core V1 simulator,
grounded in `evalValue`, `evalObservation`, `reduceContractStep`,
`applyAction` and `computeTransaction` of the
[official semantics](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/src/Language/Marlowe/Core/V1/Semantics.hs).
It does not support `DivValue`, merkleized cases, ambiguous transaction
intervals or protocol-level effects, and cannot replace the official analyzer.
