# E6 — Thiết kế dataset v3 (bản để duyệt)

Trạng thái: **bản nháp chờ người phụ trách duyệt** (2026-11-10). Chưa viết case nào ngoài các mẫu ở
mục 8. Kế hoạch chung: `docs/E6-Plan.md`.

## 1. Mục tiêu và nguyên tắc

- **Làm khó hệ thống để lộ điểm yếu**, không làm đẹp con số. Mỗi điểm yếu đã biết từ E3–E5 phải có
  case nhắm thẳng vào nó (mục 5).
- **Lời yêu cầu giống người dùng thật nói với hệ thống.** Họ cần một smart contract, nên nói thẳng
  vào việc: thường là ngôi thứ nhất ("tôi", "chúng tôi"), có thể ngắn, gạch đầu dòng, viết vội.
  Không chào hỏi, không kể chuyện, không mở đầu kiểu "An ở Huế đây, Bình ơi…".
- **Không có oracle giá.** Mọi quyết định đến từ hành động của một bên có tên (nạp tiền, chọn, Notify)
  hoặc từ thời gian.
- **Phủ rộng hơn v2:** nhiều họ hợp đồng hơn, nhiều cấu trúc Marlowe hơn, nhiều hiện tượng ngôn ngữ hơn.
  Ma trận độ phủ (mục 3–4) được chốt trước; dataset chỉ đạt khi phủ hết.
- **Tách khỏi v2:** file riêng `dataset/v3/cases.jsonl`, ID bắt đầu từ `v3-`. Không trộn với v2.

## 2. Phân bố tổng (100 case)

| Trục | Phân bố |
| --- | --- |
| Ngôn ngữ | 60 tiếng Việt (trong đó ≥10 không dấu), 40 tiếng Anh (trong đó ≥8 trộn Việt–Anh) |
| Kỳ vọng | 40 đủ thông tin; 25 thiếu thông tin, phải hỏi; 10 mơ hồ; 10 mâu thuẫn hoặc tự đính chính; 5 khả thi nhưng kèm một yêu cầu phụ ngoài khả năng; 10 bất khả hoặc ngoài phạm vi |
| Độ dài | ≥15 case rất ngắn (1–2 câu); ≥20 dạng gạch đầu dòng; ≥8 dài (đặc tả kiểu tài liệu, có chi tiết thừa) |

## 3. Họ hợp đồng (90 case khả thi + 10 bất khả)

| Họ | Số case | Ghi chú cấu trúc |
| --- | --- | --- |
| Ký quỹ 2 bên | 4 | xác nhận và báo lỗi trong cùng một `When` |
| Ký quỹ có trọng tài | 4 | trọng tài chọn 1 hoặc 2 |
| Hoán đổi token | 4 | ADA với token có policy cụ thể |
| Cho vay | 4 | giải ngân khi nạp, trả gốc kèm lãi |
| Vesting / trả theo lịch | 4 | ≥3 đợt ở một số case |
| Nghiệm thu theo chặng | 4 | chặng độc lập hoặc tuần tự |
| Gây quỹ đủ mức | 4 | ≥3 người góp ở một số case |
| Bên thứ ba báo giá (người, không phải oracle) | 4 | ngưỡng, `If` |
| Đặt cọc thuê | 4 | |
| Phí hủy | 4 | |
| **Trả góp nhiều kỳ** (mới) | 6 | ≥4 `When` lồng nhau; trễ một kỳ thì dừng |
| **Duyệt k trên n người** (mới) | 6 | 2/3, 3/5; đếm số duyệt bằng các nhánh |
| **Bán cho người đến trước** (mới) | 5 | `When` có nhiều nhánh cạnh tranh |
| **Trái phiếu zero-coupon** (mới) | 4 | nhà đầu tư nạp → chuyển cho bên phát hành → hoàn trả khi đáo hạn |
| **Trái phiếu có coupon** (mới) | 5 | nhiều kỳ lãi rồi trả gốc |
| **Chia tiền cho nhiều bên** (mới) | 5 | ≥4 người nhận, phần trăm, số lẻ |
| **Vay có tài sản thế chấp** (mới) | 5 | hai token; không trả thì tài sản thế chấp về bên cho vay; chuyển giữa các tài khoản |
| **Đặt cọc khấu trừ theo mức chọn** (mới) | 5 | giá trị chọn được dùng làm số tiền trả |
| **Tài trợ đối ứng** (mới) | 4 | nhà tài trợ góp bằng tổng người khác góp, có trần (`If`, `Let`) |
| Yêu cầu phụ ngoài khả năng (rải trong các họ trên) | 5 | ví dụ "tự gửi email nhắc", "tự chạy không cần giao dịch" |
| **Bất khả hoặc ngoài phạm vi** | 10 | xóa lịch sử, lãi kép không giới hạn, rút bất kỳ lúc nào không có nguồn tiền, cần oracle giá, KYC, sửa hạn sau khi đã chạy… |

