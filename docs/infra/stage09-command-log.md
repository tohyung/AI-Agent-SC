# Stage 0.9 command log

Date: 2026-09-29. Repository: `D:\code\marlowe_ai_agent`; SMT commands ran
through WSL2 against `/mnt/d/code/marlowe_ai_agent`.

## Baseline

```text
$ wsl bash -lc "cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/build.sh"
ghc: 9.6.7
cabal: 3.10.3.0
z3: Z3 version 4.13.3 - 64 bit
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
Up to date

$ wsl bash -lc "cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/run_tests.sh"
Ran 12 tests
OK

$ wsl bash -lc "cd /mnt/d/code/marlowe_ai_agent/marlowe_ai_agent && pytest -q tests"
bash: line 1: pytest: command not found

$ python -m pytest --collect-only -q tests
125 tests collected

$ python -m pytest -q tests
125 passed in 1.39s
```

WSL không có pytest; mốc test agent vì vậy được chạy bằng Python Windows đang
có dependency của project. SMT vẫn chạy trong môi trường WSL đóng gói.

## Policy và renderer

```text
$ python -m pytest -q tests/test_node3_policy.py tests/test_node3_not_wired.py
6 passed
```

Hai lỗi hạ tầng test renderer đầu tiên và cách sửa:

```text
OSError: [WinError 6] The handle is invalid

subprocess.CalledProcessError: Command '['wsl', 'wslpath', '-a',
'D:\\code\\marlowe_ai_agent']' returned non-zero exit status 1.
```

Test được đổi sang `stdin=DEVNULL` cho lời gọi phụ và ánh xạ đường dẫn Windows
sang `/mnt/<drive>/...` tất định. Khi renderer bắt đầu đọc field thật, dữ liệu
test policy cũ còn thiếu field và phát hiện thêm `KeyError: 'account'`; fixture
policy được sửa thành đúng structured fields của driver.

```text
$ python -m pytest -q tests/test_node3_policy.py tests/test_node3_not_wired.py tests/test_node3_renderer.py
13 passed in 16.84s
```

## Toàn văn ví dụ decision

Lệnh dựng trực tiếp `Node3Result`; lần đầu console CP1252 in được dòng `pass`
rồi dừng với `UnicodeEncodeError`. Chạy lại với `PYTHONIOENCODING=utf-8` cho kết
quả đầy đủ:

```json
{"example":"pass","decision":"pass","passed":true,"errors":[],"warnings":[],"findings":[]}
{"example":"fail_lint","decision":"fail","passed":false,"errors":["lint lỗi"],"warnings":[],"findings":["lint lỗi"]}
{"example":"fail_counterexample","decision":"fail","passed":false,"errors":["Tài khoản Alice cố trả 20 cho bên Bob nhưng chỉ trả được 10."],"warnings":[],"findings":["Tài khoản Alice cố trả 20 cho bên Bob nhưng chỉ trả được 10."]}
{"example":"inconclusive_indeterminate","decision":"inconclusive","passed":false,"errors":[],"warnings":["SMT chưa kết luận: semantic_status=indeterminate."],"findings":["SMT chưa kết luận: semantic_status=indeterminate."]}
{"example":"inconclusive_timeout","decision":"inconclusive","passed":false,"errors":[],"warnings":["SMT chưa kết luận: semantic_status=timeout."],"findings":["SMT chưa kết luận: semantic_status=timeout."]}
{"example":"inconclusive_valid_notes","decision":"inconclusive","passed":false,"errors":[],"warnings":["Còn MerkleizedCase chưa phân tích."],"findings":["Còn MerkleizedCase chưa phân tích."]}
```

## Offline replay — toàn bộ output

