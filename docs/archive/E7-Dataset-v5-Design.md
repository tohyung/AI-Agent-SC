# E7: thiết kế dataset v5, tập đánh giá mới (2026-11-12)

v5 là **100 case mới**, viết tay. Đây là tập đánh giá sạch của E7. v4 (prompt v3) chỉ là dev
(`dataset/v4/README.md`).

**Phân bố** giống v3, để so được với E6:

- 19 họ hợp đồng và 10 case bất khả, cùng số case mỗi họ và mỗi ngôn ngữ;
- 60 case tiếng Việt, 40 case tiếng Anh;
- loại thông tin: 40 đủ, 25 thiếu, 10 mơ hồ, 10 mâu thuẫn, 5 có phần không làm được, 10 bất khả;
- cùng các mức phủ tối thiểu về cấu trúc Marlowe và hiện tượng ngôn ngữ (`docs/archive/E6-Dataset-Design.md`,
  mục 4).

**Người viết:** Claude, theo yêu cầu của người dùng (2026-11-12). Claude cũng là người sửa pipeline,
người vận hành và người chấm. Báo cáo phải ghi đây là hạn chế. Bù lại, mọi tiêu chuẩn dưới đây được
**chốt trước khi viết** và **kiểm bằng máy** trong `dataset/v5/build.py`.

## 1. Tiêu chuẩn văn phong (V-…)

| Mã | Tiêu chuẩn | Kiểm bằng |
| --- | --- | --- |
| V-1 | Viết như người dùng thật gõ vào khung chat: nói thẳng việc cần làm, ở ngôi thứ nhất hoặc nhờ trợ lý. Không kể chuyện kiểu văn mẫu, không mở đầu bằng "Xin chào, tôi là…", không giới thiệu bối cảnh dài dòng. | danh sách mở đầu cấm (`BANNED`) |
| V-2 | Không dùng thuật ngữ của Marlowe hay của hệ thống: Notify, Choice, When, Close, timeout, role token, POSIX, slot. Ngoại lệ: "lovelace" chỉ ở case gắn nhãn `lovelace_units`; "role X" chỉ khi người dùng tự đặt tên vai. | danh sách từ cấm |
| V-3 | Văn phong đa dạng, mỗi kiểu có số tối thiểu: chat thường (≥ 40), gạch đầu dòng hoặc bản điều khoản (≥ 20), một câu cụt (≥ 15), trích văn bản dài có chi tiết thừa (≥ 8). | nhãn `register`, đếm |
| V-4 | Độ dài trải đều: ≥ 15 prompt dưới 25 từ, ≥ 10 prompt trên 80 từ. | đếm từ |
| V-5 | Tiếng Việt tự nhiên: dùng "mình/tôi/em/anh/chị" đúng ngữ cảnh. Lỗi chính tả là lỗi gõ thật (thiếu dấu, gõ nhầm phím), không phải lỗi bịa. ≥ 10 prompt không dấu, ≥ 8 prompt trộn Việt–Anh. | nhãn, đếm |
| V-6 | Không trùng v3: không prompt nào có độ giống từ (Jaccard) > 0,5 với một prompt v3 hoặc v2. Trong v5, không cặp nào > 0,6. | đo |
| V-7 | Tên người mới: không tên vai nào của v5 trùng một tên vai của v3. | so tập tên |
| V-8 | Mốc thời gian nằm trong 2027–2028, viết theo kiểu người dùng hay viết: 23:59, 9h sáng, "trưa", ngày/tháng, "Jan 5", ISO. | trình dựng kiểm ngày hợp lệ |

## 2. Tiêu chuẩn chính xác (C-…)

| Mã | Tiêu chuẩn | Kiểm bằng |
| --- | --- | --- |
| C-1 | `spec` dựng ra hợp đồng tham chiếu hợp lệ. Mọi kịch bản `checks` chạy trên bộ mô phỏng cho đúng khoản trả tính từ `spec`, không có đầu vào bị từ chối, không trả thiếu. | `build.py` |
| C-2 | Mọi tên vai trong `spec` có trong prompt hoặc phiếu dữ kiện. | `build.py` |
| C-3 | Mọi số tiền và mọi ngày của `spec` có trong prompt hoặc phiếu dữ kiện: dạng số, số viết bằng chữ, dấu phẩy thập phân, hoặc phép tính mà prompt nêu rõ (phần trăm, "gấp đôi"). Số tính ra được liệt kê trong `derived` của case. | `build.py` |
| C-4 | Case `complete`: mọi tên vai, số tiền, ngày, giờ và múi giờ nằm ngay trong prompt. Phiếu dữ kiện rỗng, hoặc chỉ trả lời cách xử lý khi hết hạn đã nêu trong prompt. | `build.py` (C-2, C-3 chỉ trên prompt) |
| C-5 | Case `missing` và `ambiguous`: có ít nhất một dữ kiện chỉ nằm trong phiếu dữ kiện. | `build.py` |
| C-6 | Case `extra_unsupported`: phiếu dữ kiện có một mục cho phép bỏ phần không làm được. | `build.py` (từ "bỏ"/"drop") |
| C-7 | Họ "ai cũng được" có kịch bản cho ít nhất hai người khác nhau (Q-DỮ LIỆU 3). | `build.py` (thêm kịch bản `buyer_k_first`) |
| C-8 | Hợp đồng tham chiếu là SMT `Valid`, và mọi kịch bản chạy đúng trên bộ tham chiếu Haskell. | `dataset.v5.check_reference` (trong WSL) |

## 3. Đóng băng

- `python -m dataset.v5.build --write` phải báo 0 lỗi; sau đó chạy C-8.
- Ghi SHA-256 vào `dataset/v5/README.md` và commit trước mọi lần chạy pipeline trên v5.
- Sau khi đóng băng, không sửa case. Nếu phải sửa thì tạo bản mới và ghi vào nhật ký lệch giao thức.
- Không chạy pipeline hay Baseline trên v5 cho đến khi code E7 được đóng băng trên v4 (dev).
