# Nhật ký thí nghiệm

Tệp này gom mọi thí nghiệm của dự án vào một chỗ, từ E1 đến E7, theo thứ tự thời gian. Mỗi thí nghiệm có
cùng một khung: mục đích, dữ liệu, cách làm, kết quả, hệ quả và nguồn bằng chứng.

- **Báo cáo kết quả** chỉ dùng ba thí nghiệm: E4 (RQ1), E5 (RQ2) và E7 (RQ3, RQ4). Ở đó chúng mang tên
  theo nội dung, không theo số E (bảng ở mục 1).
- **Các thí nghiệm còn lại** (E1–E3, E6) là các bước phát triển và thử nghiệm. Chúng được ghi ở đây cho đủ
  hồ sơ, không dùng làm kết quả.
- **Tài liệu gốc** của từng thí nghiệm (giao thức, thiết kế dataset, sổ lệch giao thức) nằm nguyên văn
  trong `docs/archive/`. Các file điểm và phân xử mà code đọc nằm trong `docs/evidence/`. Dữ liệu chạy
  thô nằm trong `runs/` (không đưa lên git).
- **Kết quả chi tiết** theo từng RQ: `docs/RQ-Report.md`.

## 1. Bảng tổng

| Mã | Thời gian (2026) | Tên trong báo cáo | Câu hỏi | Dataset | Model | Dùng trong báo cáo |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | trước 03/10 | — | Model có tự đi được đường thanh toán trực tiếp không | Corpus-v1 (20 yêu cầu) | Nemotron | Không |
| E2 | 03–05/10 | — | Chỉnh pipeline trên dữ liệu thật | dataset v2, case 1–20 | Nemotron | Không |
| E3 | 06/10–10/11 | — | Chạy pipeline từ đầu đến cuối với người dùng mô phỏng | dataset v2, case 1–100 (trừ 57) | Nemotron, rồi Gemini | Không (chỉ cấp hợp đồng cho E5) |
| E4 | 27/10–09/11 | Thí nghiệm so sánh hai cách formal hóa | RQ1 | dataset v2, test case 58–100, bộ mâu thuẫn bổ sung | Gemini | **Có** |
| E5 | 09–10/11 | Thí nghiệm cổng kiểm tra trên biến thể hợp đồng | RQ2 | biến thể sinh từ hợp đồng tham chiếu của dataset v2 | không gọi model | **Có** |
| E6 | 10–12/11 | — | RQ3, RQ4 (lần chạy đầu) | dataset v3 | Gemini | Không (thay bằng E7) |
| E7 | 12–13/11 | Thí nghiệm đầu-cuối | RQ3, RQ4 | dataset v5 (100 case viết tay mới) | Gemini | **Có** |

Model: `nvidia/nemotron-3-ultra-550b-a55b:free` qua OpenRouter (50 request/ngày) đến 2026-11-07; từ đó
`gemini-3.5-flash-lite` bản miễn phí (500 request/ngày) vì không có ngân sách.

Tag đóng băng:

| Tag | Khóa cái gì |
| --- | --- |
| `a2-test-freeze` | Code E4 trước khi chạy tập test (tên cũ của E4 là A2) |
| `E5-Round1`, `E5-Freeze` | Code cổng E5 vòng 1, và vòng 2 trước khi chạy tập test |
| `E6-Freeze-30` | Code E6 từ case 30 |
| `E7-Dataset-v5` | Dataset v5 (SHA-256 `85f70d43…`) |
| `E7-Freeze` | Code, giao thức và người dùng mô phỏng của E7 |

## 2. Giai đoạn chuẩn bị (08/2026 – 06/10/2026)

Đây là phần dựng hệ thống trước khi có thí nghiệm. Chi tiết nằm ở `docs/archive/JOURNAL.md`, mục 1–5.

- **Dataset v2 (08–09/2026):** 100 case sinh từ template với seed cố định 1234. Gồm 60 tiếng Việt, 40
  tiếng Anh, 11 họ hợp đồng; mức thông tin: đủ 55, thiếu 30, mơ hồ 10, bất khả 5. Mỗi case có hợp đồng
  tham chiếu và 1–4 kịch bản kiểm tra. Đóng băng với SHA `e05c23f4…a907a`. Quy ước ẩn: mọi hạn là 12:00
  UTC của ngày được nêu.
