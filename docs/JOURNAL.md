# Journal nghiên cứu

Một file duy nhất thay cho 33 báo cáo, nhật ký lệnh và README rải rác trước
ngày 2026-10-30. Bản gốc đầy đủ (lệnh, output, số đo chi tiết) vẫn còn trong
lịch sử git: `git log --all -- docs/infra docs/research research/stage2b/*.md` (đường dẫn trước khi đổi tên).
Thí nghiệm E4 (so sánh AFF với DCF) nằm ở [E4-Formalization-Comparison.md](E4-Formalization-Comparison.md).

Quy ước dùng xuyên suốt: mọi câu trả lời của "người dùng" trong các lượt chạy
là **mô phỏng** và được đánh dấu như vậy; kiểm tra kích thước giao dịch trên
node cục bộ **không** phải testnet pass; contract do model sinh luôn chỉ là
`MODEL_CANDIDATE` / `CANDIDATE_ONLY`; không sửa prompt, candidate hay dữ liệu
đóng băng để ép pass.

## Dòng thời gian

| Thời gian | Giai đoạn | Kết quả chính |
| --- | --- | --- |
| 08–09/2026 | Pipeline Node 1/2/3 ban đầu, benchmark 100 case | Dataset v2 đóng băng (SHA `e05c23f4…a907a`) |
| 27/09 | Infrastructure 0 / 0.5 hạ tầng | Testnet riêng chạy được; `marlowe-cli run analyze` 0.2.0.0 lỗi giải mã tham số Conway |
| 28/09 | Infrastructure 0.6 SMT độc lập | Route B (Haskell + Z3 trong WSL2) đạt cả 3 tiêu chí |
| 29/09 | Infrastructure 0.7 / 0.7b / 0.8 / 0.9 | Đóng gói SMT, giới hạn 60/90 giây, SMT thay phần suy luận đường đi của Logic Graph, policy Node 3 |
| 30/09 | Infrastructure 1.0 | Node 3 dùng SMT thật trong pipeline cũ |
| 01/10 | Corpus, Formalization dev10, kiến trúc v1 | Corpus 32 case đóng băng `Corpus-v1`; core v1→v4; DAG nghiên cứu |
| 03–05/10 | E2 Online Tuning (cũ: Online tuning Batch 01) | 6/20 case tới cổng kích thước ledger trong 48 request |
| 06/10 | Chuyển tuyến (`4e74599`) | CLI chỉ còn pipeline mới; Node 1/2/3 lưu trữ |
| 06–09/10 | E3 Roleplay, batch 20 | 19/20 tới cổng kích thước ledger, 1 `UNSUPPORTED` đúng |
| 09–27/10 | E3 Roleplay, batch 80 (case 21–57) | 34/37 tới cổng kích thước ledger; case 57 bị loại |
| 27/10–09/11 | E4 Formalization Comparison (cũ: A2) | Xem [E4-Formalization-Comparison.md](E4-Formalization-Comparison.md) |
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

## 2. Hạ tầng và SMT (Infrastructure 0 → 1.0, 27–30/09)

- **Infrastructure 0/0.5:** dựng testnet Cardano riêng trong WSL. `marlowe-cli 0.2.0.0`
  không giải mã được phản hồi tham số giao thức Conway của `cardano-node
  11.1.2` (`Size mismatch when decoding Record RecD. Expected 31, but found
  30`), độc lập với contract. Hệ quả: phân tích giao dịch qua CLI phải dùng
  node Babbage; về sau chạy testnet Babbage riêng (magic 42094, rồi 42123).
- **Infrastructure 0.6:** Route B — `FSSemanticsFastVerbose.warningsTraceWithState` của
  `marlowe-lang/marlowe` + cầu JSON Core V1, chạy Z3 trực tiếp, không cần node.
  Đạt cả ba tiêu chí: escrow mẫu `Valid`; ba contract âm cho đúng ba phản ví
  dụ (`TransactionPartialPay`, `TransactionNonPositiveDeposit`,
  `TransactionShadowing`); contract L4 lớn nhất `Valid` trong 0,10 giây,
  ~28 MB RAM. Route A (marlowe-cli) bị chặn.
