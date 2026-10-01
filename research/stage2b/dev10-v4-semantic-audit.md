# Stage 2B dev10-v4 semantic extraction audit (offline)

Source HEAD: `92ab13adb831d7fb5a7766f1c9668b4d406fee71`.
Only the ten canonical **development** cases were examined. The local live
JSONL SHA-256 is `BAFCDBE41F490109EB794A2D38FB0084EEBD0204AAA65A5F437FED9DF50DC6B8`;
the local native score SHA-256 is
`2786667B81FB596B138AC86BE9428A37723E19E5DF7CFD41FCEEB152797500AC`.
These artifacts were read, not changed. Stage 2A annotations remain **draft
candidates**, not human-adjudicated truth. Candidate-relative exact-key
precision/recall is not semantic accuracy.

## Method and ledger notation

Every financial claim in the candidate (62) and emitted core (63) appears
below, either alone or paired with its nearest semantic counterpart. `C` and
`P` identify candidate and prediction; each entry gives `claim_id`,
`kind=value@scope_id`, status, and exact evidence span. All evidence is from
requirement version 1 unless `v2` is shown. `none` means no evidence. Claim
IDs/scope IDs are case-local. A different spelling of an otherwise equivalent
scope ID is **not** by itself a semantic error. Comparisons marked `[CLEAR]`
are supported by the source requirement plus existing Stage 2A/2B policy;
`[REL]` are candidate-relative/ambiguous; `[EXACT]` are supported matches;
`[OUTPUT]` means no usable prediction. A row can contain both `[CLEAR]` and
`[REL]` for distinct aspects. Confidence is `high` or `medium`; low-confidence
interpretations are left candidate-relative. The rule IDs in the last column
refer to the proposed **generic** prompt refinements below, not per-case
repairs. Claim and question rows are diagnostic observations, not independent
causal failures.

Classification terms used in the ledger: `CORRECT_EXACT`,
`CLEAR_FALSE_CLAIM`, `CLEAR_MISSED_CLAIM`, `WRONG_KIND`, `WRONG_VALUE`,
`WRONG_SCOPE`, `WRONG_STATUS`, `WRONG_PROVENANCE`, `WRONG_DERIVED_FROM`,
`ROLE_CONFUSION`, `ACCOUNT_ROLE_CONFUSION`, `RECIPIENT_ROLE_CONFUSION`,
`CORRECTION_SUPERSESSION_ERROR`, `CONFLICT_HANDLING_ERROR`,
`CANDIDATE_RELATIVE_ONLY`, `CANDIDATE_AMBIGUITY`,
`STRUCTURAL_EMPTY_CORE`, and `MODEL_OUTPUT_UNAVAILABLE`. Unobserved classes
are not manufactured to fill the taxonomy.

### `pay-d1`

Requirement: Alice deposits 10 ADA into Alice's account before 1000 ms; after
valid deposit Bob receives 10 ADA. Candidate `accepted_interpretation`; model
`clarification_required`. The source account demanded by the model may be a
real missing implementation/business detail; candidate acceptance is not an
oracle, so this **resolution mismatch is candidate-relative**, not a proven
unnecessary hold.

- [CLEAR] C `c1 depositing_party=Alice@deposit-1` explicit, "Alice nạp"; P `depositing-party-deposit-1 depositing_party=Alice@deposit-1` explicit, "Alice". `WRONG_PROVENANCE`: bare name does not itself express the deposit relation. `EVIDENCE_SEMANTIC_OVERREACH`, high, R1.
- [EXACT] C `c2 destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice"; P `destination-account-owner-deposit-1 destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice". `CORRECT_EXACT`.
- [CLEAR] C `c3 amount_lovelace=10000000@deposit-1` derived, "10 ADA"; P `deposit-amount-deposit-1 amount_lovelace=10000000@deposit-1` explicit, "10 ADA". `WRONG_STATUS`: conversion to lovelace is not an explicit 10000000-lovelace source fact. `NORMALIZATION_STATUS`, high, R2.
- [CLEAR] [REL] C `c4 payment_recipient=Bob@payout-1` explicit, "Bob nhận"; P `payment-recipient-payment-1 payment_recipient=Bob@payment-1` explicit, "Bob". `WRONG_PROVENANCE` for bare name (high, R1); `CANDIDATE_RELATIVE_ONLY` for equivalent generic-payment scope ID (medium, no rule).
- [EXACT] C `c5 deposit_deadline_ms=1000@deposit-1` explicit, "POSIX 1000 ms"; P `deposit-deadline-deposit-1 deposit_deadline_ms=1000@deposit-1` explicit, "POSIX 1000 ms". `CORRECT_EXACT`.
- [EXACT] C `asset asset=ADA@global` explicit, "10 ADA"; P `asset-global asset=ADA@global` explicit, "ADA". `CORRECT_EXACT`; the symbol is directly named.
- [CLEAR] [REL] C none; P `payment-amount-payment-1 amount_lovelace=10000000@payment-1` explicit, "10 ADA". The payout amount is stated and candidate omitted a branch/payment-specific amount (`CANDIDATE_RELATIVE_ONLY`); the ADA-to-lovelace status is `WRONG_STATUS` (high, R2).
- [REL] C none; P `payment-source-account-owner-payment-1 payment_source_account_owner=null@payment-1` unresolved, none. `CANDIDATE_AMBIGUITY`: funding/payout source is not named independently. Do not tune it away merely to force candidate acceptance.

