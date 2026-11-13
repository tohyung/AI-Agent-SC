# Đề xuất: dung sai thời gian và người dùng mô phỏng cho vòng chạy lại

Ngày: 2026-11-12. Tài liệu này là phương án trình duyệt **trước khi triển khai**. Chưa có code nào được
sửa. Nó trả lời hai câu hỏi:

1. Dung sai thời gian khi chấm có thiên vị Pipeline không?
2. Baseline có thật sự hoạt động như một chatbot không, và vai người dùng mô phỏng đã đủ thực tế chưa?

Tài liệu đi kèm `docs/archive/E6-Failure-Review.md`.

## 1. Dung sai thời gian

### Thực tế đã áp dụng trong E6

- **Không có dung sai ±3 ngày.** Cả hai nhánh được chấm cùng một luật: mốc giờ lệch **tối đa 1 phút**
  (`docs/archive/E5-Adjudication-Rubric.md`, mục 15). Con số ±3 ngày xuất hiện ở E5 với nghĩa khác: đó là một
  *kiểu lỗi được cấy vào* hợp đồng (dời hạn 3 ngày) để thử cổng, không phải dung sai khi chấm.
- **Pipeline không có hợp đồng nào sai giờ,** vì builder tính mốc giờ bằng code. Nới dung sai không
  làm Pipeline được thêm case nào.

### Baseline lệch giờ bao nhiêu

Đo trên 35 hợp đồng Baseline chỉ sai mốc giờ. Mỗi hợp đồng lấy độ lệch lớn nhất giữa các mốc trong
hợp đồng và các mốc trong `spec`.

| Độ lệch lớn nhất | Số hợp đồng |
| --- | --- |
| Dưới 1 ngày (8,7–21 giờ: quên hoặc nhầm UTC+7) | 5 |
| Đúng 1 ngày, hoặc 1–2 ngày | 7 |
| 2–8 tháng | 4 |
| Khoảng 1 năm (sai năm) | 15 |
| 2–3 năm | 4 |

**Baseline thành công theo từng mức dung sai** (Pipeline giữ nguyên 38/71):

| Dung sai | Baseline |
| --- | --- |
| 1 phút (đang dùng) | 11/71 |
| 1 giờ | 11/71 |
| 1 ngày | 20/71 |
| 3 ngày | 23/71 |
| 1 tháng | 23/71 |

Kết luận không đổi ở mọi mức. 23 hợp đồng lệch từ 2 tháng trở lên, trong đó 19 hợp đồng **sai năm**.
Khoảng cách chủ yếu đến từ đó, không phải từ độ chặt của luật chấm.

### Đề xuất quy ước thời gian (áp dụng như nhau cho hai nhánh)

1. **Người dùng nêu giờ** (hoặc phiếu dữ kiện nêu giờ): lệch tối đa 1 phút, để chấp nhận cách viết
   23:59 hay 23:59:59.
2. **Người dùng chỉ nêu ngày,** phiếu dữ kiện không nói giờ: chấp nhận mọi thời điểm trong ngày đó, theo
   múi giờ đã nêu hoặc đã xác nhận.
3. **Múi giờ:** lấy múi giờ đã nêu. Nếu không nêu và cũng không được xác nhận, mô hình nào tự giả định
   mà sai múi giờ thì tính là sai. Lý do là lệch 7 giờ làm thay đổi ai được hành động vào lúc nào.
4. **Lệch 1 ngày trở lên là sai.** Hạn trễ một ngày là cho thêm một ngày để nạp hoặc rút tiền; đây là
   hành vi khác.
5. **Báo cáo thêm bảng độ nhạy** (1 phút / 1 giờ / 1 ngày / 3 ngày) cho cả hai nhánh, để người đọc thấy
   kết luận có phụ thuộc vào dung sai hay không.

## 2. Baseline có phải là chatbot không

### Cách Baseline đang chạy (`research/experiments/baseline_llm.py`)

- **Đúng là một cuộc hội thoại nhiều lượt.** Mỗi lượt, model nhận toàn bộ hội thoại và trả về một trong
  ba loại: câu hỏi, hợp đồng kèm lời giải thích, hoặc từ chối. Khi model hỏi, người dùng mô phỏng trả
  lời rồi hội thoại tiếp tục.
- **Lỗi kiểm tra được gửi lại tự động,** như khi người dùng dán thông báo lỗi vào chat. Hai loại lỗi là
  cấu trúc JSON và kích thước giao dịch trên ledger. Có 41 lần như vậy trên 71 case.
