# E7: hướng dẫn cho người phân xử mù (ghi trước khi chấm, 2026-11-13)

Người phân xử là một sub-agent mới. Nó chỉ đọc các gói chấm của nó (`packets.jsonl`, đã ẩn tên nhánh),
cùng bản hướng dẫn này, và không đọc gì khác trong repo. Mỗi sub-agent nhận một nhóm gói. Mọi nhóm dùng
chung một bản hướng dẫn.

## Căn cứ (Q-CHẤM, `docs/archive/E7-Conventions.md` bản 3)

- **Điều người dùng muốn và biết:** `prompt` và `fact_sheet` của gói. Đó là căn cứ đúng sai.
- **Hội thoại (`conversation`):** cho biết người dùng đã nói gì và đã được hỏi gì. Một dữ kiện mà prompt
  và phiếu dữ kiện đều không nêu, nhưng nhánh đã hỏi và người dùng đã để nhánh tự chọn, thì lựa chọn hợp
  lý nào cũng được.
- **Lệch máy tìm thấy (`machine_problems`):** khi chạy các kịch bản của dataset, máy thấy hợp đồng lệch
  ở đó. Người phân xử quyết định lệch đó có phải lỗi hành vi không.

## Câu hỏi `contract`: RIGHT, WRONG hay UNDETERMINED

**Được chấp nhận** (không làm hợp đồng sai):

- tên lựa chọn tùy ý;
- giá trị lựa chọn ánh xạ nhất quán với nghĩa (0 là không, 1 là có…);
- thêm `Close` hoặc bước chờ không có tiền;
- thứ tự các khoản trả trong cùng một bước khác đi;
- một nhánh thừa vô hại, tức nhánh không trả sai tiền cho ai.

**Là sai:**

- trả thừa, trả thiếu, trả một phần (tài khoản không đủ);
- sai người nhận, sai người nạp, sai người được bấm hoặc được chọn;
- thiếu nhánh hết hạn mà người dùng đã nêu;
- tiền kẹt lại trong hợp đồng khi kết thúc;
- khoản trả theo thời gian lại cần có người bấm, mà người dùng không yêu cầu;
- sai hạn: lệch quá 1 phút khi giờ đã được nêu; nằm ngoài ngày đã nêu khi chỉ nêu ngày;
- số tiền hoặc token sai (ADA là `currency_symbol` = `""`, `token_name` = `""`; số tiền tính bằng
  lovelace).

**UNDETERMINED:** chỉ dùng khi prompt, phiếu dữ kiện và hội thoại đều không đủ để quyết định.

## Câu hỏi `told_unsupported`: true hoặc false

Nhánh đã nói rõ với người dùng phần nào nó không làm được chưa, xét trong hội thoại và lời cuối?

- Một câu "phần X không làm được, có bỏ được không?" cũng tính là đã nói, miễn là đúng phần đó.
- Phần không làm được là phần trong prompt hoặc phiếu dữ kiện mà hợp đồng Marlowe không biểu diễn
  được, ví dụ lãi theo ngày thực, giá từ bên ngoài, hoặc lặp vô hạn.

## Đầu ra

Một tệp JSON, mỗi gói một khóa là `code` của gói:

```json
{"<code>": {"contract": "RIGHT" | "WRONG" | "UNDETERMINED", "told_unsupported": true | false,
            "reason": "<một câu>"}}
```

- Chỉ trả lời các câu hỏi có trong `questions` của gói.
- Mỗi verdict phải có `reason`.
- Gói nào máy báo lệch mà người phân xử chấm RIGHT thì `reason` phải giải thích vì sao lệch đó không
  phải lỗi hành vi.
