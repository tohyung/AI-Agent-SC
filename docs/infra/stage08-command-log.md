# Stage 0.8 command log

Date: 2026-09-29. Commands ran from `/mnt/d/code/marlowe_ai_agent` in WSL2.

## Baseline

```text
$ tools/marlowe_smt/build.sh
ghc: 9.6.7
cabal: 3.10.3.0
z3: Z3 version 4.13.3 - 64 bit
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
Up to date

$ tools/marlowe_smt/run_tests.sh
...
Ran 12 tests in 27.022s

OK
```

## Corpus and complete comparison

```text
$ python3 tools/marlowe_smt/compare/build_corpus.py
wrote 33 cases (2111064 bytes)

$ python3 tools/marlowe_smt/compare/run_comparison.py
progress 1/33
...
progress 33/33
```

The corpus contains 6 audit, 15 Stage 0.7b, and 12 isolated hand-written
contracts. It is 2,111,064 bytes (2.013 MiB), slightly above the prompt's 2 MiB
estimate because the mandatory Stage 0.7b JSON files alone occupy 2,090,876
bytes. No required source or error type was removed. `results.csv` contains 33
rows. The full run produced status values Valid, Counterexample, and Timeout;
F3-n128-k1 was the only Timeout.

`run_comparison.py` prints the complete diagnostic payload used for comparison:
all Logic Graph findings/errors/warnings/path count plus graph node/edge counts,
and the full SMT object including warning fields and counterexample trace. It
does not dump graph topology, which would turn one reproducible run into a
110-MB raw log; graph construction itself is not a compared finding.

## Full outputs — 12 isolated cases

Each line below is the complete emitted diagnostic for one case.

```json
{"name":"01-nonpositive-deposit","logic_graph":{"passed":false,"findings":["root.when[0].case.deposits: số tiền Deposit phải > 0."],"errors":["root.when[0].case.deposits: số tiền Deposit phải > 0."],"warnings":[],"paths_explored":2,"graph_nodes":3,"graph_edges":2},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[{"account":{"role_token":"Alice"},"amount":0,"party":{"role_token":"Alice"},"token":{"currency_symbol":"","token_name":""},"type":"Deposit"}],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"Alice"},"amount":0,"party":{"role_token":"Alice"},"type":"TransactionNonPositiveDeposit"}],"process_exit":0}}
{"name":"02-nonpositive-pay","logic_graph":{"passed":false,"findings":["root.pay: số tiền Pay phải > 0."],"errors":["root.pay: số tiền Pay phải > 0."],"warnings":[],"paths_explored":1,"graph_nodes":2,"graph_edges":1},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"Alice"},"amount":0,"payee":{"party":{"role_token":"Bob"}},"type":"TransactionNonPositivePay"}],"process_exit":0}}
{"name":"03-literal-partial-pay","logic_graph":{"passed":false,"findings":["root.when[0].then.pay: Pay 20 vượt số dư 10; sẽ chỉ trả một phần."],"errors":["root.when[0].then.pay: Pay 20 vượt số dư 10; sẽ chỉ trả một phần."],"warnings":[],"paths_explored":2,"graph_nodes":4,"graph_edges":3},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[{"account":{"role_token":"Alice"},"amount":10,"party":{"role_token":"Alice"},"token":{"currency_symbol":"","token_name":""},"type":"Deposit"}],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"Alice"},"expected":20,"paid":10,"payee":{"party":{"role_token":"Bob"}},"type":"TransactionPartialPay"}],"process_exit":0}}
{"name":"04-symbolic-partial-pay","logic_graph":{"passed":true,"findings":["root.when[0].then.timeout: timeout bên trong 1893456000000 <= timeout scope ngoài 1893456000000; chưa mô hình hóa riêng thời điểm vào nhánh Case và timeout continuation, không thể kết luận nhánh không thể thực thi.","root.when[0].then.timeout_continuation: Close còn dư 5; Marlowe sẽ hoàn về chủ account.","root: không thể kiểm tĩnh đầy đủ với giá trị không xác định."],"errors":[],"warnings":["root.when[0].then.timeout: timeout bên trong 1893456000000 <= timeout scope ngoài 1893456000000; chưa mô hình hóa riêng thời điểm vào nhánh Case và timeout continuation, không thể kết luận nhánh không thể thực thi.","root.when[0].then.timeout_continuation: Close còn dư 5; Marlowe sẽ hoàn về chủ account.","root: không thể kiểm tĩnh đầy đủ với giá trị không xác định."],"paths_explored":3,"graph_nodes":6,"graph_edges":5},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[{"account":{"role_token":"Alice"},"amount":5,"party":{"role_token":"Alice"},"token":{"currency_symbol":"","token_name":""},"type":"Deposit"}],"interval":{"from":"0","to":"0"}},{"inputs":[{"choice_id":{"choice_name":"amount","choice_owner":{"role_token":"Alice"}},"chosen":6,"type":"Choice"}],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"Alice"},"expected":6,"paid":5,"payee":{"party":{"role_token":"Bob"}},"type":"TransactionPartialPay"}],"process_exit":0}}
{"name":"05-let-shadowing","logic_graph":{"passed":true,"findings":["Logic graph pass."],"errors":[],"warnings":[],"paths_explored":1,"graph_nodes":3,"graph_edges":2},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"new_value":2,"old_value":1,"type":"TransactionShadowing","value_id":"x"}],"process_exit":0}}
{"name":"06-symbolic-assertion","logic_graph":{"passed":true,"findings":["Logic graph pass."],"errors":[],"warnings":[],"paths_explored":2,"graph_nodes":4,"graph_edges":3},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[{"choice_id":{"choice_name":"amount","choice_owner":{"role_token":"Alice"}},"chosen":0,"type":"Choice"}],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"type":"TransactionAssertionFailed"}],"process_exit":0}}
{"name":"07-duplicate-action","logic_graph":{"passed":false,"findings":["root.when[1].case: action trùng hệt case khác trong cùng When."],"errors":["root.when[1].case: action trùng hệt case khác trong cùng When."],"warnings":[],"paths_explored":3,"graph_nodes":4,"graph_edges":3},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"08-overlapping-choice-bounds","logic_graph":{"passed":false,"findings":["root.when[1].case.choose_between: các khoảng Choice cùng ID chồng lấn."],"errors":["root.when[1].case.choose_between: các khoảng Choice cùng ID chồng lấn."],"warnings":[],"paths_explored":3,"graph_nodes":4,"graph_edges":3},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"09-undefined-use-value","logic_graph":{"passed":false,"findings":["root.pay.use_value: biến 'missing' chưa được Let định nghĩa.","root: không thể kiểm tĩnh đầy đủ với giá trị không xác định."],"errors":["root.pay.use_value: biến 'missing' chưa được Let định nghĩa."],"warnings":["root: không thể kiểm tĩnh đầy đủ với giá trị không xác định."],"paths_explored":1,"graph_nodes":2,"graph_edges":1},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"Alice"},"amount":0,"payee":{"party":{"role_token":"Bob"}},"type":"TransactionNonPositivePay"}],"process_exit":0}}
{"name":"10-draft-mismatch","logic_graph":{"passed":false,"findings":["root.when[0].case.into_account.role_token: vai trò 'Alice' không có trong draft.parties.","root.when[0].case.party.role_token: vai trò 'Alice' không có trong draft.parties.","root.when[0].then: Close còn dư 1; Marlowe sẽ hoàn về chủ account.","root: bên 'Bob' trong draft không xuất hiện trong AST.","root: không thấy số tiền 2 trong Deposit/Pay; kiểm tra đơn vị lovelace.","root: deposit_timeout=1893456000001 không xuất hiện trong AST.","root: decision_timeout=1893456000002 không xuất hiện trong AST."],"errors":["root.when[0].case.into_account.role_token: vai trò 'Alice' không có trong draft.parties.","root.when[0].case.party.role_token: vai trò 'Alice' không có trong draft.parties."],"warnings":["root.when[0].then: Close còn dư 1; Marlowe sẽ hoàn về chủ account.","root: bên 'Bob' trong draft không xuất hiện trong AST.","root: không thấy số tiền 2 trong Deposit/Pay; kiểm tra đơn vị lovelace.","root: deposit_timeout=1893456000001 không xuất hiện trong AST.","root: decision_timeout=1893456000002 không xuất hiện trong AST."],"paths_explored":2,"graph_nodes":3,"graph_edges":2},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"11-infeasible-if-partial-pay","logic_graph":{"passed":false,"findings":["root.when[0].then.then.pay: Pay 1 vượt số dư 0; sẽ chỉ trả một phần."],"errors":["root.when[0].then.then.pay: Pay 1 vượt số dư 0; sẽ chỉ trả một phần."],"warnings":[],"paths_explored":3,"graph_nodes":6,"graph_edges":5},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"12-merkleized-case","logic_graph":{"passed":false,"findings":["root.when[0]: thiếu field 'then'.","root.when[0]: field không được hỗ trợ 'merkleized_then'."],"errors":["root.when[0]: thiếu field 'then'.","root.when[0]: field không được hỗ trợ 'merkleized_then'."],"warnings":[],"paths_explored":0,"graph_nodes":0,"graph_edges":0},"smt":{"analysis_notes":["1 MerkleizedCase continuation(s) are hashes and were not analyzed"],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
```