- **Hạ tầng SMT (27–30/09):** `marlowe-cli` không đọc được tham số giao thức Conway, nên phần phân tích
  dùng thẳng ngữ nghĩa Marlowe upstream (`marlowe-lang/marlowe`) cùng Z3 trong WSL. Kết quả là
  `tools/marlowe_smt/`, có pin upstream, giới hạn 60 giây cho solver và 90 giây cho process.
  `Indeterminate`, `InvalidInput`, `Timeout` luôn tính là chưa kết luận. Testnet Babbage riêng (magic
  42123) chỉ dùng để đo kích thước giao dịch, không ký và không gửi giao dịch.
- **Corpus-v1 (01/10):** 32 yêu cầu (20 gốc, 12 biến thể) có nhãn nháp, cùng bộ thực thi tham chiếu
  Marlowe pin (`tools/marlowe_smt/run_reference.py`). Kiểm bằng `python research/corpus/verify_freeze.py`.
- **Kiến trúc nghiên cứu (01–06/10):** một chuỗi artifact định danh theo nội dung, qua các cổng có thẩm
  quyền rõ ràng: lịch sử yêu cầu → intent → người dùng duyệt → sinh hợp đồng → lint, SMT → so với kỳ vọng
  độc lập → khám phá có giới hạn → kích thước ledger. Kết quả luôn chỉ là ứng viên; testnet công khai và
  triển khai bị tắt. Từ 06/10 đây là đường chạy duy nhất của CLI.

## 3. E1: Live Corridor (trước 03/10)

- **Mục đích:** kiểm tra lần đầu với model thật: model có tự đi qua đường thanh toán trực tiếp đã chứng
  minh không, và có trích được đặc tả từ 20 yêu cầu của Corpus-v1 không.
- **Cách làm:** hai nhánh; trần chi phí khai báo trước.
- **Hệ quả:** chỉ là bước kiểm tra đường chạy, không có số liệu tổng hợp. Không dùng trong báo cáo.
- **Nguồn:** `docs/archive/JOURNAL.md` mục 6 và mục 9 (bảng đổi tên).

## 4. E2: Online Tuning (03–05/10)

- **Mục đích:** chạy pipeline trên dữ liệu thật để tìm và sửa lỗi chung.
- **Dữ liệu:** 20 case đầu của dataset v2; trần 48 request.
- **Kết quả:** 6/20 case được thử, cả 6 đi hết đường đến cổng kích thước ledger (12 182–12 250 trên
  16 384 byte); 14 case không được thử vì hết ngân sách.
- **Hệ quả:** sửa lỗi phần duyệt khi gặp giá trị rỗng, chuỗi trả tiền trong compiler, kiểm đồng bộ node
  trước khi đo. Không dùng trong báo cáo.
- **Nguồn:** `docs/archive/JOURNAL.md` mục 6; `runs/online-tuning-batch01/`.

## 5. E3: Roleplay (06/10–10/11)

- **Mục đích:** chạy pipeline từ đầu đến cuối trên toàn dataset v2, với một agent đóng vai người dùng
  (chỉ đọc `prompt`).
- **Cách làm và kết quả:**
  - batch 20 (case 1–20, Nemotron): 19/20 đi hết đến cổng kích thước ledger; case đòi xóa lịch sử giao
    dịch dừng đúng ở `UNSUPPORTED`;
  - batch 80 (case 21–57, Nemotron): 34/37 đi hết. Case 57 bị loại khỏi mọi phép đo vì trường đánh giá
    của nó đã bị đọc ngày 27/10; từ đó case 58–100 là tập test đóng;
  - holdout (case 58–100, Gemini): 34 case đi hết, 2 dừng ở ứng viên, 3 chặn ở bước sinh hợp đồng, 1
    chặn ở intent, 3 case bất khả dừng ở `BLOCKED` thay vì `UNSUPPORTED`; tổng 363 request.
- **Hệ quả:** pipeline lúc đó vẫn dùng cách formal hóa DCF. Các hợp đồng E3 sinh ra được dùng làm ứng
  viên thật cho E5. Không dùng làm kết quả trong báo cáo.
- **Nguồn:** `docs/archive/JOURNAL.md` mục 6; `runs/roleplay-main-batch20/`, `runs/roleplay-main-batch80/`,
  `runs/E3-Roleplay-Holdout/`.

## 6. E4: so sánh hai cách formal hóa (RQ1, 27/10–09/11)

- **Mục đích:** yêu cầu tự nhiên được chuyển thành intent đúng nghĩa tốt hơn bằng cách nào: DCF (model
  viết thẳng cấu trúc intent) hay AFF (model chỉ liệt kê dữ kiện nguyên tử, code tất định dựng intent)?
