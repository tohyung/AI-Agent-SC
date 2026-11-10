# Báo cáo các câu hỏi nghiên cứu RQ1–RQ4

Tư liệu để viết bài báo. Ghi ngày 2026-11-10, dựa trên E2–E5 (docs/JOURNAL.md,
docs/E4-Formalization-Comparison.md, docs/E5-Evidence-Gates.md). Mọi con số dưới đây đều có trong
tài liệu hoặc dữ liệu nêu ở mục 8. Chỗ nào chưa đo thì ghi là chưa đo.

Bốn câu hỏi lấy từ paper (mục 7.1):

- **RQ1:** intent đã duyệt có giữ đúng các yêu cầu do bên độc lập phân xử không?
- **RQ2:** các cổng bằng chứng có loại được mâu thuẫn hành vi đã biết mà không loại quá nhiều ứng viên
  chấp nhận được không?
- **RQ3:** toàn bộ quy trình tổng hợp có cải thiện mức khớp hành vi cuối cùng, khi tài nguyên được đối
  sánh, không?
- **RQ4:** các biện pháp đó tốn bao nhiêu lượt gọi model, độ trễ, công duyệt và tỷ lệ không quyết định?

## 0. Tóm tắt

| RQ | Mức trả lời | Câu trả lời ngắn |
| --- | --- | --- |
| RQ1 | **Một phần** | Bước trích intent bằng AFF giữ đúng nghĩa tốt hơn hẳn DCF trên tập test đóng (quyết định đúng trên core hợp lệ 0,47 → 0,86). Nhưng 3/19 intent được chấp nhận vẫn khác nghĩa tham chiếu, bước "duyệt" là người dùng mô phỏng, và nhãn chưa có hai người phân xử độc lập. |
| RQ2 | **Có** (theo quy tắc chốt trước) | Trên 2 259 biến thể của 99 case, cổng đầy đủ giảm chấp nhận sai từ 100% xuống 19% và vẫn chấp nhận 94,4% hợp đồng đúng; từ chối nhầm 0,8%. Đạt cả ở tập giữ lại. Khoảng 19% lỗi, chủ yếu là dời hạn, vẫn lọt qua. |
| RQ3 | **Chưa trả lời theo đúng định nghĩa** | Chưa có nhánh đối chứng dùng cùng tài nguyên. Bằng chứng mô tả: quy trình E3 cho hợp đồng đúng ở 47/56 case dev và 34/43 case test; vòng sinh lại nâng tỷ lệ hợp đồng đúng từ 38/54 lên 47/54 (dev) và từ 28/36 lên 34/36 (test). |
| RQ4 | **Một phần** | Có số lượt gọi model, số lượt chạy, số câu trả lời của người dùng mô phỏng, chi phí cổng và tỷ lệ không quyết định. Chưa đo độ trễ model, chưa đo công duyệt của người thật. |

## 1. Bối cảnh chung

- **Dữ liệu:** 100 case tổng hợp, sinh từ template với seed cố định (dataset v2, SHA `e05c23f4…a907a`).
  - 11 họ hợp đồng, 60 tiếng Việt và 40 tiếng Anh.
  - Mức thông tin: `complete` 55, `missing` 30, `ambiguous` 10, `infeasible` 5.
  - Mỗi case có hợp đồng tham chiếu và 1–4 kịch bản kiểm tra.
  - Không có yêu cầu nào do người dùng thật viết.
- **Chia tập:** dev là case 1–56. Case 57 bị loại khỏi mọi phép đo, vì trường đánh giá của nó đã bị đọc
  ngày 2026-10-27. Test là case 58–100, chỉ đọc `prompt` khi chạy.
- **Model:**
  - Nemotron (`nvidia/nemotron-3-ultra-550b-a55b:free`, 50 request/ngày) dùng cho E2, E3 trên dev và
    phần đầu E4.
  - Từ 2026-11-07, model chính thức là Gemini (`gemini-3.5-flash-lite` bản miễn phí, 500 request/ngày).
    Lý do: người phụ trách không có ngân sách.
