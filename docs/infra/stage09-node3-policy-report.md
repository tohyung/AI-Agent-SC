# Stage 0.9 — Node 3 policy prototype and offline replay

## Kết luận

**Correction (Stage 0.9c): kết luận cũ về hai false acceptance không còn
đúng với evaluator hiện tại.** Báo cáo Stage 0.9 ban đầu dùng nhãn
`evaluation.strict_correct` lưu trong audit và kết luận cả Logic Graph lẫn
Node 3 cùng sai ở rental deposit và milestone (false acceptance 2/2). Hai
record này được tạo trước bản sửa choice-name fallback; khi chấm lại chính
contract đã lưu bằng evaluator hiện tại, cả hai đạt `strict_correct=true`.

Policy prototype vẫn phân biệt `fail`/`inconclusive`, giữ dữ liệu tương thích
với `LogicGraphResult` và có renderer/fingerprint tất định. Replay hiện tại
cho 7 true acceptance, 0 false acceptance và 0 false rejection ở cả hai
policy. Bộ mẫu không có contract current-ground-truth `false`, nên chưa đo
được khả năng true rejection hay chứng minh policy mới chính xác hơn. Prototype
vẫn chưa nối vào pipeline.

## Offline replay

Ground truth hiện hành được tính lại bằng `evaluate(current_case,
saved_contract, status=saved_status)` trên dataset
`marlowe_ai_agent/bench/dataset/cases.jsonl` (SHA-256
`e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`).
`record["evaluation"]["strict_correct"]` chỉ là nhãn persisted lịch sử để
phát hiện evaluator drift, không tham gia confusion matrix. Có 10 file
`*-full.json`; 7 file có contract và current ground truth boolean, 3 file
thiếu contract nên được tách khỏi bảng 2×2.

### Logic Graph so với ground truth

| Quyết định cũ | Ground truth đúng | Ground truth sai |
|---|---:|---:|
| Pass | 7 | 0 |
| Fail | 0 | 0 |

Tương ứng: true acceptance 7, false acceptance 0, true rejection 0, false
rejection 0.

### Node 3 so với ground truth

| Quyết định mới | Ground truth đúng | Ground truth sai |
|---|---:|---:|
| Pass | 7 | 0 |
| Fail | 0 | 0 |

Tương ứng: true acceptance 7, false acceptance 0, true rejection 0, false
rejection 0. `inconclusive` không được gộp vào bảng này.

### Bảng chéo độ đúng của hai policy

| Kết quả | `disagreement_type` | Số case |
|---|---|---:|
| Cả hai đúng | `both_correct` | 7 |
| Chỉ Logic Graph đúng | `old_only_correct` | 0 |
| Chỉ Node 3 đúng | `new_only_correct` | 0 |
| Cả hai sai | `both_wrong` | 0 |

Correction (Stage 0.9d): nhãn cũ `old_only_pass` / `new_only_pass` chỉ mô tả
verifier nào pass, không mô tả verifier nào đúng so với ground truth. Replay
hiện phân loại theo correctness bằng `old_only_correct` /
`new_only_correct`; số liệu current corpus không đổi.

Hai nhãn persisted đã đổi khi chấm bằng evaluator hiện tại:

- `vi-milestone-L4-003-full.json`: persisted `false` → current `true`;
  scenario accuracy 1.0, choice-name fallback ở 2 scenario.
- `vi-rental_deposit-L3-003-full.json`: persisted `false` → current `true`;
  scenario accuracy 1.0, choice-name fallback ở 2 scenario.

Milestone vẫn còn TODO về scenario tuần tự `reject_first_then_accept_second`:
dataset/ground truth chưa định nghĩa và kiểm đủ ngữ nghĩa đó. Không coi TODO
này là bằng chứng false acceptance của contract hiện tại.

Các case `inconclusive`/không có ground truth, tách riêng:

- `vi-cancellation_fee-L4-001-full.json`: thiếu contract, `unavailable`.
- `vi-cancellation_fee-L4-001-retry-full.json`: thiếu contract,
  `unavailable`.
- `vi-swap-L3-010-retry-full.json`: thiếu contract, `unavailable`.

Bảng từng hàng có thời gian SMT và phân loại nằm tại
[`node3-replay-results.csv`](../../marlowe_ai_agent/bench/node3-replay-results.csv).

## Tám nguyên tắc thiết kế

