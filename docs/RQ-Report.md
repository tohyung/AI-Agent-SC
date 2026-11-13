# Báo cáo các câu hỏi nghiên cứu (RQ1–RQ4)

> **Đọc trước:** kết quả dùng cho báo cáo là E4 (RQ1), E5 (RQ2) và E7 (RQ3, RQ4, mục 5A). E7 thay cho E6;
> các mục 4 và 5 về E6 chỉ còn để lưu hồ sơ. Toàn bộ thí nghiệm E1–E7 được tóm trong
> `docs/Experiment-Log.md`.

Tư liệu để viết bài báo. Ghi ngày 2026-11-10, dựa trên E2–E5 (docs/archive/JOURNAL.md,
docs/archive/E4-Formalization-Comparison.md, docs/archive/E5-Evidence-Gates.md). Mọi con số dưới đây đều có trong
tài liệu hoặc dữ liệu nêu ở mục 8. Chỗ nào chưa đo thì ghi là chưa đo.

RQ3 và RQ4 được trả lời bằng E6 (2026-11-12): mục 4 và 5, giao thức `docs/archive/E6-Protocol.md`, phán quyết
`docs/evidence/E6-Adjudication.json`, bảng điểm `docs/evidence/E6-Score.json`.

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
| RQ3 | **Có, kèm điều kiện** | Trên 71 case đánh giá (cùng model, cùng chi phí request), Pipeline thành công 53,5% so với 15,5% của một LLM đơn thuần (+38 điểm, CI 95% [25; 51], McNemar p ≈ 5·10⁻⁷), và giao ra hợp đồng sai 4% so với 76%. Phần lớn khoảng cách đến từ việc tính mốc giờ bằng code: cả 54 hợp đồng sai của LLM đơn thuần đều sai mốc giờ. Pipeline không giao ra gì ở 42% case. |
| RQ4 | **Đã đo** | Pipeline tốn 2,3× request, 8,6× token vào, 2,3× thời gian model và nhiều công người dùng hơn (117 kịch bản), nhưng rẻ hơn tính trên mỗi case thành công (8,3 so với 12,3 request). |
| RQ3 (E7) | **Có** | Trên 100 case viết tay mới (dataset v5), cùng quy ước và cùng người dùng mô phỏng độc lập cho hai nhánh: Pipeline thành công 49% so với 18% (+31 điểm, CI 95% [19; 43], McNemar p ≈ 5,5·10⁻⁶). Pipeline giao hợp đồng sai 2%, Baseline 72% (71/72 hợp đồng sai có lỗi hạn). Pipeline không giao ở 49% case. Mục 5A. |
| RQ4 (E7) | **Đã đo** | Pipeline tốn 2,4× request, 5,1× token vào, 2,0× thời gian model, 2,7× tin nhắn người dùng. Tính trên mỗi case thành công thì vẫn rẻ hơn một chút (14,0 so với 15,9 request). Mục 5A. |

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
  47/54 hợp đồng ĐÚNG ở dev và 34/36 ở test (`docs/evidence/E5-Adjudication.json`). Đây là bằng chứng về cả chuỗi
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

**E5** (docs/archive/E5-Evidence-Gates.md). Giao thức chốt 2026-11-09, trước khi đo.

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
  đã chốt; 51 nhãn đáng ngờ được xem tay. Ở phần test,
  964/967 nhãn khớp, 3 nhãn còn lại có cùng nguyên nhân đã giải thích.
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

### Thí nghiệm (E6)

Chi tiết: `docs/archive/E6-Protocol.md` (giao thức, 16 mục lệch giao thức), `docs/archive/E6-Dataset-Design.md`.

- **Dataset v3:** 100 case do Claude viết tay để làm khó hệ thống, 19 họ hợp đồng không cần oracle,
  60 tiếng Việt, 40 tiếng Anh, có phiếu dữ kiện cho phần prompt bỏ ngỏ. Đóng băng trước khi chạy.
