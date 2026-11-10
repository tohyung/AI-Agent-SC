# E5 — Tiêu chí phân xử hợp đồng E3 (ghi trước khi phân xử, 2026-11-10)

Áp dụng cho các tập E3-All và E3-Final. Một người phân xử (Claude) đọc tài liệu cho từng hợp đồng
và ghi một dòng lý do. Hợp đồng mà bộ máy gán nhãn khác với kết quả phân xử thì ghi rõ chỗ khác.

**Căn cứ.** Intent đúng là yêu cầu cuối cùng mà người dùng mô phỏng đã xác nhận: prompt cộng với
các câu trả lời và revision trong `requirement_history` của lượt E3 đã sinh ra hợp đồng. Hợp
đồng tham chiếu của dataset chỉ dùng để tham khảo cách mã hóa. Với dữ kiện mà prompt không nêu,
giá trị người dùng mô phỏng đã xác nhận là đúng, kể cả khi nó khác dữ kiện ẩn của dataset.

**ĐÚNG khi đủ cả các điều sau:**

1. Đúng các bên, đúng số tiền và đúng token (ADA phải là `currency_symbol = ""`, `token_name = ""`).
2. Đúng bên nạp, đúng tài khoản nhận và đúng hạn nạp. Lịch sử có nêu giờ thì hạn lệch không quá
   1 phút; không nêu giờ thì hạn nằm trong đúng ngày đã nêu, theo múi giờ đã xác nhận (nếu có).
3. Mỗi quyết định đã xác nhận (duyệt, từ chối, báo hư hỏng…) chỉ do đúng bên đó kích hoạt được,
   và dẫn tới đúng kết quả. Tên choice, giá trị số, hay việc gộp hai choice thành một choice có giá
   trị 0/1 đều được chấp nhận, miễn là ánh xạ giá trị sang kết quả rõ ràng và không giá trị nào
   dẫn tới kết quả ngoài intent.
4. Khoản trả theo thời gian diễn ra đúng thời điểm và không cần ai hành động, trừ khi intent yêu
   cầu có người hành động. Thêm một bước `Notify` hay một hành động mà intent không yêu cầu, để
   chặn trước một khoản trả, thì tính là SAI.
5. Khi hết hạn mà không ai hành động, tiền về đúng bên theo intent; intent không nói gì thì tiền
   hoàn về người nạp.
6. Không trả quá số dư (không partial pay), và không có tiền bị kẹt lại mà intent không định.

**SAI** khi vi phạm bất kỳ điều nào ở trên. **KHÔNG XÁC ĐỊNH** khi lịch sử yêu cầu không đủ để
quyết định; trường hợp này loại khỏi các tỷ lệ và báo riêng.
