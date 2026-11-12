# E7: quy ước chung (bản 2, 2026-11-12)

Văn bản này chốt các quy ước cho vòng thí nghiệm sau E6 (gọi là E7). Nó dựa trên
`docs/E6-Failure-Review.md` và `docs/E6-Rerun-Proposal.md`.

**Phạm vi:** áp dụng **như nhau cho cả hai nhánh** (Pipeline và Baseline), và cho mọi thành phần: AFF và
builder, phần gắn tên của cổng Scenario, dataset, người dùng mô phỏng và việc chấm điểm.

**Điều không đổi:** kết quả chính của E6 giữ nguyên như đã báo cáo. Quy ước này chỉ được dùng cho E6 để
lập *bảng phụ* (chấm lại theo quy ước mới), ghi rõ là bảng phụ.

**Thay đổi quy ước:** chỉ được sửa trước khi đóng băng vòng đánh giá. Mỗi lần sửa tăng số bản và ghi lý
do ở mục 11. Sau khi đóng băng thì không sửa nữa.

## 1. Danh tính các bên (Q-TÊN)

1. **Mỗi bên là một danh tính** gồm:
   - *tên hiển thị*: cách người dùng gọi, ví dụ "Công ty Sao Mai", "chị Vy", "Organizer";
   - *role token*: định danh trong hợp đồng.
2. **Role token:**
   - Người dùng hoặc phiếu dữ kiện cho token ("role: X", "(role X)") thì dùng đúng X.
   - Nếu không và bên đó có tên riêng, token là tên riêng như người dùng viết, giữ dấu (Kiều, Sương).
   - Nếu chỉ có tên vai, token được suy ra tất định: bỏ dấu (đ thành d), bỏ "the", bỏ khoảng trắng
     và dấu câu, viết hoa chữ đầu mỗi từ. Ví dụ: người thuê thành NguoiThue, the organizer thành
     Organizer.
   - Vì so khớp luôn qua `fold` (Q-TÊN 3), cách viết token không ảnh hưởng tới việc chấm.
3. **Hàm gấp tên `fold`** dùng chung cho builder, phần gắn kịch bản và bộ chấm. Các bước:
   1. chuẩn hóa Unicode NFC, chữ thường;
   2. bỏ dấu (đ thành d);
   3. bỏ danh xưng ở đầu: anh, chị, em, cô, chú, bác, ông, bà, bạn, cụ, công ty, cty, nhóm, bên, quỹ,
      mr, mrs, ms, dr, the;
   4. bỏ khoảng trắng và dấu câu.

   Hai cách viết là **cùng một bên** khi `fold` của chúng bằng nhau, hoặc khi một cách viết là role
   token đã được gán cho bên kia. Ví dụ "Công ty Sao Mai", "Sao Mai" và "SaoMai" là một bên.
4. **Ánh xạ một đối một.** Nếu hai bên khác nhau có cùng `fold` thì báo *mơ hồ* và hỏi người dùng, không
   tự ghép.
5. **Tên vai là hợp lệ** khi không có tên riêng (Organizer, Studio, NguoiThue). Chỉ hỏi tên khi:
   - một vai có thể là nhiều người, hoặc
   - "tôi, mình, I, me" không có tên ở gần.