- **Hai nhánh, cùng model** (`gemini-3.5-flash-lite`, free tier):
  - **Pipeline:** toàn bộ hệ thống, đường AFF: hỏi lại, duyệt intent, sinh hợp đồng, SMT, so kịch bản,
    khám phá, ledger.
  - **Baseline:** một LLM tự viết hợp đồng Marlowe từ hội thoại. Mỗi hợp đồng được kiểm cấu trúc và
    ledger; lỗi được tự động gửi lại cho model.
- **Cùng chi phí:** trần request của Baseline ở mỗi case bằng số request Pipeline đã dùng ở case đó.
- **Người dùng mô phỏng:** Claude, cùng một luật cho cả hai nhánh: trả lời bằng phiếu dữ kiện, nhắc lại
  điều prompt đã nói, bỏ cuộc khi bị hỏi lại sau hai lần. Chỉ nhánh Pipeline được người dùng viết kịch
  bản mong đợi (đây là một phần của hệ thống).
- **Chấm:** phân xử mù 142 gói (71 case × 2 nhánh) theo tiêu chí E5, đối chiếu với prompt, phiếu dữ
  kiện và các câu trả lời. Mốc giờ được lệch tối đa 1 phút. Quy tắc quyết định chốt trước: McNemar chính
  xác, α = 0,05, cộng bootstrap theo cặp.
- **Tách dev và đánh giá:** case 1–29 đã được dùng để tìm và sửa lỗi pipeline, nên chỉ coi là dev.
  **Kết quả chính tính trên case 30–100 (71 case), chạy trên code đã đóng băng** (tag `E6-Freeze-30`).

### Kết quả (case 30–100, 71 case)

| Kết quả của case | Pipeline | Baseline |
| --- | --- | --- |
| Thành công | **38 (53,5%)** | 11 (15,5%) |
| Giao ra hợp đồng sai | 3 (4,2%) | 54 (76,1%) |
| Không giao ra | 30 (42,3%) | 6 (8,5%) |

- **Chênh lệch thành công:** +38,0 điểm phần trăm, khoảng tin cậy 95% [25,4; 50,7], gấp 3,5 lần
  Baseline. Kiểm định McNemar: 29 case chỉ Pipeline đúng, 2 case chỉ Baseline đúng, p ≈ 4,6·10⁻⁷.
  **Theo quy tắc chốt trước: Pipeline mạnh hơn.**
- **An toàn:** Pipeline giao ra hợp đồng sai ở 3/71 case, Baseline ở 54/71 (p ≈ 9·10⁻¹⁶). Trong số hợp
  đồng được giao ra, 38/41 của Pipeline đúng (93%), so với 11/65 của Baseline (17%).
- **Theo hành vi mong đợi** (số case thành công):

  | Hành vi mong đợi | Pipeline | Baseline |
  | --- | --- | --- |
  | Đủ thông tin (29) | 19 | 1 |
  | Thiếu, phải hỏi (26) | 8 | 0 |
  | Mâu thuẫn hoặc đính chính (4) | 2 | 0 |
  | Kèm phần không làm được (2) | 0 | 0 |
  | Bất khả, phải từ chối (10) | 9 | 10 |

  Ở 61 case làm được, Pipeline đúng 29 case, Baseline đúng 1 case. Ở 10 case bất khả, cả hai nhánh đều
  không giao ra hợp đồng; Baseline giải thích lý do ở cả 10 case, Pipeline ở 9 case.

### Phải đọc kết quả này thế nào

- **Phần lớn khoảng cách đến từ việc tính mốc thời gian.** Cả 54 hợp đồng sai của Baseline đều sai mốc
  giờ (thường sai năm, sai múi giờ hoặc lệch một ngày khi tự đổi sang POSIX ms), và 35 hợp đồng chỉ sai
  mỗi mốc giờ. Pipeline không gặp lỗi này, vì builder của AFF tính mốc giờ bằng code. Nếu Baseline có
  một công cụ đổi giờ đúng, nó có thể đạt khoảng 46/71 (ước lượng giả định: cộng 35 case chỉ sai giờ).
  Con số đó cao hơn Pipeline. Kết luận vững là: **tính tất định các giá trị (giờ, tiền) là thứ tạo ra
  khác biệt lớn nhất**, chứ chưa phải toàn bộ hệ thống cổng.
