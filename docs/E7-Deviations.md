# E7: nhật ký lệch giao thức

Ghi theo `docs/E7-Protocol.md`, mục 6. Mỗi mục: thời điểm, thay đổi, lý do, case bị ảnh hưởng, cách xử lý.

## D1 (2026-11-12, trước case 1 của v5, sau lượt đầu): cách giao đầu vào cho sub-agent

- **Thay đổi:** sub-agent `sim-user` tự đọc tệp `simuser-input.txt` của case bằng công cụ Read, thay vì
  người điều khiển dán nội dung tệp vào lời gọi. Câu trả lời được ghi bằng `tools/e7/audit_agent.py`.
  Script này kiểm nhật ký của sub-agent rồi mới gọi `auto.py reply`.
- **Lý do:** dán lại toàn bộ hội thoại ở mỗi lượt tốn khoảng 5 nghìn token của phiên điều khiển. Với
  100 case thì không chạy nổi trong ngân sách.
- **Ảnh hưởng tới điều sub-agent thấy:** không có. Nội dung tệp giống hệt nội dung từng được dán.
- **Kiểm tra mới, chặt hơn trước:** mỗi lượt kiểm từ nhật ký rằng mọi tin nhắn đến từ
  `claude-haiku-5-5` ở effort medium, chỉ có đúng một lần Read đúng tệp đầu vào, và đúng một lần trả
  kết quả. Lượt nào không đạt thì không được ghi.
- **Cũng ghi lại:** tệp meta của sub-agent có dòng `pickedEffortModel: claude-opus-5-5`, nhưng nhật ký cho
  thấy mọi tin nhắn của các sub-agent đã chạy (127 tin nhắn) đều là `claude-haiku-5-5`.
- **Case bị ảnh hưởng:** lượt đầu của case 1 (Pipeline) đã dùng cách dán; các lượt sau dùng cách đọc
  tệp. Nội dung như nhau, nên giữ nguyên.
- **Bổ sung (cùng ngày):**
  - `tools: []` trong định nghĩa `sim-user` thật sự có hiệu lực: sub-agent chỉ có công cụ trả kết quả,
    nên không tự đọc được tệp. Dòng "All tools" trong danh sách agent là hiển thị sai.
  - Để dùng cách đọc tệp, định nghĩa được đổi thành `tools: Read`; phần luật SimUser-v3 giữ nguyên. Mã
    băm của tệp agent vì thế đổi so với mục 1 của giao thức.
  - Định nghĩa agent chỉ được nạp lại ở phiên mới, nên cách đọc tệp chỉ dùng được trong các phiên chạy
    sau. Hai lượt thử trong phiên hiện tại báo không có Read và không ghi gì vào case 1.

## D2 (2026-11-12, case 10 của v5): bộ chạy tiếp tục sai sau khi testnet treo

- **Hiện tượng:** lần chạy kịch bản thứ nhất của case 10 (nhánh Pipeline) gặp ledger UNAVAILABLE vì
  testnet ngừng tạo block, và bộ chạy thoát đúng với mã 4. Khi chạy lại, `auto.py pipe` không nhận ra
  case đang ở giữa bước chạy kịch bản. Nó ghi `final.json` (`pipeline_stopped`) quá sớm thay vì chạy
  tiếp.
- **Sửa (hạ tầng):** thêm `_resume_scenarios` vào `tools/e7/auto.py`. Khi đã có `scenarios.json`, bộ
  chạy tìm lần sinh hợp đồng của intent đã duyệt và chạy lại mọi kịch bản trên hợp đồng đó. Nếu lỗi xảy
  ra ngay ở bước duyệt thì chạy lại bước duyệt, không hỏi lại người dùng.
- **Không đổi:** điều mà hai nhánh hay người dùng mô phỏng nhìn thấy.
- **Case bị ảnh hưởng:** chỉ case 10. `final.json` sai được cất vào
  `runs/E7-Eval-Discarded/case-010/`. Bước chạy kịch bản được làm lại trên cùng hợp đồng, không có
  request model mới. Nhánh Baseline của case 10 chạy sau khi sửa, với trần là 3 request của Pipeline.
- **Testnet:** chuỗi ngừng tạo block hai lần dù tiến trình vẫn chạy (slot 8712 và slot 1384). Cả hai
  lần đều được khởi động lại. Không kết quả nào khác bị ảnh hưởng.

## D3 (2026-11-12, case 13 của v5): lỗi mạng khi đổi ví dụ thành kịch bản

