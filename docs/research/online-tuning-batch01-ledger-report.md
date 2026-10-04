# Online tuning Batch 01: budget-limited execution report

The sections through **Continuation: explicit control flow** below preserve an
earlier 15/48-call snapshot. They are historical, not the final state. The
authoritative 48/48-call outcome is recorded in **Final continuation** at the
end. Earlier failed attempts and their evidence have not been removed.

## Historical scope and status (15/48 snapshot)

- Baseline and starting HEAD: `99484ad5a69dc560b6f3e65a2eb4289c064a5688`; starting worktree clean.
- Frozen dataset SHA-256: `e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`.
- Selection: first 20 physical records, in the order fixed by `online-tuning-batch01.manifest.json`.
- Model: `nvidia/nemotron-3-ultra-550b-a55b:free`; 48 global outbound-attempt ceiling.
- Actual attempts: 15, journaled in ignored `runs/online-tuning-batch01/physical-attempts.jsonl` before each network attempt. SDK automatic retries disabled. Counts include repairs/retries.
- **Incomplete batch:** 3/20 cases attempted; 17/20 not attempted. Neither specified completion condition (20 terminal cases or exhausted 48-call budget) was reached. Case 01 remains unresolved at simulated Stage 2C, and later stages still need independent comparison/exploration wiring. This is not a benchmark result.
- Reached ledger: 0; ledger pass/fail/inconclusive/unavailable: 0/0/0/0. The analyzer was independently probed but no case reached the ledger stage. No testnet or deployment was run.
- Holdout: cases 21-100 were neither parsed for design nor run. No `reference_contract` or `checks` were sent to the model or used for a fix. `reference_assisted_diagnosis=false` throughout.

**Taxonomy note:** `NOT_ATTEMPTED` below is deliberately outside the five ledger outcome categories. It must not be counted as `NOT_REACHED_LEDGER` or as an infrastructure verdict for a contract that was never run.

## Case 01: `vi-third_party-L1-001`

- Index/type/difficulty/language/info mode: 1 / third_party / L1 / vi / complete.
- Original prompt: “An ở Huế đây; em là sinh viên và đang Bình gửi 20 ADA trước ngày 03/01/2027 để mua hàng từ Giang. Lan báo giá từ 0 đến 100 trước ngày 10/01/2027; nếu đạt ít nhất 50 thì Giang nhận tiền, thấp hơn thì hoàn cho Bình. Hôm qua trời mưa nên mình chưa kịp nói chuyện trực tiếp. Mình hơi lo chuyện phải đòi lại tiền nếu mọi việc không thành.”
- Physical calls: 7 across three append-only attempts (3 original, then 2 + 2 under the evolving v2 core); cumulative batch count after this case's latest attempt: 15. All earlier ignored artifacts are retained. The second attempt's historical JSON reports `physical_calls=5` because the runner then summed all calls for the case; the journal shows that attempt itself used 2 calls. The runner now records per-attempt and per-case totals separately.
- Progress/failure history: initial extraction `CORE_INVALID` (cross-kind `derived_from`, nonliteral source span), then Stage 2C crashed on `claims=null`; after a general fail-closed review fix, Stage 2C returned `BLOCKED`. After bounded extraction repair, the original core became structurally valid but Stage 2C was `WAITING_USER`. A versioned v2 core then captured inclusive Choice bounds and threshold guards, and a subsequent append-only attempt captured explicit deposit-to-Choice and branch-to-outcome links. The latest core has zero structural validation errors, but remains `WAITING_USER` with `clarification_required`.
- Root cause: model output/provenance errors plus a real Stage 2C malformed-collection bug. The earlier v1 core lost numeric Choice semantics and outcome links; the latest v2 core preserves them structurally, but has no accepted account-owner/timeout interpretation. Structural validity still does not prove business semantics.
- Clarification transcript: none. There are no hidden or missing facts for this case. The latest model questions ask about account ownership and whether Lan's report is a Choice. No synthetic answer has yet been submitted, and no synthetic answer is represented as authenticated acceptance.
- General fixes: null-safe Stage 2C review and one bounded diagnostic-feedback extraction. Both apply beyond this case. Generalization scope: all malformed core candidates / all validation-invalid core outputs; reusable for future prompts: yes; repo-growth risk: LOW; architecture impact: fail-closed review and opt-in repair, with no validator bypass; why not case-specific: no case ID, person, amount, or deadline branch. Tests: `test_malformed_candidate_collections_block_review_without_crashing`, `test_bounded_validation_feedback_preserves_validator_authority`.
- Final: `NOT_REACHED_LEDGER`; last successful stage `intent_extraction`; blocking stage `intent_acceptance`. The v2 schema and a reusable funded-choice compiler now exist, but the latest Batch 01 candidate is not accepted and lacks the explicit timeout path required by that profile. Neither the compiler fixture nor the ledger control is a verdict for this case.
- Property readiness: `NOT_READY`. Reference comparison/exploration/oracle/property evidence absent. Reference-assisted diagnosis: false. Earlier candidate does not validate the newer prompt/repair behavior.

## Case 02: `vi-rental_deposit-L4-001`