- **Infrastructure 0.7:** đóng gói thành `tools/marlowe_smt/` có pin upstream và hợp
  đồng subprocess ổn định. Đủ dùng làm cổng cảnh báo nghiệp vụ, với giới hạn:
  không mở nhánh merkleized, không xác thực địa chỉ/hash on-chain, không kiểm
  giới hạn ledger. `Indeterminate`, `InvalidInput`, `Timeout` luôn là "chưa
  kết luận", không bao giờ là pass.
- **Infrastructure 0.7b:** phía `Valid` chậm hơn nhiều so với phía phản ví dụ; giới hạn
  đổi thành 60 giây cho solver, 90 giây cho process. Tối đa 2 job song song,
  2 GiB mỗi job trên máy đo.
- **Infrastructure 0.8:** trên 33 contract, SMT khớp các kiểm tra cụ thể của Logic Graph
  và tìm thêm partial pay biểu tượng, Let shadowing, assertion failure, đồng
  thời loại false positive nhánh bất khả. SMT **không** thay được: kiểm overlap
  trong cùng `When`, tham chiếu chưa định nghĩa, nhất quán draft/AST, cảnh báo
  cấu trúc. Hai phần này vì thế tồn tại song song trong
  `research/analysis/` (lint) và cổng SMT.
- **Infrastructure 0.9:** policy Node 3 tách `fail`/`inconclusive`, renderer cảnh báo
  tiếng Việt tất định. Sau khi sửa evaluator (choice-name fallback), replay
  cho 7 chấp nhận đúng, 0 chấp nhận sai, 0 từ chối sai ở cả hai policy; bộ mẫu
  không có contract sai nên chưa đo được khả năng từ chối đúng.
- **Infrastructure 1.0:** pipeline sống dùng lint tất định + SMT thật thay cho
  `LogicGraphVerifier.verify()`; phản ví dụ SMT được ánh xạ về đường dẫn AST.

## 3. Corpus: corpus và tham chiếu (01/10)

32 case (20 gốc + 12 biến thể), chia development 16 / validation 16, nhãn
resolution: chấp nhận 12, hỏi lại 16, mâu thuẫn 3, ngoài phạm vi 1. Tất cả là
**chú thích nháp**, chưa được người duyệt; tập validation đã lộ nên không phải
test mù. Bản đóng băng `Corpus-v1` (commit nguồn `a6ea9458…`) khóa
`development.jsonl`, `validation.jsonl`, `foundation.py`, `protocol.md`;
`python research/corpus/verify_freeze.py` kiểm hash. Cùng giai đoạn có bộ thực
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
chỉ chứng minh cho đúng các trace đã khai báo; khám phá Exploration là có giới
hạn, không vét cạn; quan sát Induction không phải nhãn huấn luyện và lượt mô
phỏng không được xuất. Compiler tất định theo profile (direct payment, funded
choice, funded swap, linear time release, sequential approval) chỉ còn dùng
làm hợp đồng tham chiếu và thí nghiệm. Chuyển tuyến ngày 06/10 (`4e74599`)
biến route này thành route duy nhất của CLI; lúc đó 612 test pass.

## 5. Formalization: trích xuất intent (01–27/10)

Formalization là nơi tốn nhiều công nhất. Model đọc yêu cầu và xuất
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
  `Formalization-Repair-v44`. Lớp chuẩn hóa tất định `core_draft.py` (~1.000 dòng) lớn
  dần để vá lỗi cấu trúc của model.
- **Bài học dẫn tới AFF:** replay offline 255 output lượt đầu cho thấy chỉ
  khoảng 5–8% hợp lệ ngay; lỗi chủ yếu là cấu trúc (đồ thị scope, schema,
  span, liên kết provenance), không phải hiểu sai nghiệp vụ. Model còn không
  tính được "một nửa" hay "bảy ngày sau hạn" vì v4 không có phép tính.

## 6. Các lượt chạy live

Model cố định: `nvidia/nemotron-3-ultra-550b-a55b:free` qua OpenRouter (gói
miễn phí 50 request/ngày; kiểm `GET /api/v1/key` trước khi chạy). Mọi request
được ghi nhật ký trước khi gửi.

