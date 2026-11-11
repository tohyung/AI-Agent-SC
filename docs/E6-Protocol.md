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

1. **Không dừng sau chạy thử (2026-11-11, trước lần chạy đầu tiên trên v3).** Người phụ trách quyết định
   chạy liền cả 100 case thay vì dừng sau 20 case đầu. Chạy thử vốn đã tính vào kết quả và không cho
   chỉnh gì ngoài lỗi bộ chạy, nên quy tắc quyết định không đổi.
2. **Công cụ đóng vai** (`tools/e6/show.py`, `tools/e6/expect.py`, `tools/e6/pipe.sh`,
   `tools/e6/base.sh`), thêm trước lần chạy đầu tiên. `show.py` chỉ in những gì người dùng mô phỏng
   được thấy (prompt, phiếu dữ kiện, câu hỏi, intent, lời giải thích của model), không in đặc tả, hợp
   đồng tham chiếu, kịch bản kiểm, hành vi mong đợi hay JSON hợp đồng.
3. **Người dùng mô phỏng bán tự động (2026-11-11, người phụ trách duyệt, sau case 1).** Thay cho quy
   tắc 2, 3, 4 và 7 của mục 3, áp dụng như nhau cho hai nhánh (`research/experiments/e6_user.py`,
   `tools/e6/auto.py`):
   - Model hỏi: bộ chạy dừng, in câu hỏi và câu trả lời tự động. Câu trả lời tự động là cả phiếu dữ
     kiện; phiếu trống thì là câu cố định "không có thêm thông tin, làm đúng như đã nêu". Lần tự động
     thứ hai là "không có thông tin nào khác".
   - Người dùng chọn một trong ba:
     - gửi câu tự động;
     - nhắc lại điều prompt đã nói, khi câu hỏi có đáp án sẵn trong prompt (không thêm dữ kiện; lần
       trả lời đầu thì kèm phiếu dữ kiện nếu có);
     - bỏ cuộc, khi cùng câu hỏi quay lại sau hai lần đã trả lời.

     Mọi câu trả lời và lựa chọn được ghi vào `replies.json` của case.
   - Intent của Pipeline, hợp đồng và lời từ chối của Baseline được chấp nhận tự động; đúng sai do
     phân xử mù quyết định.
   - Kịch bản mong đợi của Pipeline vẫn do người dùng viết từ prompt, phiếu và intent, một lần cho mỗi
     case (`scenarios.json`); bộ chạy tự nạp chúng ở cổng Scenario và dừng ở kịch bản đầu tiên không
     qua.

   Lý do: ở case 1, AFF hỏi múi giờ dù prompt ghi "giờ VN". Câu trả lời cố định không giải được câu
   hỏi đó, nên nhánh hay hỏi sẽ bị phạt nặng hơn với người dùng thật. Hai lần chạy case 1 theo cách cũ
   (đóng tay; chỉ câu cố định) được giữ ở `runs/E6-Discarded/` và không tính.
4. **Sửa bước compile và chạy lại từ đầu (2026-11-11, người phụ trách duyệt, sau case 1–4).**
   - **Lỗi:** ở 3/4 case đầu, LLM của bước compile viết một bên của intent thành
     `{"address": "<tên>"}` thay vì `{"role_token": "<tên>"}`. Kịch bản viết theo vai không gắn được
     vào hợp đồng, cổng Scenario báo INCONCLUSIVE và pipeline dừng. E3 (DCF) đã gặp lỗi này ở 3 case.
   - **Sửa** (`research/synthesis/llm_generator.py`): prompt nói rõ mọi bên của intent là vai; một bên
     `address` mang tên người trong intent bị trả lại thành chẩn đoán, để vòng sinh lại sửa, giống cách
     đang làm với token ADA sai.
   - **Kiểm không dùng v3:** sinh lại từ 10 intent đã duyệt của E3 (case 58–100 của dataset v2). Prompt
     cũ: một hợp đồng có 12 chỗ `address`. Prompt mới: không còn chỗ nào. Tỷ lệ hợp đồng lần đầu sai
     cấu trúc (`deposit` thay `deposits`) là 7/10 ở cả hai prompt; vòng sinh lại của pipeline xử lý lỗi
     này.
   - **Hệ quả:** lỗi được phát hiện nhờ nhìn kết quả của 4 case v3. Lần chạy trước sửa của case 1–4 (cả
     hai nhánh) được giữ ở `runs/E6-Discarded/before-role-fix/` và không tính. E6 chạy lại từ case 1
     với cùng quy tắc; trần của Baseline lấy từ lần chạy mới của Pipeline.