- **Hiện tượng:** lần gọi Gemini để đổi ví dụ thành kịch bản bị timeout (APITimeoutError sau 183 s),
  tức không có phản hồi của model. Bộ chạy lại coi đó là lần đổi thất bại: nó hỏi người dùng ví dụ lần
  nữa và tính là một trong hai lượt cho phép. Như vậy kết quả phụ thuộc mạng, trái với mục 2.2 và mục 6
  của giao thức.
- **Sửa (hạ tầng):** `tools/e7/auto.py` gọi lại tối đa 3 lần, cách nhau 60 s, khi không có phản hồi
  (lỗi mạng, timeout, 5xx); hết quota thì đổi key. Nếu vẫn lỗi thì lưu ví dụ đang chờ, đặt trạng thái
  `converting` và thoát (mã 4, hoặc 3 nếu hết quota). Lần chạy sau đổi lại đúng các ví dụ đó, không hỏi
  lại người dùng, không tính lượt.
- **Case bị ảnh hưởng:** chỉ case 13. Lượt hỏi lại ví dụ được rút lại trước khi sim-user thấy; bộ đếm
  lượt về 0; lần gọi lỗi được cất vào `runs/E7-Eval-Discarded/case-013/`. Lần gọi đó không có phản hồi
  nên không được tính request. Lần đổi lại thành công với đúng câu trả lời đã lưu.
- **Kiểm tra:** case 1–12 không có lần đổi ví dụ nào gặp lỗi này.

## D4 (2026-11-12, case 15 của v5): bước sinh hợp đồng không có phản hồi rồi bị kẹt khi chạy tiếp

- **Hiện tượng:** ở bước duyệt, lần gọi Gemini để sinh hợp đồng bị `provider_request_failed`
  (attempt-006), tức không có phản hồi của model. Khi chạy tiếp, `_resume_scenarios` lấy chính lần thất
  bại đó làm "hợp đồng đã sinh". Vì vậy `_scenarios` lần nào cũng thoát với mã 4 mà không gọi model
  lại. Case kẹt mãi, và giới hạn `MAX_COMPILE_FAILURES` = 3 không bao giờ được đếm tới.
- **Sửa (hạ tầng):** nếu lần duyệt gần nhất của intent đã chốt mà bước sinh hợp đồng không có phản hồi
  (`provider_request_failed` hoặc `provider_limit`), bộ chạy chạy lại bước duyệt đó. Không hỏi lại
  người dùng và không tính lượt. Sau 3 lần như vậy, case kết thúc với `compile_model_failed`, như luật
  đã có.
- **Không đổi:** điều mà hai nhánh hay người dùng mô phỏng nhìn thấy. Lần gọi lỗi không có phản hồi nên
  không được tính request.
- **Case bị ảnh hưởng:** chỉ case 15. Case 1–14 không có lần sinh hợp đồng nào gặp lỗi này khi chạy
  tiếp.
- **Kiểm tra:** thêm hai test trong `tests/experiments/test_e7_driver.py`.

## D5 (2026-11-12, case 17 của v5): không kết thúc case vì bước sinh hợp đồng gặp lỗi máy chủ

- **Hiện tượng:** bộ chạy kết thúc case 17 với `compile_model_failed` sau 3 lần sinh hợp đồng
  (attempt-005..007). Mọi lần gọi lỗi trong 3 lần đó đều là `InternalServerError` (5xx) của Gemini,
  tức không có phản hồi của model. Mục 2.2, 2.4 và 6 của giao thức coi 5xx là lỗi hạ tầng: case bị dừng
  vì hạ tầng thì được chạy tiếp, không được tính là kết quả của nhánh. Nhánh Baseline cũng không bao giờ
  kết thúc case vì `provider_error`: nó dừng rồi được chạy tiếp sau. Luật `MAX_COMPILE_FAILURES` (mang
  từ E6) vì thế làm hai nhánh bị đối xử khác nhau.
- **Sửa (hạ tầng):** bỏ `MAX_COMPILE_FAILURES` trong `tools/e7/auto.py`. Khi bước sinh hợp đồng không
  có phản hồi, bộ chạy thoát với mã 4, rồi chạy lại bước duyệt (D4) khi máy chủ hoạt động lại. Người
  điều khiển chờ sự cố qua đi rồi mới chạy tiếp.
- **Case bị ảnh hưởng:** chỉ case 17. `final.json` của nó được cất vào
  `runs/E7-Eval-Discarded/case-017/`, và case được chạy tiếp từ bước duyệt.
  - Nhánh Baseline của case 17 đã chạy với trần 7, tức số request Pipeline có lúc đó. Nó được chấp nhận
    sau 3/7 request, chưa chạm trần, nên không chạy lại. Số request Pipeline chỉ có thể tăng sau khi
    chạy tiếp, nên trần cũ không làm Baseline thiệt.
  - Trần của case 17 được báo cáo với cả hai số.