- **E1 Live Corridor (cũ: Live Stage 2B corridor v1):** hai nhánh — model có tự đi qua đường
  direct-payment đã chứng minh không, và đặc tả trích xuất trên 20 yêu cầu
  Corpus; có trần chi phí khai báo trước.
- **E2 Online Tuning (cũ: Online tuning Batch 01, 03–05/10):** 20 case đầu dataset, trần 48 request.
  6/20 case được thử, cả 6 đạt core PASS → compile → so sánh tham chiếu
  `SATISFIED` → `REACHED_LEDGER_PASS` (12.182–12.250 / 16.384 byte); 14 case
  không được thử vì hết ngân sách. Sửa lỗi chung: review Ratification chịu được
  null, payout chain trong compiler profile, kiểm đồng bộ node trước khi đo.
- **E3 Roleplay, batch 20 (06–09/10):** chạy tuần tự 20 case đầu qua pipeline
  chính với câu trả lời mô phỏng. 19/20 `SIMULATED_LEDGER_SIZE_CHECKED`, 61 kịch
  bản được đo kích thước; `vi-infeasible-L2-001` (đòi xóa lịch sử giao dịch)
  dừng đúng ở `UNSUPPORTED`. GOLD dùng policy giữ chỗ được đánh dấu mô phỏng.
- **E3 Roleplay, batch 80 (09–27/10, case 21–57):** 34/37
  `SIMULATED_LEDGER_SIZE_CHECKED`; case 30 dừng ở `SIMULATED_CANDIDATE_ONLY`,
  case 45 ở `WAITING_USER`. Sửa lỗi chung đáng kể: khoản trả chỉ do thời gian
  phải nằm ở `timeout_continuation`, không giấu sau `Notify`. Case 57 bị
  **loại khỏi mọi phép đo** vì trường đánh giá của nó đã bị đọc ngày 27/10.
  Từ đó: chỉ đọc `prompt` của case chưa chạy; case 58–100 là tập test đóng.

Không lượt nào ký hay gửi giao dịch lên testnet công khai; không có ví/cách
ký. "Đạt cổng ledger" luôn chỉ là phân tích kích thước giao dịch.

## 7. Những gì đã bỏ

- Pipeline Node 1/2/3, `legacy_cli`, `OpenAIReasoner` chế độ cũ (giữ lại
  `research/adapters/openai_reasoner.py` và `reasoner_models.py` vì các
  công cụ Formalization cũ còn dùng), bộ chạy benchmark live, tool sinh sample —
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
`python -m research.experiments.run_bundles extract <bundle>`. Replay Formalization
cho kết quả giống hệt trước và sau khi gom. Bản sao toàn bộ `runs/` trước khi gom:
`D:\code\marlowe_ai_agent-runs-backup-20261030.zip` (1.601 file, đã kiểm).

## 9. Đổi tên toàn repo (2026-11-09)

### Lý do

Đến hết E4, repo dùng lẫn ba kiểu tên: số giai đoạn (`stage2a` … `stage5`, "Stage 2B"), tên
dự án (A1, A2, BASE) và tên đời pipeline cũ (`node3_*`, `online_tuning_batch01`,
`roleplay_main_case`). Chuỗi phiên bản cũng không cùng dạng: `stage2b-shadow-core-v4`,
`source-draft-v44`, `pipeline_run_v1`, `batch-v1`. Người phụ trách yêu cầu đặt lại toàn bộ theo một
chủ đề thống nhất, nghe khoa học, viết hoa chữ cái đầu, và bỏ hẳn tên cũ.

### Quy ước mới

- **Phần (phase)** của pipeline mang tên theo việc nó làm, viết hoa khi hiển thị: Corpus,
  Formalization, Ratification, Synthesis, Exploration, Induction; cùng bốn phần hỗ trợ
  Orchestration, Analysis, Adapters, Ledger. Thư mục và module Python viết thường theo chuẩn
  Python (`research/formalization/`), để tránh lỗi import và lỗi đổi hoa/thường trên Windows.
