# E5 — Evidence Gates (RQ2)

Trạng thái: **giao thức chốt 2026-11-09, trước khi đo.** Mọi thay đổi sau ngày này được ghi ở
mục "Lệch giao thức", kèm lý do.

## 1. Câu hỏi

RQ2 trong paper (mục 7.1): các cổng bằng chứng có loại được hợp đồng có mâu thuẫn hành vi đã
biết, mà không loại quá nhiều hợp đồng chấp nhận được hay không? Paper chọn đây làm phép so sánh
chính: chính sách bằng chứng đầy đủ so với điều kiện có intent cấu trúc nhưng không có chính
sách đó, chạy trên **đúng cùng một tập hợp đồng ứng viên đã gán nhãn**.

E5 không gọi model nào. Mọi hợp đồng ứng viên đều đã có sẵn hoặc được sinh tất định.

## 2. Hợp đồng ứng viên

Ba tập, báo riêng từng tập:

| Tập | Nguồn | Vai trò |
| --- | --- | --- |
| **M** (biến thể) | Biến đổi tất định từ hợp đồng tham chiếu của dataset (mục 3) | Kết quả chính: biết loại lỗi, đủ mẫu |
| **R-all** | Mọi hợp đồng khác nhau do model sinh trong E3 (75 hợp đồng ở 54 case dev) | Cổng có chặn được lỗi thật của model không |
| **R-final** | Hợp đồng cuối của mỗi case E3 (54) | Bao nhiêu lỗi thật lọt qua đủ các cổng |

R-all và R-final là mẫu đã qua chọn lọc: pipeline E3 sinh lại khi bị lint hoặc SMT chặn, nên
phần lớn hợp đồng cuối đã qua các cổng đó. Hai tập này không dùng để ước lượng tỷ lệ chặn của
một cổng mà chính pipeline đã dùng để lọc.

Hai giai đoạn:

1. **Dev**: case 1–56 (bỏ 57). Ở giai đoạn này mới được viết toán tử biến thể, bộ gán nhãn và
   code chạy cổng. Kết quả là khám phá.
2. **Gộp 99 case**: khi session E3 cho case 58–100 chạy xong, thêm biến thể của case 58–100 và
   hợp đồng E3 của các case đó, rồi chạy **một lần** với code đã chốt ở cuối giai đoạn dev
   (tag `e5-freeze`). Phần case 58–100 là tập giữ lại: chưa từng dùng để chỉnh cổng, toán tử
   hay bộ gán nhãn. Nếu session E3 chưa xong thì không có giai đoạn 2.

## 3. Biến thể

Áp lên hợp đồng tham chiếu của mỗi case. Mỗi toán tử lấy tối đa 2 vị trí áp dụng đầu tiên, theo
thứ tự duyệt cây cố định. Toán tử chỉ là giả thuyết về kết quả: **nhãn luôn do bộ gán nhãn quyết
định** (mục 4). Một biến thể "sai" mà hóa ra tương đương sẽ được tính là đúng, và được báo riêng.

Toán tử dự kiến làm sai: đổi người nhận của một `Pay`; nhân số tiền với 1/2, 2 hoặc 10⁶ (lỗi
đơn vị lovelace); đổi bên nạp; dời một hạn ±3 ngày; đảo hai nhánh của `If`; đổi
`timeout_continuation` với nhánh của case đầu; bỏ một `Pay`; dời ngưỡng so sánh giá trị chọn;
đổi token ADA thành `token_name: "ADA"`; thu hẹp khoảng `choose_between`.

Toán tử dự kiến giữ nguyên nghĩa (để đo từ chối nhầm): đổi thứ tự các case của `When` khi
chúng không chồng nhau; tách một `Pay` thành hai `Pay` cộng lại bằng số cũ; bọc bằng
`If true`; dời mọi hạn vài giờ trong cùng ngày; đổi tên một choice ở mọi nơi dùng nó.

Hợp đồng tham chiếu gốc cũng là một ứng viên đúng.

## 4. Nhãn (ground truth)

Bộ gán nhãn độc lập với các cổng:

- Dùng bộ mô phỏng Python `dataset/marlowe_sim.py`, không dùng bộ thực thi Haskell mà cổng dùng.
- **So khác biệt có giới hạn** với hợp đồng tham chiếu: duyệt mọi chuỗi hành động có độ dài tối
  đa bằng độ sâu `When` lớn nhất cộng 1. Hành động gồm các khoản nạp và lựa chọn xuất hiện trong
  một trong hai hợp đồng; giá trị lựa chọn lấy ở hai đầu khoảng và quanh mỗi hằng số đem so.
  Thời điểm gồm: 1 ngày trước hạn đầu, giữa hai hạn liền nhau, 1 ngày sau hạn cuối, tính theo
  hạn của hợp đồng tham chiếu. Lựa chọn được khớp theo người chọn và giá trị, không theo tên.
- **SAI** nếu có một chuỗi mà hai hợp đồng khác nhau ở: hành động được nhận hay bị từ chối,
  số tiền mỗi bên nhận theo từng token, hoặc hợp đồng có đóng hay không. Hợp đồng không hợp lệ
  cấu trúc cũng là SAI. Chuỗi phân biệt được lưu làm nhân chứng.
- **ĐÚNG** nếu không chuỗi nào trong giới hạn phân biệt được. Các hạn lệch nhau dưới 1 ngày được
  chấp nhận: dataset ngầm định 12:00 UTC, còn prompt không nêu giờ.