5. **Trích dẫn không phân biệt hoa thường (2026-11-11, người phụ trách yêu cầu, sau case 1–2 của lần
   chạy thứ hai).** AFF trích "giờ VN là giờ Việt Nam (UTC+7)" trong khi tin nhắn viết "Giờ VN…"; builder
   đòi khớp nguyên văn nên cả 4 lần draft đều hỏng và pipeline dừng ở case 1. `fact_builder` giờ khớp
   trích dẫn bỏ qua hoa thường và khoảng trắng, rồi thay bằng đúng đoạn gốc, nên bằng chứng vẫn là
   nguyên văn; trích dẫn khác chữ vẫn là lỗi. Dựng lại offline 4 draft đã hỏng của case 1: draft đầu
   qua, đúng mốc giờ. Lượt chạy case 1–2 trước bản sửa được giữ ở
   `runs/E6-Discarded/before-span-fix/` và không tính; E6 chạy lại từ case 1.
6. **Múi giờ ghi bằng tên (2026-11-11, người phụ trách yêu cầu, cùng lúc với mục 5, trước khi chạy lại).**
   Builder chỉ nhận "+7", "UTC+7"… là bằng chứng của +07:00, nên AFF hỏi lại múi giờ ở mọi case ghi
   "giờ VN", và draft trích "giờ VN" bị từ chối. Builder giờ nhận "giờ VN", "giờ Việt Nam", "giờ Hà
   Nội", "giờ Sài Gòn", "Vietnam time", "ICT", "Asia/Ho_Chi_Minh" (có hoặc không dấu) là +07:00; prompt
   của AFF nói rõ múi giờ ghi bằng tên là đã ghi (`Formalization-FactPrompt-v6`). Các múi giờ khác
   không đổi. Dựng lại offline 4 draft cũ của case 1: 2 draft qua; 2 draft còn lại không trích chỗ
   nào về múi giờ nên vẫn bị từ chối, đúng như mong đợi.
