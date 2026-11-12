# E7: giao thức đóng băng (2026-11-12)

E7 trả lời lại RQ3 và RQ4 sau E6, với:

- quy ước chung: `docs/E7-Conventions.md`, bản 3;
- người dùng mô phỏng độc lập cho cả hai nhánh: SimUser-v3;
- tập đánh giá mới viết tay: `dataset/v5`.

Đóng băng ở tag **`E7-Freeze`**. Từ tag này trở đi, chỉ được sửa hạ tầng (mục 6).

## 1. Thành phần đóng băng

| Thành phần | Phiên bản hoặc mã băm |
| --- | --- |
| Dataset đánh giá | `dataset/v5/cases.jsonl`, SHA-256 `85f70d4330a547663706381a8079e0b3176769d669946235650340cdd8d09cae` (tag `E7-Dataset-v5`) |
| Model của hai nhánh | `gemini-3.5-flash-lite` (Gemini free tier; 3 key xoay vòng theo ngày quota) |
| Pipeline | AFF: FactDraft v5, prompt `Formalization-FactPrompt-v7`, builder và các cổng như tại tag; đổi ví dụ thành kịch bản `E7-ExampleScenarios-v2`; tóm tắt intent `research/formalization/intent_summary.py` |
| Baseline | `research/experiments/baseline_llm.py`, prompt `Baseline-Chat-v2` |
| Người dùng mô phỏng | sub-agent `sim-user`: Claude Haiku 5.5, effort medium, prompt SimUser-v3 (`.claude/agents/sim-user.md`, SHA-256 `1dd3f56be0cd02e4255dfb0529407e6d51cdf6c7d8393f9e13031028de606630`) |
| Kiểm tra câu trả lời của người dùng | `tools/e6/simuser.py` (`check_reply`) |
| Bộ chạy | `tools/e7/auto.py`, `E7_DATASET=v5`; ghi vào `runs/E7-Eval-Pipeline`, `runs/E7-Eval-Baseline` |
| Quy ước | `docs/E7-Conventions.md` bản 3, SHA-256 `d0bc62b7b979d99c6f47651b90f3e30a75eb2b42587e346f49387a8a404b3bda` |
| Chấm máy | `research/experiments/e7_score.py --dataset v5` |

## 2. Chạy

1. Chạy đủ 100 case v5 theo thứ tự id, theo lô. Mỗi case chạy nhánh Pipeline trước rồi đến Baseline
   (`docs/E7-Run-Procedure.md`).
2. **Ngân sách:** trần request của Baseline ở mỗi case bằng số request Pipeline đã dùng ở case đó
   (gồm cả lần đổi ví dụ thành kịch bản). Luật đếm như E6: không tính lỗi quota (402/429), lỗi mạng,
   lỗi máy chủ 5xx.
3. **Người dùng mô phỏng:**
   - mỗi lượt là một sub-agent `sim-user` mới, nhận nguyên văn tệp `simuser-input.txt`;
   - câu trả lời được ghi nguyên văn bằng `auto.py reply`;
   - lượt nào có `tool_uses` khác 1 là không hợp lệ: bỏ và gọi lại, ghi vào nhật ký lệch giao thức;
   - người điều khiển không viết, không sửa, không chọn lọc câu trả lời;
   - người điều khiển không đọc `spec`, `checks`, `reference_contract`, `author_note` của v5 cho đến
     khi chạy xong cả 100 case.
4. **Case bị dừng giữa chừng vì hạ tầng** (quota, testnet, mạng) được chạy tiếp từ chỗ dừng. Case hỏng
   vì lỗi hạ tầng sau khi đã có kết quả thì không chạy lại; ghi vào nhật ký.

## 3. Chấm

1. **Chấm máy trước:** `e7_score --dataset v5` cho cả hai nhánh. Kết quả mỗi hợp đồng đã giao là
   RIGHT hoặc REVIEW.
