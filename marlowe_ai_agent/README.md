# Marlowe AI Agent CLI

CLI sinh hợp đồng Marlowe Core V1 từ mô tả tiếng Việt. Node 1 sinh draft và hỏi bổ sung khi cần; Node 2 dùng LLM kiểm tra ngữ nghĩa; Node 3 phân tích graph theo quy tắc xác định. Trace và bản audit tiếng Việt được in khi chạy, không chứa suy luận thô của LLM.

## Cài đặt và chạy

Từ thư mục `D:\code\marlowe_ai_agent\marlowe_ai_agent`:

```powershell
python -m pip install -r .\requirements.txt
python .\main.py
```

CLI giữ nguyên cơ chế đọc `.env` và cấu hình model/provider trước đây. Có thể truyền prompt trực tiếp:

```powershell
python .\main.py --prompt "Alice ký quỹ 250 ADA cho Bob ..." --out .\result.json
```

`--trace-only` chỉ in tracking, audit và Summary. Các flag `--trace`, `--audit`, `--narrative-trace` vẫn được nhận để tương thích.

## Luồng và giới hạn

Mỗi lượt gồm: Node 1 sinh draft, structural gate chuẩn hóa và kiểm AST, Node 2 kiểm semantic, rồi Node 3 phân tích logic graph. Nếu một cổng thất bại, Node 1 nhận finding, hỏi người dùng khi cần quyết định nghiệp vụ hoặc tự sửa lỗi kỹ thuật; draft mới luôn quay về structural gate và Node 2 trước Node 3.

**Research mode (mặc định):** `python main.py --prompt "..."` không giới hạn số lượt sinh draft, số lời gọi LLM hoặc số lần lặp cùng AST và lỗi. Stall được ghi cảnh báo, không tự dừng. Agent tiếp tục đến khi `done`, cần thông tin nhưng không có câu trả lời (`no_user_input`), lỗi LLM không phục hồi được, hoặc Ctrl+C. Unlimited mode có thể tiêu tốn nhiều token/chi phí API; nó chủ yếu dùng để nghiên cứu khả năng tự hội tụ của agent.

**Bounded mode (tùy chọn):**

```powershell
python .\main.py --prompt "..." --max-iterations 20 --max-llm-calls 80 --stop-on-stall 5
```

`--max-iterations N` giới hạn tổng số draft; `--max-clarifications` là alias cũ. `--max-llm-calls N` giới hạn số request LLM thực tế, kể cả retry/repair. `--stop-on-stall K` dừng khi cùng AST và cùng lỗi xuất hiện K lần. Các giới hạn truyền vào phải là số nguyên dương. `--allow-unverified` cho chạy Node 3 dù semantic chưa đạt, nhưng **không bao giờ** cho Node 3 nhận contract rỗng. Contract chưa sinh vì thiếu dữ kiện đi vào luồng hỏi người dùng hoặc Node 2, không bị coi là AST sai cấu trúc.

Cuối mỗi lượt CLI in dòng tiến độ gồm kết quả structural, semantic, logic, số LLM call và thời gian. Summary từng lượt được flush vào `runs/<timestamp>.jsonl`; dùng `--run-log-dir PATH` để đổi nơi lưu hoặc `--no-run-log` để tắt. Lỗi ghi log chỉ tạo cảnh báo. Ctrl+C trả kết quả một phần với `stop_reason=interrupted`; `--out` vẫn ghi JSON.

Node 2 thử lại tối đa 3 lần khi gặp `LLMTransientError`, có chờ ngắn giữa các lần. Lỗi hết call budget (`LLMBudgetError`) và lỗi cấu hình (`LLMConfigError`) không được retry. Reasoner còn có retry ở tầng request và JSON repair, vì vậy số request thực tế cho một lượt Node 2 có thể lớn hơn số lần thử ở pipeline; tất cả đều được tính vào `llm_calls`.

JSON đầu ra giữ các key cũ và thêm `status` (`done` hoặc `blocked`), `stop_reason`, cùng `logic_verification.errors`, `warnings`, `paths_explored`. `stop_reason` gồm `ok`, `max_iterations`, `stalled`, `no_user_input`, `llm_error`, `semantic_not_passed`, `logic_not_passed`, `interrupted`. `max_iterations` và `stalled` chỉ xuất hiện khi bật giới hạn tương ứng. Exit code là 0 khi done, 2 khi blocked, 130 khi interrupted. Khi có `--out`, kết quả JSON vẫn được ghi ngay cả khi blocked hoặc interrupted.

## Marlowe JSON

AST theo [Core V1 Types.hs](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/src/Language/Marlowe/Core/V1/Semantics/Types.hs): `Close` là chuỗi `"close"`; `Choice` dùng `for_choice` và `choose_between`; hằng số Value là số nguyên trần. `timeout` là POSIX mili giây. Số tiền ADA trong AST và `ContractDraft.amount` dùng lovelace (1 ADA = 1_000_000 lovelace), nên 250 ADA là `250000000`. `role_token` dùng `PartySpec.name`, ví dụ `Alice`.

Structural gate chỉ tự chuyển ba dạng dialect cũ xác định: `{"close":"close"}` thành `"close"`, `choice`/`bounds` thành `for_choice`/`choose_between`, và `{"constant": n}` thành `n`. Mỗi thay đổi có ghi trace. Không tự quy đổi giây sang mili giây hay ADA sang lovelace. Timeout nghi là giây bị từ chối.

Prompt Node 1 dùng mô tả grammar sinh trực tiếp từ cùng các hằng số shape với structural validator. Ví dụ escrow và Notify/If/Let/Assert trong prompt được dựng bằng builder Marlowe và kiểm bằng validator cùng Node 3 trong test.

Node 3 kiểm trùng action và Choice chồng lấn trong cùng một When, số dư trên từng đường đi, deadline lồng nhau, biến Let và Choice chưa có, nhánh chết, tài khoản còn dư khi Close, cùng độ khớp giữa draft và AST. Node 3 chỉ tạo hard error khi có thể chứng minh vấn đề bằng phân tích tĩnh. Với timeout lồng nhau không tăng, bộ phân tích hiện chưa theo dõi riêng thời điểm đi vào nhánh Case và timeout continuation, nên chỉ ghi `warning`; riêng nhánh Case có thể được kích hoạt trước timeout bên ngoài. Phân tích tĩnh giới hạn 10.000 đường đi và có thể không xác định được số dư nếu Value phụ thuộc trạng thái runtime. Ngưỡng min-ADA phụ thuộc thông số giao thức/UTxO; hiện chưa phát cảnh báo cố định cho tiền nhỏ. Công cụ không thay thế trình phân tích Marlowe chính thức hay xác nhận khả năng triển khai on-chain.

## Test

```powershell
python -m pip install -r .\requirements-dev.txt
python -m pytest -q
```

Test dùng `FakeReasoner`, không gọi LLM hay mạng.

Sinh lại sample bằng `python -m tools.regen_sample` từ thư mục project.
