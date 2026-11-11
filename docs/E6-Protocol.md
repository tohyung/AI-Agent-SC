# E6 — Giao thức RQ3 và RQ4

Trạng thái: **chốt ngày 2026-11-11, trước mọi lần chạy trên dataset v3.** Ba điểm mở (người dùng mô
phỏng, trần lượt, quy tắc quyết định) do người phụ trách chọn cùng ngày. Mọi thay đổi sau thời điểm
này ghi vào mục "Lệch giao thức". Các quyết định nền và lý do nằm ở
`docs/E6-Plan.md`; dataset nằm ở `dataset/v3/` (SHA-256 `cdc0ea45…e46cc`).

## 1. Câu hỏi

- **RQ3:** với cùng chi phí request trên từng case, hợp đồng cuối của toàn bộ hệ thống (đường AFF) có
  đúng yêu cầu nhiều hơn hợp đồng của một LLM đơn thuần tương tác với người dùng không, và hơn hay kém
  bao nhiêu phần trăm?
- **RQ4:** mỗi nhánh tốn bao nhiêu: request, token vào và ra, lượt của người dùng, thời gian chạy
  model, và tỷ lệ không giao ra hợp đồng.

## 2. Hai nhánh

Cả hai nhánh dùng cùng model (`gemini-3.5-flash-lite`, free tier), cùng cấu hình transport
(`max_tokens = 16000`, reasoning thấp nhất, không bật JSON mode), cùng cách giãn request (5 giây).

| | Nhánh Pipeline | Nhánh Baseline |
| --- | --- | --- |
| Mã | `research.experiments.roleplay_case --formalization AFF` | `research.experiments.baseline_llm` |
| Cách làm | toàn bộ pipeline: AFF, người dùng chấp nhận intent, sinh hợp đồng, SMT, so sánh, khám phá, ledger | model sinh hợp đồng thẳng từ hội thoại (prompt `Baseline-Chat-v1`) |
| Kiểm tra | các cổng của pipeline | kiểm cấu trúc (`validate_contract`), rồi phân tích kích thước giao dịch trên ledger |
| Bộ chạy trong WSL | `tools/e6/run_wsl.sh research.experiments.roleplay_case --dataset v3 --formalization AFF --provider gemini` | `tools/e6/run_wsl.sh research.experiments.baseline_llm --pipeline-case-dir runs/E6-Pipeline/case-NNN` |
| Khi kiểm không qua | pipeline tự sửa theo chính sách của nó | lỗi của công cụ được tự động chuyển lại cho model, như người dùng dán lỗi vào chat |
| Trần request | không trần (`max_llm_calls = 99999`) | đúng số request nhánh Pipeline đã dùng cho case đó |

**Chạy theo thứ tự:** mỗi case chạy nhánh Pipeline trước, đến khi kết thúc. Số request đếm được của
nhánh Pipeline (tổng trên mọi lần chạy của case, `baseline_llm.pipeline_requests`) thành trần của
nhánh Baseline trên case đó. Cả hai nhánh dùng cùng một quy tắc đếm (`baseline_llm.is_counted`).

**Đếm request (E6-Plan, quyết định 4):** mỗi lần gọi model nhận được phản hồi đều tính, kể cả phản
hồi lỗi và lượt sửa JSON. Lỗi quota (429) và lần gọi không nhận được phản hồi thì không tính; lần
chạy dừng lại và được chạy tiếp sau. Nhánh Baseline đặt ngân sách transport bằng phần trần còn lại,
nên lượt sửa JSON không vượt trần được.

**Ledger:** cả hai nhánh đều cần testnet riêng (magic 42123) đang chạy. Ledger không sẵn thì lần
chạy dừng, không tính là lỗi của hợp đồng. Kết quả "không có giao dịch để đo kích thước" (hợp đồng
chỉ có `Close`) tính là qua, vì người dùng không thấy lỗi nào.

**Chỉnh sửa:** prompt `Baseline-Chat-v1` và pipeline chỉ được thử và chỉnh trên dev cũ (dataset v2,
case 1–56, cờ `--dataset dev`). Từ lần chạy đầu tiên trên v3, không chỉnh gì nữa, trừ lỗi của bộ
chạy (harness); lỗi đó ghi vào "Lệch giao thức".

## 3. Người dùng mô phỏng

**Ai đóng vai (đã chốt):** Claude đóng vai bằng tay cho cả hai nhánh, như ở E3, theo cùng quy tắc
dưới đây. Không dùng LLM thứ hai đóng vai người dùng: cách đó tốn thêm quota và thêm một nguồn lỗi.

Quy tắc chung cho cả hai nhánh:

1. Chỉ dùng prompt và `fact_sheet` của case. Không đọc `spec`, `reference_contract` hay `checks`
   trong lúc chạy.
