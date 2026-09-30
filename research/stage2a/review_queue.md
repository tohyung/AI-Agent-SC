# Stage 2A candidate review queue

All annotations below are drafts. A human must approve, edit, or reject each case.

## choice-d1 (development; choice_based_release)

- Requirement v1: Alice nạp 12 ADA vào tài khoản Alice. Trước mốc POSIX 4000 ms, Bob chọn approve để Bob nhận 12 ADA hoặc reject để Alice được hoàn 12 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; choice_owner=Bob [explicit; scope=decision-1]; release_recipient=Bob [explicit; scope=decision-1:approve]; refund_recipient=Alice [explicit; scope=decision-1:reject]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "approve", "decision_id": "decision-1", "scope_id": "decision-1:approve", "scope_type": "branch"}, {"branch_id": "reject", "decision_id": "decision-1", "scope_id": "decision-1:reject", "scope_type": "branch"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: transaction_submitter = Bob
- Expected behavior: {"accepted_traces": ["Bob Choice approve before 4000 -> Bob receives 12 ADA", "Bob Choice reject before 4000 -> Alice receives 12 ADA"], "rejected_traces": ["Choice with Alice as owner matches Bob's Choice Case"], "terminal_outcomes": ["approve releases to Bob", "reject refunds Alice"]}
- Mutation: null
- Annotation notes: Human review: no-choice timeout outcome is not specified.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## choice-d1-m-owner (development; choice_based_release)

- Requirement v1: Alice nạp 12 ADA vào tài khoản Alice. Trước mốc POSIX 4000 ms, Bob chọn approve để Bob nhận 12 ADA hoặc reject để Alice được hoàn 12 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from choice-d1): depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; choice_owner=Bob [explicit; scope=decision-1]; release_recipient=Bob [explicit; scope=decision-1:approve]; refund_recipient=Alice [explicit; scope=decision-1:reject]
- Behavior scopes (inherited from choice-d1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "approve", "decision_id": "decision-1", "scope_id": "decision-1:approve", "scope_type": "branch"}, {"branch_id": "reject", "decision_id": "decision-1", "scope_id": "decision-1:reject", "scope_type": "branch"}]
- Inherits canonical interpretation from: `choice-d1`
- Assumptions/derivations (inherited from choice-d1): none proposed
- Required clarifications: none
- Forbidden assumptions: choice_owner = Alice
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["candidate accepts ChoiceId owned by Alice for the approve branch"], "terminal_outcomes": ["mutant changes authorization from Bob to Alice"]}
- Mutation: {"expected_semantic_difference": "ChoiceId owner is Alice rather than Bob", "mutation_type": "wrong_choice_owner", "parent_case_id": "choice-d1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## choice-d2-correction (development; choice_based_release)

- Requirement v1: Bob quyết định approve để trả 2 ADA cho Linh.
- Requirement v2: Tôi sửa lại: Alice mới là người quyết định approve; Linh vẫn nhận 2 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims: choice_owner=Bob [superseded; scope=decision-1]; choice_owner=Alice [user_confirmed; scope=decision-1]; payment_recipient=Linh [explicit; scope=decision-1:approve]
- Behavior scopes: [{"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "approve", "decision_id": "decision-1", "scope_id": "decision-1:approve", "scope_type": "branch"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: Bob remains current choice owner
- Expected behavior: {"accepted_traces": ["ChoiceId owned by Alice approves payment to Linh"], "rejected_traces": ["ChoiceId owned by Bob is treated as current authorization"], "terminal_outcomes": ["Linh receives 2 ADA when current owner Alice approves"]}
- Mutation: null
- Annotation notes: Human review must confirm whether the missing payment source requires clarification.; Human review: payment source/account and Choice timeout are unspecified.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## conditional-d1 (development; conditional_payment)

- Requirement v1: Alice nạp 4 ADA vào tài khoản Alice. Nếu điều kiện Notify hoàn thành trước mốc POSIX 9000 ms, Bob nhận 4 ADA; nếu hết hạn thì Alice lấy lại 4 ADA qua một giao dịch.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Alice [explicit; scope=deposit-1]; payment_recipient=Bob [explicit; scope=notify-1:success]; refund_recipient=Alice [explicit; scope=notify-1:timeout]; timeout_ms=9000 [explicit; scope=notify-1]; asset=ADA [explicit; scope=global]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "notify-1", "scope_type": "transition", "transition_kind": "notify"}, {"branch_id": "success", "decision_id": "notify-1", "scope_id": "notify-1:success", "scope_type": "branch"}, {"deadline_claim_id": "c4", "decision_id": "notify-1", "scope_id": "notify-1:timeout", "scope_type": "timeout", "timeout_id": "notify-deadline-1"}, {"scope_id": "global", "scope_type": "global"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: Notify has an intrinsic choice_owner
- Expected behavior: {"accepted_traces": ["Notify true before 9000 -> Bob receives 4 ADA", "post-9000 empty transaction -> Alice refund"], "rejected_traces": ["Notify false advances the conditional payment Case"], "terminal_outcomes": ["Bob payment or Alice refund"]}
- Mutation: null
- Annotation notes: Human review: the Marlowe Observation proving completion is unspecified.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## conditional-d1-m-token (development; conditional_payment)

- Requirement v1: Alice nạp 4 ADA vào tài khoản Alice. Nếu điều kiện Notify hoàn thành trước mốc POSIX 9000 ms, Bob nhận 4 ADA; nếu hết hạn thì Alice lấy lại 4 ADA qua một giao dịch.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from conditional-d1): depositing_party=Alice [explicit; scope=deposit-1]; payment_recipient=Bob [explicit; scope=notify-1:success]; refund_recipient=Alice [explicit; scope=notify-1:timeout]; timeout_ms=9000 [explicit; scope=notify-1]; asset=ADA [explicit; scope=global]
- Behavior scopes (inherited from conditional-d1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "notify-1", "scope_type": "transition", "transition_kind": "notify"}, {"branch_id": "success", "decision_id": "notify-1", "scope_id": "notify-1:success", "scope_type": "branch"}, {"deadline_claim_id": "c4", "decision_id": "notify-1", "scope_id": "notify-1:timeout", "scope_type": "timeout", "timeout_id": "notify-deadline-1"}, {"scope_id": "global", "scope_type": "global"}]
- Inherits canonical interpretation from: `conditional-d1`
- Assumptions/derivations (inherited from conditional-d1): none proposed
- Required clarifications: none
- Forbidden assumptions: asset = custom token instead of ADA
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["candidate transfers a non-ADA token on Notify branch"], "terminal_outcomes": ["mutant violates asset identity"]}
- Mutation: {"expected_semantic_difference": "Pay token is a custom token rather than ADA", "mutation_type": "wrong_token", "parent_case_id": "conditional-d1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## double-d1 (development; two_deadline_escrow)

- Requirement v1: Alice nạp 7 ADA vào tài khoản Alice trước mốc POSIX 7000 ms. Nếu đã nạp, Bob chọn approve trước mốc POSIX 8000 ms để nhận 7 ADA; nếu Bob không chọn, giao dịch sau hạn hoàn tiền cho Alice.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Alice [explicit; scope=deposit-1]; choice_owner=Bob [explicit; scope=decision-1]; deposit_deadline_ms=7000 [explicit; scope=deposit-1]; choice_deadline_ms=8000 [explicit; scope=decision-1]; refund_recipient=Alice [explicit; scope=decision-1:timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"deadline_claim_id": "c4", "decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: decision deadline precedes deposit deadline
- Expected behavior: {"accepted_traces": ["deposit before 7000; approve before 8000 -> Bob receives 7 ADA", "deposit before 7000; no choice; post-8000 transaction -> Alice refund"], "rejected_traces": ["deposit after 7000 takes the deposit Case", "approval after 8000 takes the approve Case"], "terminal_outcomes": ["Bob release or Alice refund"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## double-d1-m-deadline (development; two_deadline_escrow)

- Requirement v1: Alice nạp 7 ADA vào tài khoản Alice trước mốc POSIX 7000 ms. Nếu đã nạp, Bob chọn approve trước mốc POSIX 8000 ms để nhận 7 ADA; nếu Bob không chọn, giao dịch sau hạn hoàn tiền cho Alice.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from double-d1): depositing_party=Alice [explicit; scope=deposit-1]; choice_owner=Bob [explicit; scope=decision-1]; deposit_deadline_ms=7000 [explicit; scope=deposit-1]; choice_deadline_ms=8000 [explicit; scope=decision-1]; refund_recipient=Alice [explicit; scope=decision-1:timeout]
- Behavior scopes (inherited from double-d1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"deadline_claim_id": "c4", "decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Inherits canonical interpretation from: `double-d1`
- Assumptions/derivations (inherited from double-d1): none proposed
- Required clarifications: none
- Forbidden assumptions: deposit deadline = 8000 ms
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["candidate swaps deposit and choice deadlines"], "terminal_outcomes": ["mutant changes allowed time windows"]}
- Mutation: {"expected_semantic_difference": "Deposit waits until 8000 while choice expires at 7000", "mutation_type": "swapped_deadline", "parent_case_id": "double-d1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## double-d2-conflict (development; two_deadline_escrow)

- Requirement v1: Alice phải nạp trước mốc POSIX 24000 ms; cùng lúc hợp đồng quy định hạn nạp duy nhất là POSIX 25000 ms.
- Proposed resolution: `conflict_requires_resolution`
- Critical claims: deposit_deadline_ms=24000 [conflicted; scope=deposit-1]; deposit_deadline_ms=25000 [conflicted; scope=deposit-1]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}]
- Assumptions/derivations: none proposed
- Required clarifications: Hạn nạp duy nhất là 24000 hay 25000 ms?
- Forbidden assumptions: choose the earlier deadline without user input
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["No accepted deadline behavior until contradiction is resolved"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## escrow-d1 (development; single_deadline_escrow)

- Requirement v1: Alice đặt cọc 5 ADA vào tài khoản Alice. Bob có thể approve trước mốc POSIX 6000 ms để nhận 5 ADA; sau hạn một giao dịch hợp lệ đóng hợp đồng và hoàn tiền cho Alice.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; choice_owner=Bob [explicit; scope=decision-1]; release_recipient=Bob [explicit; scope=decision-1:approve]; refund_recipient=Alice [explicit; scope=decision-1:timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "approve", "decision_id": "decision-1", "scope_id": "decision-1:approve", "scope_type": "branch"}, {"decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "approval-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: timeout triggers autonomous refund
- Expected behavior: {"accepted_traces": ["Bob approve with interval end < 6000 -> Bob receives 5 ADA", "empty transaction with interval start >= 6000 -> Alice refund"], "rejected_traces": ["approval in interval straddling 6000 is assumed valid"], "terminal_outcomes": ["release to Bob or refund to Alice"]}
- Mutation: null
- Annotation notes: Human review: deposit deadline is not explicit; approval deadline does not establish it.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## escrow-d1-m-party (development; single_deadline_escrow)

- Requirement v1: Alice đặt cọc 5 ADA vào tài khoản Alice. Bob có thể approve trước mốc POSIX 6000 ms để nhận 5 ADA; sau hạn một giao dịch hợp lệ đóng hợp đồng và hoàn tiền cho Alice.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from escrow-d1): depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; choice_owner=Bob [explicit; scope=decision-1]; release_recipient=Bob [explicit; scope=decision-1:approve]; refund_recipient=Alice [explicit; scope=decision-1:timeout]
- Behavior scopes (inherited from escrow-d1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "approve", "decision_id": "decision-1", "scope_id": "decision-1:approve", "scope_type": "branch"}, {"decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "approval-deadline-1"}]
- Inherits canonical interpretation from: `escrow-d1`
- Assumptions/derivations (inherited from escrow-d1): none proposed
- Required clarifications: none
- Forbidden assumptions: depositing_party = Bob
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["candidate Deposit Case allows Bob to deposit where Alice is specified"], "terminal_outcomes": ["mutant changes payer obligation"]}
- Mutation: {"expected_semantic_difference": "Deposit party is Bob instead of Alice", "mutation_type": "wrong_depositing_party", "parent_case_id": "escrow-d1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## escrow-d2-clarify (development; single_deadline_escrow)

- Requirement v1: Lan ký quỹ 15 ADA. Trước mốc POSIX 23000 ms, một trong Lan hoặc Minh được phép chọn release để Minh nhận tiền; sau hạn Lan được hoàn.
- Proposed resolution: `clarification_required`
- Critical claims: choice_owner=None [unresolved; scope=decision-1]; release_recipient=Minh [explicit; scope=decision-1:release]
- Behavior scopes: [{"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "release", "decision_id": "decision-1", "scope_id": "decision-1:release", "scope_type": "branch"}]
- Assumptions/derivations: none proposed
- Required clarifications: Ai chính xác là chủ Choice release: Lan hay Minh?
- Forbidden assumptions: the depositor necessarily controls release
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["Release authorization unresolved until owner is specified"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## pay-d1 (development; simple_timed_payment)

- Requirement v1: Alice nạp 10 ADA vào tài khoản Alice trước mốc POSIX 1000 ms; khi nạp hợp lệ, Bob nhận 10 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; amount_lovelace=10000000 [derived; scope=deposit-1]; payment_recipient=Bob [explicit; scope=payout-1]; deposit_deadline_ms=1000 [explicit; scope=deposit-1]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"}]
- Assumptions/derivations: amount_lovelace=10000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: transaction_submitter = Alice
- Expected behavior: {"accepted_traces": ["interval end < 1000; Alice deposits 10000000 lovelace; Bob receives 10000000 lovelace"], "rejected_traces": ["deposit attempt with interval start >= 1000 is not the deposit Case"], "terminal_outcomes": ["Bob receives 10 ADA after valid deposit"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## pay-d1-m-recipient (development; simple_timed_payment)

- Requirement v1: Alice nạp 10 ADA vào tài khoản Alice trước mốc POSIX 1000 ms; khi nạp hợp lệ, Bob nhận 10 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from pay-d1): depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; amount_lovelace=10000000 [derived; scope=deposit-1]; payment_recipient=Bob [explicit; scope=payout-1]; deposit_deadline_ms=1000 [explicit; scope=deposit-1]
- Behavior scopes (inherited from pay-d1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"}]
- Inherits canonical interpretation from: `pay-d1`
- Assumptions/derivations (inherited from pay-d1): amount_lovelace=10000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: payment_recipient = Alice
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["candidate pays Alice instead of Bob after valid deposit"], "terminal_outcomes": ["mutant must not satisfy Bob-receives-10-ADA obligation"]}
- Mutation: {"expected_semantic_difference": "Payee changes Bob to Alice while requirement and deposit stay fixed", "mutation_type": "wrong_payment_recipient", "parent_case_id": "pay-d1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## pay-d2-clarify (development; simple_timed_payment)

- Requirement v1: Alice gửi 3 ADA trước mốc POSIX 1100 ms rồi trả cho người nhận.
- Proposed resolution: `clarification_required`
- Critical claims: amount_lovelace=3000000 [derived; scope=deposit-1]; payment_recipient=None [unresolved; scope=payout-1]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"}]
- Assumptions/derivations: amount_lovelace=3000000 [scope=deposit-1]
- Required clarifications: Ai là người nhận 3 ADA?
- Forbidden assumptions: Alice is the payment recipient
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["No accepted payout interpretation until recipient is confirmed"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## refund-d1 (development; deposit_refund)

- Requirement v1: Alice nạp 8 ADA vào tài khoản Alice trước mốc POSIX 2000 ms. Nếu chưa giải ngân đến mốc POSIX 3000 ms, một giao dịch hợp lệ sau hạn cho phép hoàn 8 ADA cho Alice.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; amount_lovelace=8000000 [derived; scope=deposit-1]; refund_recipient=Alice [explicit; scope=deposit-1:refund-timeout]; refund_deadline_ms=3000 [explicit; scope=deposit-1:refund-timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"deadline_claim_id": "c5", "decision_id": "deposit-1", "scope_id": "deposit-1:refund-timeout", "scope_type": "timeout", "timeout_id": "refund-deadline-1"}]
- Assumptions/derivations: amount_lovelace=8000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: refund happens without a transaction
- Expected behavior: {"accepted_traces": ["deposit before 2000; later empty transaction with interval start >= 3000; Close refunds Alice"], "rejected_traces": ["refund before 3000"], "terminal_outcomes": ["Alice receives remaining 8 ADA on timeout path"]}
- Mutation: null
- Annotation notes: Human review: 'not yet disbursed' and the disbursement path need definition.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## refund-d1-m-missing (development; deposit_refund)

- Requirement v1: Alice nạp 8 ADA vào tài khoản Alice trước mốc POSIX 2000 ms. Nếu chưa giải ngân đến mốc POSIX 3000 ms, một giao dịch hợp lệ sau hạn cho phép hoàn 8 ADA cho Alice.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from refund-d1): depositing_party=Alice [explicit; scope=deposit-1]; destination_account_owner=Alice [explicit; scope=deposit-1]; amount_lovelace=8000000 [derived; scope=deposit-1]; refund_recipient=Alice [explicit; scope=deposit-1:refund-timeout]; refund_deadline_ms=3000 [explicit; scope=deposit-1:refund-timeout]
- Behavior scopes (inherited from refund-d1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"deadline_claim_id": "c5", "decision_id": "deposit-1", "scope_id": "deposit-1:refund-timeout", "scope_type": "timeout", "timeout_id": "refund-deadline-1"}]
- Inherits canonical interpretation from: `refund-d1`
- Assumptions/derivations (inherited from refund-d1): amount_lovelace=8000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: timeout path may retain Alice's funds
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["after timeout, mutant leaves Alice's 8 ADA unavailable"], "terminal_outcomes": ["mutant violates refund obligation"]}
- Mutation: {"expected_semantic_difference": "Timeout continuation does not provide Alice's stated refund", "mutation_type": "missing_refund", "parent_case_id": "refund-d1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## choice-e1 (validation; choice_based_release)

- Requirement v1: An ký quỹ 9 ADA trong tài khoản An. Vy là chủ Choice accept hoặc reject trước mốc POSIX 15000 ms; accept trả 9 ADA cho Vy, reject hoàn 9 ADA cho An. Nếu không chọn trước hạn, giao dịch sau hạn hoàn 9 ADA cho An.
- Proposed resolution: `accepted_interpretation`
- Critical claims: destination_account_owner=An [explicit; scope=deposit-1]; choice_owner=Vy [explicit; scope=decision-1]; release_recipient=Vy [explicit; scope=decision-1:accept]; refund_recipient=An [explicit; scope=decision-1:reject]; choice_deadline_ms=15000 [explicit; scope=decision-1]; refund_recipient=An [explicit; scope=decision-1:timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "accept", "decision_id": "decision-1", "scope_id": "decision-1:accept", "scope_type": "branch"}, {"branch_id": "reject", "decision_id": "decision-1", "scope_id": "decision-1:reject", "scope_type": "branch"}, {"deadline_claim_id": "c5", "decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: transaction_submitter = Vy
- Expected behavior: {"accepted_traces": ["Vy Choice accept before 15000 -> Vy receives 9 ADA", "Vy Choice reject before 15000 -> An receives 9 ADA"], "rejected_traces": ["ChoiceId owned by An can approve"], "terminal_outcomes": ["release to Vy or refund to An"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## choice-e1-m-unauthorized (validation; choice_based_release)

- Requirement v1: An ký quỹ 9 ADA trong tài khoản An. Vy là chủ Choice accept hoặc reject trước mốc POSIX 15000 ms; accept trả 9 ADA cho Vy, reject hoàn 9 ADA cho An. Nếu không chọn trước hạn, giao dịch sau hạn hoàn 9 ADA cho An.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from choice-e1): destination_account_owner=An [explicit; scope=deposit-1]; choice_owner=Vy [explicit; scope=decision-1]; release_recipient=Vy [explicit; scope=decision-1:accept]; refund_recipient=An [explicit; scope=decision-1:reject]; choice_deadline_ms=15000 [explicit; scope=decision-1]; refund_recipient=An [explicit; scope=decision-1:timeout]
- Behavior scopes (inherited from choice-e1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "accept", "decision_id": "decision-1", "scope_id": "decision-1:accept", "scope_type": "branch"}, {"branch_id": "reject", "decision_id": "decision-1", "scope_id": "decision-1:reject", "scope_type": "branch"}, {"deadline_claim_id": "c5", "decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Inherits canonical interpretation from: `choice-e1`
- Assumptions/derivations (inherited from choice-e1): none proposed
- Required clarifications: none
- Forbidden assumptions: An controls the ChoiceId
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["mutant accepts ChoiceId owned by An as accept"], "terminal_outcomes": ["mutant permits unauthorized branch choice"]}
- Mutation: {"expected_semantic_difference": "An-controlled choice can release funds contrary to Vy ownership", "mutation_type": "unauthorized_choice", "parent_case_id": "choice-e1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## choice-e2-clarify (validation; choice_based_release)

- Requirement v1: Mai nạp 16 ADA. Một bên sẽ chọn approve trước mốc POSIX 26000 ms để Nam nhận tiền; nếu không thì Mai nhận lại.
- Proposed resolution: `clarification_required`
- Critical claims: choice_owner=None [unresolved; scope=decision-1]; release_recipient=Nam [explicit; scope=decision-1:approve]
- Behavior scopes: [{"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "approve", "decision_id": "decision-1", "scope_id": "decision-1:approve", "scope_type": "branch"}]
- Assumptions/derivations: none proposed
- Required clarifications: Bên nào sở hữu Choice approve?
- Forbidden assumptions: Nam automatically owns the Choice
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["Choice authorization must be resolved first"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## conditional-e1 (validation; conditional_payment)

- Requirement v1: Tú nạp 14 ADA vào tài khoản Tú. Nếu Notify về giao hàng đúng trước mốc POSIX 21000 ms, Hòa nhận một lần 14 ADA; nếu không, giao dịch sau hạn hoàn 14 ADA cho Tú.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Tú [explicit; scope=deposit-1]; destination_account_owner=Tú [explicit; scope=deposit-1]; payment_recipient=Hòa [explicit; scope=notify-1:success]; refund_recipient=Tú [explicit; scope=notify-1:timeout]; timeout_ms=21000 [explicit; scope=notify-1]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "notify-1", "scope_type": "transition", "transition_kind": "notify"}, {"branch_id": "success", "decision_id": "notify-1", "scope_id": "notify-1:success", "scope_type": "branch"}, {"deadline_claim_id": "c5", "decision_id": "notify-1", "scope_id": "notify-1:timeout", "scope_type": "timeout", "timeout_id": "notify-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: second payment to Hòa is allowed
- Expected behavior: {"accepted_traces": ["Notify true before 21000 -> Hòa receives exactly one 14 ADA payment"], "rejected_traces": ["Hòa receives 28 ADA from two payments", "Notify false causes release"], "terminal_outcomes": ["one payment to Hòa or refund Tú"]}
- Mutation: null
- Annotation notes: Human review: the Marlowe Observation proving delivery is unspecified.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## conditional-e1-m-double (validation; conditional_payment)

- Requirement v1: Tú nạp 14 ADA vào tài khoản Tú. Nếu Notify về giao hàng đúng trước mốc POSIX 21000 ms, Hòa nhận một lần 14 ADA; nếu không, giao dịch sau hạn hoàn 14 ADA cho Tú.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from conditional-e1): depositing_party=Tú [explicit; scope=deposit-1]; destination_account_owner=Tú [explicit; scope=deposit-1]; payment_recipient=Hòa [explicit; scope=notify-1:success]; refund_recipient=Tú [explicit; scope=notify-1:timeout]; timeout_ms=21000 [explicit; scope=notify-1]
- Behavior scopes (inherited from conditional-e1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "notify-1", "scope_type": "transition", "transition_kind": "notify"}, {"branch_id": "success", "decision_id": "notify-1", "scope_id": "notify-1:success", "scope_type": "branch"}, {"deadline_claim_id": "c5", "decision_id": "notify-1", "scope_id": "notify-1:timeout", "scope_type": "timeout", "timeout_id": "notify-deadline-1"}]
- Inherits canonical interpretation from: `conditional-e1`
- Assumptions/derivations (inherited from conditional-e1): none proposed
- Required clarifications: none
- Forbidden assumptions: two payouts to Hòa
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["mutant has two 14 ADA Pay constructors to Hòa on Notify path"], "terminal_outcomes": ["mutant double-payment violates once-only outcome"]}
- Mutation: {"expected_semantic_difference": "Notify path attempts two payments to Hòa instead of one", "mutation_type": "double_payment", "parent_case_id": "conditional-e1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## conditional-e2-conflict (validation; conditional_payment)

- Requirement v1: Nếu Notify giao hàng đúng, chỉ Bob nhận 17 ADA; cũng trong trường hợp Notify giao hàng đúng, chỉ Alice nhận cùng 17 ADA.
- Proposed resolution: `conflict_requires_resolution`
- Critical claims: notify_success_recipient=Bob [conflicted; scope=notify-1:success]; notify_success_recipient=Alice [conflicted; scope=notify-1:success]
- Behavior scopes: [{"scope_id": "notify-1", "scope_type": "transition", "transition_kind": "notify"}, {"branch_id": "success", "decision_id": "notify-1", "scope_id": "notify-1:success", "scope_type": "branch"}]
- Assumptions/derivations: none proposed
- Required clarifications: Khi Notify giao hàng đúng, ai là người nhận duy nhất: Bob hay Alice?
- Forbidden assumptions: pay both parties despite only-one language
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["No accepted success recipient until conflict is resolved"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## double-e1 (validation; two_deadline_escrow)

- Requirement v1: Nhi nạp 13 ADA vào tài khoản Nhi trước mốc POSIX 17000 ms. Sau khoản nạp, Quân chọn approve trước mốc POSIX 19000 ms để nhận đúng 13 ADA; quá hạn quyết định, giao dịch sau hạn hoàn cho Nhi.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Nhi [explicit; scope=deposit-1]; choice_owner=Quân [explicit; scope=decision-1]; amount_lovelace=13000000 [derived; scope=deposit-1]; deposit_deadline_ms=17000 [explicit; scope=deposit-1]; choice_deadline_ms=19000 [explicit; scope=decision-1]; refund_recipient=Nhi [explicit; scope=decision-1:timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"deadline_claim_id": "c5", "decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Assumptions/derivations: amount_lovelace=13000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: payment amount = 1300000 lovelace
- Expected behavior: {"accepted_traces": ["Nhi deposit before 17000; Quân approve before 19000 -> Quân receives 13 ADA", "post-19000 transaction after deposit -> Nhi refund"], "rejected_traces": ["approve after 19000"], "terminal_outcomes": ["Quân release or Nhi refund"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## double-e1-m-amount (validation; two_deadline_escrow)

- Requirement v1: Nhi nạp 13 ADA vào tài khoản Nhi trước mốc POSIX 17000 ms. Sau khoản nạp, Quân chọn approve trước mốc POSIX 19000 ms để nhận đúng 13 ADA; quá hạn quyết định, giao dịch sau hạn hoàn cho Nhi.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from double-e1): depositing_party=Nhi [explicit; scope=deposit-1]; choice_owner=Quân [explicit; scope=decision-1]; amount_lovelace=13000000 [derived; scope=deposit-1]; deposit_deadline_ms=17000 [explicit; scope=deposit-1]; choice_deadline_ms=19000 [explicit; scope=decision-1]; refund_recipient=Nhi [explicit; scope=decision-1:timeout]
- Behavior scopes (inherited from double-e1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"deadline_claim_id": "c5", "decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Inherits canonical interpretation from: `double-e1`
- Assumptions/derivations (inherited from double-e1): amount_lovelace=13000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: approve pays 12 ADA
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["mutant approve branch pays 12 ADA despite 13 ADA requirement"], "terminal_outcomes": ["mutant violates exact amount"]}
- Mutation: {"expected_semantic_difference": "Approve pays 12000000 instead of 13000000 lovelace", "mutation_type": "wrong_amount", "parent_case_id": "double-e1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## escrow-e1 (validation; single_deadline_escrow)

- Requirement v1: Lan nạp 11 ADA vào tài khoản Lan trước mốc POSIX 16000 ms. Minh được chọn release trước cùng mốc để nhận 11 ADA; nếu chưa release đến hạn, một giao dịch sau hạn hoàn 11 ADA cho Lan.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Lan [explicit; scope=deposit-1]; destination_account_owner=Lan [explicit; scope=deposit-1]; choice_owner=Minh [explicit; scope=decision-1]; release_recipient=Minh [explicit; scope=decision-1:release]; refund_recipient=Lan [explicit; scope=decision-1:timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "release", "decision_id": "decision-1", "scope_id": "decision-1:release", "scope_type": "branch"}, {"decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: timeout path releases to Minh
- Expected behavior: {"accepted_traces": ["Lan deposit then Minh release before 16000 -> Minh receives 11 ADA", "Lan deposit then post-16000 transaction -> Lan refund"], "rejected_traces": ["timeout path pays Minh"], "terminal_outcomes": ["release to Minh or refund to Lan"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## escrow-e1-m-timeout (validation; single_deadline_escrow)

- Requirement v1: Lan nạp 11 ADA vào tài khoản Lan trước mốc POSIX 16000 ms. Minh được chọn release trước cùng mốc để nhận 11 ADA; nếu chưa release đến hạn, một giao dịch sau hạn hoàn 11 ADA cho Lan.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from escrow-e1): depositing_party=Lan [explicit; scope=deposit-1]; destination_account_owner=Lan [explicit; scope=deposit-1]; choice_owner=Minh [explicit; scope=decision-1]; release_recipient=Minh [explicit; scope=decision-1:release]; refund_recipient=Lan [explicit; scope=decision-1:timeout]
- Behavior scopes (inherited from escrow-e1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "decision-1", "scope_type": "transition", "transition_kind": "choice"}, {"branch_id": "release", "decision_id": "decision-1", "scope_id": "decision-1:release", "scope_type": "branch"}, {"decision_id": "decision-1", "scope_id": "decision-1:timeout", "scope_type": "timeout", "timeout_id": "choice-deadline-1"}]
- Inherits canonical interpretation from: `escrow-e1`
- Assumptions/derivations (inherited from escrow-e1): none proposed
- Required clarifications: none
- Forbidden assumptions: timeout releases to Minh
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["mutant timeout continuation pays Minh instead of refunding Lan"], "terminal_outcomes": ["mutant reverses timeout outcome"]}
- Mutation: {"expected_semantic_difference": "Post-deadline path pays Minh, contradicting refund to Lan", "mutation_type": "reversed_timeout_branch", "parent_case_id": "escrow-e1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## escrow-e2-unsupported (validation; single_deadline_escrow)

- Requirement v1: Đúng mốc POSIX 22000 ms, hợp đồng phải tự động hoàn 3 ADA cho Lan dù không ai gửi giao dịch và không có dịch vụ ngoài chuỗi.
- Proposed resolution: `unsupported_for_current_study`
- Critical claims: timeout_ms=22000 [explicit; scope=auto-refund-timeout-1]; autonomous_execution=True [explicit; scope=auto-refund-timeout-1]
- Behavior scopes: [{"scope_id": "auto-refund-timeout-1", "scope_type": "timeout", "timeout_id": "auto-refund-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: none
- Forbidden assumptions: Marlowe executes without a transaction
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["Core V1 alone cannot realize autonomous wall-clock refund"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## pay-e1 (validation; simple_timed_payment)

- Requirement v1: Mai nạp 250 ADA vào tài khoản Mai trước mốc POSIX 12000 ms; sau khoản nạp hợp lệ, Nam nhận đúng 250 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Mai [explicit; scope=deposit-1]; destination_account_owner=Mai [explicit; scope=deposit-1]; amount_lovelace=250000000 [derived; scope=deposit-1]; payment_recipient=Nam [explicit; scope=payout-1]; deposit_deadline_ms=12000 [explicit; scope=deposit-1]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"}]
- Assumptions/derivations: amount_lovelace=250000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: 250 ADA = 250 lovelace
- Expected behavior: {"accepted_traces": ["Mai deposits 250000000 lovelace before 12000 -> Nam receives 250000000"], "rejected_traces": ["amount is scaled as 250 lovelace"], "terminal_outcomes": ["Nam receives exactly 250 ADA"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## pay-e1-m-unit (validation; simple_timed_payment)

- Requirement v1: Mai nạp 250 ADA vào tài khoản Mai trước mốc POSIX 12000 ms; sau khoản nạp hợp lệ, Nam nhận đúng 250 ADA.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from pay-e1): depositing_party=Mai [explicit; scope=deposit-1]; destination_account_owner=Mai [explicit; scope=deposit-1]; amount_lovelace=250000000 [derived; scope=deposit-1]; payment_recipient=Nam [explicit; scope=payout-1]; deposit_deadline_ms=12000 [explicit; scope=deposit-1]
- Behavior scopes (inherited from pay-e1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"}]
- Inherits canonical interpretation from: `pay-e1`
- Assumptions/derivations (inherited from pay-e1): amount_lovelace=250000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: 250 ADA = 250 lovelace
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["candidate accepts 250 lovelace and pays 250 lovelace"], "terminal_outcomes": ["mutant violates 250 ADA scale"]}
- Mutation: {"expected_semantic_difference": "On-chain quantity becomes 250 instead of 250000000 lovelace", "mutation_type": "wrong_unit_scaling", "parent_case_id": "pay-e1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## refund-e1 (validation; deposit_refund)

- Requirement v1: Hà nạp 6 ADA vào tài khoản Hà trước mốc POSIX 13000 ms. Nếu điều kiện hoàn tất không được Notify trước mốc POSIX 14000 ms, giao dịch sau hạn đóng hợp đồng và hoàn 6 ADA cho Hà.
- Proposed resolution: `accepted_interpretation`
- Critical claims: depositing_party=Hà [explicit; scope=deposit-1]; destination_account_owner=Hà [explicit; scope=deposit-1]; amount_lovelace=6000000 [derived; scope=deposit-1]; refund_recipient=Hà [explicit; scope=deposit-1:refund-timeout]; refund_deadline_ms=14000 [explicit; scope=deposit-1:refund-timeout]
- Behavior scopes: [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"deadline_claim_id": "c5", "decision_id": "deposit-1", "scope_id": "deposit-1:refund-timeout", "scope_type": "timeout", "timeout_id": "refund-deadline-1"}]
- Assumptions/derivations: amount_lovelace=6000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: Notify false is a completed condition
- Expected behavior: {"accepted_traces": ["Hà deposit before 13000; no completion Notify; post-14000 transaction refunds Hà"], "rejected_traces": ["timeout refund goes to a different account owner"], "terminal_outcomes": ["Hà receives 6 ADA on timeout"]}
- Mutation: null
- Annotation notes: Human review: continuation when completion Notify succeeds is unspecified.
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## refund-e1-m-account (validation; deposit_refund)

- Requirement v1: Hà nạp 6 ADA vào tài khoản Hà trước mốc POSIX 13000 ms. Nếu điều kiện hoàn tất không được Notify trước mốc POSIX 14000 ms, giao dịch sau hạn đóng hợp đồng và hoàn 6 ADA cho Hà.
- Proposed resolution: `accepted_interpretation`
- Critical claims (inherited from refund-e1): depositing_party=Hà [explicit; scope=deposit-1]; destination_account_owner=Hà [explicit; scope=deposit-1]; amount_lovelace=6000000 [derived; scope=deposit-1]; refund_recipient=Hà [explicit; scope=deposit-1:refund-timeout]; refund_deadline_ms=14000 [explicit; scope=deposit-1:refund-timeout]
- Behavior scopes (inherited from refund-e1): [{"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"}, {"deadline_claim_id": "c5", "decision_id": "deposit-1", "scope_id": "deposit-1:refund-timeout", "scope_type": "timeout", "timeout_id": "refund-deadline-1"}]
- Inherits canonical interpretation from: `refund-e1`
- Assumptions/derivations (inherited from refund-e1): amount_lovelace=6000000 [scope=deposit-1]
- Required clarifications: none
- Forbidden assumptions: destination_account_owner = Nam
- Expected behavior: {"accepted_traces": [], "rejected_traces": ["mutant deposits into Nam's account then Close refunds Nam"], "terminal_outcomes": ["mutant violates Hà refund ownership"]}
- Mutation: {"expected_semantic_difference": "Deposit is credited to Nam-owned account instead of Hà-owned account", "mutation_type": "wrong_account_owner", "parent_case_id": "refund-e1"}
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:

## refund-e2-conflict (validation; deposit_refund)

- Requirement v1: Nếu hết hạn, chỉ Alice được nhận lại 4 ADA; đồng thời chỉ Bob được nhận lại cùng 4 ADA.
- Proposed resolution: `conflict_requires_resolution`
- Critical claims: refund_recipient=Alice [conflicted; scope=refund-timeout-1]; refund_recipient=Bob [conflicted; scope=refund-timeout-1]
- Behavior scopes: [{"scope_id": "refund-timeout-1", "scope_type": "timeout", "timeout_id": "unspecified-refund-deadline-1"}]
- Assumptions/derivations: none proposed
- Required clarifications: Xác nhận người nhận hoàn tiền duy nhất: Alice hay Bob?
- Forbidden assumptions: prefer the first recipient automatically
- Expected behavior: {"accepted_traces": [], "rejected_traces": [], "terminal_outcomes": ["No single refund outcome accepted until contradiction is resolved"]}
- Mutation: null
- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer note:
