# Lịch sử nghiên cứu

Một file duy nhất thay cho 33 báo cáo, nhật ký lệnh và README rải rác trước
ngày 2026-10-30. Bản gốc đầy đủ (lệnh, output, số đo chi tiết) vẫn còn trong
lịch sử git: `git log --all -- docs/infra docs/research research/stage2b/*.md`.
Công việc đang làm (A2) nằm ở [A2.md](A2.md).

Quy ước dùng xuyên suốt: mọi câu trả lời của "người dùng" trong các lượt chạy
là **mô phỏng** và được đánh dấu như vậy; kiểm tra kích thước giao dịch trên
node cục bộ **không** phải testnet pass; contract do model sinh luôn chỉ là
`MODEL_CANDIDATE` / `CANDIDATE_ONLY`; không sửa prompt, candidate hay dữ liệu
đóng băng để ép pass.

## Dòng thời gian

| Thời gian | Giai đoạn | Kết quả chính |
| --- | --- | --- |
| 08–09/2026 | Pipeline Node 1/2/3 ban đầu, benchmark 100 case | Dataset v2 đóng băng (SHA `e05c23f4…a907a`) |
| 27/09 | Stage 0 / 0.5 hạ tầng | Testnet riêng chạy được; `marlowe-cli run analyze` 0.2.0.0 lỗi giải mã tham số Conway |
| 28/09 | Stage 0.6 SMT độc lập | Route B (Haskell + Z3 trong WSL2) đạt cả 3 tiêu chí |
| 29/09 | Stage 0.7 / 0.7b / 0.8 / 0.9 | Đóng gói SMT, giới hạn 60/90 giây, SMT thay phần suy luận đường đi của Logic Graph, policy Node 3 |
| 30/09 | Stage 1.0 | Node 3 dùng SMT thật trong pipeline cũ |
| 01/10 | Stage 2A, Stage 2B dev10, kiến trúc v1 | Corpus 32 case đóng băng `stage2a-v1`; core v1→v4; DAG nghiên cứu |
| 03–05/10 | Online tuning Batch 01 | 6/20 case tới cổng kích thước ledger trong 48 request |
| 06/10 | Chuyển tuyến (`4e74599`) | CLI chỉ còn pipeline mới; Node 1/2/3 lưu trữ |
| 06–09/10 | Roleplay batch 20 | 19/20 tới cổng kích thước ledger, 1 `UNSUPPORTED` đúng |
| 09–27/10 | Roleplay batch 80 (case 21–57) | 34/37 tới cổng kích thước ledger; case 57 bị loại |
| 27/10– | A2 và giao thức đánh giá | Xem [A2.md](A2.md) |
| 30/10 | Dọn repo | Xóa Node 1/2/3 và bộ chạy benchmark cũ; gom test, docs, dữ liệu chạy |

## 1. Pipeline ban đầu và dataset (08–09/2026)

Pipeline đầu tiên là chuỗi Node 1/2/3: Node 1 hỏi lại và soạn draft, Node 2
sinh Marlowe AST bằng LLM, Node 3 kiểm tra bằng Logic Graph (về sau bằng
SMT). Đi kèm là một benchmark 100 case sinh từ template với seed cố định 1234:
60 tiếng Việt / 40 tiếng Anh; 11 họ hợp đồng (escrow 2 và 3 bên, swap, loan,
vesting, milestone, crowdfunding, third party, rental deposit, cancellation
fee, infeasible); `info_mode` complete 55 / missing 30 / ambiguous 10 /
infeasible 5. Dataset v1 (`bddc66e4…`) chỉ dùng cho một lượt smoke bị ngắt;
v2 (`e05c23f4…a907a`) được đóng băng và là dataset của mọi phép đo sau này.
Mỗi case có `reference_contract` và kịch bản kiểm tra; hai quy ước ẩn của
dataset ảnh hưởng tới chấm điểm sau này: mọi deadline là 12:00 UTC của ngày
được nêu (prompt không nói giờ), và token GOLD dùng `currency_symbol`
giữ chỗ `"benchmark"`.

Pipeline Node 1/2/3 và bộ chạy benchmark live (runner, judge, user simulator,
narrator, báo cáo) đã bị xóa ngày 30/10; công cụ dựng và kiểm dataset còn ở
`dataset/`.