2. **Người phân xử chỉ xét case REVIEW**, theo `docs/E5-Adjudication-Rubric.md` và Q-CHẤM của quy
   ước. Gói chấm ẩn tên nhánh; các dòng trạng thái máy móc được bỏ khỏi lời cuối. Verdict nào khác với
   máy phải có lý do ghi lại.
3. **Kết quả theo hành vi mong đợi** (Q-CHẤM 5):

   | Hành vi mong đợi | Thành công khi |
   | --- | --- |
   | đủ / thiếu / mâu thuẫn | giao hợp đồng RIGHT |
   | `converge_and_decline_extra` | RIGHT và đã nói rõ phần bị bỏ |
   | `reject_unsupported` | không giao hợp đồng và đã nêu đúng phần không làm được |

## 4. Quy tắc quyết định (chốt trước)

- **RQ3, chỉ số chính:** tỷ lệ case thành công của Pipeline so với Baseline trên 100 case v5.
  - Kiểm định McNemar chính xác hai phía theo cặp, α = 0,05.
  - Khoảng tin cậy 95% của chênh lệch bằng bootstrap theo cặp: 10 000 lần, seed 20261111, dùng
    `e6_score.paired_comparison`.
  - "Pipeline mạnh hơn" khi p < 0,05 và chênh lệch > 0; "Baseline mạnh hơn" khi p < 0,05 và chênh
    lệch < 0; còn lại là "chưa phân biệt được".
- **RQ3, chỉ số phụ:** tỷ lệ giao hợp đồng sai (cùng kiểm định); kết quả chia theo họ hợp đồng, ngôn
  ngữ, loại thông tin.
- **Bảng độ nhạy thời gian:** tỷ lệ thành công khi dung sai là 1 phút, 1 giờ, 1 ngày và 3 ngày
  (Q-GIỜ 6). Bảng này chỉ để đọc kết quả, không đổi kết luận chính.
- **RQ4:** tổng và trung vị mỗi case của request, token vào, token ra, thời gian model, số tin nhắn
  người dùng, số kịch bản; request cho mỗi case thành công.
- **Người dùng mô phỏng** (báo cáo kèm):
  - số lượt;
  - số câu bị bộ kiểm tra từ chối và số câu dự phòng;
  - số lần phản đối;
  - số lượt không hợp lệ.
- **So với E6:** báo cáo song song, nhưng không gộp, vì dataset và người dùng mô phỏng đều khác.

## 5. Mã phân tích

Script tổng hợp kết quả E7 (ghép chấm máy với phán quyết, rồi tính các chỉ số ở mục 4) chưa có tại
tag. Được phép viết sau khi đóng băng, vì nó không chạm tới nhánh nào hay người dùng mô phỏng. Script
phải dùng đúng các quy tắc ở mục 3–4 và được commit trước khi mở kết quả tổng.

## 6. Được sửa sau khi đóng băng

- **Được sửa hạ tầng:** testnet, xoay key, thử lại khi lỗi mạng hoặc 5xx, đường dẫn, lỗi của bộ chạy
  không làm đổi điều một nhánh hay người dùng nhìn thấy.
- **Mọi thay đổi khác là lệch giao thức:**
  - phải ghi vào `docs/E7-Deviations.md` (lý do, case bị ảnh hưởng, cách xử lý);
  - các case đã chạy trước thay đổi thì giữ kết quả cũ, hoặc chạy lại toàn bộ cho cả hai nhánh, và
    nói rõ cách nào đã chọn.

## 7. Hạn chế đã biết

- Claude viết dataset v5, sửa pipeline, vận hành bộ chạy và phân xử. Bù lại: chấm máy là nguồn chính,
  và người phân xử chấm mù nhánh.
- Người dùng mô phỏng là Haiku. Nó đã qua bộ thử hồi quy nhỏ (`docs/E7-Dev-Trial.md`), nhưng chưa
  được kiểm trên tập lớn.
- Một model nhỏ, free tier, mỗi case một mẫu.
- Các quy tắc E7 được rút ra từ chính các lỗi của v3 và v4 (dev). v5 mới là phép thử chúng có tổng
  quát không.