- **Khi model giao một hợp đồng qua được kiểm tra, bộ chạy tự động "chấp nhận".** Người dùng mô phỏng
  không đọc lời giải thích và không phản hồi.

### Vì sao điểm thứ ba quan trọng, và phát hiện khi đọc lại

Tôi đọc lời giải thích cuối của Baseline ở các case sai giờ. Phần lớn **ghi đúng ngày** trong khi JSON
sai năm:

- case 33 ghi "by April 4, 2027", còn JSON là 2026;
- case 62 ghi "May 1, 2027";
- case 57 ghi "trước 20:00 ngày 15/03/2027".

Một người dùng thật, không đọc được POSIX ms, sẽ thấy lời giải thích đúng và chấp nhận. Vậy với loại lỗi
này, tự động chấp nhận *gần đúng* với thực tế. Nhưng có những trường hợp người thật sẽ phản ứng:

- lời giải thích **ghi sai năm** (case 31 ghi "Nov 1, 2024");
- lời giải thích **chỉ nói về việc sửa JSON**, không nói hợp đồng làm gì (case 49, 87). Người thật sẽ
  hỏi lại hợp đồng làm gì;
- lời giải thích **sai tên hoặc sai luồng** so với điều người dùng muốn.

E6 đã bỏ qua các phản ứng này. Ở chiều ngược lại, Pipeline cũng được tự động chấp nhận intent.

### Bất cân xứng giữa hai nhánh trong E6

| Điểm | Pipeline | Baseline |
| --- | --- | --- |
| Người dùng trả lời câu hỏi | Có (phiếu dữ kiện hoặc nhắc lại) | Có (cùng luật) |
| Người dùng đọc lại kết quả trước khi chấp nhận | Không (intent tự duyệt) | Không (tự chấp nhận) |
| Người dùng cung cấp ví dụ kiểm thử | **Có:** 117 kịch bản JSON do Claude viết | Không |
| Người viết câu trả lời | Claude, cũng là người thiết kế Pipeline | Claude |

Hai điểm không thực tế:

1. **Câu trả lời theo khuôn có sẵn.** Câu trả lời là "Thông tin bổ sung: - …" dán nguyên phiếu dữ kiện,
   kể cả những điều không được hỏi. Người thật trả lời đúng câu được hỏi, bằng lời của mình, đôi khi
   thiếu hoặc mơ hồ.
2. **Kịch bản dạng JSON cấu trúc.** Người dùng thật không viết được kịch bản Marlowe. Lợi thế lớn này của
   Pipeline đến từ một "người dùng chuyên gia" mà thực tế không có.

## 3. Phương án: người dùng mô phỏng bằng LLM, cùng một luật cho hai nhánh

### 3.1 Nguyên tắc

- **Một người dùng mô phỏng độc lập,** là một LLM với prompt cố định, khác model của hai nhánh, được
  đóng băng và đánh số phiên bản trước khi chạy. Claude không tự viết câu trả lời nữa, chỉ kiểm tra và
  ghi lỗi của bộ mô phỏng.
- **Nó chỉ thấy đúng những gì một người dùng thật thấy:**
  - prompt (lời của chính nó) và một "trí nhớ" là phiếu dữ kiện;
  - các tin nhắn chữ mà mỗi nhánh gửi;
  - không thấy JSON, POSIX ms, hay chẩn đoán kỹ thuật.
- **Hai nhánh dùng cùng prompt và cùng luật.** Bộ mô phỏng không được biết đang nói chuyện với nhánh nào.

### 3.2 Chân dung người dùng (persona)

- Không biết lập trình, không biết Marlowe. Biết rõ điều mình muốn, nhưng chỉ trong phạm vi prompt và
  phiếu dữ kiện.
- Trả lời đúng câu được hỏi, ngắn, bằng ngôn ngữ của prompt và theo văn phong của prompt (không dấu thì
  vẫn không dấu).
- Câu hỏi về điều không có trong trí nhớ thì trả lời "không biết, bạn chọn giúp" hoặc "như tôi đã nói".
  Không được bịa.
- Câu hỏi kỹ thuật ("bound của choice tính theo lovelace?") thì nói không hiểu và nhắc lại ý muốn.
- Khi nhận kết quả (lời giải thích hợp đồng hoặc bản tóm tắt intent): đọc và so với điều mình muốn.
  - Khớp thì chấp nhận.
  - Thấy sai điều đọc được (tên, số tiền, ngày, ai nhận, ai bấm) thì nói rõ chỗ sai.
  - Không kiểm được điều không thấy.