- **Người dùng:** mọi câu trả lời, mọi lần viết lại yêu cầu, mọi xác nhận intent và mọi kịch bản kỳ
  vọng trong E3 đều do một agent (Claude) đóng vai, chỉ đọc `prompt`. Không có người dùng thật.
- **Ledger:** chỉ kiểm kích thước giao dịch trên testnet Babbage riêng. Không ký, không gửi giao dịch
  nào, không triển khai.
- **Hai cách trích intent:**
  - DCF (Direct Core Formalization): model viết thẳng core.
  - AFF (Atomic Fact Formalization): model viết các sự kiện nguyên tử, code dựng core.

  E4 chọn AFF, **nhưng pipeline chính vẫn dùng DCF** (`research/adapters/formalization_adapter.py`
  gọi `IntentShadowExtractor`). Mọi kết quả E3, kể cả case 58–100, là của DCF.

## 2. RQ1: intent có giữ đúng yêu cầu không

### Thí nghiệm

**E4** so DCF với AFF trên cùng các prompt, ở bước trích intent:

- **Dev:** 56 case, chỉnh prompt nhiều vòng.
- **Test:** 43 case (58–100). Code đóng băng ở tag `a2-test-freeze`, chạy một lần, mỗi case một mẫu.
  Quy tắc quyết định chốt trước.
- **Hai bộ prompt:** prompt gốc, và prompt có nêu giờ hết hạn cùng policy token.
- **Bộ bổ sung:** 24 case về mâu thuẫn.

So sánh dùng McNemar chính xác. Nghĩa của intent được so với hợp đồng tham chiếu qua phép so
`MATCH`/`SUBSET`/`DIFFERENT`.

### Kết quả (tập test, 43 case)

| Chỉ số | DCF gốc | AFF gốc | DCF có nêu | AFF có nêu |
| --- | --- | --- | --- | --- |
| Core hợp lệ (M2) | 0,581 | 0,953 | 0,674 | 0,953 |
| Quyết định đúng trên core hợp lệ | 0,465 | **0,860** | 0,581 | **0,814** |
| Request cho mỗi intent hợp lệ | 4,24 | 1,90 | 4,10 | 2,02 |
| Chấp nhận sai | 4 | 0 | 2 | 1 |
| Case `infeasible` làm đúng | 0/3 | 0/3 | 0/3 | 0/3 |

- **Quyết định đúng trên core hợp lệ:** prompt gốc 1 vs 18 case bất đồng, p = 0,0001; bộ có nêu 1 vs 11,
  p = 0,0063. Quy tắc đạt trên cả hai bộ prompt, nên giữ AFF.
- **Giữ nghĩa:** trong 19 case `complete` mà AFF chấp nhận (bộ có nêu), có 12 `MATCH`, 4 `SUBSET` và
  3 `DIFFERENT` (16%; Wilson 95% 6–38%). Ngưỡng là 20%, nên chỉ đạt theo ước lượng điểm. Trên dev,
  cùng code cho 31% `DIFFERENT`.
- **Bộ bổ sung (mâu thuẫn):** AFF nhận ra 5/12 mâu thuẫn, DCF 0/12 (p = 0,063). Không bên nào báo nhầm
  mâu thuẫn ở 12 case không có mâu thuẫn. Nhưng AFF chấp nhận sai 3 case có mâu thuẫn, DCF chấp nhận
  sai 1.
- **Bằng chứng từ E5:** so hợp đồng cuối của E3 với yêu cầu mà người dùng mô phỏng đã xác nhận,
  47/54 hợp đồng ĐÚNG ở dev và 34/36 ở test (mục 4). Đây là bằng chứng về cả chuỗi
  intent → hợp đồng, không riêng bước intent.

### Điểm mạnh

- Quy tắc quyết định chốt trước khi chạy test; code đóng băng bằng tag; test chạy đúng một lần; số liệu
  bất lợi được ghi đủ.