- **KHÔNG ĐÁNH GIÁ ĐƯỢC** nếu bộ mô phỏng không chạy được hợp đồng (ví dụ có `DivValue`). Những
  hợp đồng này bị loại khỏi các tỷ lệ và được đếm riêng.
- Với hợp đồng do model sinh, tên bên được khớp sau khi chuẩn hóa (bỏ khoảng trắng hai đầu,
  không phân biệt hoa thường). Không thử hoán vị tên bên.

"Đúng" chỉ có nghĩa là không có khác biệt trong giới hạn đã duyệt, không phải chứng minh tương
đương.

## 5. Các điều kiện (chính sách)

Mỗi bậc thêm một cổng vào bậc trước. Mỗi cổng cho REJECT, ABSTAIN hoặc PASS:

| Bậc | Cổng thêm vào | REJECT khi | ABSTAIN khi |
| --- | --- | --- | --- |
| **B0** (đối chứng) | hợp lệ cấu trúc (`validate_contract`) | có lỗi cấu trúc | — |
| B1 | lint (`LogicGraphVerifier.lint`) | có lỗi lint | — |
| B2 | SMT pin (`smt_driver.analyze`) | có phản ví dụ | `Indeterminate`, `Timeout`, `InvalidInput`, `Unavailable` |
| B3 | kịch bản đã duyệt trên bộ thực thi tham chiếu (`SemanticComparisonPort`) | một kịch bản `VIOLATED` | `INCONCLUSIVE`, không bind được choice |
| **B4** (đầy đủ) | khám phá có giới hạn với oracle không cảnh báo (`explore`, `NoWarningsOracle`) | có vết cảnh báo | khám phá không kết luận |

Quyết định của một bậc: REJECT nếu có cổng nào REJECT; nếu không, ABSTAIN nếu có cổng nào
ABSTAIN; còn lại là ACCEPT. ACCEPT ở đây là "được đưa sang bước duyệt kỹ thuật tiếp theo", không
phải người dùng chấp nhận hay được triển khai.

**Kịch bản đã duyệt** (đầu vào của B3), đóng vai kịch bản người duyệt xác nhận:

- Với tập M: lấy các kịch bản trong `checks.scenarios` của case. Chạy từng kịch bản trên hợp đồng
  tham chiếu bằng bộ thực thi Haskell, rồi ghi trạng thái, các khoản trả và hợp đồng cuối (khi là
  `close`) làm kỳ vọng. Thời điểm theo hạn của hợp đồng tham chiếu, như `dataset/evaluator.py`.
- Với R-all và R-final: lấy đúng các file `behavior-expectation-*.json` mà E3 đã dùng cho case đó.
  Case không có file nào thì B3 ABSTAIN.

Bộ gán nhãn duyệt nhiều chuỗi hơn hẳn số kịch bản này, nên B3 không tự động bắt được mọi lỗi.

## 6. Chỉ số

Tính riêng cho từng tập M, R-all, R-final:

- **Chính:** tỷ lệ chấp nhận sai FA = P(ACCEPT | SAI), so B4 với B0.
- **Đồng chính:** độ phủ = P(ACCEPT | ĐÚNG) của B4.
- **Phụ:**
  - tỷ lệ từ chối nhầm P(REJECT | ĐÚNG) và tỷ lệ không quyết định P(ABSTAIN | ·);
  - FA của từng bậc B1–B3, để biết cổng nào có tác dụng;
  - tỷ lệ bị chặn theo từng toán tử biến thể;
  - những hợp đồng SAI mà B4 vẫn ACCEPT, kèm nhân chứng.
- **Chi phí (RQ4):** số lần gọi SMT và bộ thực thi tham chiếu, thời gian chạy mỗi hợp đồng.

Thống kê:

- **Khoảng tin cậy:** Wilson 95% cho mỗi tỷ lệ, và bootstrap theo case (10 000 lần), vì các hợp
  đồng cùng case tương quan với nhau.
- **So sánh B4 với B0:** McNemar chính xác hai phía, ghép cặp trên cùng các hợp đồng SAI.

## 7. Quy tắc quyết định (chốt trước khi đo)

Trên tập M, ở giai đoạn gộp 99 case (nếu không có giai đoạn này thì ở dev, và ghi rõ đó là kết
quả khám phá), RQ2 được trả lời **có** khi đủ cả ba điều:

1. FA của B4 thấp hơn FA của B0 với p < 0,05.
2. Độ phủ của B4 trên hợp đồng ĐÚNG ≥ 0,80.
3. Tỷ lệ từ chối nhầm của B4 ≤ 0,10.

Thiếu điều 2 hoặc 3 nghĩa là cổng chặn được lỗi nhưng loại quá nhiều hợp đồng đúng. Kết quả của
R-all và R-final được báo kèm, không nằm trong quy tắc.

## 8. Giới hạn đã biết

- Biến thể là lỗi do mình tạo ra, có thể dễ bắt hơn hoặc khó bắt hơn lỗi thật của model.
- Hợp đồng tham chiếu và kịch bản do cùng một bộ sinh dataset tạo ra.
- Giới hạn độ sâu khi duyệt có thể bỏ sót khác biệt nằm ở chuỗi dài hơn.
- B3 dùng kịch bản lấy từ dataset. Nếu kịch bản do người dùng thật viết thì có thể ít hơn hoặc
  khác đi.
- Hợp đồng E3 do Nemotron sinh; hợp đồng của case 58–100 do Gemini sinh.

## 9. Kết quả

(Chưa có.)

## Lệch giao thức

(Chưa có.)
