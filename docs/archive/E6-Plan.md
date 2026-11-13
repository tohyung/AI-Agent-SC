# E6 — Kế hoạch cho RQ3 và RQ4 (chưa chạy)

Trạng thái: **kế hoạch đã thống nhất với người phụ trách ngày 2026-11-10. Chưa có giao thức chốt,
chưa chạy gì.** Tài liệu ghi lại các quyết định và lý do, để người khác nắm được hướng đi trước khi
có kết quả. Báo cáo RQ1 và RQ2 nằm ở `docs/RQ-Report.md`.

## 1. Câu hỏi

- **RQ3:** toàn bộ quy trình của hệ thống có cho hợp đồng cuối khớp hành vi tốt hơn một LLM đơn
  thuần không, khi hai bên tốn cùng chi phí? Hơn hay kém bao nhiêu phần trăm?
- **RQ4:** mỗi cách tốn bao nhiêu: request model, token, lượt trao đổi với người dùng, thời gian, tỷ
  lệ không quyết định.

## 2. Các quyết định đã thống nhất

| # | Quyết định | Lý do |
| --- | --- | --- |
| 1 | **Đường chính dùng AFF**; nối AFF vào pipeline trước khi chạy E6. | E4 chọn AFF thay DCF. Đo RQ3 bằng DCF thì không nói được gì về hệ thống sẽ được báo cáo. Hiện pipeline chính vẫn gọi DCF (`IntentShadowExtractor`). |
| 2 | **Nhánh đối chứng là một LLM đơn thuần tương tác với người dùng,** như cách người ta dùng chatbot: model sinh hợp đồng thẳng từ hội thoại; mỗi hợp đồng được đem kiểm ledger; nếu không qua, người dùng mô phỏng góp ý để model sửa. | So với cách dùng LLM ngoài đời. Không đưa sẵn cho LLM yêu cầu đã được pipeline làm rõ. |
| 3 | **Trần request đặt riêng cho từng case**, bằng đúng số request pipeline đã tiêu cho case đó (pipeline tốn 10 thì LLM đơn thuần được tối đa 10; pipeline tốn 20 thì được 20). | So "cùng chi phí, ai tốt hơn". Case khó làm pipeline tốn nhiều thì đối chứng cũng được nhiều lượt. |
| 4 | **Đếm request:** mỗi lần gọi model nhận được phản hồi đều tính, kể cả phản hồi lỗi; lỗi quota (429) không tính. Cùng một quy tắc cho cả hai nhánh. | Tránh lệch do cách đếm. |
| 5 | **LLM đơn thuần được dừng sớm** khi qua ledger hoặc khi người dùng chấp nhận. Báo số request thực dùng của cả hai nhánh. | Đúng với cách dùng thật. |
| 6 | **Thắng thua chấm bằng nghĩa,** không bằng "qua ledger": hợp đồng giao ra có đúng yêu cầu đã xác nhận không, phân xử theo `docs/archive/E5-Adjudication-Rubric.md`. Báo thêm tỷ lệ giao ra hợp đồng sai. | Ledger chỉ kiểm kích thước giao dịch; ở E3 dev, 7 hợp đồng sai vẫn qua ledger. |
| 7 | **Người dùng mô phỏng chỉ thấy những gì người dùng thật thấy:** lỗi ledger hoặc validator, và lời giải thích bằng ngôn ngữ thường của model. Không được chạy kịch bản trên bộ thực thi để góp ý. | Nếu được chạy kịch bản, đối chứng ngầm có cổng Scenario. |
| 8 | **Phiếu dữ kiện của người dùng:** với mỗi case, các dữ kiện mà prompt không nêu (số tiền, giờ, vai trò…) được soạn một lần trước khi chạy nhánh nào. Cả hai nhánh trả lời theo đúng phiếu đó. | Ở E5, việc người dùng mô phỏng tự đặt dữ kiện làm lật 31 nhãn. Hai nhánh phải nhận cùng thông tin. |
| 9 | **Ghi token vào, token ra, số lượt góp ý của người dùng và thời gian** cho cả hai nhánh. | Số liệu cho RQ4. Một request của pipeline mang prompt dài hơn hẳn, nên bằng request chưa chắc bằng token. LLM đơn thuần thường cần một lượt góp ý cho mỗi request, nên có thể tốn công người dùng hơn. |
| 10 | **Dataset mới, 100 case, do Claude viết tay** (không nhờ được người thật). Không dùng seed và câu mẫu như dataset v2. | Dataset v2 có câu sai ngữ pháp ("tiệm nhỏ của mình đang Chi thuê phòng…"), tham số là số học theo thứ tự case, và mỗi họ hợp đồng chỉ có một cấu trúc. Case 58–100 cũng đã bị dùng ở E3, E4, E5. |
| 11 | **Case phải làm khó hệ thống để lộ điểm yếu,** không để làm đẹp con số. | Theo yêu cầu của người phụ trách. |
| 12 | **Mở rộng họ hợp đồng,** bỏ các dạng cần oracle giá. | Pipeline chưa hỗ trợ oracle. |
| 13 | **Lời yêu cầu giống người dùng thật nói với hệ thống:** họ cần một smart contract, nói thẳng vào việc, ngắn hoặc dạng gạch đầu dòng. Không mở đầu kiểu "An ở Huế đây, Bình ơi…", không kể chuyện lê thê. | Theo yêu cầu của người phụ trách. |