- AFF hơn DCF rõ rệt và nhất quán trên hai bộ prompt, tốn ít request hơn khoảng một nửa.
- Phép so nghĩa `MATCH`/`SUBSET`/`DIFFERENT` tách được "core hợp lệ" khỏi "core đúng nghĩa".

### Điểm yếu

- **Chưa có hai người phân xử độc lập.** Tham chiếu là hợp đồng do bộ sinh dataset tạo ra. Ở E5, phân
  xử chỉ có một người (Claude), theo quyết định của người phụ trách.
- **"Đã duyệt" là duyệt mô phỏng.** Ở case thiếu thông tin, người dùng mô phỏng tự đặt dữ kiện. Ví dụ
  case 5 xác nhận 34 ADA trong khi dữ kiện ẩn là 32 ADA. Vì vậy so với tham chiếu là so với một intent
  khác.
- **Còn ~16% intent được chấp nhận nhưng sai nghĩa.** Khoảng tin cậy rộng: một lượt chạy lại trên dev
  đổi kết quả ở 10/56 case. Các lỗi điển hình: người kể chuyện bị đưa thành một bên của hợp đồng, đảo
  chiều tiền trong hợp đồng vay, hết hạn mà tiền về sai người.
- **Case `infeasible`:** cả hai cách đều sai 3/3.
- **Nhận ra mâu thuẫn kém:** chỉ 5/12 trên bộ bổ sung do tác giả viết.

### Cải tiến đã làm

AFF thay DCF; builder tất định dựng core từ sự kiện; quy tắc đọc thời gian và tên riêng (prompt v5);
phép so nghĩa; câu hỏi làm rõ cụ thể hơn.

### Hạn chế và rào cản

- AFF chưa được nối vào pipeline chính, nên RQ1 cho pipeline thật (DCF) chưa được đo theo cách này.
- Không có người dùng thật và không có người phân xử thứ hai.
- Gemini bản miễn phí giới hạn 500 request/ngày, nên mỗi case chỉ có một mẫu.
- Prompt AFF được chỉnh trên chính Gemini.
- Dữ liệu tổng hợp từ một bộ sinh.

## 3. RQ2: cổng bằng chứng

### Thí nghiệm

**E5** (docs/E5-Evidence-Gates.md). Giao thức chốt 2026-11-09, trước khi đo.

**Ứng viên:**

- **Variants:** biến thể tất định từ hợp đồng tham chiếu, cố ý làm sai hoặc giữ nguyên nghĩa.
- **E3-All:** mọi hợp đồng khác nhau do model sinh trong E3.
- **E3-Final:** hợp đồng cuối của mỗi case E3.

**Nhãn:**

- Variants: so khác biệt có giới hạn với hợp đồng tham chiếu trên bộ mô phỏng Python, độc lập với các
  cổng. Kiểm lại bằng bộ thực thi Haskell, bằng giới hạn duyệt rộng hơn, và bằng xem tay.
- E3: phân xử tay theo tiêu chí ghi trước, căn cứ là yêu cầu người dùng mô phỏng đã xác nhận.

**Các bậc** đi theo thứ tự cổng trong pipeline: Structure (đối chứng) → Lint → SMT → Alignment →
Scenario → Oracle (đầy đủ).

**Quy tắc chốt trước** (tính trên Variants), cần đủ cả ba điều:

1. chấp nhận sai của Oracle thấp hơn Structure với p < 0,05;
2. độ phủ ≥ 0,80;
3. từ chối nhầm ≤ 0,10.

**Hai vòng:**

- **Round 1** là bản đầu. Nó không đạt quy tắc, vì cổng Scenario so danh sách từng lần trả, kịch bản thử
  đúng 1 giây sau hạn, và bước khám phá không đi qua được nút `If` ở gốc.
- **Round 2** sửa ba chỗ đó. Code được đóng băng (`E5-Freeze`) rồi chạy một lần trên case 58–100.

### Kết quả

