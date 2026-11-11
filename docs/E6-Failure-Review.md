# E6: rà soát nguyên nhân thất bại (case 1–100) và đề xuất quy ước chung

Ngày: 2026-11-12. Tài liệu này rà lại sau khi chạy và chấm xong E6, để tìm vì sao Pipeline chỉ thành
công 38/71 case đánh giá. Nó không thay đổi kết quả đã báo cáo trong `docs/RQ-Report.md`.

**Công khai:** khi rà soát, tôi đã đọc các trường dành cho người chấm của dataset v3 (`spec`, `checks`,
`author_note`) cho cả 100 case. Vì vậy **v3 không còn dùng làm tập giữ lại được nữa**. Mọi lần chạy lại
trên v3 sau khi sửa chỉ được coi là dev. Muốn có kết quả sạch cho bản sửa thì cần một tập mới (mục 7).

## 1. Tóm tắt

Trên 71 case đánh giá, Pipeline thất bại 33 case: 30 case không giao ra gì, 3 case giao hợp đồng sai.
Mỗi case được gán một **nguyên nhân chính**:

| Nhóm nguyên nhân | Số case | Case |
| --- | --- | --- |
| A. AFF thiếu cấu trúc Marlowe (k trên n, "ai cũng bấm", khấu trừ theo số nhập, ai nhanh nhất) | 13 | 51–56, 71, 75, 76, 60, 82, 83, 86 |
| B. Luật tên các bên (tên vai, đại từ, nhóm, "Me", "minh") | 8 | 38, 39, 44, 79, 84, 85, 89, 90 |
| C. Đọc chữ và số (giờ dùng chung cho danh sách ngày, số thập phân, trích dẫn nguyên văn) | 6 | 35, 45, 48, 50, 59, 70 |
| D. Sinh hợp đồng và sửa lỗi (cổng chặn đúng nhưng không sửa được; JSON hỏng) | 3 | 65, 81, 91 |
| E. Kịch bản không phủ đủ, hợp đồng sai lọt qua cổng | 2 | 58, 61 |
| F. Chấm quá chặt về tên role | 1 | 68 |

Ba điểm lớn nhất:

1. **Một lỗi kiểm tra FactDraft là dừng hẳn.** 13 case dừng ngay ở lần trích xuất đầu (`extraction_failed`,
   `repair_attempts = 0`). Pipeline không gửi lỗi lại cho model để sửa, cũng không hỏi người dùng. Đây là
   cơ chế khuếch đại: một lỗi nhỏ (ví dụ một tên vai) làm mất cả case.
2. **Hai quy ước chưa thống nhất,** dù cả hai đều không phải hành vi hợp đồng:
   - **tên các bên:** tên người, tên vai và role token bị coi là ba thứ khác nhau. Điều này ảnh hưởng
     AFF, dataset, kịch bản và cả việc chấm;
   - **giờ áp cho nhiều ngày:** một giờ ghi một lần nhưng dùng cho cả danh sách ngày.
3. **AFF chưa phủ được 4 dạng hợp đồng** mà dataset cố tình đưa vào: k trên n người duyệt, "ai cũng bấm
   được" (Notify), trả theo số người kiểm tra nhập, và "ai nạp trước".

**Ước lượng thô** (chưa kiểm chứng): sửa B, C, F và quy tắc dừng hẳn ở mục 1 có thể đưa Pipeline lên
khoảng 50–53/71. Thêm các cấu trúc của nhóm A thì trần là khoảng 65/71. Đây là cận trên, không phải kết quả.

**Dấu hiệu khớp quá vào dev:**

| Nhóm case | Pipeline giao ra hợp đồng | Baseline giao ra hợp đồng |
| --- | --- | --- |
| Dev (1–29) | 25/29 (86%) | 27/29 |
| Đánh giá, chỉ case làm được (30–100) | 32/61 (52%) | 55/71 |

Nhưng hai nhóm khác họ hợp đồng. Dev chủ yếu là escrow, swap, loan, vesting (dễ hơn); toàn bộ các họ
khó (k_of_n, deduction, first_come, matching) nằm ở phần đánh giá. Nên các bản sửa trên dev không được
thử trên đúng loại khó.

## 2. AFF: các vấn đề và đề xuất sửa

### AFF-1. Lỗi kiểm tra FactDraft là dừng hẳn (13 case, ưu tiên cao nhất)

- **Hiện tượng:** case 35, 38, 39, 44, 59, 60, 70, 79, 83, 84, 85, 89, 91 dừng ở `intent_extraction` với
  `extraction_failed`. Không có lượt sửa, không có câu hỏi nào được gửi cho người dùng.