- **Dữ liệu:**
  - dev: case 1–56 của dataset v2, dùng để chỉnh prompt;
  - test: case 58–100 (43 case), chạy đúng một lần trên code ở tag `a2-test-freeze`, mỗi case một mẫu;
  - hai bộ prompt: prompt gốc, và prompt có nêu giờ hết hạn cùng policy token;
  - bộ bổ sung 24 case về mâu thuẫn (`dataset/supplement/conflicts_author_v1.jsonl`).
- **Thước đo:** tỷ lệ core hợp lệ; tỷ lệ quyết định đúng trên core hợp lệ; request cho mỗi intent hợp lệ;
  số lần chấp nhận sai; phép so nghĩa với hợp đồng tham chiếu (`MATCH`, `SUBSET`, `DIFFERENT`).
- **Kiểm định:** McNemar chính xác hai phía trên các case bất đồng; quy tắc quyết định chốt trước.
- **Kết quả (test, 43 case):**

  | Chỉ số | DCF gốc | AFF gốc | DCF có nêu | AFF có nêu |
  | --- | --- | --- | --- | --- |
  | Core hợp lệ | 0,581 | 0,953 | 0,674 | 0,953 |
  | Quyết định đúng trên core hợp lệ | 0,465 | 0,860 | 0,581 | 0,814 |
  | Request cho mỗi intent hợp lệ | 4,24 | 1,90 | 4,10 | 2,02 |
  | Chấp nhận sai | 4 | 0 | 2 | 1 |

  - McNemar: prompt gốc 18 case chỉ AFF đúng, 1 case chỉ DCF đúng, p = 0,0001; prompt có nêu 11 so với 1,
    p = 0,0063.
  - Giữ nghĩa: trong 19 intent AFF chấp nhận, 12 `MATCH`, 4 `SUBSET`, 3 `DIFFERENT` (16%, Wilson 95%
    6–38%).
  - Mâu thuẫn: AFF nhận ra 5/12, DCF 0/12 (p = 0,063). Case bất khả: cả hai sai 3/3.
- **Hệ quả:** chọn AFF. Pipeline cuối cùng (E7) dùng AFF.
- **Nguồn:** `docs/archive/E4-Formalization-Comparison.md`; `docs/evidence/E4-test-freeze-environment.txt`;
  `research/experiments/formalization_eval.py`, `formalization_score.py`, `formalization_stats.py`.

## 7. E5: cổng kiểm tra trên biến thể hợp đồng (RQ2, 09–10/11)

- **Mục đích:** chuỗi cổng kiểm tra có giảm việc chấp nhận hợp đồng sai mà vẫn chấp nhận hợp đồng đúng
  không, và cổng nào đóng góp?
- **Dữ liệu:** biến thể tất định sinh từ hợp đồng tham chiếu của 99 case dataset v2
  (`research/experiments/gate_mutants.py`), bằng 17 toán tử:
  - 13 toán tử làm sai: đổi người nhận; số tiền ×½, ×2, ×10⁶ (lỗi đơn vị lovelace); đổi người nạp; dời hạn
    sớm hoặc muộn 3 ngày; đảo nhánh `If`; đổi chỗ nhánh quá hạn; bỏ một khoản trả; đổi ngưỡng; sai tên token
    ADA; thu hẹp miền lựa chọn;
  - 4 toán tử giữ nguyên nghĩa: đảo thứ tự các `Case`; tách một khoản trả thành hai; bọc trong `If true`;
    dời mọi mốc 3 giờ.

  Nhãn đúng hay sai không lấy theo tên toán tử, mà theo so sánh hành vi có giới hạn với hợp đồng tham chiếu
  (`gate_labels.py`), rồi kiểm lại bằng bộ thực thi Haskell. Tổng 2 259 ứng viên: dev (case 1–56) 1 292,
  test (case 58–100) 967; 1 634 sai, 625 đúng. Phần đúng gồm chính 99 hợp đồng tham chiếu cùng các biến
  thể giữ nguyên nghĩa. Toàn bộ ứng viên, kèm hợp đồng, nhãn và quyết định của từng cổng, nằm trong
  `dataset/rq2_variants.jsonl`. Ngoài ra có các hợp đồng thật do model sinh ra trong E3, nhãn do phân xử tay.
- **Các bậc:** Structure (đối chứng) → Lint → SMT → Alignment → Scenario → Oracle (đầy đủ).
- **Thước đo:**
  - chấp nhận sai = biến thể sai được chấp nhận / tổng biến thể sai;
  - độ phủ = biến thể đúng nhận được kết luận chấp nhận / tổng biến thể đúng;
  - từ chối nhầm = biến thể đúng bị từ chối / tổng biến thể đúng.