| Variants | Dev Round 1 | Dev Round 2 | **Test 58–100** | **Gộp 99 case** |
| --- | --- | --- | --- | --- |
| Sai / đúng | 948 / 344 | 948 / 344 | 686 / 281 | 1 634 / 625 |
| Chấp nhận sai: Structure → Oracle | 1,00 → 0,204 | 1,00 → 0,204 | 1,00 → **0,171** | 1,00 → **0,190** (0,171–0,209) |
| Độ phủ Oracle | 0,375 | 0,951 | **0,936** | **0,944** (0,923–0,960) |
| Từ chối nhầm Oracle | 0,462 | 0,006 | **0,011** | **0,008** |
| Quy tắc | không đạt | đạt (khám phá) | **đạt** | **đạt** |

**Hiệu quả từng cổng (99 case):**

- **Lint:** không chặn hợp đồng nào.
- **SMT:** chặn các lỗi trả quá số dư (nhân đôi số tiền, lỗi đơn vị lovelace); chấp nhận sai giảm từ
  1,00 xuống 0,695.
- **Alignment:** không đổi quyết định nào.
- **Scenario:** đem lại phần lớn hiệu quả; chấp nhận sai giảm từ 0,695 xuống 0,190.
- **Oracle:** không chặn thêm hợp đồng sai nào ngoài những gì Scenario đã chặn.

**Hợp đồng do model sinh** (nhãn phân xử):

| Tập | Sai / đúng | Chấp nhận sai Oracle | Độ phủ | Từ chối nhầm |
| --- | --- | --- | --- | --- |
| E3-All dev (Nemotron) | 27 / 48 | 3/27 | 25/48 | 1/48 |
| E3-All test (Gemini) | 8 / 37 | **0/8** | **37/37** | 0/37 |
| E3-All gộp 99 case | 35 / 85 | 3/35 | 62/85 | 1/85 |
| E3-Final gộp 99 case | 9 / 81 | 3/9 | 59/81 | 1/81 |

### Điểm mạnh

- **Giao thức chặt:** quy tắc chốt trước; tập giữ lại chưa từng dùng để chỉnh cổng; code đóng băng; kết
  quả test khớp dev (0,171 so với 0,204; 0,936 so với 0,951). Như vậy các sửa đổi của Round 2 không
  phải chỉ hợp với riêng dữ liệu dev.
- **Nhãn Variants được kiểm nhiều lớp:** 1 290/1 292 nhãn dev khớp khi phát lại trên bộ thực thi
  Haskell, 2 nhãn còn lại đã giải thích được; chỉ 4 nhãn đổi khi duyệt rộng hơn, đều nằm trong dung sai
  đã chốt; 51 nhãn đáng ngờ được xem tay. Kết quả kiểm nhãn cho phần test: xem mục 9.4 của tài liệu
  E5.
- **Không tốn request model nào;** 0,57 giây cho mỗi hợp đồng.
- **Trên hợp đồng Gemini,** cổng Scenario bắt được mọi lỗi sai danh tính bên tham gia: địa chỉ ví thay
  cho role, tên bỏ dấu tiếng Việt.

### Điểm yếu

- **~19% lỗi vẫn lọt qua,** chủ yếu do dời hạn ±3 ngày (230/310) ở chỗ kịch bản không chạm tới, tiếp
  theo là đổi người nhận, bỏ khoản trả, đổi ngưỡng ở nhánh không được thử.
- **Lỗi thật mà kịch bản không bắt được:**
  - token hex mà chính kịch bản cũng viết bằng hex (case 4);
  - `Notify` cho phép trả sớm trong khi kịch bản chỉ thử đường đi bình thường (case 6, 21).
- **Cổng phụ thuộc kịch bản của người duyệt.** 30/120 hợp đồng E3 thuộc case không có kịch bản, nên
  Oracle ABSTAIN. Độ phủ của E3 gộp 99 case chỉ còn 62/85.
- **Alignment không đóng góp gì:** phần kiểm scope chỉ xác nhận đường dẫn tồn tại.
- **So tổng tiền bỏ qua thời điểm trả** trong một kịch bản.
- **Bản sửa của Oracle chưa trọn:** chỉ thử giao dịch rỗng đã khai báo, nên còn 13 biến thể
  `if_true` ABSTAIN.