### `refund-d1`

Requirement: deposit of 8 ADA into Alice's account before 2000 ms; refund to
Alice after 3000 ms if not disbursed. "Disbursed" and the success continuation
are undefined. Both resolutions hold for clarification. Candidate omits the
**explicit 2000 ms deposit deadline**; that scored false positive is not a
model mistake.

- [EXACT] C `c1 depositing_party=Alice@deposit-1` explicit, "Alice nạp"; P `claim-depositing-party depositing_party=Alice@deposit-1` explicit, "Alice nạp". `CORRECT_EXACT`.
- [EXACT] C `c2 destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice"; P `claim-destination-account destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice". `CORRECT_EXACT`.
- [CLEAR] C `c3 amount_lovelace=8000000@deposit-1` derived, "8 ADA"; P `claim-amount-deposit amount_lovelace=8000000@deposit-1` explicit, "8 ADA". `WRONG_STATUS`, `NORMALIZATION_STATUS`, high, R2.
- [REL] C `c4 refund_recipient=Alice@refund-timeout-1` explicit, "hoàn 8 ADA cho Alice"; P `claim-refund-recipient refund_recipient=Alice@timeout-1` explicit, "hoàn 8 ADA cho Alice". Same timeout/refund role and value; ID alias is `CANDIDATE_RELATIVE_ONLY`. The predicted timeout's `decision_id=deposit-1` additionally assumes an unsupported causal link to deposit rather than the unspecified disbursement mechanism; `WRONG_SCOPE` is medium-confidence, R3.
- [REL] C `c5 refund_deadline_ms=3000@refund-timeout-1` explicit, "POSIX 3000 ms"; P `claim-refund-deadline refund_deadline_ms=3000@timeout-1` explicit, "POSIX 3000 ms". Same timing fact; scope-name mismatch alone is `CANDIDATE_RELATIVE_ONLY`.
- [CLEAR] C `asset asset=ADA@global` explicit, "8 ADA"; P `claim-asset asset=ADA@deposit-1` explicit, "ADA". `WRONG_SCOPE`: Stage 2A protocol uses global for the directly named asset of the monetary obligation, not an event-local asset. High, R3.
- [REL] C none; P `claim-deposit-deadline deposit_deadline_ms=2000@deposit-1` explicit, "POSIX 2000 ms". Candidate omitted a directly stated deadline; `CANDIDATE_RELATIVE_ONLY` omission, no model patch.
- [CLEAR] [REL] C none; P `claim-refund-amount amount_lovelace=8000000@timeout-1` explicit, "8 ADA". The amount is supported and absent from candidate (`CANDIDATE_RELATIVE_ONLY`); its converted-lovelace status is `WRONG_STATUS`, high, R2.

### `choice-d1`

Requirement: Alice deposits 12 ADA; Bob chooses approve (Bob receives 12 ADA)
or reject (Alice is refunded 12 ADA) before 4000 ms. Candidate asks only for
the no-choice timeout outcome. Model also asks about source, extra deadlines,
autonomy, and a third release recipient. Some of these may be implementation
ambiguities, but they must not be treated as five additional proven critical
business gaps.