- **Đề xuất:**
  - gửi danh sách lỗi của builder lại cho model, tối đa 2 lượt sửa (giống cách đang làm với core);
  - lỗi nào không sửa được bằng văn bản thì đổi thành câu hỏi. Ví dụ lỗi "tên là tên vai" thành câu
    "Người thuê tên là gì?" thay vì dừng.

### AFF-2. Luật tên các bên (8 case trực tiếp, nhiều case gián tiếp)

**Hiện tượng:**

- **Tên vai bị chặn** dù đủ để làm role:
  - 'người thuê', 'the organizer', 'seller', 'studio', 'ben cho thue', 'nha tai tro', 'chua Phuoc Hai';
  - 'minh' bị coi là đại từ "mình" (case 79, tên thật là Như).
- **Câu hỏi thừa:** pipeline hỏi tên của "tôi/I/me" ngay cả khi tên đã ở cạnh ("tôi (Hiền)"), hoặc gắn
  cờ "không biểu diễn được" cho chữ "me" (case 2) hay cho cả câu "Bên nạp tiền dùng đại từ 'Tôi'"
  (case 21).
- **Role do người dùng cho bị bỏ qua:**
  - case 90 nói rõ "nhóm Hy Vọng, role HyVong" mà vẫn bị gắn cờ "không biểu diễn được";
  - case 68: người dùng nói "role SaoMai", hợp đồng ghi "Công ty Sao Mai".
- **Tên trùng chữ thường:** "Me" (mẹ) trong câu không dấu bị lẫn với "me" tiếng Anh (case 55).

**Đề xuất quy ước tên (dùng chung cho AFF, dataset, kịch bản, chấm điểm):**

1. Mỗi bên có một **danh tính**, với *tên hiển thị* (Kiều, Công ty Sao Mai) và *role token* (định danh
   trong hợp đồng).
2. Nếu người dùng cho role token ("role: X", "(role X)") thì dùng đúng token đó. Nếu không, token suy ra
   tất định từ tên hiển thị: bỏ dấu, bỏ khoảng trắng, giữ chữ hoa đầu từ (Sao Mai → SaoMai).
3. Hai cách viết **cùng chỉ một người** là cùng một bên khi so khớp: "Công ty Sao Mai", "Sao Mai",
   "SaoMai", "sao mai". Danh xưng (chị, anh, công ty, bên) được bỏ qua khi so khớp.
4. **Tên vai được dùng làm role** nếu không có tên riêng (Organizer, Studio, NguoiThue). Chỉ hỏi tên khi
   một vai gắn với hai người, hoặc khi người dùng là "tôi" mà không có tên ở gần.
5. Đại từ có tên đi kèm trong ngoặc hoặc cùng mệnh đề ("tôi (Hiền)", "Mình là Phong") thì lấy tên đó,
   không hỏi lại.

### AFF-3. Giờ ghi một lần cho cả danh sách ngày (6 case)

- **Hiện tượng:** câu "hạn 23:59 các ngày 20/02, 20/03 và 20/04/2027 giờ VN" (case 50), "23:59 ngày 10
  hằng tháng từ tháng 2 đến tháng 5/2027" (45), "09:00 sáng các ngày 28/02, 31/03 và 30/04/2027" (19),
  "2027-02-15, 2027-03-15 and 2027-04-15, 12:00 UTC" (49), "18:00 UTC on 2027-03-01, 03-02…" (29),
  "23:59 ngày 01/09/2027 và 01/03/2028" (70). Pipeline hỏi lại giờ cho từng ngày sau ngày đầu, hoặc
  chặn với lỗi "hour 23 not in evidence".
- **Đề xuất:** builder áp giờ, năm và múi giờ ghi một lần cho mọi ngày trong cùng danh sách liệt kê, và
  cho các mẫu "ngày N hằng tháng từ tháng A đến tháng B".

### AFF-4. Định dạng số

- **Số thập phân kiểu Việt:** "37,5 ADA" bị hỏi lại thành "vui lòng nhập số nguyên lovelace" (case 45).
  Trong khi 37,5 ADA = 37 500 000 lovelace là hợp lệ.
- **Dấu chấm phân cách hàng nghìn:** "1.005 ADA" kiểu Việt bị đọc thành 1,005 ADA (case 71; cổng Scenario
  đã chặn đúng).
- **Đề xuất:** đọc số theo ngôn ngữ của câu. Với tiếng Việt, dấu chấm là phân cách hàng nghìn và dấu
  phẩy là thập phân. Khi có hai cách đọc hợp lý thì hỏi, nhưng không đòi số nguyên.