- **Bỏ cuộc** khi bị hỏi lại cùng một điều sau hai lần trả lời, hoặc sau N lượt (đề xuất N = 6).

### 3.3 Các hành động, giống nhau cho hai nhánh

| Khi nhánh gửi | Người dùng có thể |
| --- | --- |
| Câu hỏi | Trả lời từ trí nhớ, hoặc "không biết" |
| Đề nghị bỏ một phần | Đồng ý chỉ khi trí nhớ cho phép; nếu không thì nói phần đó vẫn cần |
| Từ chối cả yêu cầu | Chấp nhận, hoặc hỏi lại một lần |
| Kết quả (lời giải thích hoặc tóm tắt intent) | Chấp nhận, hoặc phản đối và nêu chỗ sai |
| Yêu cầu ví dụ tình huống | Mô tả bằng lời 2–4 tình huống từ trí nhớ |

### 3.4 Ví dụ kiểm thử (cổng Scenario) theo cách thực tế

- Pipeline **hỏi bằng lời**: "Cho tôi vài tình huống và kết quả bạn mong muốn". Người dùng mô phỏng mô
  tả bằng lời, ví dụ "Ngọc, Tú, Vũ góp đủ rồi ai đó bấm giải ngân thì Lâm nhận 100 ADA".
- **Pipeline tự chuyển lời mô tả thành kịch bản.** Đây là thành phần mới: LLM viết kịch bản, rồi phần
  gắn tên tất định chạy theo quy ước tên. Sau đó Pipeline đọc lại kịch bản bằng lời cho người dùng xác
  nhận.
- **Baseline được phép làm điều tương tự:** prompt hệ thống cho phép nó hỏi ví dụ. Người dùng trả lời
  theo cùng luật. Nhánh nào không hỏi thì không được nhận ví dụ.

Nếu chưa muốn thêm thành phần mới, có phương án tạm: giữ kịch bản dạng cấu trúc nhưng ghi rõ trong báo
cáo đó là "người dùng chuyên gia", và chạy thêm một biến thể Pipeline **không có** cổng Scenario để đo
riêng đóng góp của cổng.

### 3.5 Kiểm soát bộ mô phỏng (khách quan và tái lập được)

1. **Kiểm tra tự động mỗi câu trả lời:** mọi con số, ngày, tên và role trong câu trả lời phải có trong
   prompt hoặc phiếu dữ kiện. Nếu không, câu trả lời bị đánh dấu và sinh lại tối đa 2 lần, rồi ghi nhận.
2. **Ghi lại toàn bộ** prompt, phản hồi, nhiệt độ (0) và phiên bản model. Chạy lại cho cùng kết quả.
3. **Chạy thử trên dev:** 10 case dev, chạy cả hai nhánh. Claude đọc toàn bộ transcript và ghi các lỗi
   của bộ mô phỏng (bịa, lộ thông tin, quá dễ dãi, quá khó tính). Chỉ sửa prompt mô phỏng ở bước này,
   rồi đóng băng.
4. **Đo trên kết quả chạy thật:** tỷ lệ câu trả lời bị đánh dấu, số lượt trung bình, số lần phản đối
   đúng hoặc sai. Báo cáo cùng kết quả.

### 3.6 Model cho người dùng mô phỏng

| Lựa chọn | Ưu | Nhược |
| --- | --- | --- |
| Gemini (model khác `flash-lite`, ví dụ `gemini-2.5-flash`) | Không tốn tiền, đã có key | Cùng họ model với hai nhánh; quota free tier |
| Claude qua API (ví dụ Haiku 5.5) | Khác họ model, theo hướng dẫn tốt | Tốn tiền, cần API key |
| Model mở chạy cục bộ | Tái lập hoàn toàn | Yếu tiếng Việt, cần GPU |

Đề xuất: một model khác họ (Claude Haiku) nếu có ngân sách; nếu không thì `gemini-2.5-flash`. Dù chọn
gì cũng phải ghi rõ là hạn chế.

**Đã chọn (2026-11-12):** sub-agent Claude Haiku 5.5, effort low, của Claude Code, một sub-agent cho
mỗi nhánh. Không cần API key riêng.

### 3.7 Cài đặt bằng sub-agent

