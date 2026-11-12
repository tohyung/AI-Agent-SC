# E7: cách chạy (2026-11-12)

Quy ước: `docs/E7-Conventions.md`. Dataset: `dataset/v4` (chỉ là dev, xem README của nó).

## Thành phần

| Việc | Ở đâu |
| --- | --- |
| Bộ chạy hai nhánh | `tools/e7/auto.py` (`pipe N`, `base N`, `reply pipe|base N '<json>'`) |
| Người dùng mô phỏng | sub-agent `sim-user` (`.claude/agents/sim-user.md`, SimUser-v2, Haiku 5.5, effort medium) |
| Đầu vào và kiểm tra câu trả lời | `tools/e6/simuser.py` (`situation`, `check_reply`) |
| Tóm tắt intent bằng lời | `research/formalization/intent_summary.py` |
| Xin ví dụ, đổi ví dụ thành kịch bản, đọc lại | `research/synthesis/example_scenarios.py` (một lần gọi model của Pipeline, được tính request) |
| Hỏi "diễn đạt lại" khi FactDraft không sửa được | `research/orchestration/cli_runner.py` (`restate_question`, một lần mỗi case) |
| Prompt Baseline cho E7 | `Baseline-Chat-v2` (`--dataset v4`): người dùng chỉ đọc lời giải thích; model được hỏi ví dụ |
| Chấm máy | `research/experiments/e7_score.py --dataset v4 --pipeline-dir runs/E7-Pipeline --baseline-dir runs/E7-Baseline`, chạy bằng `tools/e6/score_wsl.sh` |

## Vòng chạy một case

1. Testnet riêng phải đang chạy (`tools/e6/start_testnet.sh`, kiểm bằng `tools/e6/tip.sh`). Bộ chạy
   cần nó cho bước kiểm kích thước giao dịch.
2. `python tools/e7/auto.py pipe N`.
   - Thoát với mã 5 (`NEED_SIMUSER … <file>`) khi cần người dùng.
   - Người điều khiển giao **nguyên văn** nội dung `simuser-input.txt` cho một sub-agent `sim-user`
     **mới**.
   - Người điều khiển ghi **nguyên văn** JSON nó trả về bằng `python tools/e7/auto.py reply pipe N '<json>'`.
   - Mã 6 là câu trả lời bị từ chối: gọi một sub-agent mới với cùng tệp đầu vào. Sau 2 lần bị từ
     chối, bộ chạy tự dùng câu "Tôi không biết thêm…".
   - Chạy lại `pipe N` cho đến khi thoát với mã 0.
3. `python tools/e7/auto.py base N`, cùng cách làm như bước 2.
4. Các nhánh nhìn thấy những gì:
   - **Pipeline:** câu hỏi, bản tóm tắt intent (người dùng chấp nhận hoặc phản đối), yêu cầu ví dụ,
     các kịch bản đọc lại bằng lời (người dùng chấp nhận hoặc phản đối, tối đa 2 vòng), rồi chạy
     kịch bản trên hợp đồng.
   - **Baseline:** câu hỏi, từ chối, lời giải thích hợp đồng. Người dùng chấp nhận, phản đối hoặc bỏ
     cuộc.

## Kiểm tra bắt buộc với sub-agent

- Định nghĩa `sim-user` ghi `tools: []`, nhưng Claude Code vẫn liệt kê nó là có mọi công cụ. Vì vậy
  **mỗi lượt phải kiểm `tool_uses` trong thông báo kết thúc của sub-agent: chỉ được bằng 1** (lần
  trả kết quả). Lượt nào lớn hơn 1 là không hợp lệ: bỏ câu trả lời đó, gọi lại, và ghi vào nhật ký
  lệch giao thức.
- Người điều khiển không viết, không sửa, không chọn lọc câu trả lời. Nếu một câu trả lời trông sai,
  vẫn ghi nguyên văn; chỉ bộ kiểm tra tự động được từ chối.
- Toàn bộ đầu vào và đầu ra nằm trong `simuser.json` của từng case (`history`, `turns`).

## Còn thiếu trước khi có kết quả sạch

- Prompt mới cho tập đánh giá (v4 dùng lại prompt v3, nên chỉ là dev).
- Chạy thử vài case dev từ đầu đến cuối để bắt lỗi của bộ chạy. Chưa làm: bộ chạy mới chỉ được kiểm
  bằng unit test, chưa chạy thật trên testnet.