### AFF-5. Trích dẫn nguyên văn với câu trộn ngôn ngữ hoặc không dấu (2 case)

- **Hiện tượng:**
  - case 35: model dịch câu trộn Việt–Anh rồi trích bản dịch ('rating ≥ 4 then pay cho designer Lee');
  - case 59: model trích "Mình là Phong", là câu của phiếu dữ kiện có dấu, trong khi luồng lại tìm trong
    prompt không dấu.
- **Đề xuất:** trích dẫn được tìm trong **toàn bộ lịch sử hội thoại** (prompt và các câu trả lời).
  Prompt cho model phải nói rõ là chép nguyên chữ, không dịch.

### AFF-6. Cấu trúc chưa có trong AFF (13 case)

| Cấu trúc | Case | Marlowe làm được bằng |
| --- | --- | --- |
| Ai cũng bấm được | 28 (dev), 71, 75, 76 | `Notify` |
| k trên n người duyệt | 51–56 | các `When` lồng nhau đếm số người, hoặc mỗi tập con một nhánh |
| Trả theo số người kiểm tra nhập | 82–86 | `Pay (ChoiceValue …)` và `SubValue` |
| Ai nạp trước thì được | 58, 60, 61 | một `When` có nhiều `Deposit` |

Hiện tượng đi kèm:
- Thiếu `Notify`: model đổi "ai cũng bấm" thành `Choice` của một người cụ thể (71, 75, 76, 28).
- Thiếu k trên n: hợp đồng chỉ cho một người chọn (52, 53).
- Thiếu "ai nạp trước": builder đòi "expected one first step" (60), hoặc chỉ một người được mua (58, 61).

**Đề xuất:** thêm vào FactDraft:
- một loại kích hoạt "anyone" (Notify);
- duyệt k trên n;
- số tiền là giá trị lựa chọn (có cận);
- bước đầu có nhiều người thay thế nhau.

### AFF-7. Dùng sai kênh "không biểu diễn được"

- **Hiện tượng:**
  - thông tin còn thiếu bị báo là "không biểu diễn được", ví dụ "Missing deadlines and deposit flow…"
    (case 43), "Thiếu thời gian, hạn nạp…" (26), "Commission split without deposit…" (74);
  - có lúc cả prompt bị gắn cờ (30, 48, 75);
  - khi người dùng đồng ý bỏ phần không làm được, pipeline vẫn hỏi lại (50, 18);
  - khi yêu cầu bất khả, pipeline dừng ở `WAITING_USER` và hỏi "có bỏ được không" (92, 94–100), thay vì
    kết thúc rõ ràng `UNSUPPORTED` (chỉ case 93 làm vậy).
- **Đề xuất:**
  - tách hai loại: *thiếu thông tin* (hỏi) và *không làm được* (đề nghị bỏ);
  - phần đã được người dùng đồng ý bỏ thì xóa khỏi FactDraft;
  - nếu phần lõi bất khả thì kết thúc `UNSUPPORTED` kèm lý do.

### AFF-8. Chất lượng câu hỏi

- **Hiện tượng:**
  - câu hỏi về cách cài đặt thay vì về sự kiện, ví dụ "How should the multi-signature agreement be
    structured?" (54) hay "bound của choice cần tính theo lovelace, có đúng không?" (82);
  - câu hỏi lặp lại (95, 98);
  - hỏi lại điều prompt đã nói (45, 50).
- **Đề xuất:**
  - câu hỏi chỉ hỏi sự kiện (ai, bao nhiêu, khi nào, nếu không thì sao);
  - bỏ câu trùng;
  - không hỏi điều đã có trích dẫn trong hội thoại.

### AFF-9. Sửa lỗi sau khi cổng chặn (2 case)

- **Hiện tượng:** case 65 và 81, cổng Scenario chặn đúng:
  - case 65: cấu trúc `When` rỗng, trả 2000 ADA từ tài khoản không có tiền;
  - case 81: nạp vào sai tài khoản.

  Phản hồi gửi lại cho model chỉ là "observable mismatch: status / payments", quá ngắn để sửa.
- **Đề xuất:** gửi lại tên kịch bản lỗi, các giao dịch, và khoản trả mong đợi so với thực tế.

### AFF-10. Lỗi builder riêng lẻ

- Case 48: "deadline value contradicts cited calendar date" với mẫu "mỗi tháng từ tháng 3/2027" trong
  câu không dấu.
- Case 91: model trả JSON không chuẩn, và lỗi này cũng dừng hẳn (giống AFF-1).

## 3. Cổng Scenario và kịch bản tham chiếu