- **Bước (step)** là đơn vị của orchestrator (trước gọi là stage): `StepResult`,
  `StepContext`, `StepRunStatus`, `step_order`, `entry_step` …
- **Phương pháp**: AFF (Atomic Fact Formalization, trước là A2) và DCF (Direct Core
  Formalization, trước là BASE). Tên nhánh trong CLI: `--arm AFF`, `--arm DCF`.
- **Thí nghiệm**: E1–E4 theo thứ tự thời gian.
- **Chuỗi phiên bản**: `<Phần>-<Thành phần>-vN`, giữ nguyên số phiên bản để không mất dòng lịch sử.

### Ánh xạ cũ → mới

Phần và thư mục (cả `research/` lẫn `tests/`):

| Cũ | Mới | Nội dung |
| --- | --- | --- |
| `stage2a` (Stage 2A) | `corpus` (Corpus) | corpus 32 case, giao thức, freeze |
| `stage2b` (Stage 2B) | `formalization` (Formalization) | đọc yêu cầu, dựng core/IntentSpec, FactDraft |
| `stage2c` (Stage 2C) | `ratification` (Ratification) | người dùng duyệt và chấp nhận intent |
| `stage3` (Stage 3) | `synthesis` (Synthesis) | sinh hợp đồng, so với tham chiếu, profile compiler |
| `stage4` (Stage 4) | `exploration` (Exploration) | khám phá có giới hạn, oracle |
| `stage5` (Stage 5) | `induction` (Induction) | kho quan sát property |
| `architecture` | `orchestration` (Orchestration) | DAG artifact, port, CLI |
| `marlowe_core` | `analysis` (Analysis) | AST, validator, Logic Graph, cảnh báo |
| `integrations` | `adapters` (Adapters) | model, SMT, WSL, bộ thực thi tham chiếu |
| `final_validation` | `ledger` (Ledger) | kiểm kích thước giao dịch qua marlowe-cli |
| Stage 0 … 1.0 (chỉ trong tài liệu) | Infrastructure 0 … 1.0 | dựng hạ tầng và SMT |

Module và định danh đổi tên riêng:

| Cũ | Mới |
| --- | --- |
| `integrations/stage2a.py`, `integrations/stage2b.py` | `adapters/corpus_adapter.py`, `adapters/formalization_adapter.py` |
| `marlowe_core/node3_mapper.py`, `node3_policy.py`, `node3_renderer.py` | `analysis/finding_mapper.py`, `warning_policy.py`, `warning_renderer.py` |
| `Node3Finding`, `Node3Result` | `AnalysisFinding`, `AnalysisResult` |
| `experiments/stage2b_{eval,score,semantics,stats,rebuild,replay}.py` | `experiments/formalization_{eval,score,semantics,stats,rebuild,replay}.py` |
| `experiments/live_stage2b_corridor.py` | `experiments/live_corridor.py` |
| `experiments/online_tuning_batch01.py`, `online-tuning-batch01*.json` | `experiments/online_tuning.py`, `E2-OnlineTuning*.json` |
| `experiments/roleplay_main_case.py` | `experiments/roleplay_case.py` |
| `tests/architecture/test_stage2bc_compiler_reference_path.py` | `tests/orchestration/test_formalization_ratification_compiler_reference_path.py` |
| `Stage2BExtractionPort`, `Stage2AFrozenCandidateAdapter` | `FormalizationPort`, `CorpusFrozenCandidateAdapter` |
| `STAGE2A_AGGREGATE_SHA256`, `STAGE2C_UNRESOLVED` | `CORPUS_AGGREGATE_SHA256`, `RATIFICATION_UNRESOLVED` |
| `evaluate_case_a2`, `a2_result_fields` | `evaluate_case_aff`, `aff_result_fields` |
| `StageResult`, `StageContext`, `StageExecution`, `StageRunStatus`, `StagePort`, `stage_order` … | `StepResult`, `StepContext`, `StepExecution`, `StepRunStatus`, `StepPort`, `step_order` … |

Chuỗi phiên bản:

| Cũ | Mới |
| --- | --- |
| `stage2a-v1` | `Corpus-v1` (manifest `research/corpus/freeze/Corpus-v1.manifest.json`) |
| `stage2b-shadow-v1` … `v4` | `Formalization-IntentSpec-v1` … `v4` |
| `stage2b-shadow-core-v1` … `v4` | `Formalization-Core-v1` … `v4` |
| `stage2b-fact-draft-v5` | `Formalization-FactDraft-v5` |
| `stage2b-fact-prompt-v5` | `Formalization-FactPrompt-v5` |
| `source-draft-v44` | `Formalization-Repair-v44` |
| `stage2b_offline_replay_v1` | `Formalization-OfflineReplay-v1` |
| `outside_stage2b_vN_claim_taxonomy` | `outside_formalization_vN_claim_taxonomy` (mã lý do, giữ dạng snake) |
| `simulated-v1` | `Ratification-Simulated-v1` |
| `batch-v1`, `local-v1`, `llm_from_accepted_intent_v1`, `llm_from_simulated_intent_v1` | `Synthesis-BatchExpectation-v1`, `Synthesis-LocalExpectation-v1`, `Synthesis-LlmFromAcceptedIntent-v1`, `Synthesis-LlmFromSimulatedIntent-v1` |
| `batch-timed-release-declared-actions-v1`, `batch-funded-swap-declared-deposits-v1`, `batch-sequential-approval-declared-actions-v1`, `local-user-declared-actions-v1`, `no-transaction-warning-v1` | `Exploration-TimedReleaseActions-v1`, `Exploration-FundedSwapDeposits-v1`, `Exploration-SequentialApprovalActions-v1`, `Exploration-LocalUserActions-v1`, `Exploration-NoTransactionWarning-v1` |
| `property-observation-v1` | `Induction-PropertyObservation-v1` |
| `research-architecture-v1`, `pipeline_run_v1`, `assurance-claim-v1` | `Orchestration-v1`, `Orchestration-PipelineRun-v1`, `Orchestration-AssuranceClaim-v1` |
| `adapter_empty_state_v1` | `Ledger-EmptyState-v1` |
| `live-stage2b-corridor-v1`, `live-direct-payment-v1`, `live-direct-payment-funded-alice-v1` | `E1-LiveCorridor-v1`, `E1-LiveDirectPayment-v1`, `E1-LiveDirectPaymentFundedAlice-v1` |
| `online-tuning-batch01` | `E2-OnlineTuning` |
| `roleplay-main-batch20`, `roleplay-main-batch80` | `E3-Roleplay-Batch20`, `E3-Roleplay-Batch80` |

Thí nghiệm và tài liệu:

| Cũ | Mới | Kết quả đã ghi dưới tên cũ |
| --- | --- | --- |
| Live Stage 2B corridor v1 | E1 Live Corridor | mục 6 |
| Online tuning Batch 01 | E2 Online Tuning | 6/20 case tới cổng kích thước ledger trong 48 request |
| Roleplay batch 20 và batch 80 | E3 Roleplay | 19/20 và 34/37 case tới cổng kích thước ledger |
| A2 (so sánh BASE với A2) | E4 Formalization Comparison (DCF với AFF) | giữ AFF; tập test, quyết định đúng trên core hợp lệ: 0,465 → 0,860 (prompt gốc), 0,581 → 0,814 (có nêu giờ và policy) |
| `docs/A2.md`, `docs/HISTORY.md`, `docs/a2-test-freeze-environment.txt` | `docs/E4-Formalization-Comparison.md`, `docs/JOURNAL.md`, `docs/E4-test-freeze-environment.txt` | |

### Những gì cố ý giữ nguyên

- **Bốn file của freeze Corpus-v1** (`corpus/development.jsonl`, `corpus/validation.jsonl`,
  `foundation.py`, `protocol.md`) chỉ được chuyển chỗ, không sửa một byte nào, kể cả chữ
  "Stage 2A" bên trong. Hash và aggregate được tính trên đường dẫn ở commit gốc `a6ea945`, nên
  manifest giữ `path` cũ và thêm `current_path`. `verify_freeze.py` so blob của file ở chỗ mới với
  blob ở commit gốc; aggregate vẫn là `897249e3…7a46`. Vì `foundation.py` đọc dữ liệu ở thư mục
  con `corpus/`, đường dẫn mới là `research/corpus/corpus/`.
