# Benchmark Marlowe AI Agent

Dataset SHA-256: `bddc66e4223abbdc9278edd8972651448b9752ac4e898533bde2de69bc45226d`
Số case khả thi: 2; không khả thi: 0.

**Cảnh báo: self-judging bias; judge không độc lập model với agent.**

- converged: 0/2; Wilson 95%: (0.0, 0.6576197724933345)
- correct_90: 0/2; Wilson 95%: (0.0, 0.6576197724933345)
- strict_correct: 0/2; Wilson 95%: (0.0, 0.6576197724933345)
- false_convergence: 0/2; Wilson 95%: (0.0, 0.6576197724933345)

Độ chính xác trung bình: 1.0; trung vị: 1.0.
Vòng hội tụ trung vị/p90: None/None.
Thời gian trung bình/p90: 99.66833934996976/117.88307114996715 giây.
Tổng chi phí: 0 USD; số run có giá: 2/2.

## Phân tầng

### difficulty
- 1: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- 3: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
### type
- cancellation_fee: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- swap: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
### language
- en: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- vi: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
### info_mode
- ambiguous: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- complete: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
### challenges
- absolute_date: n=2, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- conflicting_info: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- non_ada_token: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)
- refund_on_timeout: n=1, hội tụ=0, đúng tuyệt đối=0 (mẫu nhỏ, chỉ mang tính gợi ý)

## CDF hội tụ

- ≤1 vòng: 0.0
- ≤2 vòng: 0.0
- ≤3 vòng: 0.0
- ≤5 vòng: 0.0
- ≤10 vòng: 0.0
- ≤20 vòng: 0.0
- ≤30 vòng: 0.0

Lặp lại phân tầng: {'n': 0, 'same_status': 0}
Hội tụ muộn: {'n': 0, 'late_converged': 0}

## Threats to validity

- Prompt được sinh theo template nên thiên lệch phong cách; metadata độ khó không đảm bảo độ khó thực tế.
- Simulator/evaluator là xấp xỉ Core V1, không thay thế analyzer hay runtime chính thức.
- Mẫu theo tầng nhỏ; các khoảng tin cậy không điều chỉnh cho cách chọn mẫu.
- Mỗi case thường chạy một lần; LLM có tính ngẫu nhiên.
- Trần vòng, thời gian và chi phí có thể cắt cụt hội tụ muộn.
- Judge có thể cùng họ model và bị thiên lệch.
- Agent không có đồng hồ đáng tin cậy cho mốc tuyệt đối.
