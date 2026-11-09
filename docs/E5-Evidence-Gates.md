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

### 9.1 Dev, case 1–56 (khám phá, ghi 2026-11-10)

Chạy trong WSL bằng các binary pin (`runs/e5/run_wsl.sh`). Kết quả nằm ở `runs/e5/dev-M`,
`dev-R`, `dev-R-dataset`; điểm số ở `runs/e5/*-score.json`. Không có request model nào.

**Tập M (biến thể):** 1 292 hợp đồng, 56 case. Bộ gán nhãn cho 948 SAI và 344 ĐÚNG.

| Bậc | Chấp nhận sai (SAI → ACCEPT) | Độ phủ (ĐÚNG → ACCEPT) | Từ chối nhầm (ĐÚNG → REJECT) |
| --- | --- | --- | --- |
| B0 cấu trúc | 1,000 | 1,000 | 0 |
| B1 + lint | 1,000 | 1,000 | 0 |
| B2 + SMT | 0,695 | 1,000 | 0 |
| B3 + kịch bản | 0,204 | 0,532 | 0,462 |
| **B4 + khám phá** | **0,204** (Wilson 0,179–0,230; theo case 0,171–0,240) | **0,375** (theo case 0,338–0,411) | **0,462** |

- **B4 so với B0 trên hợp đồng SAI:** 755 hợp đồng chỉ B0 chấp nhận, 0 hợp đồng chỉ B4 chấp nhận;
  McNemar p ≈ 10⁻²²⁷.
- **Quy tắc quyết định (mục 7) trên dev: không đạt.**
  - Điều 1 (chấp nhận sai thấp hơn B0) đạt.
  - Điều 2 (độ phủ ≥ 0,80) và điều 3 (từ chối nhầm ≤ 0,10) không đạt.

**Từng cổng:**

- **Lint** không chặn hợp đồng nào: mọi biến thể đều hợp lệ cấu trúc và qua lint.
- **SMT** chặn 289 hợp đồng: cả 108 biến thể nhân đôi số tiền trả, cả 108 biến thể lỗi đơn vị
  lovelace, và các biến thể khiến tài khoản trả quá số dư.
- **Kịch bản** đem lại phần lớn hiệu quả: chấp nhận sai giảm từ 0,695 xuống 0,204. Nhưng 46%
  hợp đồng ĐÚNG cũng bị từ chối.
- **Khám phá** không chặn thêm hợp đồng SAI nào ngoài những hợp đồng B3 đã chặn. Nó chỉ làm giảm
  độ phủ: với 54 hợp đồng bọc trong `If true`, `DeclaredActionDomain` không đi qua nút `If` ở gốc,
  nên không sinh được vết nào và cho ABSTAIN.

**Hợp đồng SAI lọt qua B4 (193):** dời hạn ±3 ngày (132), đổi người nhận (16), bỏ một khoản trả
(16), trả một nửa (16), đổi bên nạp (8), đổi ngưỡng so sánh (5). Đó là các chỗ mà kịch bản
không chạm tới: hạn thứ hai, nhánh không được thử, giá trị nằm giữa hai ngưỡng.

**Hợp đồng ĐÚNG bị từ chối (159).** Nguyên nhân nằm ở cách B3 so, không nằm ở hợp đồng:

- B3 so danh sách từng lần trả chứ không so tổng. Tách một khoản trả thành hai làm 92/108 biến thể
  bị từ chối; hoàn tiền tường minh thay cho hoàn tiền khi `close` làm 24 biến thể bị từ chối.
- Kịch bản dataset thử đúng 1 giây sau mỗi hạn. Dời mọi hạn thêm 3 giờ trong cùng ngày làm 41/54
  biến thể bị từ chối. Bộ gán nhãn chấp nhận lệch dưới 1 ngày.

**Tập R (hợp đồng E3 do Nemotron sinh), dùng kịch bản E3:**

| Tập | Hợp đồng | SAI / ĐÚNG | Chấp nhận sai B4 | Độ phủ B4 | Từ chối nhầm B4 |
| --- | --- | --- | --- | --- | --- |
| R-all | 75 (54 case) | 47 / 28 | 11/47 = 0,234 | 17/28 = 0,607 | 1/28 |
| R-final | 54 | 26 / 28 | 11/26 = 0,423 | 17/28 = 0,607 | 1/28 |
| R-all, chỉ case `complete` | 49 | 28 / 21 | 5/28 | 14/21 | 1/21 |
| R-final, chỉ case `complete` | 31 | 10 / 21 | 5/10 | 14/21 | 1/21 |

- **Ở B0, mọi hợp đồng đều được chấp nhận.** B2 chỉ chặn 4/47 hợp đồng SAI ở R-all; ở R-final,
  B2 không chặn hợp đồng nào. Điều này khớp với chọn lọc đã biết: E3 sinh lại hợp đồng mỗi khi
  lint hoặc SMT chặn.