7. **Giờ 12 tiếng (2026-11-11, sau case 1–6 của lần chạy thứ ba).** Builder đòi thấy số 20 trong trích
   dẫn của giờ 20:00, nên "8:00 PM" bị từ chối ("hour 20 not in evidence"). Model phải để trống giờ rồi
   hỏi lại, dù phiếu dữ kiện đã nêu giờ. Builder giờ nhận giờ 12 tiếng ("8:00 PM", "8 p.m.", "2 giờ
   chiều", "9h tối", "12:00 AM"). Prompt và trích dẫn của case 1–6 không có giờ 12 tiếng, nên bản sửa
   không đổi gì với các case đó; chúng được giữ. Lượt chạy case 7 trước bản sửa được giữ ở
   `runs/E6-Discarded/before-12h-fix/` và không tính; case 7 chạy lại từ đầu.
8. **Khóa `deposit` số ít (2026-11-11, người phụ trách yêu cầu, sau case 1–10).** Ở case 9 và 10, model
   compile viết khóa `deposit` thay vì `deposits` hai lần liền; chẩn đoán của validator không làm nó
   sửa, nên pipeline dừng (`generation_stalled`). Bước compile giờ đổi tên khóa đó khi hành động có
   đúng các trường còn lại của Deposit (cách viết này không có nghĩa nào khác), và ghi các đường dẫn
   đã đổi vào `normalized_deposit_keys`. Chỉ thêm khi có đổi, nên hợp đồng không đổi giữ nguyên mã;
   prompt không đổi. Case 1–8 không có khóa này nên được giữ. Dựng lại offline: cả 4 output hỏng của
   case 9–10 hợp lệ sau khi đổi tên. Lượt chạy cũ của case 9–10 (cả hai nhánh) được giữ ở
   `runs/E6-Discarded/before-deposit-fix/` và không tính.
9. **Dấu phân cách hàng nghìn (2026-11-11, sau case 1–14).** Prompt case 15 ghi "1,200 ADA". Draft ghi
   "1200" thì builder không thấy "1200" trong trích dẫn; draft ghi "1,200" thì không đọc được thành số.
   Pipeline dừng sau 4 draft. Builder giờ tìm số trong cả trích dẫn đã bỏ dấu phân cách giữa các nhóm 3
   chữ số ("1,200", "1.200", "1 200"); cách ghi số trong draft không đổi. Case 1–14 không có số có dấu
   phân cách nên được giữ. Dựng lại offline: draft đầu của case 15 qua (1 200 ADA gốc, 1 260 ADA trả).
   Lượt chạy cũ của case 15 (cả hai nhánh) được giữ ở `runs/E6-Discarded/before-grouping-fix/`.
10. **Revision sau chốt được mâu thuẫn (2026-11-11, sau case 1–15).** Builder coi mọi lựa chọn khác giá
    trị là mâu thuẫn, kể cả khi revision sau của người dùng đã chốt một giá trị. Vì vậy case 16 (310 hay
    320 ADA) hỏi mãi, và mọi case có mâu thuẫn đều không thể hội tụ. Builder giờ coi mâu thuẫn là đã chốt
    khi tin nhắn mới nhất được trích là một revision (từ phiên bản 2), chỉ ủng hộ một giá trị, và không
    lựa chọn nào khác trích tin nhắn đó hoặc tin nhắn sau hơn. Mâu thuẫn trong cùng một tin nhắn vẫn được
    hỏi. Case 1–15 không có câu hỏi mâu thuẫn nên được giữ. Dựng lại offline: draft của case 16 cho 320
    ADA, không còn câu hỏi. Lượt chạy cũ của case 16 được giữ ở `runs/E6-Discarded/before-conflict-fix/`.
11. **Rà soát một lần các kiểm bằng chứng của builder (2026-11-11, người phụ trách yêu cầu, sau case
    1–18).** Thay vì sửa từng lỗi khi gặp, builder được rà một lượt trên dữ liệu không thuộc v3 (các lỗi
    draft của E4 trên dataset v2: 45 trích dẫn diễn đạt lại là lỗi thật của model, 12 khác hoa
    thường/khoảng trắng đã sửa ở mục 5, cộng số viết bằng chữ). Sửa cùng lúc:
    - một múi giờ nêu một lần cho cả yêu cầu áp dụng cho mọi mốc giờ khi lịch sử yêu cầu không nêu múi
      giờ nào khác (case 19: "(giờ VN)" ở cuối câu có ba mốc);
    - số viết bằng chữ tiếng Anh và tiếng Việt ("two hundred fifty", "bảy mươi", "một trăm") và dấu
      phẩy thập phân ("1,5 ADA") được tính là nêu số đó (`research/formalization/number_words.py`);
    - trích dẫn và tên người được khớp bỏ qua dấu tiếng Việt (prompt không dấu, model trích có dấu), rồi
      thay bằng đúng đoạn gốc.

    Mọi trích dẫn khác chữ vẫn là lỗi. Để mọi case chạy trên cùng một phiên bản, toàn bộ lượt chạy trước
    đó (case 1–19, cả hai nhánh) được giữ ở `runs/E6-Discarded/before-evidence-fixes/` và không tính; E6
    chạy lại từ case 1. Các mục 4–11 là sửa lỗi bộ chạy và builder trước kết quả chính thức; báo cáo
    tóm tắt chúng trong một đoạn.
    Bổ sung sau case 1–6 của lần chạy lại: builder chỉ coi tên viết thường là từ chỉ vai, nên "I",
    "Tôi", "Buyer" lọt thành tên người (case 7: người mua thành "I" thay vì "Ethan"). Thêm danh sách
    đại từ và từ chỉ vai phổ biến (giữ dấu: "mình" là đại từ, "Minh" là tên). Case 1–6 dùng tên riêng
    nên được giữ; lượt chạy cũ của case 7 ở `runs/E6-Discarded/before-role-word-fix/`.
    Khi tên một bên là đại từ hoặc từ chỉ vai, builder hỏi người dùng tên người đó, thay vì báo lỗi
    draft. Chỉ báo lỗi thì model không biết tên (nó chỉ có trong phiếu dữ kiện), nên ở lần chạy thử
    case 7 dừng sau 4 draft mà không hỏi gì. Lượt chạy đó ở `runs/E6-Discarded/before-name-question/`.
    Bổ sung ở case 20:
    - bộ chạy coi lần gọi compile không nhận được phản hồi (`provider_request_failed`) là kết thúc của
      Pipeline và đã chạy Baseline với trần đó. Bộ chạy giờ coi đây là lỗi hạ tầng và chạy tiếp; lượt
      Baseline sai được giữ ở `runs/E6-Discarded/driver-infra-bug/`;
    - binder của kịch bản đòi đúng một hành động Choice khớp. Một hợp đồng có cùng ChoiceId ở nhiều kỳ
      thì không gắn được, dù các hành động đó nhận cùng một input. Binder giờ chấp nhận khi mọi hành
      động khớp có cùng ChoiceId. Case 1–19 không gặp trường hợp này.
    Bổ sung ở case 21: tên chỉ khớp bản gốc sau khi bỏ dấu ("Nhân" cho "Nhan") được viết lại theo đúng
    cách viết của người dùng, để validator của core tìm thấy nguyên văn. Lượt chạy trước đó ở
    `runs/E6-Discarded/before-name-spelling/`.
12. **Lỗi máy chủ ở bước compile (2026-11-11, case 22).** Gemini trả lỗi 500 cho mọi lần sinh hợp đồng
    vesting có thu hồi của case 22 (3 lần chạy, mỗi lần 3 lời gọi). Lỗi 500 là phản hồi nên được tính
    là request (mục 2). Bộ chạy coi lần chạy compile không có phản hồi dùng được là lỗi hạ tầng và chạy
    lại; sau 3 lần chạy như vậy, case kết thúc là Pipeline không giao ra (`compile_model_failed`).
    Ngay sau đó, case 23 (hợp đồng nhỏ) cũng gặp lỗi 500, và một lần gọi thử bước compile cho cùng
    intent cho thấy lỗi chập chờn ở cả hai key (key 2 thành công ở lần gọi thứ hai). Đây là sự cố phía
    máy chủ, không phải kết quả của case, nên lượt chạy case 22–23 (cả hai nhánh) được giữ ở
    `runs/E6-Discarded/gemini-500-outage/` và chạy lại khi Gemini ổn định. Luật 3 lần vẫn áp dụng cho
    lần chạy lại.
13. **Lỗi máy chủ 5xx không tính là request (2026-11-11, sau case 1–22).** Trong đợt Gemini trả lỗi 500,
    4/5 request của Baseline ở case 22 là lỗi 500. Đếm chúng làm nhánh nào gặp sự cố bị thiệt, và làm
    trần của Baseline bị đội lên theo các lỗi 500 của Pipeline. Luật đếm của cả hai nhánh
    (`baseline_llm.is_counted`) giờ bỏ qua lỗi máy chủ 5xx, như lỗi quota và lỗi mạng. Tính lại trần
    cho case 1–21: 13 case Baseline dùng không quá trần mới nên được giữ. Case 6 và 14 từng chạm trần
    vì một lỗi 500 bị tính, nên Baseline của chúng được chạy lại với trần mới (vẫn chạm trần, không giao
    ra). Trường `cap` lưu trong các session cũ là trần cũ; bộ chấm tính lại chi phí theo luật mới.
    Bổ sung ở case 27: "noon", "midday", "trưa" được tính là nêu giờ 12, và "midnight", "nửa đêm" là
    giờ 0. Case 1–26 không có các chữ này. Lượt chạy cũ của case 27 ở
    `runs/E6-Discarded/before-noon-fix/`. Bộ chạy cũng phân biệt lỗi máy chủ của Baseline (đợi 60 giây
    rồi thử lại, tối đa 3 lần) với lỗi quota (đổi key).
