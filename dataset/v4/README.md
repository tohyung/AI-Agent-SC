# Dataset v4 (E7)

Bản dựng lại từ v3 theo `docs/archive/E7-Conventions.md`, bằng `python -m dataset.v4.build --write`
(2026-11-12).

SHA-256 của `cases.jsonl`:
`d9609682a9b3e4a239eb7731a26fc36cd41f3b2897791b537271197d8d48fc1b`

## Khác gì so với v3

| Quy ước | Thay đổi |
| --- | --- |
| Q-DỮ LIỆU 1 | `spec.parties`: mỗi vai có `name` (tên hiển thị mà prompt hoặc phiếu dữ kiện gắn với token, ví dụ "Công ty Sao Mai") và `role` (token, ví dụ SaoMai). Không có cụm gắn kèm thì `name` là token. |
| Q-DỮ LIỆU 3 | Họ `first_come` có thêm kịch bản `buyer_<k>_first` cho từng người mua khác người cuối danh sách. v3 chỉ kiểm người cuối, nên ở E6 case 61 một hợp đồng chỉ cho một người mua đã qua máy chấm. Kết quả mong đợi tính từ `spec` như v3, và mỗi kịch bản thêm vào đều chạy được trên hợp đồng tham chiếu bằng bộ mô phỏng. |
| Q-DỮ LIỆU 4 | `split` là `dev` (32 case) hoặc `eval` (68 case). Chia theo từng họ hợp đồng (khoảng 30% dev), theo thứ tự SHA-256 của id. |
| Id | `v4-…`, kèm `origin` là id v3. |

Prompt, `spec` (trừ `parties`), phiếu dữ kiện, hợp đồng tham chiếu và hành vi mong đợi giữ nguyên v3.

## Giới hạn: v4 chỉ là tập dev

Prompt của v4 là prompt của v3. Các prompt này:

- đã dùng để sửa pipeline (E6, case 1–29);
- đã được đọc toàn bộ, gồm cả `spec` và `checks`, trong lần rà soát lỗi E6 (`docs/archive/E6-Failure-Review.md`);
- là nguồn của các quy ước E7.

Vì vậy chạy E7 trên v4 chỉ cho kết quả **dev**, kể cả phần `split = eval`. Phần `eval` chỉ dùng để
giữ cách chia cho một bộ đánh giá sau này. Muốn có kết quả sạch cần **prompt mới**, viết theo cùng
quy ước và đóng băng trước khi chạy; nên có người khác viết, hoặc ít nhất viết mà không nhìn kết quả
của pipeline.

## Kiểm tra

- `python -m dataset.v4.build` báo 0 lỗi: mọi kịch bản thêm vào đều chạy được trên hợp đồng tham chiếu
  với bộ mô phỏng Python.
- Chấm máy kịch bản trên bộ tham chiếu Haskell:
  `bash tools/e6/score_wsl.sh research.experiments.e7_score --dataset v4 …`. Với các hợp đồng của
  Pipeline ở E6, case 58 và 61 được báo REVIEW (người mua khác không mua được), còn case 57 vẫn RIGHT.