- **25/54 case không có file kịch bản E3,** nên B3 ABSTAIN. Vì vậy 10/28 hợp đồng ĐÚNG và 22/47
  hợp đồng SAI dừng ở ABSTAIN.
- **Không nên đọc nhãn của tập R như nhãn của tập M,** vì hai lý do:
  - Ở case `missing`, 12/15 hợp đồng cuối bị gán SAI. Người dùng mô phỏng của E3 chỉ được đọc
    prompt, nên phải tự đặt các dữ kiện còn thiếu, ví dụ số tiền nạp. Hợp đồng tham chiếu lại dùng
    dữ kiện ẩn của dataset, nên "SAI" ở đây phần lớn phản ánh giả định mô phỏng, không phải lỗi
    của model.
  - Ở case `complete`, 10/31 hợp đồng cuối bị gán SAI. Các nhân chứng cho thấy phần lớn là khác
    cách mã hóa: một choice có giá trị 0/1 thay cho hai choice riêng, hay có thêm `Notify`. Một số
    khác biệt như vậy có thể chấp nhận được về nghiệp vụ. Bộ gán nhãn so hành vi với đúng một
    cách mã hóa tham chiếu, nên nghiêm hơn "đúng nghĩa". Paper yêu cầu hai người duyệt độc lập,
    và việc đó chưa làm.

**Tập R với kịch bản dataset** (phân tích thêm, xem lệch giao thức 1): B4 chấp nhận sai 3/47 và
độ phủ 5/28; từ chối nhầm 23/28. Kịch bản dataset dùng tên choice và giờ 12:00 UTC của hợp đồng
tham chiếu, trong khi hợp đồng E3 dùng tên và giờ khác (thường là 23:59 giờ Việt Nam). Vì vậy
kịch bản không khớp giao diện của hợp đồng. Con số này cho thấy kịch bản phải do người duyệt viết
cho chính hợp đồng đó; nó không đo được chất lượng cổng.

**Chi phí (RQ4), tập M:** 10 898 lần gọi bộ thực thi tham chiếu và 1 292 lần gọi SMT, tổng 747 giây
trong WSL (khoảng 0,58 giây mỗi hợp đồng).

**Kết luận tạm (dev):** các cổng chặn được phần lớn lỗi có kiểm soát (chấp nhận sai 100% → 20%),
nhưng với cách so hiện tại, B3 từ chối gần một nửa số hợp đồng tương đương. Theo quy tắc đã chốt,
RQ2 trên dev là **chưa** (loại quá nhiều hợp đồng đúng). Khám phá (B4) không đem lại gì thêm. Chưa
sửa cổng nào sau khi thấy số liệu này.

### 9.2 Gộp 99 case

(Chờ session E3 cho case 58–100.)

## Lệch giao thức

1. **(2026-11-09, trước khi xem số liệu)** Thêm phân tích tập R với kịch bản dataset (`dev-R-dataset`),
   vì chỉ 29/54 case E3 có file kịch bản. Phân tích này không nằm trong quy tắc quyết định.
2. **(2026-11-10, sau khi xem số liệu dev)** Báo thêm tập R thu hẹp về các case `complete`. Lý do:
   ở các case `missing` và `ambiguous`, nhãn bị lẫn với dữ kiện do người dùng mô phỏng tự đặt
   (mục 9.1). Đây là quyết định sau khi thấy số liệu, nên chỉ mang tính mô tả.
3. **Sửa bộ gán nhãn trước khi chạy dev** (lần chạy thử trên dev): coi partial pay là khác biệt,
   thử một ngày trước và sau mỗi hạn, so số tiền đã nhận ở từng mốc. Khi sửa, mình chỉ xem bảng
   nhãn theo toán tử, chưa chạy cổng nào.
4. **Session E3 cho case 58–100** sửa câu báo lỗi của `validate_contract` (commit `7745361`): chỉ
   thêm gợi ý tên field, kết quả đạt/không đạt giữ nguyên. Như vậy case 58–100 nhận lời báo lỗi
   rõ hơn case 1–57 khi model sinh lại, và chạy trên Gemini thay vì Nemotron.
5. **Lộ một fixture của case 88:** khi tìm chuỗi lỗi cũ, session E3 đã in ra
   `tests/dataset/fixtures/audit/vi-swap-L3-010-full.json` (case 88). File này chứa prompt gốc,
   cùng câu hỏi làm rõ và câu trả lời mô phỏng của pipeline cũ (policy ID, múi giờ). Không có
   hợp đồng tham chiếu, `checks`, `params` hay dữ kiện ẩn. Session đó cam kết không dùng lại các
   câu trả lời này.
