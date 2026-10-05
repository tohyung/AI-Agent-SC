# Marlowe AI Agent CLI

CLI mặc định đi qua luồng mới: Stage 2B trích xuất intent, Stage 2C yêu cầu người dùng duyệt, model sinh Marlowe Core V1 AST từ intent đã duyệt, structural gate và SMT kiểm candidate, rồi semantic comparison đối chiếu các claim có thể kiểm và kịch bản reference độc lập. Stage 4/5 và cổng ledger chạy khi đủ bằng chứng/thiết bị. AST model sinh ra luôn là **candidate**, không tự động có quyền triển khai. Pipeline Node 1/2/3 cũ chỉ còn ở `--research-mode legacy` để chẩn đoán; nó chưa được tách khỏi package runtime.

## Cài đặt và chạy

Từ thư mục `D:\code\marlowe_ai_agent\marlowe_ai_agent`:

```powershell
python -m pip install -r .\requirements.txt
python .\main.py
```

CLI đọc cấu hình model/provider từ `.env` như trước, nhưng dùng transport riêng cho luồng mới và đếm mọi request thực tế, kể cả JSON repair. Có thể truyền prompt trực tiếp:

```powershell
python .\main.py --prompt "Alice ký quỹ 250 ADA cho Bob ..." --out .\result.json
```

`--prompt` chạy không tương tác: kết quả sẽ dừng ở câu hỏi cần làm rõ hoặc cổng duyệt intent. Để trả lời và xác nhận trong cùng phiên, dùng `--interactive` hoặc chạy không có `--prompt`. `--trace-only` chỉ in tiến độ và Summary; các flag `--trace`, `--audit`, `--narrative-trace` vẫn được nhận để tương thích.

Mặc định tối đa 8 lượt trích xuất, tối đa 8 lượt sinh AST trên mỗi intent đã duyệt, 40 request LLM vật lý và dừng khi candidate/finding lặp. Lỗi AST hoặc SMT được đưa lại cho model trong cùng intent đã duyệt; lỗi provider/driver không biến thành câu hỏi nghiệp vụ. Không tự thay đổi intent đã duyệt hay giả định câu trả lời.

SMT và Marlowe reference dùng driver Haskell đã pin. Trên Windows, adapter chạy wrapper trong WSL; trên Linux/WSL gọi trực tiếp. Có thể truyền `--reference-binary PATH` để chọn binary Linux cụ thể. Kịch bản độc lập do người dùng tự chuẩn bị có thể truyền bằng `--expectation PATH` trong phiên tương tác; JSON cần `request.state` (đủ `accounts`, `choices`, `boundValues`, `minTime`), `request.transactions` (các cặp `interval`/`inputs`), `expected_status`, và tùy chọn expected final state/contract/warnings/payments. CLI sẽ hiển thị để người dùng xác nhận riêng. Chỉ có AST path không chứng minh tương đương hành vi; kịch bản reference đã duyệt chỉ chứng minh trace được kiểm. Cổng ledger-size cần cấu hình `MARLOWE_LEDGER_*` đầy đủ trong môi trường; nó chỉ phân tích kích thước giao dịch với node đồng bộ, không ký hay submit giao dịch. Chưa có ví/ký testnet, nên testnet/deployment chưa thể chạy thật và `CANDIDATE_ONLY` là kết quả đúng khi thiếu bằng chứng hoặc hạ tầng. `runs/<timestamp>.jsonl` lưu lịch sử stage/artifact và metadata request của từng prompt, không lưu chain-of-thought hay API key.

## Pipeline legacy (chỉ chẩn đoán)

Các đoạn dưới đây mô tả riêng `python .\main.py --research-mode legacy`, không phải luồng mặc định.

## Luồng và giới hạn

Mỗi lượt gồm: Node 1 sinh draft, structural gate chuẩn hóa và kiểm AST, Node 2 kiểm semantic, rồi Node 3 phân tích logic graph. Nếu một cổng thất bại, Node 1 nhận finding, hỏi người dùng khi cần quyết định nghiệp vụ hoặc tự sửa lỗi kỹ thuật; draft mới luôn quay về structural gate và Node 2 trước Node 3.

**Legacy mode (opt-in):** `python main.py --research-mode legacy --prompt "..."` không giới hạn số lượt sinh draft, số lời gọi LLM hoặc số lần lặp cùng AST và lỗi. Stall được ghi cảnh báo, không tự dừng. Agent tiếp tục đến khi `done`, cần thông tin nhưng không có câu trả lời (`no_user_input`), lỗi LLM không phục hồi được, hoặc Ctrl+C. Unlimited mode có thể tiêu tốn nhiều token/chi phí API; nó chủ yếu dùng để nghiên cứu khả năng tự hội tụ của agent.

**Bounded mode (tùy chọn):**

```powershell
python .\main.py --research-mode legacy --prompt "..." --max-iterations 20 --max-llm-calls 80 --stop-on-stall 5
```

`--max-iterations N` giới hạn tổng số draft; `--max-clarifications` là alias cũ. `--max-llm-calls N` giới hạn số request LLM thực tế, kể cả retry/repair. `--stop-on-stall K` dừng khi cùng AST và cùng lỗi xuất hiện K lần. Các giới hạn truyền vào phải là số nguyên dương. `--allow-unverified` cho chạy Node 3 dù semantic chưa đạt, nhưng **không bao giờ** cho Node 3 nhận contract rỗng. Contract chưa sinh vì thiếu dữ kiện đi vào luồng hỏi người dùng hoặc Node 2, không bị coi là AST sai cấu trúc.