## 3. Dataset mới (bản nháp hướng thiết kế)

**Ma trận độ phủ chốt trước khi viết case.** Mỗi ô có số case tối thiểu.

- **Họ hợp đồng:** 10 họ khả thi của v2 (escrow 2 bên, escrow có trọng tài, swap, vay, vesting,
  milestone, gây quỹ, bên thứ ba báo giá, đặt cọc thuê, phí hủy). Thêm các họ không cần oracle:
  - trả góp nhiều kỳ;
  - duyệt k trên n người;
  - bán cho người đến trước (nhiều nhánh cạnh tranh);
  - trái phiếu zero-coupon và có coupon;
  - chia tiền cho nhiều bên;
  - vay có tài sản thế chấp (không thanh lý theo giá);
  - đặt cọc có khấu trừ theo mức do bên kiểm tra chọn;
  - tài trợ đối ứng.

  Thêm một nhóm yêu cầu bất khả hoặc ngoài phạm vi.
- **Cấu trúc Marlowe phải có mặt:**
  - `Notify`;
  - `When` nhiều nhánh cạnh tranh;
  - chuyển tiền giữa các tài khoản;
  - giá trị chọn được dùng làm số tiền trả;
  - `If` và `Let`;
  - từ 3 `When` lồng nhau trở lên;
  - từ 4 bên trở lên;
  - nhiều loại token.
- **Hiện tượng của yêu cầu:**
  - thông tin đủ, thiếu, mơ hồ, mâu thuẫn, bất khả;
  - đính chính ở cuối tin nhắn;
  - người dùng là một bên ("tôi");
  - giờ và múi giờ;
  - số viết bằng chữ, phần trăm, số lẻ;
  - tiếng Việt không dấu, sai chính tả, trộn Việt–Anh;
  - gạch đầu dòng;
  - yêu cầu chen việc ngoài khả năng, ví dụ "tự động gửi email nhắc".
- **Nhắm vào điểm yếu đã biết:**
  - hạn thứ hai bị dời mà kịch bản không chạm tới;
  - `Notify` cho phép trả sớm;
  - token có policy và tên hex;
  - tên có dấu;
  - người kể bị nhầm thành một bên;
  - hoàn tiền qua `Close`;
  - các nửa khoản độc lập;
  - case bất khả bị chặn vì lỗi khác thay vì `UNSUPPORTED`.

**Hợp đồng tham chiếu và kịch bản** được dựng bằng code từ đặc tả có cấu trúc của từng case. Họ hợp
đồng mới được đối chiếu với ví dụ chính thức của Marlowe. Mỗi hợp đồng tham chiếu phải qua SMT và qua
bộ thực thi tham chiếu.

**Chống thiên vị** (vì người viết case cũng là người làm thí nghiệm, người đóng vai người dùng và
người phân xử):

- viết xong và đóng băng toàn bộ dataset, cả phiếu dữ kiện, bằng mã băm trước khi chạy bất kỳ nhánh
  nào;
- không chỉnh pipeline hay prompt đối chứng trên dataset mới; mọi chỉnh sửa làm trên dev cũ (case
  1–56);
- giới hạn này được ghi trong mọi báo cáo.

## 4. Thứ tự làm

1. Soạn ma trận độ phủ, giọng văn, quy tắc làm khó và vài case mẫu, để người phụ trách duyệt.
2. Nối AFF vào pipeline chính (có test, chỉnh trên dev cũ).
3. Viết nhánh LLM đơn thuần.
4. Viết 100 case, đặc tả, hợp đồng tham chiếu và phiếu dữ kiện; kiểm tự động; đóng băng.
5. Viết giao thức E6 và quy tắc quyết định, chốt trước khi chạy.
6. Chạy thử 20 case, rồi chạy cả 100 (khoảng 2 000 request Gemini, 4–5 ngày quota miễn phí).
7. Phân xử, báo cáo RQ3 và RQ4 theo cùng khung với RQ1 và RQ2.

## 5. Điểm còn mở

- Ngưỡng và quy tắc quyết định của RQ3 (ví dụ chênh lệch tối thiểu, kiểm định) chưa chốt.
- Trần số lượt góp ý của người dùng cho cả hai nhánh chưa chốt.
- Có thêm nhánh tách phần đóng góp của bước intent và của các cổng không: để sau, nếu còn quota.
