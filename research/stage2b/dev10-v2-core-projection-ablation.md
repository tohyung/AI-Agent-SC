# Dev10 v2 offline core/projection ablation

Source: local, gitignored `runs/stage2b/dev10-v2-live.jsonl`.
SHA-256: `AE1A6FF9B5CD02836FF22365B12640322CE9F642A473912E197197AA9D1E69BA` (verified).
No API call, new contract generation, or public-validation input was used.

This is a **core-like extraction from historical full predictions**, not a native
`stage2b-shadow-core-v1` measurement. The utility copies only the seven
authoritative fields, changes the schema tag for validation, and ignores all
historical rich sections as authority. `conflicts` and
`assumptions_and_provenance` are not input authority.

| Case | Core valid | Core errors | New projector errors | Historical non-core messages |
| --- | --- | ---: | ---: | ---: |
| pay-d1 | yes | 0 | 0 | 4 |
| refund-d1 | no | 2 | N/A | 9 |
| choice-d1 | no | 2 | N/A | 9 |
| escrow-d1 | no | 1 | N/A | 13 |
| double-d1 | no | 2 | N/A | 8 |
| conditional-d1 | no | 1 | N/A | 3 |
| choice-d2-correction | no | 1 | N/A | 4 |
| pay-d2-clarify | no | 4 | N/A | 3 |
| escrow-d2-clarify | no | 5 | N/A | 8 |
| double-d2-conflict | no | 1 | N/A | 2 |

Totals: 10 cases; 1 core-like valid, 9 invalid; 19 core messages from the 82
historical validator messages; 63 historical non-core messages. The generic
projector produced 1 full-valid prediction (the sole core-valid case), with
zero projection errors on that case. Projection error counts are N/A for
core-invalid cases because the conservative projector emits no authoritative
rich facts from invalid core. Full-validation failures on such records are not
classified as projector bugs.

Top core patterns: seven scope-reference errors (`decision_id` does not refer
to a transition); three invalid `derived_from` provenance links; five invalid
unscored-observation shapes; two missing business questions; two conflict
consistency messages in `escrow-d2-clarify`. The remaining core messages are
included in the utility output. The historical non-core messages cluster around
claim references, transition/scope links, actor/deadline links and rich-field
backing. They are **not** proof that the new projector would err on nine
core-invalid cases. There was no projection error pattern on the one eligible
core-valid case.

Reproduce locally with `python -m research.stage2b.ablation
runs/stage2b/dev10-v2-live.jsonl`. The utility accepts arbitrary historical
JSONL and contains no candidate-specific rules. Raw JSONL remains local and
gitignored: a repo-only reviewer cannot independently reproduce these
raw-derived counts without that exact file.