| # | Kết quả | Bằng chứng |
|---:|---|---|
| 1 | Đạt | `Node3Result` có `passed`, `findings`, `errors`, `warnings`; Counterexample luôn sinh `errors` không rỗng; test policy phủ các nhánh. |
| 2 | Đạt | `findings` là property bắt buộc và test xác nhận đúng `errors + warnings`; trace compatibility đọc trực tiếp cả ba trường. |
| 3 | Đạt sau correction | Replay chạy độc lập Logic Graph và Node 3 trên contract đã lưu, rồi so với `strict_correct` do evaluator hiện tại tính lại; nhãn persisted chỉ dùng để audit drift. |
| 4 | Đạt | `next_inconclusive_state` có bộ đếm riêng, hai lần liên tiếp trả `logic_inconclusive`; pass/fail reset; không dùng `StallTracker` hay `stalled`. |
| 5 | Đạt | Fingerprint dùng canonical JSON của contract và các warning `{type, fields}` đã sắp xếp; test chứng minh đổi elapsed không đổi hash, đổi field làm đổi hash. Raw solver output/stderr không tham gia. |
| 6 | Đạt | Test trace giữ nguyên `findings`/`errors`/`warnings`, chỉ thêm năm field mới và chạy thật `bench.report.generate()` không crash. |
| 7 | Đạt | `valid` chỉ pass khi `analysis_notes` rỗng; `valid` kèm ghi chú là `inconclusive`, có test riêng. |
| 8 | Đạt | Renderer phủ đủ năm constructor; fixture được chạy qua driver SMT thật, và test kiểm vị trí từng field có số liệu phân biệt. |

## Renderer tất định

Các dòng sau được dựng từ structured warning do driver SMT thật trả về trên
năm fixture có sẵn, không dùng raw solver text:

```text
Bên Alice cố nạp 0 vào tài khoản Alice; Deposit phải lớn hơn 0.
Tài khoản Alice cố trả 0 cho bên Bob; Pay phải lớn hơn 0.
Tài khoản Alice cố trả 20 cho bên Bob nhưng chỉ trả được 10.
Biến x bị Let ghi đè: giá trị cũ 1, giá trị mới 2.
Assert có thể sai trên một đường đi khả thi.
```

Với partial pay, `expected=20` nằm sau “cố trả” và `paid=10` nằm sau “chỉ trả
được”; test không dùng hai số trùng nhau nên phát hiện được việc đảo trường.

## Tương thích log/trace

`test_node3_trace_compat.py` tạo một record có schema cũ
`findings`/`errors`/`warnings`, cộng thêm `verification_backend`, `smt_status`,
`smt_warnings`, `counterexample`, `analysis_notes`, rồi chạy thật
`bench.report.generate()`. Kết quả không crash và dữ liệu gốc không đổi.

Không phát hiện rủi ro từ các field trace cộng thêm: `report.py` hiện không đọc
payload trace này. `report.py` vẫn index trực tiếp một số field top-level bắt
buộc như `case_id`, `iterations`, `wall_seconds`; đây là ràng buộc schema cũ,
không bị prototype thay đổi.

## Test và tính cô lập

- Trước thay đổi: 125 test được collect, 125 test pass.
- Sau thay đổi: 139 test được collect, 139 test pass.
- SMT regression: 12 test pass; upstream pin được xác nhận và không có patch.
- `test_node3_not_wired.py` pass: AST của `nodes.py`, `openai_reasoner.py`,
  `models.py`, `cli.py` không import `node3_policy` hoặc `node3_renderer`.
- Không sửa `tools/marlowe_smt/`, không gọi LLM/API và không dùng
  `cardano-node`.

Cây file mới:

```text
marlowe_ai_agent/
├── bench/
│   ├── node3_replay.py
│   └── node3-replay-results.csv
├── marlowe_agent/
│   ├── node3_policy.py
│   └── node3_renderer.py
└── tests/
    ├── test_node3_not_wired.py
    ├── test_node3_policy.py
    ├── test_node3_renderer.py
    └── test_node3_trace_compat.py
docs/infra/
├── stage09-command-log.md
└── stage09-node3-policy-report.md
```

Không tạo package con. Không file production/test/SMT có sẵn nào bị sửa; thay
đổi duy nhất trên file tài liệu có sẵn là thêm liên kết Stage 0.9 vào
`stage0-feasibility-report.md`, đúng yêu cầu.

## Đã kiểm chứng và chưa kiểm chứng

Đã kiểm chứng:

- đủ năm decision/status class ở policy và công thức `findings`;
- fingerprint ổn định trước elapsed và nhạy với structured fields;
- bộ đếm inconclusive độc lập;
- đủ năm renderer bằng output driver thật;
- replay toàn bộ 10 audit file, các bảng 2×2 và bảng chéo;
- trace additive chạy qua report hiện tại;
- toàn bộ test agent và SMT vẫn xanh; test renderer hiện chạy không cần
  `wsl.exe`, chỉ cần `bash` có sẵn; prototype chưa được import bởi pipeline.

Chưa kiểm chứng:

- hành vi khi nối thật vào vòng lặp Node 1/Node 3;
- chất lượng tự sửa sau khi LLM nhận renderer text;
- timeout/indeterminate thật trên audit hiện tại (ba inconclusive là do thiếu
  contract, không phải solver timeout);
- độ nhạy với contract current-ground-truth sai: mẫu replay hiện tại không có
  negative case trong 7 contract có thể chấm lại.

Khuyến nghị: giữ prototype chưa nối dây; bổ sung negative cases và định nghĩa
scenario tuần tự milestone trước khi dùng replay để quyết định Stage 1.0.