## 2. Hạ tầng và SMT (Stage 0 → 1.0, 27–30/09)

- **Stage 0/0.5:** dựng testnet Cardano riêng trong WSL. `marlowe-cli 0.2.0.0`
  không giải mã được phản hồi tham số giao thức Conway của `cardano-node
  11.1.2` (`Size mismatch when decoding Record RecD. Expected 31, but found
  30`), độc lập với contract. Hệ quả: phân tích giao dịch qua CLI phải dùng
  node Babbage; về sau chạy testnet Babbage riêng (magic 42094, rồi 42123).
- **Stage 0.6:** Route B — `FSSemanticsFastVerbose.warningsTraceWithState` của
  `marlowe-lang/marlowe` + cầu JSON Core V1, chạy Z3 trực tiếp, không cần node.
  Đạt cả ba tiêu chí: escrow mẫu `Valid`; ba contract âm cho đúng ba phản ví
  dụ (`TransactionPartialPay`, `TransactionNonPositiveDeposit`,
  `TransactionShadowing`); contract L4 lớn nhất `Valid` trong 0,10 giây,
  ~28 MB RAM. Route A (marlowe-cli) bị chặn.
- **Stage 0.7:** đóng gói thành `tools/marlowe_smt/` có pin upstream và hợp
  đồng subprocess ổn định. Đủ dùng làm cổng cảnh báo nghiệp vụ, với giới hạn:
  không mở nhánh merkleized, không xác thực địa chỉ/hash on-chain, không kiểm
  giới hạn ledger. `Indeterminate`, `InvalidInput`, `Timeout` luôn là "chưa
  kết luận", không bao giờ là pass.
- **Stage 0.7b:** phía `Valid` chậm hơn nhiều so với phía phản ví dụ; giới hạn
  đổi thành 60 giây cho solver, 90 giây cho process. Tối đa 2 job song song,
  2 GiB mỗi job trên máy đo.
- **Stage 0.8:** trên 33 contract, SMT khớp các kiểm tra cụ thể của Logic Graph
  và tìm thêm partial pay biểu tượng, Let shadowing, assertion failure, đồng
  thời loại false positive nhánh bất khả. SMT **không** thay được: kiểm overlap
  trong cùng `When`, tham chiếu chưa định nghĩa, nhất quán draft/AST, cảnh báo
  cấu trúc. Hai phần này vì thế tồn tại song song trong
  `research/marlowe_core/` (lint) và cổng SMT.
- **Stage 0.9:** policy Node 3 tách `fail`/`inconclusive`, renderer cảnh báo
  tiếng Việt tất định. Sau khi sửa evaluator (choice-name fallback), replay
  cho 7 chấp nhận đúng, 0 chấp nhận sai, 0 từ chối sai ở cả hai policy; bộ mẫu
  không có contract sai nên chưa đo được khả năng từ chối đúng.
- **Stage 1.0:** pipeline sống dùng lint tất định + SMT thật thay cho
  `LogicGraphVerifier.verify()`; phản ví dụ SMT được ánh xạ về đường dẫn AST.

## 3. Stage 2A: corpus và tham chiếu (01/10)

32 case (20 gốc + 12 biến thể), chia development 16 / validation 16, nhãn
resolution: chấp nhận 12, hỏi lại 16, mâu thuẫn 3, ngoài phạm vi 1. Tất cả là
**chú thích nháp**, chưa được người duyệt; tập validation đã lộ nên không phải
test mù. Bản đóng băng `stage2a-v1` (commit nguồn `a6ea9458…`) khóa
`development.jsonl`, `validation.jsonl`, `foundation.py`, `protocol.md`;
`python research/stage2a/verify_freeze.py` kiểm hash. Cùng giai đoạn có bộ thực
thi tham chiếu Marlowe pin (`tools/marlowe_smt/run_reference.py`, nhận
contract + state + giao dịch, trả từng bước với cảnh báo, khoản trả, state).
Đây là ngữ nghĩa tham chiếu, không phải kiểm tra ledger. Động cơ học thuật:
FSM-SCG (kiểm IR trước khi sinh code), Lamela Seijas et al. (ngữ nghĩa thực thi
được của Marlowe), LeVer (bổ trợ hình thức/đối kháng; độ trung thành dịch
nghĩa vẫn là giới hạn).

