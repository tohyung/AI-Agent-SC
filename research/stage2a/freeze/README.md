# Stage 2A v1 semantic freeze

`stage2a-v1` is a reproducible snapshot of the public research corpus,
validator/schema, and evaluation protocol from source commit
`a6ea94587783d45ffc68406dd856a636a59874ed`. It is a semantic freeze,
not human-reviewed ground truth or a production-readiness claim. Freeze
acceptance and Stage 2A closure remain pending separate review.

The manifest freezes exact Git blob content at the source commit for exactly
four artifacts:

- `research/stage2a/corpus/development.jsonl`
- `research/stage2a/corpus/validation.jsonl`
- `research/stage2a/foundation.py`
- `research/stage2a/protocol.md`

From the repository root, verify with:

```bash
python research/stage2a/verify_freeze.py research/stage2a/freeze/stage2a-v1.manifest.json
```

The aggregate SHA-256 hashes the UTF-8 concatenation of one
`<path>\t<sha256>\n` line per artifact, sorted lexicographically by path.
Each artifact SHA-256 and byte count come from `git show <source_commit>:<path>`
as bytes, not from a checkout that may use CRLF. The verifier also requires
the current tracked semantic core to be clean against the source commit.
`review_queue.md` is a generated projection and is not part of
the semantic aggregate. The manifest records the pinned Marlowe reference
commit and reference driver version.

The public validation split is not hidden evaluation. Clarification-required
facts remain unresolved and annotation metadata remains draft/candidate.
Any future semantic-core change requires a new version (for example,
`stage2a-v2`); the meaning and manifest of `stage2a-v1` must remain unchanged.