### Đánh giá chung

Khi rà lại các case bị chặn (28, 65, 71, 75, 76, 81, 51–56), **cổng Scenario chặn đúng ở mọi case**:
- sai người kích hoạt;
- số tiền nhỏ hơn 1000 lần;
- sai tài khoản;
- chỉ một người được duyệt.

Không có case nào bị chặn chỉ vì kịch bản sai. Nhưng có ba điểm yếu.

### S-1. So khớp tên theo chuỗi ký tự

Case 75: kịch bản viết "CongTy" (theo phiếu dữ kiện), còn hợp đồng viết "Công ty". Nếu hợp đồng đúng ở
mọi chỗ khác thì cổng vẫn báo lệch, chỉ vì tên. Case này còn sai người kích hoạt nên kết quả không đổi,
nhưng đây chính là loại "chặt vô lý" cần bỏ.

**Đề xuất:** khi gắn tên trong kịch bản vào role token của hợp đồng, dùng quy ước tên ở AFF-2. Tên được
gấp (bỏ dấu, hoa thường, khoảng trắng, danh xưng) và so với cả tên hiển thị lẫn role token của intent.
Phải ánh xạ một đối một; nếu hai bên trùng sau khi gấp thì báo mơ hồ chứ không tự ghép.

### S-2. Kịch bản phủ thiếu nhánh

Case 58 và 61 là "ai nạp trước". Kịch bản chỉ dùng một người mua, đúng người mà hợp đồng sai đã chọn,
nên hợp đồng chỉ cho một người mua vẫn lọt qua.

**Đề xuất mẫu kịch bản theo họ hợp đồng:**
- một kịch bản cho mỗi người trong nhóm "ai cũng được" (ít nhất 2 người khác nhau);
- một kịch bản cho mỗi nhánh hết hạn;
- với k trên n: một kịch bản đúng k người, một kịch bản k − 1 người;
- với khấu trừ: các giá trị 0, giữa và cận trên.

### S-3. Nguồn của kịch bản

Giao thức hiện nói kịch bản "viết từ intent". Nếu intent đã sai thì kịch bản có thể thừa hưởng lỗi đó.
Trên thực tế tôi viết theo prompt, phiếu dữ kiện và các câu trả lời, chỉ lấy tên từ intent.

**Đề xuất:** ghi rõ điều này thành luật: *nội dung* kịch bản lấy từ yêu cầu của người dùng, còn *tên* thì
gắn qua quy ước S-1.

### S-4. Chẩn đoán k trên n

Với k trên n, cổng trả `INCONCLUSIVE` ("declared Choice action cannot bind uniquely") thay vì chỉ ra
rằng chỉ một người chọn được. Kết quả chặn vẫn đúng, nhưng thông tin không giúp sửa.

**Đề xuất:** khi kịch bản có lựa chọn của một người mà hợp đồng không có, báo `VIOLATED` kèm tên người đó.

### S-5. Viết tay, không có mẫu

Tôi viết tay 117 kịch bản, mỗi case khác nhau và không có mẫu theo họ. Các mẫu ở S-2 vừa giảm công vừa
giảm sai sót của người viết.

## 4. Dataset v3

| Mã | Vấn đề | Ví dụ | Đề xuất |
| --- | --- | --- | --- |
| D-1 | Một bên có hai danh tính (tên và role) | "Công ty Sao Mai, role SaoMai" (68); "Công ty, role CongTy" (75); "Nhi (người thuê)" (38) | Mỗi bên trong `spec.roles` có `name` và `role`; chấm theo danh tính (AFF-2) |
| D-2 | Role token khi có dấu, khi ASCII | `Kiều`, `Sóng` cạnh `TruongHoc`, `CongTy` | Thống nhất: role token là ASCII suy ra tất định, tên hiển thị giữ dấu |
| D-3 | Chữ mơ hồ không giải được bằng phiếu dữ kiện | "Me" (mẹ) trong câu không dấu (55); "minh" (79) | Thêm mục phiếu dữ kiện cho các chữ này, hoặc ghi "chấp nhận hỏi lại" |
| D-4 | Phiếu dữ kiện thiếu câu trả lời cho câu hỏi hợp lý | "ai cũng bấm được không?" (76); đơn vị nhập (82, 83) | Mỗi phần tử của `spec` không có nguyên văn trong prompt phải có một mục phiếu dữ kiện; thêm các câu chuẩn (giờ, múi giờ, năm, hoàn tiền khi hết hạn) |
| D-5 | Tiêu chí thành công của `reject_unsupported` và `converge_and_decline_extra` chưa rõ | Pipeline chỉ hỏi "có bỏ được không" mà vẫn được tính thành công (92, 94–100) | Ghi rõ: phải nêu phần không làm được *và* không giao hợp đồng (bất khả); hoặc giao phần làm được *và* nêu phần bỏ (decline_extra) |
| D-6 | Chia dev và đánh giá không phân tầng theo họ | Dev toàn họ dễ; mọi họ khó nằm ở phần đánh giá | Tập mới chia theo họ: mỗi họ có case ở cả dev và đánh giá |
| D-7 | `checks.scenarios` có sẵn nhưng không dùng để chấm | Việc chấm là người phân xử | Chấm tự động bằng `checks.scenarios` trên bộ tham chiếu Haskell, với so khớp tên ở S-1; người phân xử chỉ xử lý case máy báo lệch (giảm thiên lệch một người chấm) |
| D-8 | Ghi chú role trong prompt không đều | "(role: TruongHoc)" ở case này, không có ở case khác | Chủ ý thì giữ, nhưng ghi vào `phenomena` để phân tích |

