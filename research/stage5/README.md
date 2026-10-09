# Stage 5 property dataset

The supported CLI records Stage 4 oracle observations in a local SQLite store
(`runs/property-dataset.sqlite3` by default). This is evidence collection, not
automatic training or universal property verification. `PropertyRegistry` still
tracks violated-property candidates and optional checker outcomes separately.
The dataset also keeps satisfied and inconclusive oracle observations so an
eventual validator is not trained only on failures.

## Trust boundaries

1. `OBSERVED`: immutable, content-addressed contract, reference trace, oracle
   finding, source artifact IDs, comparison identity, and declared coverage.
   This is an observation, not a ground-truth label. Simulated runs remain
   `simulation_only` even if every pipeline stage succeeds.
2. `CHECKER_OUTCOME`: a scoped property-checker result with evidence IDs. It is
   recorded as evidence, not silently promoted into a training label.
3. `REPLAY_CHECK=MATCH`: a pinned Marlowe reference replay matches the stored
   trace's status, final state/contract, warnings, payments, oracle verdict,
   and reference identity. Other oracle types remain ineligible until their
   replay rule is implemented.
4. `REVIEW`: two distinct reviewers must agree on the replayed oracle verdict,
   provide a rationale, and consent to use their review for training. A
   conflicting latest review, `INCONCLUSIVE`, or a shared human disagreement
   with the oracle blocks export pending a separate oracle/corpus investigation.
5. `DATA_USE_AUTHORIZATION`: the source reviewer named in the expectation must
   explicitly grant validator-training use. A later revocation blocks export.
   This identity is self-asserted, not authenticated. It is not proof of legal
   ownership or a substitute for organizational data-governance review.

Only non-simulated observations meeting all gates can enter the explicit
export. Neither a checker result nor an LLM output bypasses review. A
`SATISFIED` label means one observed trace satisfied one oracle, not that every
possible Marlowe execution is safe.

## Commands

Run from the repository root. These commands make no LLM/API calls:

```bash
python -m research.stage5.dataset audit
python -m research.stage5.dataset ingest-run runs/<run-file>.jsonl
python -m research.stage5.dataset replay <example_id> --binary <pinned-reference-binary>
python -m research.stage5.dataset review <example_id> --reviewer <id> --label SATISFIED --rationale "checked the trace" --consent-for-training
python -m research.stage5.dataset authorize-use <example_id> --grantor <source-reviewer-id> --rationale "validator training approved"
python -m research.stage5.dataset export runs/property-reviewed.jsonl
```

Use `authorize-use ... --revoke` to withdraw use. `export` writes a JSONL file
and a `.manifest.json` with its SHA-256 and the source event-chain head. Keep a
copy of the manifest outside the database/repository as an external anchor;
`audit --anchor <manifest>` detects later changes relative to that copy. The
internal hash chain detects accidental or partial tampering, but an attacker
who controls the whole database can rewrite it and its hashes. There is no
cryptographic reviewer signature or authenticated identity in v1.

The export has **no train/validation/test split**. Each row carries requirement
and contract leakage-group IDs. Freeze a split with connected groups (same
requirement or contract in one split) and a separate manifest before measuring
model quality. Do not mix these adaptive development observations into the
frozen Stage 2A corpus or claim an unbiased benchmark from them.

The store and normal run logs may contain names, amounts, and contract details.
They live under gitignored `runs/` by default; do not publish the database or
JSONL without reviewing privacy and data-use rights. `--no-property-dataset`
disables automatic recording, and `--property-dataset PATH` selects another
local path. Database schema changes require an explicit migration/version bump;
unknown versions fail closed.