- **Prompt người dùng** nằm ở `.claude/agents/sim-user.md` (SimUser-v1). Định nghĩa đó không có công
  cụ, nên sub-agent không đọc được dataset hay thư mục `runs/`.
  - Định nghĩa agent mới chỉ được nạp khi mở phiên mới.
  - Trong phiên hiện tại, thử nghiệm dùng sub-agent `general-purpose` (Haiku, low), dán nguyên văn
    prompt SimUser-v1 kèm lệnh "không dùng công cụ". Kiểu này còn quyền dùng công cụ, nên chỉ dùng để
    thử, không dùng cho lần chạy thật.
- **Mỗi lượt là một lần gọi mới, không có trạng thái.** Đầu vào luôn đầy đủ: yêu cầu, điều người dùng
  biết, và toàn bộ lời đã thấy. Mọi thứ nằm trong đầu vào nên kiểm tra lại được.
  - `tools/e6/simuser.py input N base|pipe` dựng đầu vào chỉ từ prompt, phiếu dữ kiện và lời hiển thị
    của nhánh; không đọc các trường dành cho người chấm.
  - `tools/e6/simuser.py check N '<json>'` kiểm câu trả lời: có đúng JSON không, hành động có hợp lệ
    không, có con số nào không có trong yêu cầu hay phiếu dữ kiện không.
- **Claude chỉ chuyển tiếp.** Đầu ra của sub-agent được lưu nguyên văn vào thư mục case rồi đưa cho bộ
  chạy (`auto.py answer … "<message>"`). Claude không sửa câu chữ. Câu trả lời không qua được `check`
  thì gọi lại, tối đa 2 lần, và ghi nhận số lần.
- **Giới hạn:**
  - không đặt được nhiệt độ, nên kết quả không tái lập tuyệt đối. Bù lại bằng việc lưu nguyên văn đầu
    vào và đầu ra của mọi lượt;
  - mỗi lượt đi qua phiên chính, nên tốn ngữ cảnh của phiên chính. Nên chạy theo lô.
- **Thiếu ở nhánh Pipeline:** Pipeline hiện chưa có bản tóm tắt intent bằng lời cho người dùng đọc, và
  chưa có bước đổi ví dụ bằng lời thành kịch bản (mục 3.4). Hai phần này phải làm trước khi người dùng
  mô phỏng duyệt được kết quả của Pipeline.

### 3.8 Chạy thử Haiku 5.5, effort low (2026-11-12)

Lấy 5 tình huống đã ghi lại trong E6, mỗi tình huống gọi một sub-agent mới.

| Tình huống | Hành vi mong đợi | SimUser-v1 | SimUser-v2 |
| --- | --- | --- | --- |
| 33 (B): lời giải thích đúng, không ghi giờ | accept, hoặc hỏi về giờ | Chuyển sang tiếng Việt, nhắc lại yêu cầu (sai) | `object`: thiếu giờ 15:00 UTC (chấp nhận được, khó tính) |
| 31 (B): lời giải thích ghi năm 2024 | object: năm phải là 2027 | Bắt được 2024 nhưng nhãn `answer`, lại thêm dữ kiện | Bắt đúng, nhưng nhãn vẫn `answer` |
| 49 (B): lời cuối chỉ nói "đã sửa JSON" | hỏi hợp đồng làm gì | Hỏi đúng ý, nhưng viết tiếng Việt không dấu (sai ngôn ngữ) | Nhắc lại yêu cầu thay vì hỏi (yếu) |
| 45 (P): đòi số nguyên lovelace | nói không hiểu, nhắc 37,5 ADA | Đúng | Đúng |
| 82 (P): "input by Vân chưa biểu diễn được" | vẫn cần, nhắc lại | Đúng | **Sai nặng:** đồng ý bỏ phần Vân nhập, và bịa rằng cửa hàng nhập |

(B) là nhánh Baseline, (P) là nhánh Pipeline.

Kết quả và nhận xét:

- **Giao kết quả không chắc chắn:** 2/5 lần ở v1 sub-agent kết thúc mà không trả kết quả về. Ở v2, nhờ
  câu lệnh "final report là JSON", cả 5/5 lần đều trả về.
- **Ngôn ngữ:** v2 hết lỗi sai ngôn ngữ, nhờ dòng `YOUR LANGUAGE`.
- **Nhãn hành động không đáng tin** (2/5 sai). Cách xử lý: bộ chạy không dựa vào nhãn. Khi đang xem kết
  quả, *mọi tin nhắn khác rỗng* được coi là phản đối; chỉ `accept` với tin nhắn rỗng mới là chấp nhận.
