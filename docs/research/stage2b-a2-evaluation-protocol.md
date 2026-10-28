# Giao thức đánh giá refactor A2 (Stage 2B)

Trạng thái: **DRAFT — chốt trước khi viết code A2.** Mọi ngưỡng và tập dữ liệu
dưới đây phải được cố định trước lần chạy live đầu tiên của bất kỳ nhánh nào.
Đổi giao thức sau khi đã thấy kết quả phải ghi rõ trong báo cáo.

## Câu hỏi

A2 (model xuất sự kiện nguyên tử + biểu thức đóng; code tất định dựng đồ thị
scope, tính số tiền và mốc thời gian) có làm giảm lỗi cấu trúc và số lần gọi
model, **mà không** làm giảm độ đúng của các dữ kiện nghiệp vụ được trích xuất
so với code hiện tại hay không.

## Tập dữ liệu

- **Tập phát triển:** case 1–56 trong `marlowe_ai_agent/bench/dataset/cases.jsonl`
  (SHA-256 `e05c23f4…a907a`). Đã dùng để tinh chỉnh; kết quả trên tập này chỉ
  là bằng chứng phát triển, không phải độ chính xác công bố.
- **Case 57:** loại khỏi mọi phép đo. Trường đánh giá của nó đã bị đọc khi
  chạy roleplay ngày 2026-10-27.
- **Tập test đóng:** case 58–100. Không chạy, không đọc `reference_contract`,
  `params`, `checks`, `hidden_facts` cho đến khi code đóng băng. Chạy đúng một
  lần mỗi nhánh; không vá giữa chừng.

## Hai nhánh so sánh

| Nhánh | Code | Ghi chú |
| --- | --- | --- |
| BASE | commit có `stage2b_replay` trên nền `cca0836` | Prompt và validator hiện tại |
| A2 | commit A2 đã đóng băng | Schema core v5 |

Cả hai dùng cùng model (`nvidia/nemotron-3-ultra-550b-a55b:free`), cùng cấu
hình transport, chỉ prompt gốc (`requirement_history` version 1). Không có câu
trả lời roleplay hay revision, để loại bỏ biến do người viết tay.

## Chỉ số

Chỉ số chính, tự động, không cần người chấm:

1. **M1 — hợp lệ ở lượt đầu:** tỷ lệ output qua validator core + projection
   không cần repair.
2. **M2 — chi phí tới intent hợp lệ:** tỷ lệ hợp lệ sau tối đa 3 lần repair, và
   số request vật lý trung bình cho mỗi intent hợp lệ.
3. **M3 — độ đúng dữ kiện:** recall/precision của vai trò (`role_token`), số
   tiền nguyên (`deposits`/`pay`) và mốc `timeout` mà `reference_contract` thực
   sự dùng, so với claim có trạng thái explicit/derived/user_confirmed. Chỉ tính
   trên case `info_mode=complete`. Scorer tự động
   (`research/experiments/stage2b_score.py`) chạy **sau** khi lượt chạy kết
   thúc. Ghi chú 2026-10-28, trước khi chấm bất kỳ nhánh nào: định nghĩa ban
   đầu so với `params` bị bỏ vì mọi case đều mang đủ `fee`, `units`,
   `threshold`, `t1..t3` kể cả khi prompt không dùng.
4. **M4 — quyết định hỏi/chấp nhận:** `complete` → `accepted_interpretation`;
   `missing`/`ambiguous` → `clarification_required` hoặc
   `conflict_requires_resolution`; `infeasible` →
   `unsupported_for_current_study`.

Chỉ số phụ: số dòng lớp chuẩn hóa tất định (`core_draft.py` và tương đương),
kích thước prompt system/user, số loại mã lỗi.

## Baseline offline đã có (không phải chỉ số so sánh)

`python -m research.experiments.stage2b_replay --output <file>` phát lại 255
output lượt đầu đã lưu của case 1–57 qua code hiện tại, 0 request. Kết quả tại
`cca0836` (chế độ `normalized`):

| Kỷ nguyên output | Số output | PASS |
| --- | --- | --- |
| core v3 đầy đủ (06–12/10) | 144 | 15 |
| draft v3 | 8 | 0 |
| draft v4 (13–27/10) | 103 | 5 |

Bảng này mô tả lớp tất định trên output lịch sử. Nó không so được trực tiếp với
A2: output được sinh dưới các prompt khác nhau, và validator đã thêm luật mới
sau khi một phần output được ghi. Phép so sánh BASE/A2 phải dùng lượt chạy live
mới theo giao thức này.

## Quy tắc quyết định

Quyết định ngày 2026-10-27: **không đặt ngưỡng trước.** Người phụ trách sẽ xem
M1–M4 của cả hai nhánh rồi mới quyết định giữ A2 hay không. Hệ quả:

- So sánh BASE/A2 trên tập phát triển là **khám phá**, không phải kiểm định đã
  đăng ký trước. Báo cáo phải ghi rằng ngưỡng được chọn sau khi xem kết quả.
- Chỉ số và cách đo ở trên vẫn cố định; không thêm hay bỏ chỉ số sau khi chạy.
- Bằng chứng xác nhận duy nhất là một lần chạy tập test đóng (58–100) trên code
  đã đóng băng của nhánh được chọn.

## Ngân sách và số mẫu

Một mẫu cho mỗi case dev (1–56, bỏ 57), mỗi nhánh. Mỗi case là một lượt trích
xuất với tối đa 3 repair: M1 lấy từ lỗi trước repair, M2 từ kết quả cuối.
Tối đa 4 request mỗi case, 224 mỗi nhánh. Runner dừng khi provider báo hết hạn
mức và chạy tiếp được từ case chưa có kết quả. Model ngẫu nhiên, nên một mẫu
chỉ cho ước lượng thô.