### Cải tiến đã làm

- Scenario so tổng tiền mỗi bên nhận theo token.
- `DeclaredActionDomain` đi qua được gốc `If`, `Let`, `Assert`.
- Kịch bản dựng cách hạn 1 ngày.
- Thêm cổng Alignment.
- Đổi tên các bậc theo cổng.
- Bộ đối chiếu nhãn trên Haskell.
- Tiêu chí và file phân xử.

### Hạn chế và rào cản

- **Biến thể là lỗi do mình tạo ra.** Hợp đồng tham chiếu và kịch bản do cùng một bộ sinh dataset tạo.
- **Ba sửa đổi của Round 2 được chọn sau khi xem dev.** Chỉ phần test là kiểm chứng.
- **Nhãn của E3 do một người phân xử.** Nhãn máy của E3 không dùng được, vì nó so với dữ kiện ẩn chứ
  không so với yêu cầu đã xác nhận: 31 nhãn bị lật, không nhãn nào theo chiều ngược lại.
- **Mẫu E3-Final nhỏ:** chỉ 9 hợp đồng sai, và mẫu đã qua chọn lọc, vì pipeline sinh lại cho tới khi
  qua kịch bản.
- **Không có nhánh "intent có cấu trúc nhưng không có chính sách" chạy song song.** Bậc Structure
  đóng vai đối chứng, đúng theo định nghĩa trong paper.

## 4. RQ3: toàn bộ quy trình có cải thiện mức khớp hành vi cuối cùng không

### Hiện trạng

**Chưa có thí nghiệm đúng định nghĩa.** Định nghĩa đòi một nhánh đối chứng, ví dụ sinh hợp đồng trực
tiếp từ prompt không qua cổng, chạy trên cùng các case với cùng ngân sách request, rồi so mức khớp
hành vi cuối cùng. Phần dưới đây chỉ là bằng chứng mô tả từ E2 và E3.

### Bằng chứng có được

- **E2 Online Tuning** (Nemotron, 20 case đầu, trần 48 request): chỉ 6/20 case được thử; cả 6 tới bước
  kiểm kích thước giao dịch; 14 case hết ngân sách. Hợp đồng do compiler tất định sinh, không phải model.
- **E3 Roleplay:** mỗi case chạy qua pipeline chính, có người dùng mô phỏng. Bảng dưới là trạng thái
  cuối, kèm kết quả phân xử của hợp đồng cuối.

| | Dev 1–56 (Nemotron, DCF) | Test 58–100 (Gemini, DCF) |
| --- | --- | --- |
| Tới bước kiểm kích thước, hợp đồng ĐÚNG | 46 | 34 |
| Tới bước kiểm kích thước, hợp đồng SAI | **7** | **0** |
| Dừng trước, hợp đồng ĐÚNG | 1 (case 30) | 0 |
| Dừng trước, hợp đồng SAI | 0 | 2 (case 67, 95) |
| Không sinh hợp đồng | 2 (case 8 `UNSUPPORTED` đúng; case 45 `WAITING_USER`) | 7 (58, 60, 62 bị chặn ở bước sinh hợp đồng; 76 intent không hợp lệ; 75, 77, 100 `infeasible` bị chặn thay vì `UNSUPPORTED`) |
| **Case có hợp đồng cuối ĐÚNG** | **47/56 = 84%** | **34/43 = 79%** |

- **Vòng sinh lại có giúp:** hợp đồng đầu tiên của mỗi case ĐÚNG ở 38/54 case (dev) và 28/36 (test);
  hợp đồng cuối ĐÚNG ở 47/54 và 34/36.
- **Ở test, không hợp đồng SAI nào tới được trạng thái cuối tích cực.** Ở dev có 7: 5 dùng token hex,
  2 dùng `Notify` cho phép trả sớm.

### Điểm mạnh