## 4. Kiến trúc v1 và chuyển tuyến (01–06/10)

Kiến trúc nghiên cứu là một DAG các artifact định danh theo nội dung
(`canonical_json_v1`, `artifact_id = type:schema:cj1:sha256`) qua các cổng có
thẩm quyền rõ ràng:

```text
requirement history
  -> 2B ShadowSemanticCore + chiếu tất định sang IntentSpec   [MODEL_CANDIDATE]
  -> 2C người dùng duyệt đúng IntentSpec đó                    [USER_ACCEPTED_INTENT]
  -> 3  LLM sinh Core V1 AST                                     [MODEL_CANDIDATE]
  -> lint cấu trúc + SMT pin; phát hiện -> sinh lại có giới hạn
  -> so sánh ngữ nghĩa với expectation độc lập qua reference pin
  -> CandidateGatePort                                           [luôn CANDIDATE_ONLY]
  -> 4  khám phá có giới hạn + oracle; 5 ghi quan sát SQLite
  -> ledger: phân tích kích thước giao dịch (tùy chọn); testnet/deploy: tắt
```

Nguyên tắc: không có cạnh tự sửa từ oracle ngược về intent hay compiler;
`Valid` của SMT chỉ là "không thấy cảnh báo trong mô hình"; so sánh tham chiếu
chỉ chứng minh cho đúng các trace đã khai báo; khám phá Stage 4 là có giới
hạn, không vét cạn; quan sát Stage 5 không phải nhãn huấn luyện và lượt mô
phỏng không được xuất. Compiler tất định theo profile (direct payment, funded
choice, funded swap, linear time release, sequential approval) chỉ còn dùng
làm hợp đồng tham chiếu và thí nghiệm. Chuyển tuyến ngày 06/10 (`4e74599`)
biến route này thành route duy nhất của CLI; lúc đó 612 test pass.

## 5. Stage 2B: trích xuất intent (01–27/10)

Stage 2B là nơi tốn nhiều công nhất. Model đọc yêu cầu và xuất
`ShadowSemanticCore`: scope hành vi (global / transition / branch / timeout /
terminal outcome), claim có trích dẫn nguyên văn, câu hỏi làm rõ, quan sát
ngoài taxonomy và resolution. Validator kiểm nghiêm ngặt; projector tất định
đổi core hợp lệ thành IntentSpec.

- **Dev10 (10 case development, mỗi phiên bản một lượt):** v2: 10/10 bản ghi
  chạy được nhưng 0 hợp lệ cấu trúc; ablation chỉ giữ core: 1/10 hợp lệ. v3:
  2 hợp lệ / 8 core sai. v4: 7/10 hợp lệ và chiếu PASS, 1 core sai, 2 lỗi
  JSON, sau khi prompt nêu đủ các bất biến tham chiếu; vẫn còn hỏi thừa và
  lệch claim. Kiểm toán ngữ
  nghĩa dev10-v4 (62 claim tài chính đề cử / 63 claim dự đoán) dẫn tới các
  luật prompt tổng quát, không vá theo case.