- **Kiểm tra:** case 1–16 không có case nào kết thúc vì `compile_model_failed`. Case 1, 5 và 15 kết thúc
  vì `generation_stalled` khi chạy kịch bản, không có lần gọi lỗi nào, nên đó là kết quả thật của model.
  Thêm một test trong `tests/experiments/test_e7_driver.py`.

## Ghi nhận khi chạy (không phải lệch giao thức)

### O1 (2026-11-13): bản đọc lại kịch bản không nêu người bấm

- **Hiện tượng:** `describe` trong `research/synthesis/example_scenarios.py` đọc lại mọi bước `notify`
  thành "có người bấm xác nhận" / "someone presses confirm". Nó không nêu ai bấm, và gọi mọi hành động
  là "xác nhận", kể cả khi người dùng nói "LotusCo bấm dừng".
- **Ảnh hưởng tính đến case 21:**
  - Case 2: bị phản đối một lần, sau đó vẫn giao được.
  - Case 20 và 21: bị phản đối hai lần, kết thúc với `scenarios_not_confirmed`. Ở case 20, lần phản đối
    thứ hai còn đòi bản đọc lại ghi từng lần trả tiền.
- **Quyết định của người dùng:** giữ nguyên bản đóng băng, không sửa và không chạy lại. Đây được báo
  cáo là điểm yếu của nhánh Pipeline, kèm số case bị ảnh hưởng khi chạy xong 100 case.

## D6 (2026-11-13, case 22 của v5): lần chạy đầu không có phản hồi nhưng bị tính là thử lại thất bại

- **Hiện tượng:** cả ba lần chạy đầu của case 22 (attempt-001..003) đều hỏng ở `intent_extraction` vì
  `InternalServerError` (5xx) của Gemini, với `model_content_received: false`. Bộ chạy coi đó là các lần
  thử lại `llm_error` thông thường, nên sau `MAX_RETRIES` lần thì kết thúc case với `pipeline_stopped`
  (0 request). Đây là cùng loại lỗi với D5, chỉ khác bước.
- **Sửa (hạ tầng):** lần chạy hỏng mà không có nội dung nào từ model (`provider_request_failed` hoặc
  `provider_limit` ở bước chặn) không còn bị tính vào `MAX_RETRIES`.
  - Bộ chạy chờ 60 s rồi chạy lại, tối đa 3 lần cho mỗi lần gọi.
  - Sau đó nó thoát với mã 4 để chạy tiếp sau, và không bao giờ kết thúc case vì lý do này.
  - `MAX_RETRIES` vẫn áp dụng cho các lỗi có phản hồi của model (`invalid_candidate`, hoặc `llm_error`
    có nội dung).
- **Case bị ảnh hưởng:** chỉ case 22. `final.json` sai được cất vào `runs/E7-Eval-Discarded/case-022/`.
  Nhánh Baseline của case 22 chưa chạy. Case 1–21 không có case nào kết thúc `pipeline_stopped`.
- **Kiểm tra:** thêm một test trong `tests/experiments/test_e7_driver.py`.

## Ghi nhận hạ tầng (không phải lệch giao thức)

### I1 (2026-11-13): từ case 31, hai nhánh chạy song song bằng các key riêng

- **Lý do:** cho nhanh hơn. Người dùng chọn giữ sim-user Haiku và giữ nguyên phương pháp.
- **Cách làm:**
  - Từ case 31, một phiên chạy nhánh Pipeline cho các case 31–100 theo thứ tự id, dùng key 1–2
    (`E7_GEMINI_KEYS=1,2`).
  - Một phiên khác chạy nhánh Baseline, cũng theo thứ tự id, dùng key 3 (`E7_GEMINI_KEYS=3`). Case nào
    đã có `final.json` của Pipeline thì mới được chạy Baseline.
- **Vẫn đúng giao thức:** mục 2.1 (trong mỗi case, Pipeline chạy trước Baseline) và mục 2.2 (trần
  Baseline bằng số request Pipeline) không đổi.
- **Không đổi:** điều mà hai nhánh hay người dùng mô phỏng nhìn thấy. Key chỉ quyết định quota dùng
  chung nào bị trừ.

### O1 (tiếp): case 21–30

- Case 21 và 25 không chốt được kịch bản (`scenarios_not_confirmed`) vì dòng "someone presses
  confirm" / "có người bấm xác nhận".
- Case 27 cũng không chốt được, nhưng vì lý do khác: bản đọc lại bỏ mất các bước quá hạn. Lý do này
  được ghi riêng là O2.

### O2 (2026-11-13): bản đọc lại kịch bản bỏ mất các bước quá hạn