## 4. Độ phủ tối thiểu theo cấu trúc Marlowe và hiện tượng ngôn ngữ

**Cấu trúc Marlowe** (đếm trên hợp đồng tham chiếu):

| Cấu trúc | Tối thiểu |
| --- | --- |
| `Notify` | 6 |
| `When` nhiều nhánh cạnh tranh | 10 |
| Chuyển tiền giữa các tài khoản | 5 |
| Giá trị chọn dùng làm số tiền | 5 |
| `If` / `Let` | 12 |
| ≥3 `When` lồng nhau | 20 |
| ≥4 bên | 12 |
| Nhiều loại token trong một hợp đồng | 8 |
| Số lẻ (ví dụ 12,5 ADA) | 8 |

**Hiện tượng ngôn ngữ:**

| Hiện tượng | Tối thiểu |
| --- | --- |
| Người dùng là một bên ("tôi") | 50 |
| Có giờ cụ thể | 30 |
| Có múi giờ | 30 |
| Thời gian tương đối ("5 ngày sau khi…") | 25 |
| Phần trăm | 10 |
| Số viết bằng chữ | 8 |
| Đơn vị lovelace | 4 |
| Sai chính tả | 8 |
| Người dùng tự đính chính | 8 |
| Đại từ mơ hồ ("bên kia", "chúng tôi") | 6 |

## 5. Nhắm vào điểm yếu đã biết

Mỗi điểm yếu có ít nhất 3 case nhắm thẳng vào nó.

| Điểm yếu (nguồn) | Case làm khó |
| --- | --- |
| Hạn thứ hai bị dời mà kịch bản không chạm tới (E5) | ≥3 hạn, các hạn cách nhau không đều, hạn tính từ một sự kiện khác |
| `Notify` cho phép trả sớm (E3 dev) | "trả vào ngày X, không cần ai thao tác" bên cạnh một bước có người xác nhận |
| Token hex hoặc sai policy (E3 dev) | người dùng đưa policy ID và tên token dạng hex, hoặc dạng chữ |
| Tên có dấu bị bỏ dấu, địa chỉ ví thay cho role (E3 test) | tên nhiều dấu (Quỳnh, Nguyễn Thị Ánh), tên trùng một phần, người dùng tự đưa địa chỉ ví |
| Người kể chuyện bị đưa thành một bên (E4) | "tôi làm hộ sếp", "chúng tôi" gồm nhiều người |
| Hoàn tiền qua `Close` và khoản lẻ (E5) | khấu trừ phần trăm, tiền dư phải về đúng người |
| Các nửa khoản độc lập (E3) | chặng 2 vẫn duyệt được khi chặng 1 trễ |
| Case bất khả bị chặn vì lỗi khác thay vì `UNSUPPORTED` (E3 test) | yêu cầu bất khả viết rất tự nhiên, xen lẫn phần khả thi |
| Mâu thuẫn bị bỏ qua (E4 bổ sung) | hai con số khác nhau ở hai chỗ, đính chính kiểu "à không" |

## 6. Định dạng một case

Mỗi dòng của `dataset/v3/cases.jsonl` là một case:

```json
{
  "id": "v3-vi-installment-001",
  "language": "vi",
  "family": "installment",
  "expected_behavior": "ask_then_converge",
  "info_mode": "missing",
  "phenomena": ["first_person", "relative_time", "bullet_list"],
  "marlowe_features": ["nested_when_4"],
  "prompt": "…lời người dùng gửi hệ thống…",
  "spec": {"roles": {}, "tokens": {}, "deadlines": {}, "flow": []},
  "fact_sheet": [{"topic": "…", "answer": "…"}],
  "adversarial_target": ["second_deadline", "first_person_party"],
  "author_note": "…vì sao case này khó…"
}
```

- **`expected_behavior`** nhận một trong các giá trị `converge`, `ask_then_converge`,
  `flag_conflict_then_converge`, `converge_and_decline_extra`, `reject_unsupported`.
- **`spec`** là đặc tả có cấu trúc. Code (`dataset/v3/builders.py`) dựng hợp đồng tham chiếu và kịch
  bản kiểm tra từ đặc tả này. Người viết không viết JSON Marlowe bằng tay.
- **`fact_sheet`** chứa các câu trả lời cho người dùng mô phỏng khi hệ thống hỏi. Nó là nguồn duy nhất
  cho dữ kiện mà prompt không nêu, và cả hai nhánh của E6 dùng chung.

## 7. Quy trình viết và kiểm

1. Viết đặc tả và prompt theo từng họ, đối chiếu với ma trận sau mỗi họ.
2. Viết builder cho họ mới. Mỗi hợp đồng tham chiếu phải:
   - qua `validate_contract`;
   - qua SMT, ra `Valid`;
   - qua mọi kịch bản của chính nó trên bộ thực thi tham chiếu.
3. Kiểm tự động:
   - không có prompt trùng hoặc gần trùng, trong v3 hay với v2;
   - đếm độ phủ theo mục 2–5;
   - mọi dữ kiện trong `spec` có mặt trong prompt hoặc trong `fact_sheet`;
   - không có chuỗi chào hỏi hay kể chuyện ("ở … đây", "ơi").
4. Đóng băng: ghi mã băm SHA-256 của `cases.jsonl` và commit **trước khi** chạy bất kỳ nhánh nào trên
   v3. Sau đó không sửa case nào; nếu buộc phải sửa thì ghi vào phần lệch giao thức.
5. Ghi rõ trong mọi báo cáo: người viết case cũng là người làm thí nghiệm, người đóng vai người dùng
   và người phân xử.

## 8. Case mẫu

**Mẫu 1 — vi, ký quỹ 2 bên, đủ thông tin, nhiều nhánh cạnh tranh, người dùng là một bên**

> Tạo giúp tôi hợp đồng ký quỹ mua laptop cũ. Tôi là Minh, người mua, sẽ nạp 45 ADA trước 23:59 ngày
> 20/03/2027 giờ VN. Người bán là Thảo. Nhận hàng xong tôi bấm xác nhận thì tiền chuyển cho Thảo. Nếu
> tôi báo hàng lỗi, hoặc đến 23:59 ngày 25/03/2027 mà tôi chưa xác nhận, thì hoàn tiền về cho tôi.

- Kỳ vọng: `converge`.
- Khó ở chỗ:
  - "tôi" phải được ánh xạ thành role Minh;
  - xác nhận và báo lỗi là hai lựa chọn của cùng một người trong cùng một `When`;
  - hạn thứ hai là hạn tuyệt đối, không phải "7 ngày sau".

**Mẫu 2 — en, trả góp, thiếu thông tin, ≥4 `When` lồng nhau**

> Need a contract to sell my motorbike in installments. Buyer is Kevin Tran. Price 600 ADA in 4 equal
> monthly payments, first one due April 1, 2027. If he misses a payment the deal stops and I keep
> whatever he already paid.

- Phiếu dữ kiện:
  - người bán là Daniel;
  - mỗi kỳ hạn 23:59 UTC+7 của ngày 1 các tháng 4, 5, 6, 7/2027;
  - mỗi kỳ nạp xong thì chuyển ngay cho người bán.
- Kỳ vọng: `ask_then_converge`.
- Khó ở chỗ:
  - phải hỏi tên người bán, giờ và múi giờ;
  - phải tự chia 150 ADA mỗi kỳ;
  - "monthly" là các hạn không đều nhau (30 hoặc 31 ngày);
  - các khoản đã trả không được hoàn lại.