Cuối mỗi lượt CLI in dòng tiến độ gồm kết quả structural, semantic, logic, số LLM call và thời gian. Summary từng lượt được flush vào `runs/<timestamp>.jsonl`; dùng `--run-log-dir PATH` để đổi nơi lưu hoặc `--no-run-log` để tắt. Lỗi ghi log chỉ tạo cảnh báo. Ctrl+C trả kết quả một phần với `stop_reason=interrupted`; `--out` vẫn ghi JSON.

Có hai tầng retry: **request-level** trong reasoner thử lại request tới provider và sửa JSON; **operation-level** trong pipeline thử lại toàn bộ `draft_from_prompt`, `semantic_verify` hoặc `logic_feedback_to_clarification` tối đa 3 lần khi gặp `LLMTransientError`, với thời gian chờ ngắn. `LLMBudgetError`, `LLMConfigError` và lỗi LLM khác không được retry. Với `LLM_RETRY_ATTEMPTS=3` và 3 lần thử operation, số request thực tế có thể lớn hơn 3; `llm_calls` chỉ đếm request được phép gửi, không tính lượt bị chặn vì vượt budget.

JSON đầu ra giữ các key cũ và thêm `status` (`done` hoặc `blocked`), `stop_reason`, cùng `logic_verification.errors`, `warnings`, `paths_explored`. `stop_reason` gồm `ok`, `max_iterations`, `stalled`, `no_user_input`, `llm_error`, `semantic_not_passed`, `logic_not_passed`, `interrupted`. `max_iterations` và `stalled` chỉ xuất hiện khi bật giới hạn tương ứng. Exit code là 0 khi done, 2 khi blocked, 130 khi interrupted. Khi có `--out`, kết quả JSON vẫn được ghi ngay cả khi blocked hoặc interrupted.

## Marlowe JSON

AST theo [Core V1 Types.hs](https://github.com/marlowe-lang/marlowe-cardano/blob/main/marlowe/src/Language/Marlowe/Core/V1/Semantics/Types.hs): `Close` là chuỗi `"close"`; `Choice` dùng `for_choice` và `choose_between`; hằng số Value là số nguyên trần. `timeout` là POSIX mili giây. Số tiền ADA trong AST và `ContractDraft.amount` dùng lovelace (1 ADA = 1_000_000 lovelace), nên 250 ADA là `250000000`. `role_token` dùng `PartySpec.name`, ví dụ `Alice`.

Structural gate chỉ tự chuyển ba dạng dialect cũ xác định: `{"close":"close"}` thành `"close"`, `choice`/`bounds` thành `for_choice`/`choose_between`, và `{"constant": n}` thành `n`. Mỗi thay đổi có ghi trace. Không tự quy đổi giây sang mili giây hay ADA sang lovelace. Timeout nghi là giây bị từ chối.

Prompt Node 1 dùng mô tả grammar sinh trực tiếp từ metadata có kiểu của structural validator: mỗi constructor Core V1 được ghi bằng tên, JSON field và kiểu field, ví dụ `Pay: { pay: Value, from_account: Party, to: Payee, token: Token, then: Contract }`. Validator lấy tập field hợp lệ từ chính metadata này, không duy trì một bảng shape thứ hai. Ví dụ escrow và Notify/If/Let/Assert trong prompt được dựng bằng builder Marlowe và kiểm bằng validator cùng Node 3 trong test.

Khi người dùng trả lời ít nhất một câu hỏi, bộ đếm stall semantic của trạng thái hiện tại được reset; structural và logic stall vẫn giữ riêng. `semantic_history` trong JSON chỉ lưu fingerprint của prompt, contract và kết quả semantic theo generation, không lưu nội dung câu trả lời hay suy luận thô. Nhánh logic dùng action tường minh để quyết định regenerate hoặc cần input, không suy luận từ việc chuỗi prompt có thay đổi hay không.

Node 3 kiểm trùng action và Choice chồng lấn trong cùng một When, số dư trên từng đường đi, deadline lồng nhau, biến Let và Choice chưa có, nhánh chết, tài khoản còn dư khi Close, cùng độ khớp giữa draft và AST. Node 3 chỉ tạo hard error khi có thể chứng minh vấn đề bằng phân tích tĩnh. Với timeout lồng nhau không tăng, bộ phân tích hiện chưa theo dõi riêng thời điểm đi vào nhánh Case và timeout continuation, nên chỉ ghi `warning`; riêng nhánh Case có thể được kích hoạt trước timeout bên ngoài. Phân tích tĩnh giới hạn 10.000 đường đi và có thể không xác định được số dư nếu Value phụ thuộc trạng thái runtime. Ngưỡng min-ADA phụ thuộc thông số giao thức/UTxO; hiện chưa phát cảnh báo cố định cho tiền nhỏ. Công cụ không thay thế trình phân tích Marlowe chính thức hay xác nhận khả năng triển khai on-chain.

## Test

```powershell
python -m pip install -r .\requirements-dev.txt
python -m pytest -q
```

Test dùng `FakeReasoner`, không gọi LLM hay mạng.

Sinh lại sample bằng `python -m tools.regen_sample` từ thư mục project.