- **Pipeline thua ở khâu hiểu yêu cầu.** 30/71 case Pipeline không giao ra gì. Lý do chính:
  - AFF chưa biểu diễn được k trên n người duyệt, khấu trừ bằng số người kiểm tra nhập, và "ai cũng
    bấm được";
  - bên chỉ có tên vai ("organizer", "người thuê"), hoặc "Me" (mẹ) trùng với đại từ "me";
  - không chấp nhận khi người dùng đồng ý bỏ phần không làm được;
  - trích dẫn bị dịch trong câu trộn Việt–Anh.
- **Cổng Scenario có giá trị thật:** nó chặn các hợp đồng sai bên duyệt, sai người kích hoạt hoặc sai
  số tiền (ví dụ case 51, 52, 53, 54, 56, 71, 75, 76). Nhưng nó chỉ bắt được điều kịch bản kiểm: case 58
  và 61 vẫn lọt hợp đồng chỉ cho một người mua, vì kịch bản đã chọn đúng người đó.

### Điểm mạnh

- So sánh theo cặp, cùng model, cùng chi phí request, cùng người dùng mô phỏng, cùng luật trả lời.
- Quy tắc quyết định và tiêu chí chấm được chốt trước khi chạy phần đánh giá.
- Code đóng băng trên toàn bộ phần đánh giá; mọi thay đổi bộ chạy đều ghi vào lệch giao thức.

### Điểm yếu

- Pipeline giao ra hợp đồng ở ít case hơn nhiều (41 so với 65).
- Pipeline tốn gấp nhiều lần token (mục 5).
- Hiệu quả phụ thuộc kịch bản do người dùng viết.

### Hạn chế và rào cản

1. **Một người làm mọi vai** (viết case, đóng vai người dùng, viết kịch bản, phân xử). Việc phân xử mù
   chỉ một phần: dòng trạng thái của pipeline trong lời cuối để lộ nhánh.
2. **Case 1–29 đã dùng để sửa pipeline** (lệch giao thức 4–14), nên bị loại khỏi kết quả chính. Phần
   đánh giá chỉ còn 71 case.
3. **Prompt của Baseline không được tinh chỉnh,** còn pipeline thì có. Một Baseline có công cụ đổi giờ
   hoặc prompt tốt hơn có thể thu hẹp hoặc đảo ngược khoảng cách.
4. **Kịch bản chỉ dành cho Pipeline,** và có giới hạn: lấy tên vai và giá trị lựa chọn từ intent, không
   kiểm hành vi thừa, không kiểm thời điểm trả.
5. **Một model nhỏ, free tier,** mỗi case một mẫu; Gemini có lúc trả lỗi 500 hàng loạt (lệch giao thức
   12–13).
6. **Hai lỗi của bộ chạy được sửa giữa chừng** (kịch bản chạy trên hợp đồng cũ; tên trong kịch bản), các
   case bị ảnh hưởng đã được chạy lại phần liên quan (lệch giao thức 15–16).

## 5. RQ4: chi phí của các biện pháp kiểm soát

Cùng 71 case, đếm theo một luật chung (không tính lỗi quota, lỗi mạng và lỗi máy chủ 5xx).