- Index/type/difficulty/language/info mode: 2 / rental_deposit / L4 / vi / missing.
- Original prompt: “Bình ở Huế đây; tiệm nhỏ của mình đang Chi thuê phòng của Hà và đặt cọc 23 ADA trước một ngày mình sẽ nói sau. Đến bảy ngày sau hạn đầu nếu không hư hại thì hoàn đủ; nếu có hư hại, Hà giữ 3 ADA và trả phần còn lại cho Chi.”
- Physical calls: 6 across two sequential extraction attempts; cumulative batch count 9. Initial evidence was retained before rerun.
- Progress/failure history: first candidate `CORE_INVALID` because the retained 3 ADA and refunded remainder shared one damage scope, falsely creating an amount conflict; Stage 2C `BLOCKED`. A general prompt-contract rule for distinct monetary obligations/terminal outcomes was added and the old candidate invalidated. The next candidate passed structural validation; Stage 2C is `WAITING_USER`.
- Root cause: missing outcome granularity in model scoping, then unresolved deposit date and damage-decision semantics. The later candidate still made some account-owner inferences not established by the original sentence; structural PASS must not be treated as semantic acceptance.
- Clarification transcript: no answers were submitted to the pipeline. The allowed hidden fact has exact canned answer “Hạn đầu là ngày 04/01/2027.” The questions about who determines damage have no provided fact; any answer would be synthetic and is not recorded as a human review.
- General fix: branch-local split obligations receive distinct terminal-outcome scopes; not a case-ID rule. Generalization scope: escrow, rental deposit, milestone, fee/remainder and other split-payment branches; reusable: yes; repo-growth risk: LOW; architecture impact: extraction guidance only, not a weakened conflict validator; why not case-specific: expressed in obligation/scope terms. Test: `test_fake_extractor_separates_prompt_transport_parse_and_validation` checks the guidance. Stage 2C also now renders structured clarification `question` text rather than a Python dict; test: `test_structured_clarification_renders_question_not_python_dict`.
- Final: `NOT_REACHED_LEDGER`; last successful stage `intent_extraction`; blocking stage `intent_acceptance` with unresolved semantics and no authenticated acceptance. Damage branching and split-payment lowering are not supported by the existing direct-payment-only compiler. No ledger failure was observed.
- Property readiness: `NOT_READY`; no deterministic compile/reference/exploration/oracle evidence. Reference-assisted diagnosis: false. Earlier candidate does not validate the newer prompt contract.

## Case 03: `vi-escrow_3party-L3-001`

- Index/type/difficulty/language/info mode: 3 / escrow_3party / L3 / vi / complete.
- Original prompt: “Chi ở Huế đây; mình làm tự do, đang bán món đồ cho Dũng giá 26 ADA. Người này gửi tiền trước ngày 05/01/2027; đến bảy ngày sau hạn đầu nếu có bất đồng thì Nga quyết định chuyển cho Huy hay hoàn lại Dũng. Nếu không quyết định thì hoàn lại.”
- Physical calls: 2; cumulative batch count 11. Both attempts were journaled before network.
- Progress/failure history: `intent_extraction` returned safe `MODEL_ERROR` (`provider_error`, `LLMTransientError`); `intent_acceptance` was `NOT_EVALUATED`. No core candidate exists. The provider path took an abnormally long time and did not yield a usable response.
- Clarification transcript/synthetic assumptions: none; no Stage 2C question was reached.
- Source fix: none for the provider failure; retries are already bounded and globally counted. Repeated calls would consume the finite free quota without evidence of a local repair. Generalization assessment: no case-specific fix added. Tests: transport/budget tests in `research/experiments/test_online_tuning_batch01.py`.
- Final: `NOT_REACHED_LEDGER`; no successful pipeline stage; blocker `intent_extraction`, external model transport. This is not a contract-level ledger result.
- Property readiness: `NOT_READY`; no downstream evidence. Reference-assisted diagnosis: false.

## Cases 04-20: status at 15/48 snapshot

Every item below has physical model calls 0, no clarification transcript or synthetic assumption, no stage progression, no source fix, no regression replay, no reference-assisted diagnosis, no ledger outcome, and `property_readiness=NOT_READY`. Each is `NOT_ATTEMPTED`, **not** `NOT_REACHED_LEDGER`. The original prompts are preserved exactly for audit; no `reference_contract` or `checks` were read to prepare them.

### 04 `vi-swap-L2-001` (swap, L2, vi)
“Dũng ở Huế đây; mình là chủ nhà, đang muốn đổi 29 ADA của Giang lấy 13 điểm thưởng GOLD của Lan. Giang đưa phần mình trước ngày 06/01/2027, Lan đưa điểm trước ngày 13/01/2027; đủ cả hai mới đổi, thiếu thì mỗi người nhận lại phần của mình.”

### 05 `vi-milestone-L2-001` (milestone, L2, vi)
“Giang ở Huế đây; bác muốn nhờ chút, đang thuê Minh làm hai chặng với tổng một khoản tiền, Hà đưa tiền trước ngày 07/01/2027. Nếu Hà nghiệm thu chặng đầu trước bảy ngày sau hạn đầu thì người làm nhận một nửa; nghiệm thu phần còn lại trước mười bốn ngày sau hạn đầu thì nhận hết. Phần chưa nghiệm thu phải quay về Hà.”