- [CLEAR] C `c1 depositing_party=Alice@deposit-1` explicit, "Alice nạp"; P `claim-3 depositing_party=Alice@deposit-1` explicit, "Alice". `WRONG_PROVENANCE`, high, R1.
- [EXACT] C `c2 destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice"; P `claim-4 destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice". `CORRECT_EXACT`.
- [CLEAR] [REL] C `c3 choice_owner=Bob@decision-1` explicit, "Bob chọn approve"; P `claim-6 choice_owner=Bob@choice-1` explicit, "Bob". Bare-name `WRONG_PROVENANCE` (high, R1); otherwise equivalent choice-transition ID is `CANDIDATE_RELATIVE_ONLY`.
- [REL] C `c4 release_recipient=Bob@decision-1:approve` explicit, "Bob nhận 12 ADA"; P `claim-8 payment_recipient=Bob@decision-1:approve` explicit, "Bob nhận". `RECIPIENT_ROLE_CONFUSION` is **not proven** here: the text does not explicitly say escrow/release. `CANDIDATE_AMBIGUITY` on kind, no recipient-kind prompt rule added.
- [EXACT] C `c5 refund_recipient=Alice@decision-1:reject` explicit, "Alice được hoàn 12 ADA"; P `claim-10 refund_recipient=Alice@decision-1:reject` explicit, "Alice được hoàn". `CORRECT_EXACT`.
- [CLEAR] C `amount amount_lovelace=12000000@deposit-1` derived, "Alice nạp 12 ADA"; P `claim-2 amount_lovelace=12000000@deposit-1` explicit, "12 ADA". `WRONG_STATUS`, high, R2.
- [REL] C `choice-deadline choice_deadline_ms=4000@decision-1` explicit, "POSIX 4000 ms"; P `claim-5 choice_deadline_ms=4000@choice-1` explicit, "4000 ms". Equivalent choice transition; `CANDIDATE_RELATIVE_ONLY` scope ID.
- [EXACT] C `asset asset=ADA@global` explicit, "12 ADA"; P `claim-1 asset=ADA@global` explicit, "ADA". `CORRECT_EXACT`.
- [CLEAR] [REL] C none; P `claim-7 amount_lovelace=12000000@decision-1:approve` explicit, "12 ADA". Outcome amount is stated, candidate omitted this atomic branch amount (`CANDIDATE_RELATIVE_ONLY`); converted status is `WRONG_STATUS`, high, R2.
- [CLEAR] [REL] C none; P `claim-9 amount_lovelace=12000000@decision-1:reject` explicit, "12 ADA". Same supported branch amount/candidate omission, but `WRONG_STATUS`, high, R2.
- [REL] C none; P `claim-11 payment_source_account_owner=null@decision-1:approve` unresolved, none. Funding source may be a genuine missing detail; `CANDIDATE_AMBIGUITY`, no rule to suppress categorically.
- [CLEAR] C none; P `claim-12 refund_deadline_ms=null@decision-1:reject` unresolved, none. `CLEAR_FALSE_CLAIM`: reject is a stated branch, not evidence for a second refund deadline. High, R4.
- [REL] C none; P `claim-13 deposit_deadline_ms=null@deposit-1` unresolved, none. No deposit deadline is specified; whether its absence blocks this research intent is `CANDIDATE_AMBIGUITY`, not a proven false fact.
- [CLEAR] C none; P `claim-15 timeout_ms=null@global` unresolved, none. The choice deadline is already 4000 ms; the missing fact is the no-choice *outcome*, not a global second timeout. `WRONG_SCOPE` / `CLEAR_FALSE_CLAIM`, high, R3/R4.
- [CLEAR] C none; P `claim-16 release_recipient=null@global` unresolved, none. The two named outcomes already name recipients; inventing a third release issue is `CLEAR_FALSE_CLAIM`, high, R4.

### `escrow-d1` and `double-d1`: unavailable model output

Both records are `model_error` with historical `invalid_model_json` code. The
pre-observability raw data cannot resolve whether SDK response decode or
model-content parsing failed. Neither case has a core/predicted claim. Each
candidate claim below is `MODEL_OUTPUT_UNAVAILABLE`, **not** a demonstrated
semantic omission by the model. No model-specific semantic rule is derived
from these cases.

`escrow-d1` candidate, expected `clarification_required`, asks for the missing
deposit deadline:

- [OUTPUT] `c1 depositing_party=Alice@deposit-1` explicit, "Alice đặt cọc".
- [OUTPUT] `c2 destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice".
- [OUTPUT] `c3 choice_owner=Bob@decision-1` explicit, "Bob có thể approve".
- [OUTPUT] `c4 release_recipient=Bob@decision-1:approve` explicit, "để nhận 5 ADA".
- [OUTPUT] `c5 refund_recipient=Alice@decision-1:timeout` explicit, "hoàn tiền cho Alice".
- [OUTPUT] `amount amount_lovelace=5000000@deposit-1` derived, "Alice đặt cọc 5 ADA".
- [OUTPUT] `choice-deadline choice_deadline_ms=6000@decision-1` explicit, "POSIX 6000 ms".
- [OUTPUT] `asset asset=ADA@global` explicit, "5 ADA".

`double-d1` candidate, expected `accepted_interpretation`, no clarification:

- [OUTPUT] `c1 depositing_party=Alice@deposit-1` explicit, "Alice nạp".
- [OUTPUT] `c2 choice_owner=Bob@decision-1` explicit, "Bob chọn approve".
- [OUTPUT] `c3 deposit_deadline_ms=7000@deposit-1` explicit, "POSIX 7000 ms".
- [OUTPUT] `c4 choice_deadline_ms=8000@decision-1` explicit, "POSIX 8000 ms".
- [OUTPUT] `c5 refund_recipient=Alice@decision-1:timeout` explicit, "hoàn tiền cho Alice".
- [OUTPUT] `account-owner destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice".
- [OUTPUT] `amount amount_lovelace=7000000@deposit-1` derived, "Alice nạp 7 ADA".
- [OUTPUT] `release-recipient release_recipient=Bob@decision-1:approve` explicit, "Bob chọn approve trước mốc POSIX 8000 ms để nhận 7 ADA".
- [OUTPUT] `asset asset=ADA@global` explicit, "7 ADA".

### `conditional-d1`

Requirement: after Alice's deposit, Notify completion before 9000 ms pays Bob;
timeout refunds Alice. The missing *Observation that makes Notify true* is the
business question. Model and candidate both hold, but the model attaches
unrelated Choice-owner and extra-deadline gaps. Structural scope validity does
not establish semantic branch placement.