- **Core v1→v4:** v2 thêm `choice_bounds`, `choice_guard`,
  `continuation_scope_id`, outcome có cha; v3 thêm token native
  (`amount_token_units`, `native:<policy>/<hex>`) và tín hiệu ngoài phạm vi
  `ledger_history_deletion`; v4 thêm `payment_release_time_ms` ("không trước
  thời điểm") và luật scope cho người nạp/tài khoản nhận. v4 là mặc định.
- **Repair:** tối đa N lần sửa theo lỗi validator, dừng khi hai bước liên tiếp
  không cải thiện (`_repair_stalled`), chính sách hiện tại
  `source-draft-v44`. Lớp chuẩn hóa tất định `core_draft.py` (~1.000 dòng) lớn
  dần để vá lỗi cấu trúc của model.
- **Bài học dẫn tới A2:** replay offline 255 output lượt đầu cho thấy chỉ
  khoảng 5–8% hợp lệ ngay; lỗi chủ yếu là cấu trúc (đồ thị scope, schema,
  span, liên kết provenance), không phải hiểu sai nghiệp vụ. Model còn không
  tính được "một nửa" hay "bảy ngày sau hạn" vì v4 không có phép tính.

## 6. Các lượt chạy live

Model cố định: `nvidia/nemotron-3-ultra-550b-a55b:free` qua OpenRouter (gói
miễn phí 50 request/ngày; kiểm `GET /api/v1/key` trước khi chạy). Mọi request
được ghi nhật ký trước khi gửi.

- **Live Stage 2B corridor v1:** hai nhánh — model có tự đi qua đường
  direct-payment đã chứng minh không, và đặc tả trích xuất trên 20 yêu cầu
  Stage 2A; có trần chi phí khai báo trước.
- **Online tuning Batch 01 (03–05/10):** 20 case đầu dataset, trần 48 request.
  6/20 case được thử, cả 6 đạt core PASS → compile → so sánh tham chiếu
  `SATISFIED` → `REACHED_LEDGER_PASS` (12.182–12.250 / 16.384 byte); 14 case
  không được thử vì hết ngân sách. Sửa lỗi chung: review Stage 2C chịu được
  null, payout chain trong compiler profile, kiểm đồng bộ node trước khi đo.
- **Roleplay batch 20 (06–09/10):** chạy tuần tự 20 case đầu qua pipeline
  chính với câu trả lời mô phỏng. 19/20 `SIMULATED_LEDGER_SIZE_CHECKED`, 61 kịch
  bản được đo kích thước; `vi-infeasible-L2-001` (đòi xóa lịch sử giao dịch)
  dừng đúng ở `UNSUPPORTED`. GOLD dùng policy giữ chỗ được đánh dấu mô phỏng.
- **Roleplay batch 80 (09–27/10, case 21–57):** 34/37
  `SIMULATED_LEDGER_SIZE_CHECKED`; case 30 dừng ở `SIMULATED_CANDIDATE_ONLY`,
  case 45 ở `WAITING_USER`. Sửa lỗi chung đáng kể: khoản trả chỉ do thời gian
  phải nằm ở `timeout_continuation`, không giấu sau `Notify`. Case 57 bị
  **loại khỏi mọi phép đo** vì trường đánh giá của nó đã bị đọc ngày 27/10.
  Từ đó: chỉ đọc `prompt` của case chưa chạy; case 58–100 là tập test đóng.

Không lượt nào ký hay gửi giao dịch lên testnet công khai; không có ví/cách
ký. "Đạt cổng ledger" luôn chỉ là phân tích kích thước giao dịch.

## 7. Những gì đã bỏ

- Pipeline Node 1/2/3, `legacy_cli`, `OpenAIReasoner` chế độ cũ (giữ lại
  `research/integrations/openai_reasoner.py` và `reasoner_models.py` vì các
  công cụ Stage 2B cũ còn dùng), bộ chạy benchmark live, tool sinh sample —
  xóa ngày 30/10.
- `--research-mode legacy|shadow|candidate|authorized` — bỏ khi chuyển tuyến.
- Fallback compiler tất định trong CLI — bỏ; compiler profile chỉ còn làm
  tham chiếu.

## 8. Bằng chứng gốc

Dữ liệu chạy nằm trong `runs/` (không đưa vào git). Lượt đã xong được gom 20
case một file ngay trong thư mục của lượt đó (`runs/<lượt>/cases-AA-BB.jsonl`,
mỗi dòng là một file gốc nguyên văn kèm SHA-256); 349 log phiên CLI gom vào
`runs/cli-sessions.jsonl`. Lượt đang chạy (`runs/eval/`) giữ nguyên. Đọc bằng
`research.experiments.run_bundles.iter_cases`; khôi phục file gốc bằng
`python -m research.experiments.run_bundles extract <bundle>`. Replay Stage 2B
cho kết quả giống hệt trước và sau khi gom. Bản sao toàn bộ `runs/` trước khi gom:
`D:\code\marlowe_ai_agent-runs-backup-20261030.zip` (1.601 file, đã kiểm).