| Chi phí | Pipeline | Baseline | Tỷ lệ |
| --- | --- | --- | --- |
| Request | 316 | 135 | 2,3× |
| Token vào | 1 319 771 | 153 045 | 8,6× |
| Token ra | 475 931 | 93 043 | 5,1× |
| Thời gian chạy model | 2 839 s | 1 220 s | 2,3× |
| Request cho mỗi case thành công | 8,3 | 12,3 | 0,68× |
| Tin nhắn của người dùng | 59 | 22 | 2,7× |
| Kịch bản người dùng viết | 117 | 0 | |
| Lượt duyệt intent (tự động trong E6) | 42 | 0 | |
| Lỗi tự động gửi lại cho model | 0 | 41 | |
| Không giao ra hợp đồng | 30 (42%) | 6 (8%) | |
| Chạm trần request | 0 | 4 | |

- **Tính trên mỗi case thành công, Pipeline rẻ hơn** (8,3 so với 12,3 request), vì Baseline tiêu request
  vào các hợp đồng sai. Tính trên tổng chi phí, Pipeline đắt hơn: gấp 2,3 lần request và 8,6 lần token
  vào, do mỗi request mang prompt dài (ngữ pháp, intent, phản hồi).
- **Công của người dùng là chi phí lớn nhất của Pipeline:** cần hỏi đáp nhiều hơn, cộng trung bình
  khoảng 2,9 kịch bản cho mỗi case giao ra. Trong E6, việc duyệt intent được tự động hóa; với người thật
  thì đây sẽ là công thêm.
- **Tỷ lệ không quyết định cao:** Pipeline không giao ra ở 42% case. Phần lớn là lúc bước hiểu yêu cầu
  dừng, chứ không phải lúc cổng chặn.

## 5A. E7: chạy lại RQ3 và RQ4 với quy ước chung và dataset viết tay (2026-11-13)

### Thí nghiệm

E7 làm lại E6 sau bản rà lỗi E6 (`docs/archive/E6-Failure-Review.md`), với ba thay đổi lớn:

- **Quy ước chung cho hai nhánh** (`docs/archive/E7-Conventions.md` bản 3): gắn tên bên, giờ, số, chấm, kịch
  bản, người dùng mô phỏng.
- **Người dùng mô phỏng độc lập:** SimUser-v3 là một sub-agent Claude Haiku 5.5 mới cho mỗi lượt. Nó chỉ
  đọc tệp đầu vào của lượt đó, và bộ kiểm tra câu trả lời áp dụng cùng luật cho cả hai nhánh.
- **Dataset v5:** 100 case mới viết tay (60 tiếng Việt, 40 tiếng Anh, 20 họ hợp đồng), đóng băng ở tag
  `E7-Dataset-v5`. Không case nào sinh từ template.

Giữ nguyên so với E6:

- Cả hai nhánh dùng `gemini-3.5-flash-lite`.
- Trần request của Baseline bằng số request Pipeline đã dùng ở cùng case. Số request của Pipeline gồm cả
  các lần đổi ví dụ thành kịch bản.
- Giao thức đóng băng ở tag `E7-Freeze` (`docs/archive/E7-Protocol.md`).
- Các lần sửa hạ tầng trong lúc chạy được ghi trong `docs/archive/E7-Deviations.md` (D1–D6, I1–I3). Không lần
  nào đổi điều mà một nhánh hay người dùng mô phỏng nhìn thấy.

Cách chấm:

1. **Chấm máy:** `e7_score` chạy các kịch bản của dataset trên bộ tham chiếu Haskell và so mọi hạn với
   dung sai 1 phút.
2. **Phân xử mù:** 103 gói chấm được giao cho 8 sub-agent phân xử mới
   (`docs/archive/E7-Adjudication-Brief.md`, ghi trước khi chấm). Gói gồm các hợp đồng máy báo lệch và các case
   cần biết nhánh có nói rõ phần không làm được hay không.
3. **Tổng hợp:** `research/experiments/e7_analysis.py`, được commit trước khi mở kết quả.

### Kết quả RQ3 (100 case, đủ cặp)