### 06 `vi-vesting-L3-001` (vesting, L3, vi)
“Hà ở Huế đây; tôi làm văn phòng, đang Huy dành 35 ADA cho Nga, gửi trước ngày 08/01/2027. Một nửa chuyển cho người làm vào bảy ngày sau hạn đầu, nửa còn lại vào mười bốn ngày sau hạn đầu.”

### 07 `en-swap-L1-002` (swap, L1, en)
“Grace from Hue here; I'm new in town and am trading 38 ADA from Helen for 16 GOLD reward points from Kate. The first person sends their side by 09/01/2027, the second by 16/01/2027; exchange only when both arrive, otherwise return what was sent.”

### 08 `vi-infeasible-L2-001` (infeasible, L2, vi)
“Lan ở Huế đây; muốn xóa giao dịch đã chốt một cách đơn phương mà không có người tham gia.”

### 09 `vi-escrow_2party-L3-001` (escrow_2party, L3, vi)
“Minh ở Huế đây; em là sinh viên và đang bán chiếc máy ảnh cho Nga với giá một khoản tiền. Nga chuyển tiền trước ngày 11/01/2027; nếu họ xác nhận ưng ý trước bảy ngày sau hạn đầu thì Sơn nhận tiền, không thì trả lại Nga.”

### 10 `en-third_party-L1-002` (third_party, L1, en)
“Jack from Hue here; my small shop is buying from Noah with 47 ADA supplied by Kate by a date I'll confirm later. Rita reports a price from 0 to 100 by 19/01/2027; Noah receives the money if it is at least 50, otherwise Kate gets it back.”

### 11 `en-rental_deposit-L3-002` (rental_deposit, L3, en)
“Kate from Hue here; I'm a freelancer and am renting a room from Olivia to Liam with a an agreed amount security amount by 13/01/2027. By seven days after the first deadline no damage means full refund; damage lets Olivia keep 5 ADA and returns the rest.”

### 12 `en-escrow_2party-L4-002` (escrow_2party, L4, en)
“Liam from Hue here; as a homeowner I'm selling my camera to Maya for 53 ADA. Maya sends the money by a date I'll confirm later; if they approve the camera by seven days after the first deadline, Paul receives it; otherwise Maya gets it back. I'm worried about getting the money back if it does not work out.”

### 13 `vi-rental_deposit-L3-003` (rental_deposit, L3, vi)
“Sơn ở Huế đây; bác muốn nhờ chút, đang Thảo thuê phòng của Uyên và đặt cọc 56 ADA trước ngày 15/01/2027. Đến ngày 22/01/2027 nếu không hư hại thì hoàn đủ; nếu có hư hại, Uyên giữ 7 ADA và trả phần còn lại cho Thảo.”

### 14 `en-escrow_3party-L1-002` (escrow_3party, L1, en)
“Noah from Hue here; at my office I'm selling an item to Olivia for 59 ADA. They send the money by 16/01/2027; by seven days after the first deadline Alex decides whether Sam receives it or Olivia gets a refund. No decision means a refund.”

### 15 `en-vesting-L2-002` (vesting, L2, en)
“Olivia from Hue here; I'm new in town and am setting aside 62 ADA from Paul for Tina by 17/01/2027. Half reaches the worker on seven days after the first deadline, and the other half on fourteen days after the first deadline. We have only talked by phone so far.”

### 16 `en-swap-L1-003` (swap, L1, en)
“Paul from Hue here; my online business is trading 65 ADA from Rita for 16 GOLD reward points from Will. The first person sends their side by 18/01/2027, the second by 25/01/2027; exchange only when both arrive, otherwise return what was sent.”

### 17 `en-milestone-L4-002` (milestone, L4, en)
“Rita from Hue here; I'm a student and am hiring Alex for two pieces of work worth 68 ADA total. Sam puts the money in by 19/01/2027; they approve part one by seven days after the first deadline and the remainder by fourteen days after the first deadline. Each approval releases half; anything unapproved goes back.”

### 18 `vi-third_party-L2-003` (third_party, L2, vi)
“Vân ở Huế đây; tiệm nhỏ của mình đang Yến gửi 71 ADA trước ngày 20/01/2027 để mua hàng từ Bình. Giang báo giá từ 0 đến 100 trước bảy ngày sau hạn đầu; nếu đạt ít nhất 50 thì Bình nhận tiền, thấp hơn thì hoàn cho Yến.”

### 19 `en-swap-L1-004` (swap, L1, en)
“Tina from Hue here; I'm a freelancer and am trading 74 ADA from Will for 10 GOLD reward points from Clara. The first person sends their side by 03/01/2027, the second by 10/01/2027; exchange only when both arrive, otherwise return what was sent.”

### 20 `vi-crowdfunding-L3-001` (crowdfunding, L3, vi)
“Đạt ở Huế đây; mình là chủ nhà, đang An và Dũng cùng góp 77 ADA cho Huy, mỗi người một nửa. Người đầu góp trước ngày 04/01/2027, người sau trước bảy ngày sau hạn đầu; đủ mức thì dự án nhận, không đủ thì hoàn lại người đã góp.”

## Cross-case accounting and limitations

