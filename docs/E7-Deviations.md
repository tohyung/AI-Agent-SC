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