- **Bịa và tự ý bỏ yêu cầu** (1/5 ở v2) là lỗi nặng nhất, vì nó thay đổi nội dung yêu cầu. Cần một lớp
  kiểm tra tất định:
  - câu trả lời có đồng ý bỏ (bỏ, drop, không cần…) mà phiếu dữ kiện không có mục cho phép bỏ thì từ
    chối và gọi lại;
  - câu trả lời gán vai mới cho một bên (tên đi với động từ hành động không có trong yêu cầu) thì đánh
    dấu để kiểm.
- **Kết luận:** Haiku ở effort low **chưa đủ tin cậy** để chạy thật. Trước khi chạy cần:
  1. thêm các kiểm tra tất định ở trên;
  2. thử effort medium (hoặc Sonnet) trên cùng bộ tình huống;
  3. chạy một bộ thử 20 tình huống, với ngưỡng đặt trước: không quá 1 câu bịa hoặc tự ý bỏ yêu cầu, và
     không quá 10% câu cần gọi lại.

### 3.9 Chạy lại với Haiku 5.5, effort medium (cùng SimUser-v2, cùng 5 tình huống)

| Tình huống | Effort low | Effort medium |
| --- | --- | --- |
| 33: lời giải thích đúng | `object` vì thiếu giờ (khó tính) | `accept` (đúng) |
| 31: năm 2024 | Bắt đúng, nhãn `answer` | Bắt đúng, nhãn `answer` |
| 49: chỉ nói "đã sửa JSON" | Nhắc lại yêu cầu | Nói không hiểu phần kỹ thuật, nhắc lại đủ yêu cầu (chấp nhận được) |
| 45: đòi số nguyên lovelace | Đúng | Đúng |
| 82: "input by Vân" | **Bịa, tự ý bỏ yêu cầu** | "Không cần bỏ", giữ nguyên phần Vân nhập (đúng) |

**Đánh giá:**

- Effort medium cho nội dung chấp nhận được ở cả 5/5 tình huống, không bịa, không tự ý bỏ yêu cầu.
- Nhãn vẫn sai 2/5 (`answer` thay vì `object`). Lỗi này được trung hòa bằng luật của bộ chạy ở mục 3.8:
  khi đang xem kết quả, mọi tin nhắn khác rỗng là phản đối.
- Thời gian mỗi lượt khoảng 3–5 giây, tương đương effort low.

**Đề xuất:**

- dùng Haiku 5.5 với **effort medium** cho người dùng mô phỏng;
- vẫn giữ các kiểm tra tất định ở mục 3.8;
- 5 tình huống là quá ít, nên vẫn chạy bộ thử 20 tình huống với ngưỡng đã đặt trước khi chạy thật.

## 4. Kế hoạch triển khai (sau khi được duyệt)

1. **Chốt các quy ước:** tên (Failure-Review, AFF-2 và S-1), thời gian (mục 1), chấm (Failure-Review,
   mục 5). Đã chốt ở `docs/archive/E7-Conventions.md` (bản 1).
2. **Dataset v4:**
   - phiếu dữ kiện viết thành "trí nhớ người dùng": đủ để trả lời mọi câu hỏi hợp lý, có mục cho giờ,
     múi giờ, năm, hoàn tiền khi hết hạn, và ví dụ tình huống;
   - chia dev và đánh giá theo họ hợp đồng;
   - chấm tự động bằng `checks.scenarios` kèm so khớp tên, người phân xử chỉ xem các case máy báo lệch.
3. **Bộ mô phỏng người dùng** (mục 3) và bộ kiểm tra câu trả lời; dùng chung cho hai nhánh.
4. **Sửa AFF** theo Failure-Review mục 7, chỉ trên dev (v3 và phần dev của v4).
5. **Chạy thử** 10 case dev, Claude kiểm transcript, rồi đóng băng code, prompt mô phỏng và dataset.
6. **Chạy đánh giá trên v4,** chấm tự động trước, phân xử phần còn lại, báo cáo kèm bảng độ nhạy thời gian.

## 5. Ảnh hưởng tới báo cáo E6 hiện tại

Kết quả E6 vẫn đứng, vì dung sai không làm đổi kết luận (mục 1). Nhưng phần hạn chế của RQ3 nên ghi
thêm ba điều:

- câu trả lời của người dùng theo khuôn;
- người dùng không đọc lại kết quả ở cả hai nhánh;
- kịch bản dạng JSON là lợi thế của một "người dùng chuyên gia" mà người dùng thật không có.