- Attempted: 3. First failure classes observed: Stage 2B core/provenance errors (cases 01-02), Stage 2C malformed review (01), Stage 2C unresolved acceptance (01-02), external model/transport (03). No reference, exploration, oracle, property, or ledger case verdict exists.
- General capabilities added: durable pre-request call ledger and extraction checkpoint; fail-closed malformed-candidate review; bounded validation feedback; distinct obligation scoping guidance; readable structured clarification text; configurable `marlowe-cli` transaction-size adapter. Generalization audit: six `GENERAL`/`FAMILY_GENERAL`, zero `CASE_SPECIFIC`. All fixes are independent of exact case IDs/names/amounts/deadlines. The adapter is configured, not enabled in the default production pipeline.
- Ledger infrastructure probe (historical): `marlowe-cli 0.2.0.0` against the old stale socket returned `Network.Socket.connect ... Connection refused`. The former node 11.1.2 also caused a protocol-parameter decoder mismatch. These were infrastructure observations, **not** ledger verdicts for Batch 01 contracts. The local replacement and live control are recorded in the correction below.
- General architecture impact: stronger accounting and fail-closed review, plus an opt-in v2 numeric-Choice core and one family-level compiler profile. Damage branching, split payments, and several other Batch 01 families remain outside compiler coverage. No authority boundary was promoted, and simulated customer text was never treated as authenticated human acceptance. Repo growth remains bounded by shared primitives/profile logic rather than one compiler per case. The partial run cannot establish model accuracy or production fitness.
- Technical debt: the ledger adapter has live compatible controls and an independent compiler-generated fixture, but no Batch 01 contract has crossed the acceptance and independent expectation gates. Stage 2B still permits structurally valid but semantically incomplete claims. The batch runner does not yet wire the simulated-customer port, funded-choice profile, pinned reference comparison, exploration, and ledger config into one sequential case loop. Free provider latency and availability are not controlled by local code.
- Physical-call budget impact: 15/48 consumed, 33 left. No model was used as a customer surrogate. No API credential, raw provider response, or full external log is committed. The ignored `runs/` evidence and journal remain local; this report alone is not sufficient for an independent replay of raw model output.
- Production impact: no production authority change, no pipeline testnet/deployment-stage evidence, no unbiased quality estimate. Batch 01 is an adaptive development/tuning set. Its success rate is not an unbiased accuracy estimate. Cases 21–100 remain untouched by live execution and are reserved for subsequent generalization evaluation unless explicitly authorized otherwise.

## Correction: local ledger-size infrastructure

The Stage 0.5 node/CLI incompatibility was resolved by installing the official
`cardano-node 8.9.0` Linux release outside the repository and using it to
generate a Babbage private network (magic `42090`). The `cardano-testnet 8.8.0`
launcher generated valid network files and live nodes but failed its own
post-start stake-pool property. Its generated configuration and keys were
preserved outside Git, and the three nodes were started directly as WSL system
services (`marlowe-ledger-42090-pool1`, `pool2`, `pool3`, running as user `tohung`).
Transient user services were tried first but stopped with the WSL login session.
WSL itself stopped when no Windows process held the distro open; a hidden
`wsl.exe -e sleep infinity` keeper now holds the local instance while the
system services run. The earlier `42089` restored network could answer
protocol queries but had an old genesis and did not advance blocks. The
replacement `42090` network was started promptly from fresh genesis; its
`query tip` advanced from block 1 to block 3 in 20 seconds with
`syncProgress=100%`. These transient services and the keeper are **not**
configured to auto-start after reboot. This bypasses only the launcher
self-test, not a pipeline or ledger validation gate.

The stable socket is
`/home/tohung/stage05-infra/ledger-testnet-8.9/network-42090/socket/pool1/sock`.
`cardano-cli query tip --testnet-magic 42090` returned Babbage on the local
network. The pinned `marlowe-cli 0.2.0.0` binary (SHA-256
`464f14957aafeefc86aa868074e200f700aefc070f1ecb32466d999110e58939`,
release source commit `2c0ad60ad2caabb7865b6dda56f7ec478f8637e7`)
initialized a Babbage envelope from a clean four-field Marlowe state. Its
control role-policy ID is a fixed, synthetic 28-byte value used only for
offline size analysis; no role token is minted or transaction submitted. Its
`run analyze --transaction-size --best` control returned `Actual=12154`,
`Maximum=16384`, `Invalid=false`. The adapter now pins the
initialized-template SHA-256 and replaces template state with an explicit
empty initial state before analysis; it cannot silently reuse a nonempty
sample account balance. The active Babbage template has SHA-256
`298ca1d3cdec167d88d33a8a77147df74b7ae3b2c077a08d2dbedb19a0a79269`;
the opt-in real-node adapter integration test passed against this template and
the `42090` socket (`1 passed`).

This control proves the configured ledger-size analysis path works locally.
It is **not** a Batch 01 candidate verdict, a full ledger validation, or
transaction submission. Cases 01-03 remain `NOT_REACHED_LEDGER`; cases 04-20
remain `NOT_ATTEMPTED`. The new code is harness-only and does not change
candidate content or compiler semantics.

## Continuation: explicit control flow, simulation boundary, and ledger health