6. **Đại từ có tên kèm** trong cùng mệnh đề hoặc trong ngoặc ("tôi (Hiền)", "Mình là Phong", "Bầu show
   Kiều (tôi)") thì bên đó là tên kèm, không hỏi lại.
7. **Chữ mơ hồ** (ví dụ "Me" trong câu không dấu, "minh") chỉ được hiểu là đại từ khi không có cách đọc
   thành tên riêng phù hợp. Nếu cả hai cách đều được thì hỏi.
8. **Khi chấm:** đúng nếu mỗi vai trong hợp đồng ánh xạ một đối một tới đúng người thật. Sai nếu gộp hai
   người, đổi vai, hoặc dùng một người khác (ví dụ "Minh" thay cho "Như").

## 2. Thời gian (Q-GIỜ)

1. **Có giờ** (do người dùng hoặc phiếu dữ kiện nêu): mốc trong hợp đồng phải trùng, được lệch tối đa
   **1 phút**.
2. **Chỉ có ngày** và phiếu dữ kiện không nêu giờ: chấp nhận mọi thời điểm trong ngày đó, theo múi giờ
   đã nêu hoặc đã xác nhận.
3. **Giờ, năm và múi giờ ghi một lần** áp cho mọi ngày trong cùng một danh sách liệt kê ("23:59 các
   ngày 20/02, 20/03 và 20/04/2027 giờ VN") và cho mẫu lặp ("ngày 10 hằng tháng từ tháng 2 đến tháng
   5/2027").
4. **Múi giờ:**
   - "giờ VN" là UTC+7;
   - không nêu múi giờ mà nhánh không hỏi lại, tự giả định sai, thì tính là sai;
   - không nêu năm thì phải hỏi, hoặc lấy từ phiếu dữ kiện.
5. **Lệch từ 1 ngày trở lên là sai.**
6. **Báo cáo độ nhạy:** mọi kết quả kèm bảng thành công ở các mức dung sai 1 phút, 1 giờ, 1 ngày, 3
   ngày, cho cả hai nhánh.

## 3. Số tiền và token (Q-SỐ)

1. **Chấm đúng tuyệt đối** theo đơn vị nhỏ nhất (lovelace, hoặc đơn vị token). 120 BOOK khác
   120 000 000 BOOK.
2. **Đọc số theo ngôn ngữ của câu:**
   - tiếng Việt: dấu chấm là phân cách hàng nghìn, dấu phẩy là thập phân ("1.005 ADA" là 1005 ADA;
     "37,5 ADA" là 37 500 000 lovelace);
   - tiếng Anh: ngược lại;
   - chữ số viết bằng chữ ("ba trăm", "twenty-five") được đọc như chữ số.
3. **Số thập phân ADA hợp lệ** khi đổi ra được số nguyên lovelace. Không được đòi người dùng nhập số
   nguyên.
4. **Mâu thuẫn** (ví dụ "25 ADA, tức 5% của 400 ADA"): phải hỏi. Chấm theo câu trả lời trong phiếu dữ
   kiện.

## 4. Chấm hợp đồng (Q-CHẤM)

1. **Chấm máy trước.** Chạy `checks.scenarios` của dataset trên bộ tham chiếu Haskell, gắn tên theo
   Q-TÊN 3 và lấy giờ theo Q-GIỜ. Qua hết thì là RIGHT.
2. **Người phân xử chỉ xét các case máy báo lệch,** để quyết lệch đó có phải lỗi hành vi không. Ví dụ
   một nhánh thừa vô hại được chấp nhận. Mọi verdict khác với máy phải có lý do ghi lại.
3. **Được chấp nhận:**
   - tên lựa chọn tùy ý;
   - giá trị lựa chọn ánh xạ nhất quán với nghĩa (0 là không, 1 là có…);
   - thêm `Close` hoặc bước chờ không có tiền;
   - thứ tự các khoản trả trong cùng một bước khác đi.
4. **Là sai:**
   - trả thừa, trả thiếu, trả một phần (tài khoản không đủ);
   - sai người nhận, sai người nạp, sai người được bấm hoặc chọn;
   - thiếu nhánh hết hạn mà người dùng đã nêu;
   - tiền kẹt lại trong hợp đồng khi kết thúc.
5. **Kết quả theo hành vi mong đợi:**

   | `expected_behavior` | Thành công khi |
   | --- | --- |
   | `converge`, `ask_then_converge`, `flag_conflict_then_converge` | Giao hợp đồng RIGHT |
   | `converge_and_decline_extra` | Giao hợp đồng RIGHT cho phần làm được **và** đã nói rõ phần bị bỏ |
   | `reject_unsupported` | Không giao hợp đồng **và** đã nêu đúng phần không làm được (một câu "có bỏ được không" cũng tính, nếu đúng phần đó) |

6. **Mù nhánh:** gói chấm không ghi tên nhánh. Các dòng trạng thái máy móc (status, stop_reason) được
   bỏ khỏi lời cuối trước khi đóng gói.

## 5. Kịch bản kiểm thử của người dùng (Q-KỊCH BẢN)

1. **Nguồn:** nội dung kịch bản lấy từ yêu cầu và trí nhớ của người dùng (prompt và phiếu dữ kiện),
   không lấy từ intent. Intent chỉ dùng để gắn tên (Q-TÊN 3).
2. **Người dùng mô phỏng mô tả tình huống bằng lời** khi được hỏi. Pipeline tự chuyển lời mô tả thành
   kịch bản, rồi đọc lại bằng lời cho người dùng xác nhận.
3. **Mẫu phủ tối thiểu theo họ hợp đồng.** Đây là phần Pipeline phải *hỏi* người dùng; người dùng chỉ
   trả lời những gì được hỏi.
   - mỗi nhánh hết hạn có một tình huống;
   - nhóm "ai cũng được" hoặc "ai nạp trước": ít nhất 2 người khác nhau;
   - k trên n: đúng k người, và k − 1 người;
   - khấu trừ hoặc số nhập: 0, một giá trị giữa, và cận trên.
4. **Biến thể chuyên gia** (kịch bản viết sẵn dạng cấu trúc như E6) chỉ chạy như một thí nghiệm phụ,
   báo cáo riêng.

## 6. Người dùng mô phỏng (Q-NGƯỜI DÙNG)

1. **Cấu hình:** sub-agent `sim-user` (`.claude/agents/sim-user.md`), prompt SimUser-v2, Claude Haiku
   5.5, effort medium, không có công cụ. Dùng cùng prompt cho hai nhánh và không cho biết đang nói với
   nhánh nào.
2. **Mỗi lượt là một lần gọi mới.** Đầu vào do `tools/e6/simuser.py input` dựng, gồm:
   - dòng ngôn ngữ;
   - yêu cầu;
   - trí nhớ (phiếu dữ kiện);
   - các lời hiển thị của nhánh.

   Không có JSON, POSIX ms hay chẩn đoán kỹ thuật. Đầu vào và đầu ra của mọi lượt được lưu nguyên văn.
3. **Kiểm tra tất định cho mỗi câu trả lời.** Câu trả lời không đạt thì gọi lại, tối đa 2 lần. Sau đó
   ghi nhận và dùng câu trả lời "Tôi không biết thêm, bạn làm theo những gì tôi đã nói".
   - đúng JSON, hành động hợp lệ;
   - đúng ngôn ngữ;
   - không có con số ngoài yêu cầu, phiếu dữ kiện và hội thoại;
   - không đồng ý bỏ một phần nếu phiếu dữ kiện không có mục cho phép bỏ.
4. **Không dựa vào nhãn hành động.** Khi đang xem kết quả, chỉ `accept` kèm tin nhắn rỗng mới là chấp
   nhận; mọi tin nhắn khác rỗng là phản đối và được gửi cho nhánh.
5. **Giới hạn:** tối đa 6 tin nhắn của người dùng mỗi nhánh mỗi case. Người dùng bỏ cuộc khi bị hỏi lại
   điều đã trả lời 2 lần.
6. **Claude chỉ chuyển tiếp**, không sửa câu chữ, không tự trả lời thay.
7. **Trước khi chạy thật:** chạy thử 20 tình huống, với ngưỡng không quá 1 câu bịa hoặc tự ý bỏ yêu
   cầu, và không quá 10% câu phải gọi lại. Không đạt thì sửa prompt, tăng số bản, rồi chạy thử lại.

## 7. Hai nhánh (Q-NHÁNH)

1. **Cùng model** sinh hợp đồng, **cùng trần request** cho mỗi case (bằng số request Pipeline đã dùng),
   cùng luật đếm request (không tính lỗi quota, lỗi mạng, lỗi 5xx).
2. **Baseline** là chatbot: hỏi, giao hợp đồng kèm lời giải thích, hoặc từ chối. Lỗi kiểm tra cấu trúc
   và ledger được dán lại tự động. Khi giao hợp đồng, **người dùng mô phỏng đọc lời giải thích** và chấp
   nhận hoặc phản đối. Baseline được phép hỏi ví dụ tình huống.
3. **Pipeline** cho người dùng xem **bản tóm tắt intent bằng lời** (sinh tất định từ intent) để chấp
   nhận hoặc phản đối, trước bước sinh hợp đồng. Pipeline hỏi ví dụ tình huống theo Q-KỊCH BẢN.
4. **Không nhánh nào được thấy** phiếu dữ kiện, `spec` hay `checks`. Chỉ có người dùng mô phỏng thấy
   phiếu dữ kiện.

## 8. Dataset (Q-DỮ LIỆU)

1. Mỗi bên trong `spec.roles` có `name` (tên hiển thị) và `role` (token theo Q-TÊN 2).
2. **Phiếu dữ kiện là "trí nhớ người dùng".** Nó phải có:
   - một mục cho mỗi phần tử của `spec` không có nguyên văn trong prompt;
   - các câu trả lời chuẩn: giờ, múi giờ, năm, ai nhận tiền, chuyện gì xảy ra khi hết hạn;
   - mục cho mỗi chữ mơ hồ được cài cố ý (Q-TÊN 7);
   - quyền bỏ, ghi rõ bằng mục dạng "có thể bỏ: <phần đó>". Không có mục này thì không được bỏ.
3. **`checks.scenarios`** phải phủ các mẫu tối thiểu ở Q-KỊCH BẢN 3.
4. **Dev và đánh giá chia theo họ hợp đồng:** họ nào cũng có case ở cả hai phần. Đánh giá chiếm khoảng
   70%.
5. **Đóng băng dataset** (ghi SHA) trước khi chạy dev. Người dùng mô phỏng và người sửa pipeline không
   được đọc `spec`, `checks`, `author_note` của phần đánh giá.

## 9. Dev, đóng băng và báo cáo (Q-QUY TRÌNH)

1. **v3 từ nay là dev.** Mọi lần sửa AFF, builder, bộ gắn tên hay prompt người dùng mô phỏng chỉ dựa
   trên dev.
2. **Đóng băng** code, prompt SimUser và dataset bằng một tag trước khi chạy phần đánh giá. Sau đó chỉ
   được sửa hạ tầng; mọi lệch giao thức đều ghi lại.
3. **Quy tắc quyết định chốt trước:** McNemar chính xác, α = 0,05, kèm bootstrap theo cặp, như E6.
4. **Báo cáo bắt buộc có:**
   - bảng độ nhạy thời gian (Q-GIỜ 6);
   - số liệu của người dùng mô phỏng: số lần gọi lại, câu bị đánh dấu, số lần phản đối;
   - các hạn chế.

## 10. Việc cần làm để áp dụng quy ước

| Quy ước | Thành phần phải sửa |
| --- | --- |
| Q-TÊN 1–7 | builder AFF (`fact_builder.py`), prompt FactDraft |
| Q-TÊN 3, 8 | gắn kịch bản (`scenario_binding.py`), bộ chấm mới (chấm máy bằng `checks`) |
| Q-GIỜ 3 | builder: giờ dùng chung cho danh sách ngày, mẫu "hằng tháng" |
| Q-SỐ 2–3 | builder: đọc số theo ngôn ngữ, số thập phân ADA |
| Q-CHẤM 1–2, 6 | `e6_score.py` (hoặc `e7_score.py`): chấm máy, bỏ dòng trạng thái khỏi gói chấm |
| Q-KỊCH BẢN 2 | Pipeline: hỏi ví dụ bằng lời, đổi thành kịch bản, đọc lại |
| Q-NGƯỜI DÙNG 3–4 | `tools/e6/simuser.py`: kiểm tra quyền bỏ; bộ chạy: luật không dựa vào nhãn |
| Q-NHÁNH 2–3 | Baseline: người dùng đọc lời giải thích. Pipeline: tóm tắt intent bằng lời |
| Q-DỮ LIỆU | dataset v4 (hoặc sửa phiếu dữ kiện của v3 cho dev) |

## 11. Trạng thái áp dụng (2026-11-12)

| Quy ước | Trạng thái | Ở đâu |
| --- | --- | --- |
| Q-TÊN 1–7 | Đã làm | `research/formalization/party_names.py`; `fact_builder.py` (`identify`); prompt FactDraft v7 |
| Q-TÊN 3 (kịch bản) | Đã làm | `scenario_binding.py` (`bind_party_names`), gọi trong `comparison.py` |
| Q-GIỜ 3 | Đã làm | `fact_builder.py` (`_hours_of_day`, `_shared_hour`); prompt v7 |
| Q-SỐ 2–3 | Đã làm | `fact_builder.py` (`_plain_number` theo ngôn ngữ); prompt v7 |
| Notify ("ai cũng bấm") | Đã làm ở prompt | Grammar vốn có bước `notify`; prompt v7 nói rõ khi nào dùng |
| Q-CHẤM 1–2 | Đã làm | `research/experiments/e7_score.py`; chạy bằng `tools/e6/score_wsl.sh` |
| Q-NGƯỜI DÙNG 3 (quyền bỏ) | Đã làm | `tools/e6/simuser.py check` |
| Q-NGƯỜI DÙNG 4–6 | Đã làm | `tools/e7/auto.py` (`reply`: không dựa vào nhãn, gọi lại tối đa 2 lần, câu dự phòng, tối đa 6 tin nhắn) |
| Q-NHÁNH 2 | Đã làm | Baseline-Chat-v2; người dùng đọc lời giải thích và có thể phản đối |
| Q-NHÁNH 3 | Đã làm | `research/formalization/intent_summary.py` |
| Q-KỊCH BẢN 2–3 | Đã làm | `research/synthesis/example_scenarios.py` (xin ví dụ theo cấu trúc intent, đổi thành kịch bản, đọc lại) |
| AFF-1 (hỏi thay vì dừng) | Đã làm | `cli_runner.restate_question`, một lần mỗi case |
| Q-DỮ LIỆU 1, 3, 4 | Đã làm (trên prompt v3) | `dataset/v4`: `spec.parties`, kịch bản cho mọi người mua `first_come`, chia dev/eval theo họ |
| Q-DỮ LIỆU 2 (phiếu dữ kiện đầy đủ), 5 | Chưa | Cần prompt mới cho tập đánh giá sạch (`dataset/v4/README.md`) |

**Kiểm chứng chấm máy trên E6** (case 30–100, các hợp đồng đã giao):

| Nhánh | Máy và tay khớp | Lệch |
| --- | --- | --- |
| Baseline | 55/55 | 0 |
| Pipeline | 29/32 | 3 |

Ba case lệch của Pipeline:

- **41:** máy chuyển sang REVIEW, vì cách mã hóa lựa chọn bị đảo và người dùng không nêu cách mã
  hóa. Người phân xử chấm RIGHT. Đây đúng là việc của bước REVIEW.
- **68:** máy chấm RIGHT, tay chấm WRONG. Theo Q-TÊN, "Công ty Sao Mai" và SaoMai là một bên, nên máy
  đúng theo quy ước mới.
- **61:** máy chấm RIGHT, tay chấm WRONG (chỉ Sương mua được). Đây là **lỗ hổng của dataset**: cả 5 case
  `first_come` (57–61) chỉ có kịch bản cho người mua cuối danh sách, trái với Q-DỮ LIỆU 3. Phải sửa
  trong v4.

**Bảng phụ E6 theo quy ước mới:** chỉ có case 68 đổi verdict. Pipeline thành 39/71 (54,9%); Baseline
giữ nguyên 11/71.

## 12. Lịch sử

- Bản 1 (2026-11-12): chốt lần đầu, theo yêu cầu "chốt quy ước trước" sau khi rà soát E6.
- Bản 2 (2026-11-12): Q-TÊN 2 giữ tên riêng làm token, chỉ suy ra token cho tên vai. Lý do: khớp với
  token mà các nhánh đang tạo; việc so khớp vẫn qua `fold` nên không đổi kết quả chấm.