**Mẫu 3 — vi không dấu, duyệt 2 trên 3, mơ hồ và thiếu**

> can hop dong quy chung: Lan, Hoa, Tuan moi nguoi gop 100 ADA truoc 1/4/2027. muon chuyen tien cho
> nha cung cap thi can 2 trong 3 nguoi dong y, han dong y la cuoi thang 4. khong du 2 nguoi dong y thi
> tra lai tien cho tung nguoi

- Phiếu dữ kiện:
  - nhà cung cấp là role `PhucAn`;
  - "trước 1/4" nghĩa là trước 00:00 ngày 01/04/2027 UTC+7;
  - "cuối tháng 4" nghĩa là 23:59 ngày 30/04/2027 UTC+7;
  - nếu có người không góp thì hoàn lại cho những người đã góp và đóng hợp đồng.
- Kỳ vọng: `ask_then_converge`.
- Khó ở chỗ:
  - viết không dấu;
  - phải đếm số người đồng ý bằng các nhánh;
  - có hai mốc mơ hồ;
  - thiếu tên người nhận;
  - phải xử lý trường hợp không ai góp đủ.

**Mẫu 4 — en, trái phiếu zero-coupon, đủ thông tin**

> Set up a zero-coupon bond. Investor: Alice. Issuer: Bob. Alice deposits 1,000 ADA by 2027-05-01 12:00
> UTC and it goes straight to Bob. Bob must deposit 1,050 ADA by 2027-11-01 12:00 UTC, which is then
> paid to Alice. If Bob doesn't pay, just close — nothing can be recovered on-chain.

- Kỳ vọng: `converge`.
- Khó ở chỗ:
  - chiều tiền đảo ở bước hai;
  - không được bịa ra một khoản hoàn cho Alice;
  - số có dấu phẩy phân cách hàng nghìn.

**Mẫu 5 — vi, trái phiếu có coupon, tự đính chính, người dùng là bên phát hành**

> Tôi cần phát hành trái phiếu nhỏ. Tôi là bên phát hành (role: AnBinh). Nhà đầu tư Hưng nạp 500 ADA
> trước 10/02/2027, số tiền chuyển luôn cho tôi. Tôi trả lãi 10 ADA mỗi quý, 4 kỳ, kỳ đầu hạn 10/05/2027;
> kỳ cuối trả lãi cộng 500 ADA gốc. Kỳ nào tôi không nạp đúng hạn thì dừng. À sửa lại: lãi là 12 ADA
> mỗi kỳ chứ không phải 10.

- Phiếu dữ kiện: mọi hạn là 23:59 UTC+7.
- Kỳ vọng: `converge`, dùng 12 ADA, sau khi hỏi giờ và múi giờ hoặc tự hỏi lại cho chắc.
- Khó ở chỗ:
  - đính chính nằm ở cuối tin nhắn;
  - có 5 `When` lồng nhau;
  - người dùng vừa là bên nạp lãi vừa là bên nhận tiền đầu tư.

**Mẫu 6 — vi, bất khả**

> Mình cần hợp đồng gửi tiết kiệm: gửi 200 ADA, lãi kép 0,5%/ngày tự động cộng, rút lúc nào cũng được,
> và hợp đồng tự gửi email nhắc khi gần đến hạn.

- Kỳ vọng: `reject_unsupported`.
- Lý do bất khả:
  - không có bên nào nạp tiền lãi;
  - lãi kép theo ngày không có giới hạn số kỳ;
  - Marlowe không gửi được email.
- Câu trả lời đúng là giải thích phần nào không làm được, và có thể đề xuất một phiên bản khả thi. Sinh
  hợp đồng luôn mà im lặng bỏ các phần không làm được là SAI.

## 9. Câu hỏi cần duyệt

1. Phân bố ở mục 2 và các họ ở mục 3 có ổn không?
2. Giọng văn của 6 mẫu đã đúng ý chưa: thẳng vào việc, ngôi thứ nhất, không kể chuyện?
3. Mức độ khó của các mẫu đã đủ chưa?