- [EXACT] C `c1 depositing_party=Alice@deposit-1` explicit, "Alice nạp"; P `claim-depositing-party depositing_party=Alice@deposit-1` explicit, "Alice nạp". `CORRECT_EXACT`.
- [CLEAR] C `c2 payment_recipient=Bob@notify-1:success` explicit, "Bob nhận 4 ADA"; P `claim-payment-recipient payment_recipient=Bob@payment-1` explicit, "Bob nhận 4 ADA". Value/kind are right, but `WRONG_SCOPE`: this outcome belongs to the Notify-success branch, not a detached payment transition. High, R3.
- [CLEAR] C `c3 refund_recipient=Alice@notify-1:timeout` explicit, "Alice lấy lại 4 ADA"; P `claim-refund-recipient refund_recipient=Alice@refund-1` explicit, "Alice lấy lại 4 ADA". `WRONG_SCOPE`: timeout branch fact, high, R3.
- [EXACT] C `c4 timeout_ms=9000@notify-1` explicit, "POSIX 9000 ms"; P `claim-notify-timeout timeout_ms=9000@notify-1` explicit, "mốc POSIX 9000 ms". `CORRECT_EXACT`.
- [EXACT] C `c5 asset=ADA@global` explicit, "4 ADA"; P `claim-asset asset=ADA@global` explicit, "4 ADA". `CORRECT_EXACT`.
- [EXACT] C `account-owner destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice"; P `claim-destination-owner destination_account_owner=Alice@deposit-1` explicit, "tài khoản Alice". `CORRECT_EXACT`.
- [EXACT] C `amount amount_lovelace=4000000@deposit-1` derived, "Alice nạp 4 ADA"; P `claim-deposit-amount amount_lovelace=4000000@deposit-1` derived, "4 ADA". `CORRECT_EXACT`; normalization basis is present in the raw core.
- [REL] C none; P `claim-deposit-deadline deposit_deadline_ms=null@deposit-1` unresolved, none. Missing deposit deadline may matter to implementation, but candidate did not adjudicate it as critical: `CANDIDATE_AMBIGUITY`, no rule to suppress categorically.
- [CLEAR] C none; P `claim-choice-owner choice_owner=null@notify-1` unresolved, none. `ROLE_CONFUSION`: a missing Notify Observation is not a missing Choice owner. Existing prompt already forbids this; R5 makes priority clearer.
- [CLEAR] [REL] C none; P `claim-payment-amount amount_lovelace=4000000@payment-1` derived, "Bob nhận 4 ADA". Amount is directly supported but candidate omitted it (`CANDIDATE_RELATIVE_ONLY`); detached success-payment scope is `WRONG_SCOPE`, high, R3.
- [REL] C none; P `claim-payment-source payment_source_account_owner=null@payment-1` unresolved, none. The requirement does not independently name a payout account; whether that missing field is critical is `CANDIDATE_AMBIGUITY`, not automatically a false claim.
- [CLEAR] [REL] C none; P `claim-refund-amount amount_lovelace=4000000@refund-1` derived, "Alice lấy lại 4 ADA". Supported amount omitted by candidate (`CANDIDATE_RELATIVE_ONLY`); detached timeout-refund scope is `WRONG_SCOPE`, high, R3.
- [CLEAR] C none; P `claim-refund-deadline refund_deadline_ms=null@refund-1` unresolved, none. The specified Notify timeout already defines the timeout path; a separate refund deadline is not an expressed business fact. `CLEAR_FALSE_CLAIM`, high, R4.

### `choice-d2-correction`: structural empty core

The raw semantic core is `{}` with nine cascading core validation messages;
the full projection has seven cascading messages. The model did not expose
its interpretation of the explicit later owner correction. This is
`STRUCTURAL_EMPTY_CORE`, **not** evidence of
`CORRECTION_SUPERSESSION_ERROR` or conflict confusion. Candidate resolution is
`clarification_required` for funding, deadline and no-approval outcome.

- [OUTPUT] `old-owner choice_owner=Bob@decision-1` superseded, "Bob quyết định approve" (v1), `superseded_by=new-owner`.
- [OUTPUT] `new-owner choice_owner=Alice@decision-1` user_confirmed, "Alice mới là người quyết định approve" (v2).
- [OUTPUT] `recipient payment_recipient=Linh@decision-1:approve` explicit, "Linh vẫn nhận 2 ADA" (v2).
- [OUTPUT] `amount amount_lovelace=2000000@decision-1:approve` derived, "2 ADA" (v2).
- [OUTPUT] `asset asset=ADA@global` explicit, "2 ADA" (v2).

### `pay-d2-clarify`

Requirement: Alice sends 3 ADA before 1100 ms and pays an unnamed recipient.
Candidate and model both hold for clarification. Candidate omits the directly
named sender/depositor; model omission of a separate payment source cannot be
scored as a clear error without adjudicating the account semantics.

- [EXACT] C `amount amount_lovelace=3000000@deposit-1` derived, "3 ADA"; P `claim-amount-lovelace amount_lovelace=3000000@deposit-1` derived, "3 ADA". `CORRECT_EXACT`.
- [REL] C `recipient payment_recipient=null@payout-1` unresolved, none; P `claim-payment-recipient payment_recipient=null@payment-1` unresolved, "người nhận". Both identify the missing recipient; scope ID and optional unresolved evidence differ. `CANDIDATE_RELATIVE_ONLY`, no rule.
- [EXACT] C `deposit-deadline deposit_deadline_ms=1100@deposit-1` explicit, "POSIX 1100 ms"; P `claim-deposit-deadline deposit_deadline_ms=1100@deposit-1` explicit, "POSIX 1100 ms". `CORRECT_EXACT`.
- [CLEAR] C `asset asset=ADA@global` explicit, "3 ADA"; P `claim-asset asset=ADA@deposit-1` explicit, "ADA". `WRONG_SCOPE` under Stage 2A global-asset convention, high, R3.
- [CLEAR] [REL] C none; P `claim-depositing-party depositing_party=Alice@deposit-1` explicit, "Alice". Source clearly says Alice sends, so candidate omission is `CANDIDATE_RELATIVE_ONLY`; bare-name `WRONG_PROVENANCE`, high, R1.
- [CLEAR] C none; P `claim-destination-account-owner destination_account_owner=null@payment-1` unresolved, "người nhận". `ACCOUNT_ROLE_CONFUSION`: destination owner of the *deposit* is missing, not established by "recipient" and not a payment-scope deposit-account fact. High, R3/R4.
- [REL] C none; P `claim-payment-source-account-owner payment_source_account_owner=null@payment-1` unresolved, none. A payment source/account question may be material but cannot be settled from this source/candidate alone: `CANDIDATE_AMBIGUITY`, no categorical suppression.

### `escrow-d2-clarify`

Requirement: Lan escrows 15 ADA; Lan or Minh may choose release before 23000
ms so Minh receives funds, otherwise Lan is refunded. Candidate asks for the
Choice owner **and** destination escrow account owner. Model asks only the
Choice-owner question. Release/refund recipient values are right but attached
to detached payment transitions instead of the named branch/timeout.

- [EXACT] C `owner choice_owner=null@decision-1` unresolved, none; P `claim-choice-owner choice_owner=null@decision-1` unresolved, "một trong Lan hoặc Minh". `CORRECT_EXACT` for the unresolved role; optional evidence does not choose an owner.
- [CLEAR] C `recipient release_recipient=Minh@decision-1:release` explicit, "Minh nhận tiền"; P `claim-release-recipient release_recipient=Minh@payment-release` explicit, "Minh nhận tiền". `WRONG_SCOPE`, high, R3.
- [CLEAR] [REL] C `depositor depositing_party=Lan@deposit-1` explicit, "Lan ký quỹ 15 ADA"; P `claim-depositing-party depositing_party=Lan@deposit-1` explicit, "Lan". Matching role/value; bare-name `WRONG_PROVENANCE`, high, R1.
- [EXACT] C `amount amount_lovelace=15000000@deposit-1` derived, "Lan ký quỹ 15 ADA"; P `claim-deposit-amount amount_lovelace=15000000@deposit-1` derived, "15 ADA". `CORRECT_EXACT`.
- [EXACT] C `choice-deadline choice_deadline_ms=23000@decision-1` explicit, "POSIX 23000 ms"; P `claim-choice-deadline choice_deadline_ms=23000@decision-1` explicit, "POSIX 23000 ms". `CORRECT_EXACT`.
- [CLEAR] C `refund-recipient refund_recipient=Lan@decision-1:timeout` explicit, "sau hạn Lan được hoàn"; P `claim-refund-recipient refund_recipient=Lan@payment-refund` explicit, "Lan được hoàn". `WRONG_SCOPE`, high, R3.
- [CLEAR] C `asset asset=ADA@global` explicit, "15 ADA"; P `claim-deposit-asset asset=ADA@deposit-1` explicit, "ADA". `WRONG_SCOPE`, high, R3.
- [CLEAR] C no claim but candidate asks account owner; P no `destination_account_owner` unresolved claim/question for the escrow deposit. The requirement names depositor but no account owner. `CLEAR_MISSED_CLAIM` for a business-critical unknown, high, R4; this is a question-quality finding, not part of the 7/7 candidate/predicted claim inventory above.

### `double-d2-conflict`

Requirement: Alice must deposit before 24000 ms while the same contract calls
25000 ms its *only* deposit deadline. This is an explicit same-kind/same-event
conflict. Both model and candidate choose `conflict_requires_resolution`, but
the model's questions do not ask which deadline governs.

- [CLEAR] C `t1 deposit_deadline_ms=24000@deposit-1` conflicted, "POSIX 24000 ms"; P `claim-1 deposit_deadline_ms=24000@global` conflicted, "POSIX 24000 ms". `WRONG_SCOPE`: deposit deadline belongs to a deposit transition, not global. High, R3.
- [CLEAR] C `t2 deposit_deadline_ms=25000@deposit-1` conflicted, "POSIX 25000 ms"; P `claim-2 deposit_deadline_ms=25000@global` conflicted, "POSIX 25000 ms". Same `WRONG_SCOPE`, high, R3. The conflict grouping remains internally consistent on the predicted scope.
- [CLEAR] [REL] C none; P `claim-3 depositing_party=Alice@global` explicit, "Alice". Source names Alice as depositor, so candidate omission is `CANDIDATE_RELATIVE_ONLY`; global placement and bare-name evidence are `WRONG_SCOPE` / `WRONG_PROVENANCE`, high, R1/R3.
- [REL] C none; P `claim-4 amount_lovelace=null@global` unresolved, none. No amount is supplied; whether asking for it during deadline-conflict resolution is necessary is `CANDIDATE_AMBIGUITY`, not a concrete false value.
- [REL] C none; P `claim-5 asset=null@global` unresolved, none. Same `CANDIDATE_AMBIGUITY`; no asset is named.

## Resolution and clarification ledger

The native `required_clarification_recall=6/8` measures whether a case was
held, **not** whether its questions address the missing facts. Predicted
question IDs are not stable across response formats; `Q1`, `Q2`, etc. below
follow the raw list order. `REQUIRED_BUSINESS_QUESTION` can coexist with a
language/style defect. No question content exists for the three unusable
cores.

- `pay-d1`: predicted clarification vs candidate accepted =
  `CANDIDATE_RELATIVE_ONLY` (medium). A separately identified source account
  is not explicit, but candidate considers the funded path sufficient.
  - [REL] Q1 "Tài khoản nào là nguồn thanh toán 10 ADA cho Bob? (payment_source_account_owner)" = `CANDIDATE_RELATIVE_ONLY`; possible funding ambiguity. The schema token is poor business phrasing, but not proof the underlying question is unnecessary. R4 if asked.
- `refund-d1`: predicted/candidate clarification = `CORRECT_HOLD` (high).
  - [REL] Q1 "Ai là chủ tài khoản nguồn cung cấp 8 ADA hoàn lại ...?" = `ACCOUNT_CONFUSION_QUESTION` / `CANDIDATE_AMBIGUITY`; Alice's deposit account is named, but refund funding may not be fully specified.
  - [CLEAR] Q2 "Ai là người gửi giao dịch hoàn tiền ...?" = `TECHNICAL_NOT_BUSINESS`; a valid post-deadline transaction does not require the user to nominate a submitter in this intent taxonomy. High, R4.
  - [REL] Q3 "Điều kiện 'chưa giải ngân' ám chỉ ... bên nào, số tiền và tài khoản đích ...?" = `CANDIDATE_RELATIVE_ONLY`; it partly probes disbursement but does not directly define its event/state or successful continuation.
  - [CLEAR] Missing question: what constitutes disbursement and what happens on its successful branch? `CLEAR_MISSED_CLAIM` at question level (high, R4). Candidate's two questions are grounded in the undefined phrase, not presumed gold wording.
- `choice-d1`: predicted/candidate clarification = `CORRECT_HOLD` (high); the
  no-choice outcome is genuinely unspecified.
  - [REL] Q1 source account for approve = `CANDIDATE_AMBIGUITY`; not enough evidence to suppress categorically.
  - [CLEAR] Q2 separate refund deadline after reject = `REDUNDANT_QUESTION`; the source defines reject as a branch but does not call for a second deadline. High, R4.
  - [REL] Q3 deposit deadline = `CANDIDATE_AMBIGUITY`; implementation may need a bound, but no source deadline is stated.
  - [CLEAR] Q4 whether contract executes automatically = `TECHNICAL_NOT_BUSINESS` / `OUTSIDE_TAXONOMY_QUESTION`; no autonomous-execution claim was made. High, R4.
  - [EXACT] Q5 what happens if Bob makes no choice by 4000 ms = `REQUIRED_BUSINESS_QUESTION`; parenthetical `timeout_ms` should be omitted from user-facing wording. R4.
  - [CLEAR] Q6 other release recipient outside approve/reject = `REDUNDANT_QUESTION`; no third release path is stated. High, R4.
- `escrow-d1`: resolution/question unavailable due `MODEL_OUTPUT_UNAVAILABLE`;
  no semantic attribution. Candidate asks for a deposit deadline distinct from
  the approval deadline.
- `double-d1`: resolution/question unavailable due `MODEL_OUTPUT_UNAVAILABLE`;
  no semantic attribution. Candidate accepts.
- `conditional-d1`: predicted/candidate clarification = `CORRECT_HOLD` (high),
  but the actual Notify condition question was missed.
  - [CLEAR] Q1 who chooses/activates Notify = `ROLE_CONFUSION_QUESTION`; Notify is not Choice. High, R5.
  - [REL] Q2 payment source account = `CANDIDATE_AMBIGUITY`; funding details may matter, but candidate did not adjudicate this separately.
  - [CLEAR] Q3 separate refund deadline after Notify timeout = `REDUNDANT_QUESTION`; high, R4.
  - [REL] Q4 deposit deadline = `CANDIDATE_AMBIGUITY`.
  - [CLEAR] Q5 automatic execution vs manual transaction = `TECHNICAL_NOT_BUSINESS` / `OUTSIDE_TAXONOMY_QUESTION`; not raised by requirement. High, R4.
  - [CLEAR] Missing question: what business Observation makes "Notify hoàn thành" true? `CLEAR_MISSED_CLAIM` at question level. High, R5.
- `choice-d2-correction`: `STRUCTURAL_EMPTY_CORE`; resolution and questions
  unavailable. No evidence of `CORRECTION_AS_CONFLICT`, `FALSE_CONFLICT`, or
  correct supersession behavior; no correction-specific prompt tuning from
  this case.
- `pay-d2-clarify`: predicted/candidate clarification = `CORRECT_HOLD` (high).
  - [CLEAR] Q1 recipient identity = `REQUIRED_BUSINESS_QUESTION`, but English
    "Who is ... Provide a party identifier" violates the existing Vietnamese
    business-question instruction; `TECHNICAL_NOT_BUSINESS` wording, high, R4.
  - [CLEAR] [REL] Q2 payment-source account owner = `CANDIDATE_AMBIGUITY` on
    substance, but its English/code-facing wording is a clear question-quality
    violation. High for language, medium for business necessity, R4.
- `escrow-d2-clarify`: predicted/candidate clarification = `CORRECT_HOLD`
  (high) for Choice owner, but the deposit account is also unspecified.
  - [EXACT] Q1 who may choose release = `REQUIRED_BUSINESS_QUESTION`; the
    parenthetical claim that Marlowe allows only one owner is implementation
    language, not needed in a user-facing question. R4.
  - [CLEAR] Missing question: into which account is the 15 ADA deposited and
    who owns it? `CLEAR_MISSED_CLAIM` at question level, high, R4.
- `double-d2-conflict`: predicted/candidate conflict = `CORRECT_HOLD` on
  resolution label (high); the raw same-kind/same-scope values genuinely
  conflict. There is **no false conflict** in this case.
  - [REL] Q1 deposit amount = `CANDIDATE_AMBIGUITY`; it may be needed later to
    instantiate a full contract, but does not resolve the current conflict.
  - [REL] Q2 asset type = `CANDIDATE_AMBIGUITY` for the same reason.
  - [CLEAR] Missing question: which single deposit deadline governs, 24000 or
    25000 ms? `CONFLICT_HANDLING_ERROR` at question level; high, R4. Asking
    only about amount/asset leaves the conflicting values unresolved.

No v4 evidence establishes `MISSED_HOLD`, `FALSE_CONFLICT`,
`CORRECTION_AS_CONFLICT`, or `UNSUPPORTED_MISCLASSIFICATION`. One resolution
label differs (`pay-d1`), and that difference is candidate-relative rather
than a proven model policy violation. Several held cases have incomplete or
irrelevant *question content* despite matching resolution labels.

## Cross-case provenance and scope findings

- `47/47` provenance completeness means every active predicted critical claim
  met the scorer's structural evidence check; it does **not** prove semantic
  support. Seven bare-party-name spans above do not themselves express the
  claimed depositor/Choice/recipient role. Broader valid spans such as "Alice
  nạp" or "Bob nhận" are available in the same requirement. No v4
  `WRONG_DERIVED_FROM` error was observed; the normalized amount status issue
  is separate.
- Converting `N ADA` to `N*1000000 lovelace` while marking the result
  `explicit` occurred seven times (`pay-d1` 2, `refund-d1` 2, `choice-d1` 3).
  These are clear status/normalization-provenance defects even when exact-key
  scoring counts the numeric value as matched. Other emitted converted values
  are correctly marked `derived`.
- Genuine business branch facts should retain the stated Choice/Notify
  success or timeout context. Detached payment/refund transitions in
  `conditional-d1` and `escrow-d2-clarify` pass structural validation but
  change the semantic scope. Conversely, `payout-1` vs `payment-1` or
  `refund-timeout-1` vs `timeout-1` alone are naming differences, not proof of
  wrong behavior. `double-d2-conflict` demonstrates wrong `global` scope for
  explicit deposit deadlines even though its conflict status is correct.
- `asset=ADA@global` is the Stage 2A convention for a directly named asset
  spanning a monetary obligation. Event-local `asset=ADA` in `refund-d1`,
  `pay-d2-clarify`, and `escrow-d2-clarify` is a semantic-scope mismatch under
  that protocol, not a new asset kind.
- No v4 core can demonstrate correction/supersession behavior: the only
  correction case returned `{}`. Do not strengthen a correction rule from that
  failure alone. No v4 model output demonstrates invented concrete recipient,
  Choice owner, account owner, or normalized numeric value; most extra claims
  are unresolved questions or supported branch amounts.

## Counts and root causes

The claim ledger has **32 `[CLEAR]` rows** (31 claim comparisons plus one
question-only account-owner omission),
**14 `[REL]`-only rows** (candidate-relative-only claim comparisons), 18
supported `[EXACT]` rows, and 22 `[OUTPUT]` candidate-claim rows without usable
model output. Another 11 rows carry both clear and candidate-relative aspects;
the extra account-owner question finding for `escrow-d2-clarify` has no claim ID
and is included in the 32 clear rows only as a question-level omission. The
question ledger has **13 `[CLEAR]` observations**, **9 `[REL]`-only
observations**, and 2 supported `[EXACT]` questions. Several question findings
are the *same* causal issue as a claim finding; do not add these figures or
equate them with the 47 predicted active claims used by the native scorer.
Three whole cases have unusable output: two historical `invalid_model_json`
records and one empty core. There is no correction/conflict inference from
their absence.

Counts in the next table refer to **claim rows (C)** and **question observations
(Q)** carrying that rule ID. A row can have more than one root cause; these
counts overlap and are not separate model failures. `REL-only` excludes any
row also marked `[CLEAR]`.

| Root cause / generic rule | Clear count; affected cases | REL-only count / boundary | Existing prompt coverage and justified change |
| --- | --- | --- | --- |
| R1 `EVIDENCE_SEMANTIC_OVERREACH` | 7 C; bare-party-name spans in `pay-d1`, `choice-d1`, `pay-d2-clarify`, `escrow-d2-clarify`, `double-d2-conflict` | 0 linked REL-only; other broad spans may or may not prove a fact. | Existing exact-span wording checks substring presence but not the expressed relation. Require role/action-bearing evidence, without changing validator or scorer. |
| R2 `NORMALIZATION_STATUS` | 7 C; ADA-to-lovelace conversions labelled `explicit` in `pay-d1`, `refund-d1`, `choice-d1` | 0 linked REL-only; supported payout/branch amounts omitted by candidate remain candidate-relative. | Existing basis rule covers `derived` claims but does not explicitly say converted numeric values are derived. Clarify status ordering; preserve directly stated ADA asset as explicit. |
| R3 `SCOPE_SEMANTIC_MISBINDING` | 14 C; event/branch/local-vs-global scopes in `refund-d1`, `choice-d1`, `conditional-d1`, `pay-d2-clarify`, `escrow-d2-clarify`, `double-d2-conflict` | 1 linked REL-only; scope-ID aliases and unproven causal linkage are not hard errors. | Existing schema explains structural IDs, not how to bind *business* facts to event/branch. Add one semantic mapping rule, including global asset only when genuinely branch-independent. |
| R4 `QUESTION_MINIMALITY` / `ACCOUNT_ROLE_CONFUSION` | 6 C, 10 Q; technical/extra questions in `refund-d1`, `choice-d1`, `conditional-d1`; wrong deposit-account role in `pay-d2-clarify`; missing owner in `escrow-d2-clarify`; conflict question in `double-d2-conflict` | 1 linked REL-only Q; source-account/deposit-deadline/amount gaps elsewhere need adjudication. | Existing Vietnamese/unknown wording and role list are dispersed. Put question-to-critical-issue and role-source checks before resolution precedence; do not suppress every unannotated gap. |
| R5 `ROLE_CONFUSION` at Notify | 1 C, 2 Q; `conditional-d1` emits `choice_owner=null` and asks its owner instead of the missing Notify Observation. | 0 linked REL-only; not every Notify needs a question. | Existing prompt **already forbids** this. Move/consolidate into the event-role decision order, not another repeated prohibition. |

No new prompt rule is justified for `CORRECTION_SUPERSESSION_ERROR`,
`RECIPIENT_ROLE_CONFUSION`, a categorical ban on payment-source clarifications,
or a fixed accepted/hold outcome for `pay-d1`: the v4 evidence is absent or
candidate-relative. The existing correction and active-conflict rules stay in
force. Resolution order can be made explicit as a consolidation of existing
policy, not an inference that the model demonstrably violated it in v4.

## Offline hardening and future gate

This patch changes only the research extraction instructions and synthetic
tests. R1-R5 are generic constraints on source grounding, numeric status,
semantic scope, role-specific minimal questions, and Notify semantics. None
contains a development case answer or performs deterministic semantic repair.
The prompt retains one semantic model output followed by deterministic
validation/projection. Existing JSON syntax-repair transport behavior is
unchanged. Historical v4 predictions and scores remain historical evidence,
not a post-patch measurement.

After the user **explicitly confirms model quota has reset**, use the new
semantic-hardening commit as baseline and execute exactly one exploratory
development pass. These commands are prepared, **not executed by this patch**
(run from repository root):

```powershell
git rev-parse HEAD
python research/stage2a/verify_freeze.py research/stage2a/freeze/stage2a-v1.manifest.json
python -m pytest research/stage2b/ -q
if ((Test-Path runs/stage2b/dev10-v5-dry.jsonl) -or (Test-Path runs/stage2b/dev10-v5-live.jsonl) -or (Test-Path runs/stage2b/dev10-v5-score.json)) { throw 'v5 output exists; do not overwrite' }
python research/stage2b/run_shadow.py --dry-run --split development --output runs/stage2b/dev10-v5-dry.jsonl
python research/stage2b/run_shadow.py --live --split development --model nvidia/nemotron-3-ultra-550b-a55b:free --output runs/stage2b/dev10-v5-live.jsonl
python -c "import json; from pathlib import Path; from research.stage2b.scoring import FrozenCandidateAdapter, score_predictions; p=Path('runs/stage2b/dev10-v5-live.jsonl'); rows=[json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]; records={row['case_id']:row for row in rows}; assert len(rows)==len(records)==10; predictions={case_id:row['prediction'] for case_id,row in records.items() if row.get('prediction') is not None}; result=score_predictions(predictions, FrozenCandidateAdapter().load(split='development'), run_records=records); Path('runs/stage2b/dev10-v5-score.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')"
```

Do not overwrite v1-v4, rerun a bad case, call validation, or claim causal
improvement from one stochastic pass. Score the new raw records through
`FrozenCandidateAdapter().load(split="development")` and
`score_predictions(..., run_records=...)`, writing only
`runs/stage2b/dev10-v5-score.json`; report core output/validity, full validity,
projection completeness, critical-claim precision/recall, provenance
completeness, resolution exact match, conflict/clarification metrics, unsafe
freeze/acceptance/assumption, and transport/model failure-phase counts. Wording:
"Observed result on one additional exploratory stochastic development pass."
If semantic quality remains weak with healthy structural/projector results,
classify the limit as model semantic extraction quality, not another automatic
harness patch. Public validation and Stage 2C remain outside this task.