- Có số liệu đầu-cuối trên 99 case, đi qua cả bước kiểm kích thước giao dịch thật.
- Hợp đồng cuối được phân xử theo yêu cầu đã xác nhận.
- Có tập test chạy theo đúng quy trình như dev.

### Điểm yếu

- **Không có đối chứng dùng cùng tài nguyên,** nên chưa nói được quy trình "cải thiện" so với cái gì.
  So hợp đồng đầu với hợp đồng cuối không phải là đối chứng: hợp đồng đầu cũng đã qua bước làm rõ
  intent.
- **Người dùng mô phỏng vừa viết intent vừa viết kịch bản kỳ vọng,** nên mức khớp được đo phần nào theo
  chính tiêu chuẩn của người đó.
- **Dev và test khác nhau ở ba điểm:** model (Nemotron so với Gemini), lời báo lỗi của validator (đổi
  trước case 58), và số lượt chạy (trung bình 10,0 so với 7,3). So sánh hai cột không phải là so một
  biến.
- **Case `infeasible` ở test bị chặn vì lỗi khác** chứ không dừng đúng ở `UNSUPPORTED` (0/3).

### Hạn chế và rào cản

- Một nhánh đối chứng sẽ cần thêm khoảng 300–400 request Gemini cho 99 case, tức khoảng 1 ngày quota
  miễn phí. Nhánh đó cũng cần người dùng mô phỏng đóng vai giống hệt cho cả hai nhánh.
- Pipeline chưa dùng AFF.
- Không có người dùng thật.

## 5. RQ4: chi phí của các biện pháp kiểm soát

### Số liệu có được

| Hạng mục | Giá trị | Nguồn |
| --- | --- | --- |
| Lượt gọi model cho mỗi case, E3 dev | ~10,6 (605 lượt ghi nhận cho 57 case, Nemotron) | `runs/roleplay-main-batch*` |
| Lượt gọi model cho mỗi case, E3 test | 8,4 (363 cho 43 case, Gemini) | session E3 |
| Lượt chạy pipeline cho mỗi case | dev: trung vị 8, trung bình 10,0, tối đa 24; test: trung vị 7, trung bình 7,3, tối đa 14 | như trên |
| Câu trả lời của người dùng mô phỏng cho mỗi case | dev 5,3; test 4,6 | như trên |
| Request cho mỗi intent hợp lệ, bước trích intent (E4 test) | AFF 1,90–2,02; DCF 4,10–4,24 | E4 |
| Chi phí cổng (E5) | 0,57 giây/hợp đồng; 8,6 lần gọi bộ thực thi tham chiếu + 1 lần SMT; 0 request model | E5 |
| Tỷ lệ không quyết định (Oracle), Variants gộp 99 case | 4,8% hợp đồng đúng; 0% hợp đồng sai | E5 |
| Tỷ lệ không quyết định (Oracle), E3 gộp 99 case | 26% hợp đồng đúng; 31% hợp đồng sai (chủ yếu vì không có kịch bản) | E5 |
| Thời gian thực để chạy E3 test | ~2 ngày, do giới hạn 500 request/ngày | session E3 |

### Điểm mạnh

Các cổng gần như không tốn gì: dưới 1 giây, không gọi model. AFF giảm khoảng một nửa số request ở
bước trích intent. Tỷ lệ không quyết định được đo và báo riêng, không gộp vào "đạt".

### Điểm yếu, hạn chế

- **Chưa đo độ trễ của model.** Bản ghi không lưu thời gian từng lượt gọi một cách nhất quán.
- **Chưa đo công duyệt của người thật.** Số câu trả lời mô phỏng chỉ là chỉ số đại diện. Một người dùng
  thật có thể cần nhiều hoặc ít lượt hơn.
- **Lượt gọi ở dev đếm chưa chắc chắn.** Một số lượt chạy cũ ghi lượt gọi theo trường khác nhau, nên
  605 là số ghi nhận được, có thể thiếu.
- **Chi phí phân xử tay của E5 không được đo.** Đó là công của người phân xử, cần thiết vì nhãn máy của
  E3 không dùng được.