2. Model hỏi điều có trong phiếu: trả lời đúng câu trong phiếu, chỉ phần được hỏi.
3. Model hỏi điều không có trong phiếu và cũng không có trong prompt: trả lời "tôi không có yêu cầu
   gì thêm về điểm này, bạn chọn cách hợp lý". Không tự đặt ra dữ kiện mới (đây là bài học từ E5,
   nơi dữ kiện người dùng mô phỏng tự đặt ra đã làm lật 31 nhãn).
4. Khi đọc hợp đồng hay intent mà model trình bày, người dùng chỉ dựa vào lời giải thích bằng ngôn
   ngữ thường (nhánh Baseline) hoặc bản intent pipeline đưa ra (nhánh Pipeline). Không chạy kịch bản
   trên bộ thực thi, không đọc JSON hợp đồng.
   - Khớp với prompt và phiếu: chấp nhận.
   - Không khớp: chỉ ra một điểm sai, mỗi lượt một câu.
5. Model từ chối (`decline`) hoặc nói một phần yêu cầu không làm được: người dùng chấp nhận nếu điều
   đó đúng với yêu cầu thật; nếu không, nhắc lại yêu cầu một lần.
6. **Riêng nhánh Pipeline,** người dùng làm theo các bước pipeline đòi hỏi, như ở E3:
   - trả lời câu hỏi bằng một revision (`--revision-file`);
   - duyệt intent (`--review-candidate-id`) theo quy tắc 4;
   - sau khi hợp đồng được sinh, viết kịch bản mong đợi (`--expectation-file`, phát lại hợp đồng bằng
     `--replay-contract-id`, xác nhận bằng `"dong y"`). Mỗi kết cục mà yêu cầu nêu ra (mỗi nhánh
     lựa chọn, mỗi lần hết hạn) có một kịch bản. Kịch bản viết từ prompt, phiếu dữ kiện và bản intent;
     không đọc JSON hợp đồng.

   Phần công này nhánh Baseline không có, vì người dùng chatbot không viết kịch bản. Nó được báo riêng
   ở RQ4 (`intent_reviews`, `scenarios`).
7. **Trần lượt của người dùng (đã chốt): không có.** Chỉ trần request giới hạn nhánh Baseline. Người
   dùng chỉ bỏ cuộc (`--give-up`) khi model hỏi lại cùng một điều đã được trả lời đủ ba lần liền; khi
   đó hợp đồng đã qua kiểm tra gần nhất (nếu có) vẫn được tính là hợp đồng giao ra. Số tin nhắn của
   người dùng được báo cho cả hai nhánh (RQ4).

## 4. Kết quả của một case

**Hợp đồng giao ra:**

- Nhánh Pipeline: hợp đồng của lần chạy cuối mà bước `ledger_validation` qua (trạng thái
  `SIMULATED_LEDGER_SIZE_CHECKED`; bước testnet và deployment bị tắt theo thiết kế).
- Nhánh Baseline: hợp đồng qua kiểm tra gần nhất, lúc người dùng chấp nhận, bỏ cuộc hoặc lúc chạm
  trần request.

**Phân xử:** theo `docs/E5-Adjudication-Rubric.md`, đối chiếu với yêu cầu người dùng mô phỏng đã xác
nhận (prompt, phiếu dữ kiện và các câu trả lời trong lượt chạy đó). Có hai thay đổi so với E5:

- **Phân xử mù nhánh:** hợp đồng của hai nhánh được trộn, mỗi hợp đồng mang một mã ngẫu nhiên. Bảng
  ánh xạ mã sang nhánh chỉ được mở sau khi ghi xong mọi phán quyết.
- **Hành vi mong đợi** (`expected_behavior`) được chấm như sau.

| `expected_behavior` | Case THÀNH CÔNG khi |
| --- | --- |
| `converge`, `ask_then_converge` | giao ra hợp đồng ĐÚNG |
| `flag_conflict_then_converge` | giao ra hợp đồng ĐÚNG với yêu cầu đã chốt sau đính chính |
| `converge_and_decline_extra` | giao ra hợp đồng ĐÚNG, và có nói rõ với người dùng rằng phần thêm (ví dụ gửi email) không làm được |
| `reject_unsupported` | không giao ra hợp đồng, và có nói với người dùng là không làm được |

Nếu không THÀNH CÔNG, case được xếp vào một trong bốn loại sau (`e6_score.classify`):

- **giao ra hợp đồng SAI**, gồm cả trường hợp giao ra hợp đồng cho case bất khả;
- **không giao ra;**
- **ĐÚNG nhưng không báo** phần thêm không làm được (`converge_and_decline_extra`);
- **KHÔNG XÁC ĐỊNH**, loại khỏi các tỷ lệ và báo riêng.

Bộ chấm là `research.experiments.e6_score`. Lệnh `packets` ghi các gói phân xử đã trộn
(`packets.jsonl`) và khóa mã (`blind-key.json`, chỉ mở khi chấm). Lệnh `score` tính các chỉ số ở
mục 5 và 6.

## 5. Chỉ số

- **Chính (RQ3):** tỷ lệ THÀNH CÔNG trên 100 case, của từng nhánh.
- **Phụ (RQ3):**
  - tỷ lệ giao ra hợp đồng SAI;
  - tỷ lệ không giao ra;
  - tách theo `expected_behavior`, họ hợp đồng và ngôn ngữ.