- The v2 shadow core now records numeric Choice bounds and branch guards with
  exact source evidence, `continuation_scope_id` for causal succession, and
  `parent_scope_id` for terminal outcomes. The validator checks typed references;
  it does **not** infer business correctness from structural validity. The v1
  schema and existing frozen corpus are unchanged. This is a shared semantic
  primitive for any bounded Choice, not a case-ID rule. Generalization scope:
  numeric-choice and dependent-outcome contracts. Reusable: yes. Repo-growth
  risk: LOW. Architecture impact: versioned core/projector contract. Regression:
  `test_choice_guard_v2.py`.
- `SimulatedIntentAcceptancePort` is an opt-in Batch-only boundary. It requires a
  structurally valid, resolved candidate and checks simulated answers against
  requirement history. It emits `NO_AUTHORITY`, never `USER_ACCEPTED_INTENT`.
  `CompilerPort` rejects simulated intent unless explicitly opted in, and
  `CompilerAuthorityPort` cannot promote a contract derived from it. No
  simulated answer has yet been injected into Batch 01. Generalization scope:
  all research/tuning customer simulations. Reusable: yes. Repo-growth risk:
  LOW. Architecture impact: explicit authority separation. Regression:
  `test_simulated_acceptance.py`, `test_authority_identity.py`.
- The family-level `funded-choice-v1` compiler accepts only an explicit graph
  with one funded ADA deposit, one bounded Choice, two disjoint/exhaustive
  guarded branches, and an explicit Choice-timeout refund. It rejects missing
  account ownership, a gap/overlap in integer guards, absent timeout behavior,
  or extra claims. It emits Marlowe Core V1 with mapping evidence; no
  benchmark candidate was modified to match it. Generalization scope:
  deposit/choice/pay-or-refund contracts. Reusable: yes. Repo-growth risk:
  MEDIUM, one profile for a contract family. Architecture impact: deterministic
  lowering only, no profile authority. Regression: `test_funded_choice_v1.py`.
- The local `42090` and `42093` private chains retained sockets but eventually
  stopped advancing after a long idle period. Their tips showed low
  `syncProgress`, and node logs showed `TraceNoLedgerView`. The ledger adapter
  now requires `cardano-cli query tip` and rejects a node below 99% sync before
  issuing a size verdict. The first `42094` launcher attempt also exposed the
  Unix socket path-length limit; moving its generated files to the short path
  `/home/tohung/stage05-infra/net42094` resolved it without touching contracts.
  The replacement Babbage chain advanced from block 0 to 3 to 13 at 100% sync.
  Generalization scope: all local-node size analyses. Reusable: yes. Repo-growth
  risk: LOW. Architecture impact: fail-closed infrastructure preflight.
  Regression: `test_marlowe_cli.py` and opt-in live integration.
- The new network's initialized template SHA-256 is
  `652605044bf9c1407891a09be62ed5780e6cea62e38a40dc7fb4a5337af0aec3`.
  Against node magic `42094`, the opt-in live test passed both the independent
  control contract and a **compiler-generated synthetic funded-choice fixture**
  (`2 passed`). The latter carries `simulation_only=true`; it demonstrates a
  compiler-to-ledger-size integration path, **not** a Batch 01 candidate reaching
  ledger and not independent semantic/reference validation. No signing, wallet,
  submission, testnet stage, or deployment stage was invoked.
- Final offline verification after these edits: `python -m pytest research/ -q`
  → `300 passed, 15 skipped`; `python -m pytest marlowe_ai_agent/tests/ -q`
  → `228 passed, 7 skipped`; `uvx ruff check --select F401,F841` → clean;
  `python -m compileall -q research marlowe_ai_agent` → clean. API attempts in
  this continuation: 4, all for case 01 and included in the durable 15/48 total.

Batch status remains **INCOMPLETE**. No Batch 01 candidate has a ledger outcome;
the profile fixture and control must not be counted as `REACHED_LEDGER_PASS` in
the 20-case denominator. The next architectural work is the explicit
simulated-customer answer loop, independent behavior expectations, reference
and exploration wiring, and additional family-level lowering. A real ledger
failure has not been observed, so no candidate contract has been optimized to
evade a protocol limit.

## Final continuation (48/48 physical calls)

This addendum supersedes the historical 15/48 status above without deleting
its failure history. Six of 20 selected records were attempted sequentially.
The append-only journal reached exactly 48/48 outbound attempts; cases 07-20
remain `NOT_ATTEMPTED`. No call was made after the cap. The model remained
`nvidia/nemotron-3-ultra-550b-a55b:free` on OpenRouter. No evaluator-only
`reference_contract` or `checks` informed model input, simulated answers, or
source fixes (`reference_assisted_diagnosis=false` for every case). No
candidate core or Marlowe contract was hand-edited.

### Final case outcomes

- **01 `vi-third_party-L1-001`:** 13 physical calls total; exact prompt and
  metadata are in Case 01 above. Three simulated answers in
  `runs/online-tuning-batch01/case-01-synthetic-input.json` resolved account
  ownership, payment/refund source, and Lan's numeric Choice; each is marked
  `synthetic_assumption=true`, not human acceptance. Prior CORE_INVALID and
  WAITING_USER attempts remain preserved. Attempt 08 reached extraction PASS,
  simulated acceptance, deterministic funded-choice compilation, pinned
  reference comparison `SATISFIED`, bounded exploration/oracle, property
  `NO_CANDIDATES`, and `REACHED_LEDGER_PASS`. On private Babbage network 42094,
  pinned `marlowe-cli run analyze --transaction-size --best` measured
  **12182 / 16384 bytes** with `syncProgress=100.00`.
  `compiler_authority=CANDIDATE_ONLY`, `simulation_only=true`;
  `property_readiness=NEEDS_MORE_EVIDENCE` because review was synthetic,
  exploration bounded, and no property candidate was produced. The later
  Stage 2B prompt change does not retroactively verify this live extraction.
