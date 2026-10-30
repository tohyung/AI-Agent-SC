# Benchmark dataset v2

This file contains 100 deterministic, template-generated prompts and Core V1
reference contracts. The distributions are checked by
`python -m bench.validate_dataset`; the expected scenario outcomes are written
separately in `bench/templates.py` and checked by the independent simulator.

SHA-256 of `cases.jsonl`:

`e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`

The prompt generator uses fixed seed 1234. Dataset v1 had SHA-256
`bddc66e4223abbdc9278edd8972651448b9752ac4e898533bde2de69bc45226d`
and was used for an interrupted live smoke: two of five cases produced records,
both timed out. After that smoke, review found prompt style and relative-time
label defects. Version 2 changes all 100 prompts, keeps the template reference
contracts and outcome rules, and has not been used for a live result. The v1
smoke output remains in the ignored results directory, identified by its hash;
it must not be merged with v2 runs. Do not regenerate v2 after observing live
v2 results without another version increment and a full disclosure.

Known design limitation: difficulty labels are stratification metadata, not an
independent psychometric calibration. Some L1-labelled contract families still
have more than one stage because the fixed family distribution and the strict
L1 definition cannot both be satisfied. Prompt phrasing is template-derived,
so it should not be treated as a representative sample of real users.