| Chỉ số | Pipeline | Baseline | Chênh lệch |
| --- | --- | --- | --- |
| **Thành công** | **49%** | **18%** | **+31 điểm**, CI 95% [19; 43], McNemar p ≈ 5,5·10⁻⁶ |
| Giao hợp đồng sai | 2% | 72% | −70 điểm, p ≈ 1,7·10⁻²¹ |
| Không giao | 49% | 10% | |
| Chỉ một nhánh thành công | 39 case | 8 case | |

**Kết luận theo quy tắc chốt trước: Pipeline mạnh hơn.** Kết quả cùng chiều và gần cỡ với E6 (53,5% so
với 15,5% trên 71 case), nhưng lần này trên dataset viết tay, với người dùng mô phỏng độc lập cho cả hai
nhánh.

**Độ nhạy thời gian:** số case thành công gần như không đổi khi nới dung sai.

| Dung sai | Pipeline | Baseline |
| --- | --- | --- |
| 1 phút | 49 | 18 |
| 1 giờ | 49 | 18 |
| 1 ngày | 49 | 18 |
| 3 ngày | 49 | 19 |

Lỗi giờ của Baseline không phải do bộ chấm quá khắt khe. Trong các hạn sai, 93 hạn lệch hơn 1 ngày theo
kiểu không đều, 20 hạn lệch khoảng 1 năm, và chỉ 4 hạn lệch đúng 7 giờ, tức lỗi múi giờ. Không có lỗi hệ
thống kiểu dùng giây thay mili giây.

**Theo hành vi mong đợi** (Pipeline / Baseline thành công):

| `expected_behavior` | n | Pipeline | Baseline |
| --- | --- | --- | --- |
| `converge` | 44 | 22 | 5 |
| `ask_then_converge` | 35 | 16 | 4 |
| `flag_conflict_then_converge` | 6 | 3 | 0 |
| `converge_and_decline_extra` | 5 | 1 | 0 |
| `reject_unsupported` | 10 | 7 | 9 |

**Theo ngôn ngữ:**

- tiếng Việt: Pipeline 30/60, Baseline 9/60;
- tiếng Anh: Pipeline 19/40, Baseline 9/40.

**Theo họ hợp đồng:**

- Pipeline thành công trọn ở 6 họ: escrow_arbiter, swap, rental_deposit, cancellation_fee, matching (đều
  4/4) và loan (4/5).
- Pipeline 0 ở 4 họ: k_of_n (0/6), first_come (0/5), zero_coupon_bond (0/4), deduction (0/5). Baseline
  cũng gần như 0 ở các họ này, chỉ có first_come 2/5 và zero_coupon_bond 1/4.

### Phải đọc kết quả này thế nào

**Baseline thua chủ yếu vì giao hợp đồng sai giờ.** Nó giao 81 hợp đồng:

- 6 hợp đồng máy chấm đúng ngay;
- 75 hợp đồng máy báo lệch; người phân xử chấm 3 trong số đó là đúng, 72 là sai.

71 trong 72 hợp đồng sai có lỗi hạn, thường là sai năm, sai tháng hoặc sai giờ khi đổi sang POSIX ms. Vì
vậy, phần lớn chênh lệch đến từ việc Pipeline tính mốc giờ bằng code, như E6 đã thấy.

**Pipeline giao ít nhưng gần như luôn đúng.**

- Giao 44 hợp đồng: máy chấm đúng 41, báo lệch 3; người phân xử chấm 1 trong 3 là đúng. Chỉ 2 hợp
  đồng sai (case 23 và 35).
- Pipeline không giao ở 49 case:

| Lý do Pipeline không giao | Case |
| --- | --- |
| người dùng hết 6 tin nhắn | 11 |
| không chốt được kịch bản | 10 |
| dừng ở bước hiểu yêu cầu hoặc khi gặp phần không làm được | 10 |
| bộ sinh hợp đồng không thỏa được kịch bản (`generation_stalled`) | 9 |
| người dùng bỏ cuộc | 7 |
| dừng trước khi chạy kịch bản | 2 |

