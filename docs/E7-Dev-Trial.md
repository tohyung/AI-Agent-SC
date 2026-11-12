# E7: chạy thử trên dev (2026-11-12)

Chạy thử bộ chạy E7 (`tools/e7/auto.py`) đầu-cuối trên testnet riêng, với sub-agent `sim-user`
(Haiku 5.5, effort medium) làm người dùng, trên 3 case dev của v4. Mục đích là bắt lỗi của bộ chạy
và của các quy ước. Kết quả **không phải là số liệu đánh giá**.

## Kết quả

| Case | Pipeline | Baseline | Số lượt người dùng |
| --- | --- | --- | --- |
| 17 (loan, đủ, en) | RIGHT, 3 request | REVIEW: hạn năm 2026 dù lời giải thích ghi 2027; người dùng chấp nhận | P: 4, B: 1 |
| 50 (trả góp, có phần không làm được, vi) | RIGHT, 4 request (ở E6 thì không giao ra) | REVIEW: người dùng mô phỏng đẩy nó sang "trễ hạn vẫn tiếp tục" | P: 5, B: 4 |
| 92 (bất khả, en) | Dừng giữa chừng: lặp lại câu hỏi thay vì từ chối | chưa chạy | P: 2 |

Mọi lượt của sub-agent đều có `tool_uses` = 1 (chỉ lần trả kết quả).

## Lỗi tìm thấy và đã sửa

| # | Ở đâu | Lỗi | Sửa |
| --- | --- | --- | --- |
| 1 | Tóm tắt intent (en) | Ngày kiểu dd/mm ("05/08/2027") đọc nhầm thành 8 tháng 5 | Tiếng Anh dùng ngày ISO |
| 2 | Bộ kiểm tra câu trả lời | Số thứ tự ("Situation 3", "Kịch bản 1", "kỳ 2") bị coi là con số bịa | Bỏ qua số thứ tự |
| 3 | Bộ kiểm tra câu trả lời | Tổng người dùng tự tính (3 × 40 = 120) bị coi là con số bịa | Chấp nhận tổng hoặc tích của các con số đã biết |
| 4 | Luật không dựa vào nhãn | "Yes, these are what I mean…" gắn nhãn `answer` bị coi là phản đối | Tin nhắn chỉ có ý đồng ý thì tính là chấp nhận (`plain_agreement`) |
| 5 | Kiểm lịch (`intent_spec`) | "20/02, 20/03 và 20/04/2027": hai ngày đầu không có năm nên bị coi là mâu thuẫn | Các ngày trong danh sách dùng năm của ngày có năm đứng sau (Q-GIỜ 3) |
| 6 | `identify()` của builder | "tôi (Trúc)", "chị Hồng" bị đổi thành token ASCII, rồi bước kiểm v4 chặn vì tên người nhận không có trong trích dẫn | Lấy tên trong ngoặc; bỏ danh xưng; tên vai giữ nguyên như người dùng viết (Q-TÊN 2 bản 3) |
| 7 | Tóm tắt intent | "nạp (vào tài khoản của Hồng)": người dùng hiểu là tiền vẫn ở chỗ Hồng | Viết đời thường: "nạp vào hợp đồng", "hợp đồng chuyển … (tiền X đã nạp) cho Y" |
| 8 | Đổi ví dụ thành kịch bản | Model chèn bước chờ giữa các hành động và sau khi đã trả xong; bản đọc lại khó hiểu, và giao dịch rỗng sau khi đóng bị bộ tham chiếu từ chối | Chỉ giữ bước chờ cuối khi hạn của nó muộn hơn mọi hành động; prompt v2 |
| 9 | Đầu vào của người dùng mô phỏng | Phiếu dữ kiện mất chủ đề ("Bỏ hai phần đó" không rõ bỏ gì) | Ghi cả chủ đề: "(nếu không làm được …) …" |

Lần chạy bị lỗi 5, 6, 7 được cất vào `runs/E7-Discarded/`, sau đó case chạy lại từ đầu. Lỗi 8: đổi
lại ví dụ với đúng câu trả lời cũ của người dùng, không hỏi lại; có ghi trong `simuser.json`.

## Lỗi tìm thấy, chưa sửa

1. **Người dùng mô phỏng không nhất quán giữa hai nhánh** (case 50). Với Pipeline, nó chấp nhận "quá hạn
   thì hợp đồng kết thúc". Với Baseline, nó phản đối đúng câu đó, rồi tự đặt thêm yêu cầu "đừng hủy
   các kỳ còn lại", điều mà prompt và phiếu dữ kiện không có. Kết quả là Baseline giao một hợp đồng
   khác ý ban đầu. Đây là bịa thông tin mà bộ kiểm tra hiện tại không bắt được, vì không có con số
   nào.
   - Đề xuất: thêm vào SimUser luật "không thêm điều kiện mới; điều mình không nói thì để trợ lý chọn";
     kiểm thêm câu phản đối nhắm vào hành vi mà prompt và phiếu dữ kiện không đề cập; và chạy thử lại
     trên cùng các tình huống cho cả hai nhánh.
2. **Viết không dấu khi prompt có dấu** (một lần ở case 50). Bộ kiểm tra chưa có luật này cho tiếng
   Việt.
3. **Yêu cầu bất khả không kết thúc `UNSUPPORTED`** (case 92). Khi người dùng nói vẫn cần phần không làm
   được, Pipeline hỏi lại đúng câu cũ. Đây là mục AFF-7 của `docs/E6-Failure-Review.md`, chưa làm.
4. **Nhãn người dùng tự đặt** ("use 'Me' for my side") vẫn bị coi là đại từ và hỏi lại tên.
5. **Chi phí vận hành:** mỗi case cần 4–6 lượt sub-agent, và mỗi lượt phải dán lại toàn bộ hội thoại. Chạy
   100 case đánh giá theo cách này rất tốn ngữ cảnh của phiên chính. Nên chạy theo lô, mỗi lô một
   phiên.