- **Chi phí cổng tính trong WSL.** Qua bridge Windows thì chậm hơn khoảng 20 lần (~1,4 giây mỗi lần gọi).

## 6. Mối đe dọa tính hợp lệ chung

1. **Dữ liệu tổng hợp từ một bộ sinh.** Hợp đồng tham chiếu, kịch bản và prompt có chung giả định, ví dụ
   hạn là 12:00 UTC và token GOLD dùng một policy giữ chỗ.
2. **Người dùng, người duyệt và người phân xử đều là Claude.** Không có người thật ở bất kỳ vai nào.
3. **Một model cho mỗi giai đoạn, mỗi case một mẫu.** Một lượt chạy lại trên dev đổi kết quả ở 10/56
   case.
4. **Nhiều chỉnh sửa diễn ra sau khi xem dev.** Mỗi lần như vậy đều ghi vào "Lệch giao thức", và kiểm
   chứng chỉ dựa trên tập test đã đóng băng.
5. **Đổi tên ngày 2026-11-09.** Số liệu E1–E4 đo bằng code trước khi đổi tên. Chuỗi phiên bản trong
   prompt đổi theo, và ảnh hưởng của việc này chưa được đo.
6. **Gemini bản miễn phí** có thể dùng dữ liệu gửi lên để huấn luyện. Điều này đã được chấp thuận cho
   dữ liệu tổng hợp, nhưng không áp dụng được cho yêu cầu do người thật viết.

## 7. Việc nên làm tiếp (theo thứ tự ưu tiên)

1. **Nối AFF vào pipeline chính,** rồi chạy lại E3 cho test. Kết quả đầu-cuối hiện tại là của DCF.
2. **RQ3 có đối chứng:** nhánh sinh hợp đồng trực tiếp, cùng case, cùng ngân sách request, cùng người
   dùng mô phỏng.
3. **Cổng bắt lỗi dời hạn:** so mọi hạn trong hợp đồng với các claim thời gian của intent đã chốt (tức
   làm Alignment so được thời gian), hoặc tự sinh kịch bản quanh mọi hạn.
4. **Kịch bản thử nhánh bất thường,** ví dụ ai đó gửi `Notify` trước thời điểm sớm nhất. Cùng với đó,
   kiểm tên token theo intent: hex hay không, policy nào.
5. **Bộ gán nhãn so với "tham chiếu theo yêu cầu đã xác nhận"** cho E3, để không phải phân xử tay mỗi lần.
6. **Người phân xử thứ hai** và người dùng thật, nếu có điều kiện, để đáp ứng yêu cầu của paper.
7. **Đo độ trễ model và công duyệt** (RQ4).
8. **Rút gọn gốc hợp đồng trước khi khám phá,** để không còn 13 trường hợp ABSTAIN của `if_true`.

## 8. Nguồn số liệu

| Phần | Tài liệu | Dữ liệu | Code |
| --- | --- | --- | --- |
| E2, E3 dev | docs/JOURNAL.md mục 6 | `runs/online-tuning-batch01`, `runs/roleplay-main-batch20`, `runs/roleplay-main-batch80` | `research/experiments/online_tuning.py`, `roleplay_case.py` |
| E3 test | docs/JOURNAL.md mục 6 (commit `4469740`) | `runs/E3-Roleplay-Holdout` | `roleplay_case.py` (commit `70ad70f`) |
| E4 (RQ1) | docs/E4-Formalization-Comparison.md | `runs/eval/T-*`, `S-*`, `G-*` | tag `a2-test-freeze` (`faacc61`) |
| E5 (RQ2) | docs/E5-Evidence-Gates.md, E5-Adjudication-Rubric.md, E5-Adjudication.json | `runs/e5/E5-Round1-*`, `E5-Round2-*`, `E5-Freeze-Holdout-*` | tag `E5-Round1` (`275365a`), `E5-Freeze` (`b55c7ca`) |

`runs/` không có trong git. Tag chưa được push lên GitHub.