## Full outputs — three audit and three Stage 0.7b examples

```json
{"name":"en-loan-L4-007-full","logic_graph":{"passed":true,"findings":["Logic graph pass."],"errors":[],"warnings":[],"paths_explored":3,"graph_nodes":7,"graph_edges":6},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"vi-crowdfunding-L4-004-full","logic_graph":{"passed":true,"findings":["Logic graph pass."],"errors":[],"warnings":[],"paths_explored":5,"graph_nodes":14,"graph_edges":13},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"vi-escrow_3party-L4-006-full","logic_graph":{"passed":true,"findings":["Logic graph pass."],"errors":[],"warnings":[],"paths_explored":4,"graph_nodes":9,"graph_edges":8},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"C1-n1-k1","logic_graph":{"passed":false,"findings":["root.when[0].then.pay: Pay 11 vượt số dư 10; sẽ chỉ trả một phần."],"errors":["root.when[0].then.pay: Pay 11 vượt số dư 10; sẽ chỉ trả một phần."],"warnings":[],"paths_explored":2,"graph_nodes":4,"graph_edges":3},"smt":{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[{"account":{"role_token":"F2-0-0"},"amount":10,"party":{"role_token":"Depositor"},"token":{"currency_symbol":"","token_name":""},"type":"Deposit"}],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"F2-0-0"},"expected":11,"paid":10,"payee":{"party":{"role_token":"Receiver"}},"type":"TransactionPartialPay"}],"process_exit":0}}
{"name":"F1-n1-k1","logic_graph":{"passed":true,"findings":["Logic graph pass."],"errors":[],"warnings":[],"paths_explored":2,"graph_nodes":3,"graph_edges":2},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
{"name":"F3-n1-k1","logic_graph":{"passed":true,"findings":["root: không thể kiểm tĩnh đầy đủ với giá trị không xác định."],"errors":[],"warnings":["root: không thể kiểm tĩnh đầy đủ với giá trị không xác định."],"paths_explored":3,"graph_nodes":13,"graph_edges":12},"smt":{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[],"process_exit":0}}
```

## Result assertions

```text
$ python3 <results assertions>
verified 33 rows; hand-written agreement matrix matches observed outputs
```

Observed hand-written agreement categories:

- both catch: cases 01, 02, 03, 09;
- only SMT: cases 04, 05, 06;
- only Logic Graph: cases 07, 08, 11, 12;
- not applicable by design: case 10.

No command failed during corpus construction or comparison. The 110-MB
uncommitted first-run stdout capture was deleted/not retained as an artifact;
only `results.csv`, the reproducible corpus, scripts, and this command log are
committed.

Final verification after all changes:

```text
$ tools/marlowe_smt/run_tests.sh
Ran 12 tests in 26.544s
OK

$ tools/marlowe_smt/verify_upstream.sh
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
```