- **Quy tắc chốt trước:** chấp nhận sai của Oracle thấp hơn Structure với p < 0,05; độ phủ ≥ 0,80; từ chối
  nhầm ≤ 0,10.
- **Cách làm:** vòng 1 không đạt (độ phủ 0,375; từ chối nhầm 0,462). Vòng 2 sửa ba chỗ trên dev (so tổng
  tiền theo token, kịch bản cách hạn 1 ngày, khám phá đi qua `If` ở gốc), đóng băng ở `E5-Freeze`, rồi chạy
  một lần trên case 58–100.
- **Kết quả:**

  | Tập | Sai / đúng | Chấp nhận sai Structure → Oracle | Độ phủ | Từ chối nhầm |
  | --- | --- | --- | --- | --- |
  | Test 58–100 | 686 / 281 | 1,00 → 0,171 | 0,936 | 0,011 |
  | Gộp 99 case | 1 634 / 625 | 1,00 → 0,190 (0,171–0,209) | 0,944 (0,923–0,960) | 0,008 |

  - Theo cổng: Lint và Alignment không đổi quyết định nào; SMT 1,00 → 0,695; Scenario 0,695 → 0,190; Oracle
    không chặn thêm.
  - Còn 310 biến thể sai lọt qua, 230 trong số đó là dời hạn ±3 ngày ở chỗ kịch bản không chạm tới.
- **Hệ quả:** đạt cả ba điều kiện. Chuỗi cổng được giữ trong pipeline cuối.
- **Nguồn:** `docs/archive/E5-Evidence-Gates.md`, `docs/archive/E5-Adjudication-Rubric.md`;
  `docs/evidence/E5-Adjudication.json`; `research/experiments/gate_*.py`; `runs/e5/`.

## 8. E6: lần chạy đầu của RQ3 và RQ4 (10–12/11)

- **Mục đích:** so toàn bộ pipeline với một LLM đơn thuần (Baseline), cùng model và cùng trần request.
- **Dữ liệu:** dataset v3, 100 case viết tay.
- **Vì sao không dùng:** case 1–29 đã được dùng để sửa pipeline, nên kết quả chính chỉ còn 71 case. Bản rà
  lỗi sau đó (`docs/archive/E6-Failure-Review.md`) cho thấy hai nhánh chưa được đối xử như nhau về quy ước
  và về người dùng mô phỏng. E7 làm lại toàn bộ trên dataset mới với quy ước chung. Số liệu E6 không dùng
  trong báo cáo.
- **Nguồn:** `docs/archive/E6-*.md`; `docs/evidence/E6-Score.json`, `docs/evidence/E6-Adjudication.json`;
  `runs/E6-*`.

## 9. E7: thí nghiệm đầu-cuối (RQ3, RQ4, 12–13/11)

- **Mục đích:** toàn bộ pipeline có làm đúng ý người dùng thường xuyên hơn một LLM đơn thuần không (RQ3),
  và tốn thêm bao nhiêu (RQ4)?
- **Dữ liệu:** dataset v5, 100 case viết tay mới (60 tiếng Việt, 40 tiếng Anh, 20 họ hợp đồng), không case
  nào sinh từ template. Hành vi mong đợi: `converge` 44, `ask_then_converge` 35,
  `flag_conflict_then_converge` 6, `converge_and_decline_extra` 5, `reject_unsupported` 10. Mỗi case có
  prompt, phiếu dữ kiện (điều người dùng biết nhưng chưa nói), đặc tả tham chiếu và kịch bản kiểm. Đóng băng
  ở tag `E7-Dataset-v5` trước khi chạy. Dataset v4 (dùng lại prompt v3) chỉ để chạy thử bộ chạy.
- **Hai nhánh**, cùng `gemini-3.5-flash-lite`:
  - Pipeline: AFF, hỏi lại, duyệt intent, sinh hợp đồng, SMT, kịch bản, khám phá, ledger;
  - Baseline: một LLM tự hỏi và tự viết hợp đồng Marlowe; lỗi cấu trúc và ledger được gửi lại tự động.
  - Trần request của Baseline ở mỗi case bằng số request Pipeline đã dùng ở case đó. Lỗi quota, mạng và
    5xx không tính.
- **Người dùng mô phỏng:** SimUser-v3, mỗi lượt một sub-agent Claude Haiku 5.5 mới, chỉ đọc đầu vào của lượt
  đó. Một bộ kiểm tra tất định áp cùng luật cho cả hai nhánh (gọi lại tối đa 2 lần, rồi dùng câu dự phòng).
  Người vận hành không viết hay sửa câu trả lời nào.