- Case 27: người dùng mô phỏng bác cả hai bản đọc lại, vì cả hai đều không nói gì xảy ra khi đến hạn
  mà chưa ai làm. Đây là hành vi của nhánh Pipeline (`E7-ExampleScenarios-v2`, đã đóng băng), nên giữ
  nguyên và chỉ báo cáo.

### I2 (2026-11-13, case 28 Pipeline): kiểm tra một lượt sim-user khi lượt đó chưa xong

- Bước kiểm tra của lô 3 chạy `audit_agent.py` cho sub-agent `aa7a24114709b799e` khi sub-agent này
  chưa xong, nên kết quả là "0 handbacks" và không có gì được ghi.
- Khi sub-agent xong, cùng sub-agent đó được kiểm tra lại. Lần này hợp lệ, và câu trả lời được ghi.
- Không gọi sub-agent mới, nên không có chuyện chọn giữa nhiều câu trả lời. Cả hai lần kiểm tra đều nằm
  trong `subagent-audit.jsonl`.

### I3 (2026-11-13, case 33 Pipeline): gọi lại `pipe N` khi một lượt đang chờ làm mất số lần bị từ chối

- **Hiện tượng:** người dùng mô phỏng trả lời lượt `examples` của case 33. Bộ kiểm tra từ chối câu trả
  lời hai lần ("number 60 is not in the request or the fact sheet"). Sau đó người điều khiển lỡ chạy lại
  `auto.py pipe 33` thay vì gọi sim-user mới. `_need` ghi đè `simuser-pending.json` với `retries` = 0,
  nên câu trả lời thứ ba, cũng bị từ chối, không chuyển sang câu dự phòng như giao thức quy định (tối đa
  2 lần thử lại).
- **Sửa (hạ tầng):** `_need` giữ số lần từ chối khi cùng lượt đó (cùng loại, cùng nội dung hiển thị)
  vẫn đang chờ. Có thêm test.
- **Sửa dữ liệu case 33:**
  - Bản cũ của `simuser.json` và `simuser-pending.json` được cất vào `runs/E7-Eval-Discarded/case-033/`.
  - Lượt từ chối thứ ba được ghi lại đúng như lẽ ra phải ghi: cùng câu trả lời thô, với `retry` = 2.
  - Bộ kiểm tra từ chối lần nữa, nên câu dự phòng được ghi.
  - Không gọi sub-agent mới, và không có câu trả lời nào được chọn.
- **Kiểm tra:** đã quét `simuser.json` của mọi case trên cả hai nhánh. Chỉ case 33 có chuỗi thử lại bị
  đặt về 0 sau một lần từ chối.

### A1 (2026-11-13): script phân tích viết sau khi đóng băng (giao thức mục 5)

- **Script:** `research/experiments/e7_analysis.py`, có test trong `tests/experiments/test_e7_analysis.py`.
  Được commit trước khi mở kết quả tổng. Lúc viết, chưa chạy chấm máy hay phân xử case v5 nào.
- **Hai chỗ phải chọn cách đọc giao thức, chốt ngay trong docstring của script:**
  1. **`told_unsupported`.** Q-CHẤM 5 cần biết nhánh đã nói rõ phần không làm được hay chưa, mà máy
     không chấm được điều này. Vì vậy người phân xử cũng chấm mù câu hỏi đó, nhưng chỉ cho
     `converge_and_decline_extra` và `reject_unsupported`. Hợp đồng nào máy đã chấm RIGHT thì người
     phân xử không chấm lại.
  2. **Bảng độ nhạy thời gian.** Ở dung sai T, hợp đồng là RIGHT nếu máy chấm RIGHT ở T. Nếu không,
     giữ verdict ở mức 1 phút.
- **`e7_score`:** thêm `--time-tolerance-minutes`, mặc định 1, đúng luật đã đóng băng. Các giá trị khác
  chỉ dùng cho bảng độ nhạy.
- **Giao hàng của Pipeline:** tính theo `final.json` (`delivered`). Case không giao thì coi như không có
  hợp đồng, dù lần chạy cuối có chứa hợp đồng nào.

### I1 (tiếp, 2026-11-13)

- **Quota:** key 1 và 2 hết quota trong ngày lúc 00:52 UTC, ở case 85 của nhánh Pipeline.
- **Cách xử lý:** từ case 85, nhánh Pipeline dùng chung key 3 với nhánh Baseline, thay vì chờ quota đặt
  lại lúc 08:00 UTC. Hai luồng vẫn chạy từng lần gọi một, nên không vượt giới hạn mỗi phút.
- **Không đổi:** cùng model, cùng luật đếm; không có gì khác với điều hai nhánh hay người dùng mô phỏng
  nhìn thấy.
