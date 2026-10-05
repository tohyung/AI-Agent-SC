# Báo cáo chuyển tuyến pipeline (big update)

Baseline: `87ce815` (`feat(research): extend Batch 01 contract coverage and validate six ledger paths`).

## Phạm vi đã thay đổi

1. **Một entrypoint cho người dùng.** `marlowe_ai_agent/main.py` chỉ gọi CLI mới.
   CLI chính không còn `--research-mode legacy/shadow/candidate/authorized` hoặc
   `--allow-unverified`. Khi chạy từ thư mục project, `main.py` đưa repo root
   vào Python path để import `research` ổn định.
2. **Tách phần còn giá trị.** AST builders/normalization, Core V1 structural
   validator, graph lint, Node 3 warning renderer, SMT counterexample mapper
   và utilities đã chuyển vào `research/marlowe_core/`. Các stage đang hoạt động
   import trực tiếp package này. Triển khai Node 1/2/3 và reasoner cũ được
   chuyển vào `research/legacy/`. Alias ở import path cũ chỉ phục vụ test và
   benchmark lịch sử; import CLI chính trong process sạch không nạp
   `research.legacy`.
3. **Stage 2B → 2C → sinh candidate.** `ModelTransport` dùng endpoint, model
   và key trong `.env`, đếm request vật lý kể cả JSON repair. Stage 2B sinh
   semantic core; Stage 2C đòi người dùng xem và đồng ý với đúng IntentSpec.
   Sau đó LLM sinh Marlowe Core V1 AST cùng mapping evidence; contract vẫn mang
   authority `MODEL_CANDIDATE`. Structural gate và SMT pinned driver kiểm
   candidate. Finding được đưa lại cho model để sinh lại trong giới hạn call
   và iteration; unavailable/model error không bị đổi thành câu hỏi nghiệp vụ.
4. **Đối chiếu và assurance.** Semantic comparison đối chiếu claim/scope với
   AST trong phạm vi có thể chứng minh; AST path tồn tại không đủ để kết luận
   tương đương intent. Trace Marlowe reference chỉ được so với expectation độc
   lập do người dùng xác nhận. Stage 4 chỉ duyệt input đã khai báo, giới hạn
   depth/trace và trả `INCONCLUSIVE` khi không có trace/oracle được đánh giá.
   Stage 5 và các gate sau tiếp tục xử lý artifact theo boundary hiện có,
   không tự nâng candidate thành proof.
5. **Tracking.** CLI hiển thị stage đang chạy, giữ requirement history,
   execution history, artifacts và metadata LLM đã loại nội dung nhạy cảm
   trong `runs/<timestamp>.jsonl`. Mặc định 8 lượt, 40 physical LLM calls
   và stall threshold 2. Run log không lưu API key hay raw chain-of-thought.
6. **Tài liệu/test.** README chính chỉ mô tả route mới; README cũ lưu tại
   `docs/research/legacy-pipeline-readme.md`. Test mới kiểm route LLM, SMT
   gate, reference seam, transport, CLI isolation và cutover. Test lịch sử
   vẫn được giữ để regression các primitive và tái lập benchmark.

## Ranh giới và điều chưa được chứng minh

- SMT `Valid` nghĩa là không tìm thấy modeled warning trong phạm vi analyzer;
  không phải chứng minh hợp đồng đúng intent hay an toàn trên ledger.
- Reference comparison với một kịch bản xác nhận chỉ kiểm trace đó. Stage 4
  là bounded exploration, không exhaustive. Stage 5 chưa có independent
  checker tổng quát cho mọi property.
- Ledger adapter chỉ kiểm tra size với CLI/node đã pin và đã cấu hình; không
  ký, submit hay deploy. Hiện chưa có ví/cách ký testnet, và chưa có bằng
  chứng transaction được xác nhận trên public testnet. Vì vậy bản cập nhật
  này **chưa được gọi là production-ready**.
- Không chạy live LLM/API, public testnet hay chạy lại 20 prompt trong patch
  này. Chất lượng semantic của model và khả năng hội tụ trên prompt mới cần
  được đo riêng; test offline không thay thế được phép đo đó.

## Kiểm tra

- `python -m pytest -q`: **612 passed, 36 skipped**.
- `python -m compileall -q research marlowe_ai_agent tools`: pass.
- `uvx ruff check --select F401,F841`: pass.
- `python .\main.py --help` từ `marlowe_ai_agent/`: pass.
- CLI import isolation: pass, không nạp module `research.legacy`.
- API calls trong kiểm tra này: **0**.

Kết luận: pipeline cũ đã bị cắt khỏi supported runtime và được archive cho
nghiên cứu. Route mới được nối và test offline; ledger/testnet production gate
vẫn fail closed cho đến khi có hạ tầng, signing và bằng chứng on-chain thật.