- **02 `vi-rental_deposit-L4-001`:** 15 calls total; exact prompt and metadata
  are in Case 02 above. The first simulated answer used the exact hidden-fact
  canned date `04/01/2027`; later answers assumed Ha makes a bounded damage
  Choice and Chi's contract account funds the payouts and refunds. The
  append-only transcript is `case-02-synthetic-input-v3.json`; assumptions
  were never authenticated. Prior attempts retained CORE_INVALID and
  unresolved clarification. Attempt 05 had a valid v2 core but the old
  compiler rejected a two-payment branch. Family-level payout-chain lowering
  compiled the **unchanged** core on offline replay. Attempt 06 reached pinned
  reference comparison `SATISFIED`, but stale devnet 42094 failed its sync
  preflight (`LEDGER_INFRASTRUCTURE_UNAVAILABLE`, not a contract failure).
  Attempt 07 reused the valid core with 0 model calls and reached
  `REACHED_LEDGER_PASS`: **12222 / 16384 bytes** on private network 42096,
  sync 100.00. Authority remained `CANDIDATE_ONLY`; property was
  `NO_CANDIDATES`; `property_readiness=NEEDS_MORE_EVIDENCE` for the same
  synthetic and bounded-coverage limits. The final Stage 2B prompt correction
  postdates this live extraction.
- **03 `vi-escrow_3party-L3-001`:** 10 calls including the early provider
  failure and one interrupted request, all journaled. Exact prompt and
  metadata are in Case 03 above. Chat Completions later produced a structurally
  valid candidate but asked for deposit account owner and payment source.
  `case-03-synthetic-input.json` answers both with Dung's funded account as
  the simplest consistent choice; both are `synthetic_assumption=true`.
  Re-extraction twice produced an invalid Choice -> timeout continuation,
  including after a general prompt correction and bounded repair. The full
  validator errors that followed are cascades, not independent projector bugs.
  Final `NOT_REACHED_LEDGER`: last completed extraction, blocking simulated
  acceptance (`CORE_INVALID`), no compile/reference/ledger verdict;
  `property_readiness=NOT_READY`. The model output was not rewritten.
- **04 `vi-swap-L2-001`:** 4 calls, no clarification or assumption. Exact
  prompt and metadata are in historical Case 04. The model put two distinct
  asset and amount claims in `global` and again linked Choice to timeout.
  Those are distinct obligations, not a business contradiction to hide or
  coerce into ADA. Extraction `CORE_INVALID`, acceptance BLOCKED, compile not
  evaluated. `NOT_REACHED_LEDGER`; `property_readiness=NOT_READY`. A genuine
  two-asset swap needs source-grounded token identity and multi-funding
  lowering; no case-specific adapter was added.
- **05 `vi-milestone-L2-001`:** 4 calls. Exact prompt and metadata are in
  historical Case 05. The hidden amount has canned answer `32 ADA`, but no
  valid clarification was reached, so it was not injected. The model produced
  two invalid Choice -> timeout edges and a recipient evidence span absent
  from the requirement. Extraction `CORE_INVALID`, acceptance BLOCKED,
  compile not evaluated. No synthetic assumption; `NOT_REACHED_LEDGER`;
  `property_readiness=NOT_READY`; no forged evidence or hand-corrected core.
- **06 `vi-vesting-L3-001`:** 2 calls. Exact prompt and metadata are in
  historical Case 06. Extraction failed safely with
  `MODEL_ERROR/physical_call_budget_exhausted`; the next outbound attempt was
  denied before network. No candidate, clarification, compile, or ledger
  result. `NOT_REACHED_LEDGER`; `property_readiness=NOT_READY`.
- **07-20:** 0 calls each, no clarification, stage progression, synthetic
  assumption, reference-assisted diagnosis, or ledger result. Exact original
  prompts and metadata remain in the historical list. Each is
  `NOT_ATTEMPTED`, not a failed contract or an infrastructure verdict;
  `property_readiness=NOT_READY`.

### Generalized fixes and regression evidence

- **Stage 2B v2 graph primitives** record bounded Choice guards, typed
  continuation/parent links, and irrelevant context. A later prompt correction
  distinguishes Choice alternatives from causal successors. Generalization
  scope: conditional contracts; reusable: yes; repo-growth risk: LOW;
  architecture impact: versioned extraction contract. The correction was
  tested but did **not** fix the observed case-03 model failure. Regression:
  `test_choice_guard_v2.py`, `test_shadow_extractor.py`.