- **Tag `a2-test-freeze`** (`faacc61`), đã push, trỏ vào code trước khi đổi tên. Hằng
  `FREEZE_TAG` vẫn mang tên tag này.
- **Dữ liệu ghi lại**: `dataset/cases.jsonl`, `dataset/supplement/`, các fixture trong
  `tests/dataset/fixtures/` (output của pipeline Node 1/2/3 cũ) và giá trị `multi_stage` của
  dataset. Code sinh dataset chỉ được sửa dòng import.
- **Thư mục `runs/`** (ngoài git) giữ tên cũ, như `runs/eval/A2-v5-dev` hay `T-BASE-test`; tài liệu
  E4 vẫn dẫn đúng các tên đó.
- **Tên của chính Marlowe và chuẩn kỹ thuật**: `core-v1`, `marlowe-core-v1` (Marlowe Core V1),
  `canonical_json_v1` và `cj1` (cách băm artifact).
- **Bài báo trong `docs/papers/`**, vì đó là bản đã phát hành; bài báo vẫn dùng chữ Stage.
- **Câu chữ prompt**: phần hướng dẫn không đổi. Chỉ các chuỗi phiên bản chèn vào prompt đổi theo:
  prompt AFF yêu cầu `"schema_version": "Formalization-FactDraft-v5"`; prompt DCF có hợp đồng
  schema (`Formalization-Core-v4`, `Formalization-IntentSpec-v4`), dòng `Repair policy
  Formalization-Repair-v44` và mã `outside_formalization_v4_claim_taxonomy`.

### Hệ quả

- Mọi số liệu E1–E4 được đo với tên cũ và chuỗi phiên bản cũ trong prompt. Sau khi đổi tên,
  không chạy lại; ảnh hưởng của việc đổi chuỗi phiên bản trong prompt chưa được đo. Muốn tái lập
  đúng kết quả cũ, dùng tag `a2-test-freeze` hoặc commit `b8e9610` (commit cuối trước khi đổi tên).
- Code mới không đọc được record cũ ở những chỗ có so chuỗi phiên bản (ví dụ `schema_version` của
  FactDraft hay của core); record cũ phải đọc bằng code ở commit trước khi đổi tên.
- ID artifact (`type:schema:cj1:sha256`) chứa tên schema, nên artifact mới có ID khác artifact cũ
  dù nội dung giống nhau.
- Lượt Nemotron phụ của AFF prompt v5 (`runs/eval/A2-v5-dev`) bị dừng ở 51/56 case để đổi tên;
  lượt `A2-v5-stated` chưa chạy. Đây chỉ là kiểm tra phụ, không ảnh hưởng kết luận E4.

### Cách thực hiện và kiểm chứng

Một script áp dụng cùng một danh sách quy tắc cho cả đường dẫn file (`git mv`, 181 file) lẫn nội
dung (164 file). Thứ tự quy tắc: tên cụ thể trước, tên gói sau, rồi tới chữ "stage" chung. Script
bỏ qua bốn file freeze, dữ liệu, fixture, bài báo và `tools/`; dòng prompt chứa "a stage" hay
"staged payment" (nghĩa nghiệp vụ, chặng thanh toán) được giữ nguyên. Sau đó sửa tay
`verify_freeze.py`, test freeze, README và tài liệu. Kiểm chứng:

- `python -m pytest -q`: 2531 passed, 76 skipped, đúng bằng trước khi đổi tên.
- `python research/corpus/verify_freeze.py research/corpus/freeze/Corpus-v1.manifest.json`:
  `FREEZE VERIFIED: Corpus-v1`, aggregate không đổi.
- `python main.py --help` và `python -m research.experiments.formalization_eval --help` chạy được.
- `uvx ruff check`: 240 cảnh báo so với 233 trước đó; 7 cảnh báo thêm đều là I001 (thứ tự import
  đổi theo tên module mới). Repo đã có sẵn 124 cảnh báo loại này.
