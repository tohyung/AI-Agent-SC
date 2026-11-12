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