- **Stage 2C fail-closed review** handles malformed claim collections without
  a raw crash, renders structured clarification as readable questions, and
  keeps simulated answers at `NO_AUTHORITY`. Scope: all malformed or
  clarification-required candidates; reusable: yes; growth risk: LOW;
  architecture impact: safer acceptance boundary, not weaker validation.
  Regression: `test_acceptance_boundary.py`,
  `test_simulated_acceptance.py`, `test_authority_identity.py`.
- **Family-level funded-choice compiler 0.2.0** adds fully funded payout
  chains, per-outcome positive amounts, exact conservation, matching account
  ownership, and complete mapping evidence. Scope: funded deposits with one
  bounded Choice and one or two payouts on the selected branch; reusable:
  yes; growth risk: MEDIUM (one profile, not per case); architecture impact:
  deterministic lowering only, no authority promotion. Live attempts retain
  their historical pre-bump compiler identity. Regression:
  `test_funded_choice_v1.py`, `test_batch_scenarios.py`, real Haskell reference
  integration. The one-payment case remains supported.
- **Intent-sourced synthetic scenarios** derive declared transaction inputs
  and expected payment vectors from accepted claims, never the compiler AST;
  `NO_AUTHORITY` prevents simulated review from becoming human acceptance.
  Scope: research/tuning; reusable: yes; growth risk: LOW; architecture
  impact: a separate synthetic expectation policy and reference adapter.
  Regression: `test_batch_scenarios.py`,
  `test_batch_scenarios_integration.py`, `test_batch_corridor_integration.py`.
  A multi-payout sibling order is used only with an explicit first
  continuation, full deposit conservation, and matching source account;
  payment event order itself is not claimed as a proven business requirement.
  A future explicit sequence primitive would remove this residual ambiguity.
- **Transport and budget hardening** keeps a durable pre-request journal,
  disables hidden SDK retries, bounds each request's wall time on POSIX, and
  uses the same model through Chat Completions for this batch. Later removal
  of forced JSON mode did not prevent provider empty/retry responses in case
  05; no cost-saving claim is made. Scope: any provider run under a physical
  call cap; reusable: yes; growth risk: LOW; architecture impact: transport
  only. Regression: `test_online_tuning_batch01.py` on Windows and WSL. The
  externally interrupted case-03 run has no standalone result JSON (the next
  run reused that free attempt number), but its two outbound requests remain
  in the journal and count toward 48.
- **Node-backed ledger-size adapter** verifies pinned binary/template hashes,
  socket, real tip, and >=99% sync before calling official `marlowe-cli`.
  Scope: local Babbage-size analysis; reusable: yes; growth risk: LOW. A
  stale devnet returned UNAVAILABLE, never an invented PASS. Fresh network
  42097 subsequently passed an opt-in real-reference/ledger corridor
  (`3 passed`), independent of Batch-case verdicts. These private devnets are
  short-lived: nodes can stop forging while sockets remain. Later sessions
  require a fresh genesis and healthy tip. No wallet, signing, submission,
  Stage 5 testnet, or deployment was run.

### Final verification and limits

- `python -m pytest research/ -q`: 315 passed, 19 skipped after the final
  compiler-version bump and test assertion.
- `python -m pytest marlowe_ai_agent/tests/ -q`: 228 passed, 7 skipped.
- `uvx ruff check --select F401,F841`: clean after the unused-variable test
  assertion; `python -m compileall -q research marlowe_ai_agent`: clean.
- Opt-in WSL real Haskell/reference-to-ledger tests: `3 passed` on healthy
  network 42097 after the compiler-version bump. A prior run on stale 42096
  correctly failed the ledger sync
  gate (`2 passed, 1 failed`); it was not relabeled as contract failure.
- `marlowe-cli` source commit
  `2c0ad60ad2caabb7865b6dda56f7ec478f8637e7`, binary SHA-256
  `464f14957aafeefc86aa868074e200f700aefc070f1ecb32466d999110e58939`.
  Case-02 template SHA-256:
  `4dc1b9749e254f6113488c918bfea338465d9bf0c8bf99316b34fa7906cab141`.
  Final control-network 42097 template SHA-256:
  `2de4fe437aaa5fe3e6c01f50b445d659c787832476504be5576c3639fba4cfda`.
- Counts: 2 `REACHED_LEDGER_PASS`, 0 `REACHED_LEDGER_FAIL`, 0
  `REACHED_LEDGER_INCONCLUSIVE`, 4 `NOT_REACHED_LEDGER`, 14 `NOT_ATTEMPTED`.
  Adaptive development outcomes are **not** an unbiased accuracy estimate or
  proof of Marlowe/ledger safety. Cases 21-100 stayed untouched.
- Generalization audit: six GENERAL/FAMILY_GENERAL fix groups above, zero
  CASE_SPECIFIC source branches. The only new compiler is a shared
  funded-choice family module, not one module per benchmark case.

### Source inventory and worktree state

Baseline and starting clean HEAD:
`99484ad5a69dc560b6f3e65a2eb4289c064a5688`. This execution left the
following source changes **uncommitted and unpushed**; no reset, candidate
rewrite, or hidden evidence deletion was performed.

