# Benchmark Marlowe AI Agent

Dataset SHA-256: `e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`
Số case khả thi: 95; không khả thi: 5.

**Cảnh báo: self-judging bias; judge không độc lập model với agent.**

- converged: 95/95; Wilson 95%: (0.9611351464605291, 1.0)
- correct_90: 95/95; Wilson 95%: (0.9611351464605291, 1.0)
- strict_correct: 95/95; Wilson 95%: (0.9611351464605291, 1.0)
- false_convergence: 0/95; Wilson 95%: (0.0, 0.0388648535394709)

Độ chính xác trung bình: 1.0; trung vị: 1.0.
Vòng hội tụ trung vị/p90: 1/1.0.
Thời gian trung bình/p90: 0.0010143505305198854/0.0015026999870315194 giây.
Tổng chi phí: None USD; số run có giá: 0/102.

## Phân tầng

### difficulty
- 1: n=24, hội tụ=24, đúng tuyệt đối=24
- 2: n=29, hội tụ=29, đúng tuyệt đối=29
- 3: n=28, hội tụ=28, đúng tuyệt đối=28
- 4: n=14, hội tụ=14, đúng tuyệt đối=14
### type
- cancellation_fee: n=7, hội tụ=7, đúng tuyệt đối=7 (mẫu nhỏ, chỉ mang tính gợi ý)
- crowdfunding: n=8, hội tụ=8, đúng tuyệt đối=8 (mẫu nhỏ, chỉ mang tính gợi ý)
- escrow_2party: n=14, hội tụ=14, đúng tuyệt đối=14
- escrow_3party: n=10, hội tụ=10, đúng tuyệt đối=10
- loan: n=10, hội tụ=10, đúng tuyệt đối=10
- milestone: n=8, hội tụ=8, đúng tuyệt đối=8 (mẫu nhỏ, chỉ mang tính gợi ý)
- rental_deposit: n=8, hội tụ=8, đúng tuyệt đối=8 (mẫu nhỏ, chỉ mang tính gợi ý)
- swap: n=10, hội tụ=10, đúng tuyệt đối=10
- third_party: n=10, hội tụ=10, đúng tuyệt đối=10
- vesting: n=10, hội tụ=10, đúng tuyệt đối=10
### language
- en: n=39, hội tụ=39, đúng tuyệt đối=39
- vi: n=56, hội tụ=56, đúng tuyệt đối=56
### info_mode
- ambiguous: n=10, hội tụ=10, đúng tuyệt đối=10
- complete: n=55, hội tụ=55, đúng tuyệt đối=55
- missing: n=30, hội tụ=30, đúng tuyệt đối=30
### challenges
- absolute_date: n=33, hội tụ=33, đúng tuyệt đối=33
- conflicting_info: n=10, hội tụ=10, đúng tuyệt đối=10
- long_narrative: n=14, hội tụ=14, đúng tuyệt đối=14
- multi_party: n=28, hội tụ=28, đúng tuyệt đối=28
- multi_stage: n=28, hội tụ=28, đúng tuyệt đối=28
- noise_context: n=14, hội tụ=14, đúng tuyệt đối=14
- non_ada_token: n=10, hội tụ=10, đúng tuyệt đối=10
- refund_on_timeout: n=42, hội tụ=42, đúng tuyệt đối=42
- relative_time: n=62, hội tụ=62, đúng tuyệt đối=62
- third_party_oracle: n=10, hội tụ=10, đúng tuyệt đối=10
- threshold: n=18, hội tụ=18, đúng tuyệt đối=18

## CDF hội tụ

- ≤1 vòng: 1.0
- ≤2 vòng: 1.0
- ≤3 vòng: 1.0
- ≤5 vòng: 1.0
- ≤10 vòng: 1.0
- ≤20 vòng: 1.0
- ≤30 vòng: 1.0

Lặp lại phân tầng: {'n': 2, 'same_status': 2}
Hội tụ muộn: {'n': 0, 'late_converged': 0}

## Threats to validity

- Prompt được sinh theo template nên thiên lệch phong cách; metadata độ khó không đảm bảo độ khó thực tế.
- Simulator/evaluator là xấp xỉ Core V1, không thay thế analyzer hay runtime chính thức.
- Mẫu theo tầng nhỏ; các khoảng tin cậy không điều chỉnh cho cách chọn mẫu.
- Mỗi case thường chạy một lần; LLM có tính ngẫu nhiên.
- Trần vòng, thời gian và chi phí có thể cắt cụt hội tụ muộn.
- Judge có thể cùng họ model và bị thiên lệch.
- Agent không có đồng hồ đáng tin cậy cho mốc tuyệt đối.