- **Cách chấm:**
  1. máy chạy kịch bản của dataset trên bộ tham chiếu Haskell, mọi hạn lệch tối đa 1 phút;
  2. hợp đồng máy báo lệch, và các case cần biết nhánh có nói rõ phần không làm được, được đóng thành 103 gói
     mù (ẩn tên nhánh), giao cho 8 sub-agent phân xử mới theo bản hướng dẫn viết trước khi chấm;
  3. `research/experiments/e7_analysis.py`, commit trước khi mở kết quả, tổng hợp và kiểm định.
- **Kiểm định:** McNemar chính xác hai phía, α = 0,05; bootstrap theo cặp 10 000 lần, seed 20261111. Quy tắc
  chốt trước: Pipeline mạnh hơn nếu p < 0,05 và chênh lệch thành công dương.
- **Kết quả RQ3:**

  | Chỉ số | Pipeline | Baseline |
  | --- | --- | --- |
  | Thành công | 49 | 18 |
  | Giao hợp đồng sai | 2 | 72 |
  | Không giao | 49 | 10 |

  - Chênh lệch +31 điểm, CI 95% [19; 43]; 39 case chỉ Pipeline đúng, 8 case chỉ Baseline đúng;
    p ≈ 5,5·10⁻⁶. Giao sai: p ≈ 1,7·10⁻²¹. Kết luận: Pipeline mạnh hơn.
  - Nới dung sai giờ lên 1 giờ, 1 ngày, 3 ngày: 49/18, 49/18, 49/19.
  - 71/72 hợp đồng sai của Baseline có lỗi hạn.
- **Kết quả RQ4 (tổng 100 case):** request 684 so với 287; token vào 2 620 648 so với 511 136; token ra
  1 008 415 so với 243 090; thời gian model 8 499,7 s so với 4 200,2 s; tin nhắn người dùng 267 so với 100;
  134 kịch bản được xác nhận; request cho mỗi case thành công 13,96 so với 15,94; Baseline chạm trần ở 28
  case.
- **Sổ lệch giao thức:** D1–D6 (bộ chạy), I1–I3 (hạ tầng: chạy song song hai nhánh bằng key riêng từ case
  31, kiểm tra sớm ở case 28, giữ bộ đếm gọi lại), O1–O2 (quan sát về bản đọc lại kịch bản, giữ nguyên bản
  đóng băng), A1 (script phân tích viết sau đóng băng nhưng commit trước khi mở kết quả). Không lệch nào đổi
  điều mà một nhánh hay người dùng mô phỏng nhìn thấy.
- **Nguồn:** `docs/archive/E7-Protocol.md`, `E7-Conventions.md`, `E7-Dataset-v5-Design.md`,
  `E7-Adjudication-Brief.md`, `E7-Deviations.md`, `E7-Dev-Trial.md`, `E7-Run-Procedure.md`;
  `docs/evidence/E7-Score.json`, `docs/evidence/E7-Adjudication.json`; `runs/E7-Eval-*`. Chấm lại bằng
  `bash tools/e7/score_all.sh` rồi `python -m research.experiments.e7_analysis score`.

## 10. Dataset

Toàn bộ case dùng trong báo cáo được gom vào một file: `dataset/all_cases.jsonl` (mô tả ở
`dataset/README.md`). Các file gốc được giữ nguyên vì SHA đóng băng và các bộ chạy dựa vào chúng.

| Dataset | File gốc | Số case | Dùng cho |
| --- | --- | --- | --- |
| v2 | `dataset/cases.jsonl` | 100 | E2, E3, E4 (RQ1), E5 (RQ2) |
| bộ mâu thuẫn bổ sung | `dataset/supplement/conflicts_author_v1.jsonl` | 24 | E4 (RQ1) |
| v3 | `dataset/v3/cases.jsonl` | 100 | E6 (không dùng trong báo cáo) |
| v4 | `dataset/v4/cases.jsonl` | 100 (dùng lại prompt v3) | chạy thử bộ chạy E7 |
| v5 | `dataset/v5/cases.jsonl` | 100 | E7 (RQ3, RQ4) |
| biến thể RQ2 | `dataset/rq2_variants.jsonl` | 2 259 ứng viên sinh từ v2 | E5 (RQ2) |

Các biến thể RQ2 không phải case viết sẵn, nên nằm ở file riêng. Lệnh
`python -m dataset.rq2_variants --check` sinh lại mọi hợp đồng từ `dataset/cases.jsonl` và so với file.