- Existing files modified:
  `marlowe_ai_agent/requirements-dev.txt`,
  `research/architecture/bootstrap.py`, `research/integrations/stage2b.py`,
  `research/stage2b/intent_spec.py`, `research/stage2b/projector.py`,
  `research/stage2b/shadow_extractor.py`,
  `research/stage2b/test_shadow_extractor.py`, `research/stage2c/review.py`,
  `research/stage2c/test_acceptance_boundary.py`,
  `research/stage3/authority.py`, `research/stage3/compiler.py`,
  `research/stage3/profiles.py`, `research/stage3/test_authority_identity.py`.
- New source and tests:
  `research/experiments/batch_scenarios.py`,
  `research/experiments/online_tuning_batch01.py`,
  `research/experiments/simulated_acceptance.py`,
  `research/experiments/test_batch_corridor_integration.py`,
  `research/experiments/test_batch_scenarios.py`,
  `research/experiments/test_batch_scenarios_integration.py`,
  `research/experiments/test_online_tuning_batch01.py`,
  `research/experiments/test_simulated_acceptance.py`,
  `research/final_validation/marlowe_cli.py`,
  `research/final_validation/test_marlowe_cli.py`,
  `research/final_validation/test_marlowe_cli_integration.py`,
  `research/stage2b/test_choice_guard_v2.py`,
  `research/stage3/profile_compilers/funded_choice_v1.py`,
  `research/stage3/test_funded_choice_v1.py`.
- New report/selection files: this report and
  `docs/research/online-tuning-batch01.manifest.json`.
- Ignored local evidence: `runs/online-tuning-batch01/` contains the
  append-only physical-call journal, case attempts, extraction checkpoints,
  and simulated transcripts. It is deliberately not committed; a reviewer
  without this workspace cannot independently recompute all raw metrics from
  the report alone. No API key was placed in source/report/manifest.
- Final `git diff --check` exited 0 (only Windows LF/CRLF notices); no
  commit or push was made in this execution.

## Continuation after user-authorized budget extension (2026-10-04)

The original 48-attempt journal was preserved. The user reported that
OpenRouter had accounted 28/50 daily requests and requested continuation.
`online-tuning-batch01-budget-extension.json` grants **at most 22 additional
pre-request attempts**, not a reinterpretation or reset of the original
48-attempt batch limit. Provider-accounted requests and journaled outbound
attempts are distinct measures. The extension pins a canonical SHA-256 of
the first 48 journal entries and fails if that prefix differs. The local
append-only journal now contains
**70/70** attempts; attempts 49-70 are the extension. No further live model
request is authorized by this extension.

- Case 03, attempt 08: after scope-repair diagnostics and two simulated
  clarification revisions, the model still predicted clarification without
  an unresolved claim or unrepresented behavior. Core invalid; simulated
  acceptance blocked; no compiler/reference/ledger case verdict.
- Case 04, attempt 02: core structurally valid but waits for clarification
  on the two funding accounts, swap outcomes and recipients. The business
  identity of GOLD reward points as an on-chain asset remains unproven.
  No multi-asset swap compiler or ledger case verdict was claimed.
- Case 05, attempt 02: core invalid; the model invented numeric Choice
  bounds/guards for two sequential milestones and a recipient evidence span.
  No source-backed numeric choice or compiler/ledger case verdict exists.
- Case 06, attempt 06: a simulated-customer revision specified Huy's
  funding account, Nga as recipient, two 17.5 ADA releases, and UTC dates.
  Attempt 04 had passed the old validator and simulated acceptance, but
  its three POSIX timestamps corresponded to 2024 despite source ISO dates
  in 2027. That earlier PASS is superseded by the corrected validator, not
  promoted into a ledger result. Attempt 05 was blocked for the same date
  mismatch; attempt 06 is core invalid due to three invalid `derived_from`
  references and unsupported clarification. No case-06 ledger verdict exists.

General harness changes in this continuation: typed, source-preserving
validation feedback; v2 clarification consistency; absolute calendar-date
checks for both `dd/mm/yyyy` and ISO `YYYY-MM-DD`; deterministic UTC hints
only for exact `Z` timestamps; explicit terminal-outcome continuation schema;
and a conservative two-installment ADA time-release compiler profile. The
profile passed a real pinned Haskell-reference trace with two 17.5 ADA
payments, but that is a synthetic fixture, **not** case-06 acceptance or
ledger validation. The last available outbound attempt ran with repair
disabled, so its raw candidate and diagnostics were retained. No candidate,
frozen dataset, hidden evaluator, authority label, or ledger verdict was
rewritten to force progression.

Offline revalidation of the two historical ledger-size PASS candidates
(`case-01-attempt-08` and `case-02-attempt-07`) under the new core-v2
validator found no errors. This does not rerun their model extraction or
change the limited meaning of their earlier size-analysis verdicts.

Final verification for this continuation: `python -m pytest research/ -q`
reported `324 passed, 20 skipped`; the agent test suite reported
`228 passed, 7 skipped`. In WSL, the real-reference time-release test file
reported `3 passed` (no skip). Ruff F401/F841, compileall, and
`git diff --check` passed.

Pre-push verification repeated both suites separately with the same results.
A combined invocation of both test roots in one pytest process was not clean:
`551 passed, 27 skipped, 1 failed`. The unrelated pinned-reference unit test
could not resolve `tools.marlowe_smt` because another `tools` module shadowed
that package during combined collection. The two separate suite invocations
pass; this combined-run import collision was not relabeled as a pass or folded
into the Batch 01 patch.