- **RQ4, theo từng case và tổng:**
  - request đếm được;
  - token vào và ra;
  - số tin nhắn của người dùng mô phỏng;
  - số lỗi được chuyển tự động (nhánh Baseline);
  - thời gian chạy model.

  Thêm hai chỉ số: số request trên mỗi case THÀNH CÔNG, và tỷ lệ case mà nhánh Baseline dừng vì chạm
  trần.

## 6. Quy tắc quyết định (đã chốt)

- **So sánh theo cặp** trên cùng 100 case. Gọi Δ là tỷ lệ THÀNH CÔNG của Pipeline trừ tỷ lệ của
  Baseline. Báo Δ theo điểm phần trăm, khoảng tin cậy 95% (bootstrap theo cặp, 10 000 lần), và mức hơn
  tương đối Δ / tỷ lệ Baseline.
- **Kiểm định:** McNemar chính xác, hai phía, α = 0,05, trên các case mà hai nhánh khác kết quả.
- **Kết luận:**
  - **"Pipeline mạnh hơn"** khi Δ > 0 và p < 0,05.
  - **"Baseline mạnh hơn"** khi Δ < 0 và p < 0,05.
  - Các trường hợp còn lại: **"chưa phân biệt được"**, kèm khoảng tin cậy.
- **An toàn,** kết luận riêng: so tỷ lệ giao ra hợp đồng SAI bằng cùng phép kiểm.
- **Chạy thử:** 20 case đầu theo thứ tự của file (lần chạy thật, kết quả được giữ). Sau chạy thử chỉ
  được sửa lỗi bộ chạy. Không xem kết quả theo nhánh để quyết định có chạy tiếp hay không.

## 7. Chuẩn bị (xong ngày 2026-11-11)

1. `roleplay_case --dataset v3` đọc dataset v3 (chỉ `id`, `prompt`, `language`), chỉ cho chạy AFF, và
   ghi bằng chứng vào `runs/E6-Pipeline/`. Bản ghi mỗi lần chạy lưu thêm intent đã duyệt và kịch bản
   mong đợi.
2. Testnet riêng (magic 42123) được dựng lại bằng `tools/e6/start_testnet.sh`. `tools/e6/run_wsl.sh`
   tự dùng socket mới nhất trong `/tmp`.
3. Chạy thử trên dev (thư mục tạm, không thuộc kết quả):
   - Baseline, case dev 1–3: giao ra hợp đồng ở cả ba case. Case 2 có 2 lỗi cấu trúc được tự chuyển
     lại cho model, rồi qua ledger (12 238 / 16 384 byte).
   - Pipeline AFF, case dev 3: tới `REACHED_LEDGER_PASS` với 9 request và 35 375 token vào. Baseline
     trên cùng case dùng 2 request và 2 102 token vào. AFF hỏi lại giờ của hạn thứ hai dù câu trả lời
     đã nêu rõ; nó chỉ hiểu sau một revision viết lại.
   - Hai lỗi bộ chạy được sửa nhờ lần chạy thử này:
     - phát lại candidate AFF đã duyệt cần phát lại mọi FactDraft đã lưu, kể cả bản lỗi, để giữ nguyên
       mã candidate (`FactDraftReplayModel`);
     - một test toolchain vẫn ngầm dùng DCF sau khi AFF thành mặc định.
4. Bộ chấm `e6_score` có test cho bảng phân loại, McNemar chính xác, bootstrap và gói mù. Transport
   ghi thời gian của mỗi lần gọi model (`seconds`).

## 8. Giới hạn đã biết

- Một người (Claude) vừa viết case, vừa làm thí nghiệm, vừa đóng vai người dùng, vừa phân xử. Phân xử
  mù nhánh chỉ giảm phần nào thiên vị: văn phong của hợp đồng có thể để lộ nhánh.
- Người dùng mô phỏng của nhánh Pipeline duyệt bản intent có cấu trúc và viết kịch bản mong đợi;
  người dùng của nhánh Baseline chỉ đọc lời giải thích. Đây là khác biệt có chủ ý (hệ thống đưa cho người dùng nhiều thông tin
  hơn), nhưng nó cũng làm hai nhánh không hoàn toàn cân xứng.
- Không có trần lượt của người dùng; nhánh Pipeline không có trần request. Một case khó có thể làm
  nhánh Pipeline tốn nhiều request, và vì vậy nhánh Baseline cũng được trần cao.
- Ledger chỉ đo kích thước giao dịch. Qua ledger không có nghĩa là hợp đồng đúng.
- Kết quả chỉ áp dụng cho một model nhỏ, free tier; với model lớn hơn, nhánh Baseline có thể thu
  hẹp khoảng cách.
- 100 case cho độ chính xác vừa phải. Nếu Δ dưới khoảng 10 điểm, khả năng cao là chưa phân biệt được.

## Lệch giao thức

(chưa có)
