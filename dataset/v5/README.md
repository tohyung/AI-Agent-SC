# Dataset v5 (E7, tập đánh giá)

100 case mới, viết tay (2026-11-12) theo `docs/E7-Dataset-v5-Design.md`. Đây là **tập đánh giá
sạch của E7**: pipeline và Baseline chưa từng chạy trên nó. v4 (prompt v3) là tập dev.

SHA-256 của `cases.jsonl`:
`85f70d4330a547663706381a8079e0b3176769d669946235650340cdd8d09cae`

## Nội dung

| Mục | Phân bố |
| --- | --- |
| Ngôn ngữ | 60 tiếng Việt, 40 tiếng Anh |
| Loại thông tin | 40 đủ, 25 thiếu, 10 mơ hồ, 10 mâu thuẫn, 5 có phần không làm được, 10 bất khả |
| Hành vi mong đợi | 44 `converge`, 35 `ask_then_converge`, 6 `flag_conflict_then_converge`, 5 `converge_and_decline_extra`, 10 `reject_unsupported` |
| Họ hợp đồng | 19 họ, cùng số case mỗi họ và mỗi ngôn ngữ như v3 |
| Văn phong (`register`) | 57 chat, 20 gạch đầu dòng hoặc điều khoản, 15 câu cụt, 8 văn bản dài |
| Độ dài | 21 prompt dưới 25 từ, 10 prompt trên 80 từ |

Các mức phủ tối thiểu về cấu trúc Marlowe và hiện tượng ngôn ngữ của v3 đều đạt: không dấu, trộn
Việt–Anh, số viết bằng chữ, lovelace, lỗi gõ, tự đính chính, đại từ mơ hồ, phần trăm, số lẻ, Notify,
nhiều nhánh cạnh tranh, chuyển tiền giữa tài khoản, giá trị chọn làm số tiền, nhiều token, ≥4 bên.

## Đã kiểm

- `python -m dataset.v5.build --write`: 0 lỗi. Gồm:
  - tiêu chuẩn văn phong V-1 đến V-7: không mở đầu kiểu kể chuyện, không thuật ngữ hệ thống, đủ các
    kiểu văn phong và độ dài, độ giống từ với v2/v3 ≤ 0,5 và trong v5 ≤ 0,6, không tên vai nào trùng
    v3 (so qua `fold_name`);
  - tiêu chuẩn chính xác C-1 đến C-7: mọi tên, số tiền, ngày, giờ và múi giờ của `spec` có trong
    prompt (với case đủ) hoặc trong phiếu dữ kiện; case thiếu và mơ hồ có dữ kiện chỉ nằm trong
    phiếu; case có phần không làm được có quyền bỏ; mọi kịch bản chạy đúng trên bộ mô phỏng; họ
    `first_come` có kịch bản cho từng người mua.
- Bộ kiểm tra đã được thử bằng các lỗi cài vào (sai số tiền, sai giờ, sai ngày): bắt được cả ba.
- `E5_FULL=dataset.v5.check_reference bash runs/e5/run_wsl.sh` (C-8): cả 90 hợp đồng tham chiếu khả
  thi là SMT `Valid`, mọi kịch bản chạy đúng trên bộ tham chiếu Haskell.

## Ngoại lệ có chủ ý

- `v5-vi-coupon_bond-004` có một hạn năm 2029 (trái phiếu 2 năm bắt đầu 2027), ngoài khoảng
  2027–2028 của V-8.

## Quy tắc

- Đóng băng từ commit này. Không sửa case; mọi sửa đổi là bản mới và ghi vào nhật ký lệch giao thức.
- Không chạy pipeline hay Baseline trên v5 trước khi code E7 được đóng băng trên v4.
- Người viết case (Claude) cũng là người sửa pipeline, người vận hành bộ chạy và người chấm. Báo cáo
  phải ghi rõ. Vì vậy chấm máy (`research/experiments/e7_score.py --dataset v5`) là nguồn chính;
  người phân xử chỉ xét các case máy báo REVIEW.
- Khi vận hành người dùng mô phỏng trên v5, người điều khiển chỉ chuyển tiếp nguyên văn; không đọc
  `spec`, `checks` hay `reference_contract` để trả lời.