**Điểm yếu đã ghi nhận của Pipeline** (giữ nguyên bản đóng băng, chỉ báo cáo):

- **Đọc lại kịch bản (O1, O2):** 10 case không chốt được kịch bản. Đa số vì bản đọc lại viết "có người bấm
  xác nhận" thay vì nêu đúng người bấm và đúng hành động. Case 27 thì vì bản đọc lại bỏ mất các bước quá
  hạn.
- **Phần không làm được nhận ra mà không báo người dùng:** ở `reject_unsupported`, Pipeline thành công
  7/10, Baseline 9/10. Ba case thua (92, 95, 99) là lúc Pipeline dừng ngay ở bước intent (`unsupported_intent`),
  dùng 1 request, và không nói gì với người dùng. Người phân xử vì thế chấm "chưa nói rõ phần không làm
  được".
- **Bỏ phần thừa:** ở `converge_and_decline_extra`, Pipeline chỉ thành công 1/5 (Baseline 0/5).

**Đồng thuận giữa máy và người phân xử:**

- Trong 78 hợp đồng máy báo lệch, người phân xử chấm 4 là đúng: Pipeline case 4, Baseline case 25, 58,
  69. Lý do của từng verdict có trong `docs/evidence/E7-Adjudication.json`.
- 74 hợp đồng còn lại bị chấm sai, đúng như máy báo.

### Kết quả RQ4

| Chỉ số (tổng trên 100 case) | Pipeline | Baseline | Tỷ lệ |
| --- | --- | --- | --- |
| Request được tính | 684 | 287 | 2,4× |
| Token vào | 2,62 triệu | 0,51 triệu | 5,1× |
| Token ra | 1,01 triệu | 0,24 triệu | 4,1× |
| Thời gian model | 8 500 s | 4 200 s | 2,0× |
| Tin nhắn của người dùng | 267 | 100 | 2,7× |
| Kịch bản người dùng xác nhận | 134 | 0 | |
| **Request cho mỗi case thành công** | **14,0** | **15,9** | 0,88× |
| Chạm trần request | | 28 case | |

- **Trung vị mỗi case:**
  - request: Pipeline 5, Baseline 2,5;
  - token vào: Pipeline 16 891, Baseline 2 893;
  - thời gian model: Pipeline 47 s, Baseline 20 s;
  - tin nhắn người dùng: Pipeline 2, Baseline 1.
- **Chi phí trên mỗi case thành công:** Pipeline vẫn rẻ hơn một chút (14,0 so với 15,9 request). Khoảng
  cách hẹp hơn E6 (8,3 so với 12,3), vì Pipeline nay tốn thêm các vòng tóm tắt intent, xin ví dụ và đọc lại
  kịch bản.
- **Tổng chi phí:** Pipeline đắt hơn rõ rệt, nhất là token: mỗi request mang prompt dài.
- **Công của người dùng:** Pipeline cần gấp 2,7 lần tin nhắn, cộng 134 kịch bản phải xác nhận. Với người
  thật, đây là chi phí lớn nhất.

### Người dùng mô phỏng

| | Pipeline | Baseline |
| --- | --- | --- |
| Câu trả lời được ghi | 394 | 172 |
| Câu bị bộ kiểm tra từ chối | 15 | 0 |
| Câu dự phòng ("tôi không biết thêm") | 2 | 0 |
| Phản đối một kết quả được cho xem | 116 | 48 |
| Lượt sub-agent không hợp lệ | 1 (I2: kiểm tra chạy khi lượt chưa xong; chính lượt đó được ghi sau) | 0 |

- **Câu bị từ chối:** hầu hết là các số không có trong yêu cầu. Chúng xuất hiện khi Pipeline xin ví dụ có
  số tiền, mốc giờ.
- **Lệch giữa hai nhánh:** người dùng chỉ phản đối được những gì nó được cho xem. Pipeline cho xem tóm tắt
  intent và kịch bản; Baseline chỉ cho xem lời giải thích. Phần lớn hợp đồng sai giờ của Baseline vì thế
  được chấp nhận, do người dùng mô phỏng không đọc được JSON hay POSIX ms.