## 5. Quy ước chấm thống nhất (đề xuất, áp dụng như nhau cho hai nhánh)

1. **Danh tính các bên:** đúng nếu mỗi role ánh xạ một đối một tới đúng người thật. Cách viết role token
   là tự do: dấu, khoảng trắng, danh xưng, ASCII hay không. Sai nếu gộp hai người, đổi vai, hoặc dùng một
   người khác ("Minh" thay cho "Như" là sai).
2. **Thời gian:** lệch tối đa 1 phút, đúng múi giờ.
3. **Số tiền và token:** đúng tuyệt đối theo đơn vị nhỏ nhất. 120 BOOK khác 120 000 000 BOOK.
4. **Tên lựa chọn:** tự do. Giá trị lựa chọn phải ánh xạ nhất quán với nghĩa (0 là không, 1 là có…).
5. **Nhánh thừa vô hại** (một `Close` thêm, một bước chờ không tiền) được chấp nhận. Khoản trả thừa
   hoặc thiếu là sai.
6. **Bất khả** và **phần không làm được:** theo D-5.

**Chấm lại theo quy ước 1** (chưa áp dụng, chờ đồng ý):
- case 68 của Pipeline thành RIGHT, nên Pipeline lên **39/71 (54,9%)**;
- không verdict nào của Baseline đổi: các case có lỗi tên của Baseline (42, 44, 73, 79) đều sai người
  thật hoặc sai cả mốc giờ.

## 6. Bộ chạy và giao thức

- **Luật trả lời** "phần không làm được chỉ bỏ khi phiếu dữ kiện cho phép" là công bằng giữa hai nhánh.
  Nhưng nó khiến mỗi lần Pipeline báo nhầm "không biểu diễn được" (AFF-7) gần như chắc chắn dẫn đến bỏ
  cuộc: các case 82, 86 và 90. Nên giữ luật này, vì nó phạt đúng lỗi của Pipeline, và sửa ở phía AFF.
- **Tự động duyệt intent** che mất lỗi intent mà người thật có thể bắt được (role ở 68, một người mua ở
  58 và 61). Có thể thêm một bước duyệt mô phỏng: so intent với phiếu dữ kiện theo quy ước tên.
- **Một model nhỏ, free tier, mỗi case một mẫu:** kết quả từng case dao động. Case 58 dao động giữa hai
  hợp đồng khi chạy lại.

## 7. Thứ tự làm đề xuất

1. **Chốt quy ước** ở mục 2 (AFF-2), 3 (S-1) và 5, trước khi sửa code. Đã chốt ở
   `docs/E7-Conventions.md` (bản 1).
2. **AFF-1** (sửa lỗi thay vì dừng hẳn), **AFF-2** (tên), **AFF-3** (giờ cho danh sách), **AFF-4** (số):
   chi phí thấp, ảnh hưởng tới khoảng 15 case.
3. **AFF-7** và **AFF-8** (kênh "không làm được", chất lượng câu hỏi).
4. **AFF-6:** Notify, k trên n, số tiền theo lựa chọn, bước đầu có nhiều người. Chi phí cao nhất, ảnh
   hưởng 13 case.
5. **Mẫu kịch bản theo họ** (S-2) và so khớp tên (S-1); chẩn đoán rõ hơn (S-4, AFF-9).
6. **Dataset v4:** sửa D-1 đến D-5; chia dev và đánh giá theo họ (D-6); chấm tự động bằng `checks`
   (D-7). Đóng băng v4 trước khi chạy vòng đánh giá mới. v3 từ nay chỉ là dev.