```json
{"case_id":"en-escrow_2party-L1-010","ground_truth":true,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_correct"}
{"case_id":"en-loan-L4-007","ground_truth":true,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_correct"}
{"case_id":"vi-cancellation_fee-L4-001","ground_truth":null,"old_pass":null,"new_decision":"inconclusive","semantic_status":"unavailable","analysis_notes":["Audit record không có contract để replay."],"disagreement_type":"ground_truth_unavailable"}
{"case_id":"vi-cancellation_fee-L4-001","ground_truth":null,"old_pass":null,"new_decision":"inconclusive","semantic_status":"unavailable","analysis_notes":["Audit record không có contract để replay."],"disagreement_type":"ground_truth_unavailable"}
{"case_id":"vi-crowdfunding-L4-004","ground_truth":true,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_correct"}
{"case_id":"vi-escrow_3party-L4-006","ground_truth":true,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_correct"}
{"case_id":"vi-milestone-L4-003","ground_truth":false,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_wrong"}
{"case_id":"vi-rental_deposit-L3-003","ground_truth":false,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_wrong"}
{"case_id":"vi-swap-L3-010","ground_truth":true,"old_pass":true,"new_decision":"pass","semantic_status":"valid","analysis_notes":[],"disagreement_type":"both_correct"}
{"case_id":"vi-swap-L3-010","ground_truth":null,"old_pass":null,"new_decision":"inconclusive","semantic_status":"unavailable","analysis_notes":["Audit record không có contract để replay."],"disagreement_type":"ground_truth_unavailable"}
{"cross":{"both_correct":5,"both_wrong":2,"new_only_pass":0,"old_only_pass":0},"ground_truth_unavailable":["vi-cancellation_fee-L4-001-full.json","vi-cancellation_fee-L4-001-retry-full.json","vi-swap-L3-010-retry-full.json"],"inconclusive":["vi-cancellation_fee-L4-001-full.json","vi-cancellation_fee-L4-001-retry-full.json","vi-swap-L3-010-retry-full.json"],"logic_graph":{"false_accept":2,"false_reject":0,"true_accept":5,"true_reject":0},"node3_policy":{"false_accept":2,"false_reject":0,"true_accept":5,"true_reject":0}}
```

Hai dòng `both_wrong` ở trên là toàn bộ case bất đồng với ground truth. Không có
case mà hai policy bất đồng với nhau (`old_only_pass=0`, `new_only_pass=0`).

## Trace compatibility và final regression

```text
$ python -m pytest -q tests/test_node3_trace_compat.py
1 passed

$ python -m pytest --collect-only -q tests
139 tests collected

$ python -m pytest -q tests
139 passed in 20.46s

$ wsl bash -lc "cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/run_tests.sh"
Ran 12 tests in 30.108s
OK

$ wsl bash -lc "cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/verify_upstream.sh"
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
```

No LLM/API command and no `cardano-node` command was run.

## Correction (Stage 0.9b)

Independent acceptance on a host without `wsl.exe` found
`FileNotFoundError: 'wsl'` in seven renderer tests. The test helper wrapped an
already available `bash` invocation in `wsl`, which only works on Windows with
WSL configured. The helper now invokes `bash -lc` directly; path conversion
retains the same behavior. Commands and full regression output are recorded in
[stage09b-command-log.md](stage09b-command-log.md).

## Correction — current evaluator ground truth replay

Stage 0.9 originally treated persisted `record["evaluation"]["strict_correct"]`
as current ground truth. Rental deposit and milestone audit records were created
before the choice-name fallback evaluator patch, so their persisted `false`
labels and `input_rejected` scenario results were stale. The correction keeps
those labels for drift telemetry but re-evaluates each saved contract with the
current dataset and evaluator. Base commit before this patch: `c9954f2`.

The first attempt from Windows Python could not access the Linux SMT driver
and stopped at a CP1252 console encoding error; it did not rewrite the CSV.
The successful replay used the already-built driver inside WSL:

```text
PS D:\code\marlowe_ai_agent> bash -lc "cd /mnt/d/code/marlowe_ai_agent/marlowe_ai_agent && PYTHONIOENCODING=utf-8 python3 -m bench.node3_replay"
{"cross":{"both_correct":7,"both_wrong":0,"new_only_pass":0,"old_only_pass":0},"dataset_path":"/mnt/d/code/marlowe_ai_agent/marlowe_ai_agent/bench/dataset/cases.jsonl","dataset_sha256":"e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a","ground_truth_drift":[{"audit_file":"vi-milestone-L4-003-full.json","current":true,"persisted":false},{"audit_file":"vi-rental_deposit-L3-003-full.json","current":true,"persisted":false}],"ground_truth_drift_count":2,"ground_truth_unavailable":["vi-cancellation_fee-L4-001-full.json","vi-cancellation_fee-L4-001-retry-full.json","vi-swap-L3-010-retry-full.json"],"inconclusive":["vi-cancellation_fee-L4-001-full.json","vi-cancellation_fee-L4-001-retry-full.json","vi-swap-L3-010-retry-full.json"],"logic_graph":{"false_accept":0,"false_reject":0,"true_accept":7,"true_reject":0},"node3_policy":{"false_accept":0,"false_reject":0,"true_accept":7,"true_reject":0}}
```

Both changed records now have current scenario accuracy 1.0 and
`choice_name_fallback_count=2`; their saved contracts were not changed. No
LLM/API or agent benchmark was run.