### Hạn chế

1. **Claude đóng nhiều vai:** Claude viết dataset v5, sửa pipeline, vận hành bộ chạy và viết bản hướng dẫn
   phân xử. Bù lại: chấm máy là nguồn chính, và người phân xử là sub-agent mới, chấm mù nhánh.
   - Văn phong của gói chấm vẫn có thể lộ nhánh: Pipeline có tóm tắt intent và đọc lại kịch bản.
2. **Mỗi case một mẫu, một model nhỏ, free tier.**
3. **Lệch giao thức:** các lệch D1–D6 và I1–I3 đều là hạ tầng. Riêng D5 đổi một case từ "không giao" sang
   "giao": case 17, có lỗi 5xx khi sinh hợp đồng.
4. **Baseline không có công cụ đổi giờ.** Kết quả vì vậy đo "LLM đơn thuần", chưa đo "LLM có công cụ".
   Việc tách đóng góp của việc tính giờ tất định khỏi đóng góp của các cổng vẫn là việc nên làm tiếp
   (mục 7, điểm 1).

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

1. **Baseline mạnh hơn cho RQ3:** cho LLM đơn thuần một công cụ đổi giờ sang POSIX ms (hoặc prompt tốt
   hơn), rồi chạy lại trên case 30–100, để tách phần đóng góp của việc tính tất định khỏi phần của các
   cổng.
2. **Mở rộng AFF:** k trên n người duyệt, khấu trừ bằng giá trị lựa chọn, "ai cũng bấm được"
   (Notify), bên chỉ có tên vai, chấp nhận khi người dùng đồng ý bỏ phần không làm được. Đây là các
   nguyên nhân chính khiến Pipeline không giao ra ở E6.
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
| E2, E3 dev | docs/archive/JOURNAL.md mục 6 | `runs/online-tuning-batch01`, `runs/roleplay-main-batch20`, `runs/roleplay-main-batch80` | `research/experiments/online_tuning.py`, `roleplay_case.py` |
| E3 test | docs/archive/JOURNAL.md mục 6 (commit `4469740`) | `runs/E3-Roleplay-Holdout` | `roleplay_case.py` (commit `70ad70f`) |
| E4 (RQ1) | docs/archive/E4-Formalization-Comparison.md | `runs/eval/T-*`, `S-*`, `G-*` | tag `a2-test-freeze` (`faacc61`) |
| E5 (RQ2) | docs/archive/E5-Evidence-Gates.md, E5-Adjudication-Rubric.md; docs/evidence/E5-Adjudication.json | `runs/e5/E5-Round1-*`, `E5-Round2-*`, `E5-Freeze-Holdout-*` | tag `E5-Round1` (`275365a`), `E5-Freeze` (`b55c7ca`) |
| E6 (RQ3, RQ4) | docs/archive/E6-Protocol.md; docs/evidence/E6-Adjudication.json, E6-Score.json | `runs/E6-Pipeline`, `runs/E6-Baseline`, `runs/E6-Adjudication` | tag `E6-Freeze-30` (`bb26cc5`); `research/experiments/baseline_llm.py`, `e6_score.py`, `tools/e6/` |
| E7 (RQ3, RQ4) | docs/archive/E7-Protocol.md, E7-Conventions.md, E7-Deviations.md, E7-Adjudication-Brief.md; docs/evidence/E7-Adjudication.json, E7-Score.json | `runs/E7-Eval-Pipeline`, `runs/E7-Eval-Baseline`, `runs/E7-Eval-Score` | tag `E7-Freeze` (`175d748`), `E7-Dataset-v5`; `research/experiments/e7_score.py`, `e7_analysis.py`, `tools/e7/` |

`runs/` không có trong git. Các tag đóng băng đã được push lên GitHub.
