# A2: Stage 2B fact draft v5 — thiết kế

Trạng thái: **Quyết định đã chốt (mục 10) — đang spike.** Đánh giá theo
[stage2b-a2-evaluation-protocol.md](stage2b-a2-evaluation-protocol.md).

## 1. Vấn đề cần giải

Ở core v4, model phải tự dựng cùng lúc: đồ thị scope (transition, branch,
timeout, terminal outcome, `continuation_scope_id`), claim có trích dẫn nguyên
văn, số đã quy đổi sang lovelace, mốc POSIX ms, và liên kết `derived_from`.

Bằng chứng tại `cca0836`:

- Replay offline: chỉ 5/103 output draft v4 hợp lệ ở lượt đầu. Lỗi phổ biến
  nhất là cấu trúc (`SCOPE_GRAPH`, `SCHEMA`, `SOURCE_EVIDENCE`,
  `PROVENANCE_LINK`), không phải hiểu sai nghiệp vụ.
- `core_draft.py` (~1.000 dòng) và phần repair trong `shadow_extractor.py`
  chủ yếu vá lại cấu trúc model làm sai.
- Phép tính bị đẩy sang người: ở case dev 5 (milestone), câu trả lời roleplay
  phải tự ghi "mỗi chặng được đúng 17 ADA" và xác nhận mốc gốc của "bảy ngày
  sau hạn đầu", vì pipeline không suy được "một nửa" hay mốc tương đối.

## 2. Ý tưởng

Chia việc theo thế mạnh:

- **Model:** đọc hiểu. Xuất các mục nguyên tử (bên tham gia, số lượng, mốc thời
  gian, bước, kết quả), mỗi mục có trích dẫn nguyên văn, liên kết bằng ID, và
  dùng một **ngôn ngữ biểu thức đóng** cho mọi giá trị suy ra.
- **Builder tất định:** tính số, tính mốc, dựng đồ thị scope, sinh claim v4,
  gắn evidence/`derived_from`/`normalization_basis`, và quyết định resolution.

**Builder xuất core có `schema_version` v4.** Validator, projector, Stage 2C
và Stage 3 giữ nguyên. Hai nhánh BASE/A2 được chấm bằng **cùng một validator**,
nên M1 so được trực tiếp. Draft v5 được lưu thành artifact riêng để truy vết.

```text
prompt ──model──> FactDraft v5 ──validate_draft──> builder ──> ShadowSemanticCore v4
                     (đọc hiểu)      (tham chiếu, span)  (tất định)   (validator hiện có)
```

## 3. FactDraft v5 (model xuất)

Bảy trường cấp cao; mọi mục có `id` và `evidence` (danh sách span nguyên văn
trong `requirement_history`, cùng định dạng evidence v4).

| Trường | Nội dung |
| --- | --- |
| `parties` | `{id, name, evidence}`. `name` phải xuất hiện nguyên văn trong một span. |
| `asset` | `{"ada": true}` hoặc `{"native": "<policy>.<token>"}`, kèm evidence. |
| `quantities` | `{id, expr, evidence}` — số tiền, dùng ngôn ngữ biểu thức ở mục 4. |
| `instants` | `{id, expr, evidence}` — mốc thời gian, mục 4. |
| `steps` | Các bước có thứ tự: `deposit`, `choice`, `notify`, `wait_until`. |
| `outcomes` | Các khoản trả `{id, from_account, to, amount, then}`. |
| `notes` | `{clarifications: [{target_id, question}], unsupported: [{reason, evidence}], resolution_hint}` |

Bước (`steps`), tham chiếu bằng ID:

```json
{"id": "s1", "kind": "deposit", "by": "p_van", "into": "p_van",
 "amount": "q_total", "deadline": "i_d1",
 "on_timeout": "end", "then": "s2", "evidence": [...]}

{"id": "s2", "kind": "choice", "by": "p_van", "deadline": "i_d2",
 "bounds": {"from": 1, "to": 1},
 "branches": [{"guard": {"op": "eq", "value": 1}, "then": ["o_pay1", "s3"]}],
 "on_timeout": ["o_refund_all"], "evidence": [...]}
```

`then`/`on_timeout` là danh sách outcome rồi (tùy chọn) một bước kế tiếp,
hoặc `"end"`. Model **không** viết `scope_id`, `continuation_scope_id`,
`decision_id`, `claim_id` hay giá trị lovelace/ms.

## 4. Ngôn ngữ biểu thức đóng

**Nguyên tắc phạm vi (quyết định 2026-10-29):** phủ càng rộng càng tốt, nhưng
chỉ trong đại số `Value`/`Observation` của Marlowe Core V1 đã pin
(`tools/marlowe_smt/upstream/marlowe/.../Semantics/Types.hs`). Phép mới chỉ
được thêm khi nó tương ứng với một cấu tử Marlowe, không được thêm vì một case
cụ thể. Thứ gì Marlowe không diễn đạt được (oracle ngoài, tự động thực thi, sửa
ledger) → `notes.unsupported`. Quyết định nghiệp vụ như làm tròn khi chia không
hết luôn thành câu hỏi, không do builder chọn.

Đại số Marlowe chia làm hai lớp, triển khai theo hai giai đoạn:

| Lớp | Cấu tử Marlowe | Giai đoạn |
| --- | --- | --- |
| **Tĩnh** — gấp được thành số nguyên lúc trích xuất | `Constant`, `AddValue`, `SubValue`, `NegValue`, `MulValue`, `DivValue` trên hằng; mọi timeout (hằng POSIX ms) | **1** — core v4 chứa được |
| **Động** — chỉ biết khi contract chạy | `ChoiceValue`, `AvailableMoney`, `Cond`, `UseValue`/`Let`, `TimeIntervalStart`/`End`, `Observation` ngoài so sánh choice | **2** — cần kind claim "số tiền là biểu thức" (core v5) |

Ngoại lệ: `AvailableMoney` dùng làm số tiền trả ("hoàn phần còn lại") gấp
được thành hằng khi đường đi đã biết, vì builder theo dõi số dư từng tài khoản
dọc đường. Draft viết `"amount": "remaining"` ở outcome; dạng này thuộc giai
đoạn 1 (spike mục 11).

Giai đoạn 2 chỉ bắt đầu sau khi giai đoạn 1 đã so xong với BASE. Trong giai
đoạn 1, draft dùng giá trị động → `notes.unsupported` với lý do
`dynamic_value_not_in_phase_1`, được đếm riêng trong ma trận độ phủ. Builder
đưa mục này thành `unscored_observation` (`outside_stage2b_v4_claim_taxonomy`)
và `clarification_required`, vì v4 chỉ cho `unsupported_for_current_study` khi
có claim `ledger_history_deletion` (mục 11, xung đột 4).

Số lượng (`quantities.expr`) giai đoạn 1, kết quả luôn là số nguyên lovelace.
Phép chia theo đúng `DivValue` (`quot`, làm tròn về 0), nhưng builder chỉ chấp
nhận khi **chia hết**; không chia hết → `unresolved` + câu hỏi làm tròn, trừ khi
nguồn nêu rõ cách làm tròn.

| Dạng | Marlowe | Ý nghĩa | Điều kiện |
| --- | --- | --- | --- |
| `{"ada": "188"}` | `Constant` | Hằng số ADA | Chuỗi số + "ADA" xuất hiện nguyên văn trong evidence |
| `{"lovelace": "1500000"}` | `Constant` | Hằng số lovelace | Như trên, với "lovelace" |
| `{"sum": ["q_a", "q_b"]}` | `AddValue` | Tổng | — |
| `{"subtract": {"from": "q_total", "minus": ["q_fee"]}}` | `SubValue` | Phần còn lại | Kết quả ≥ 0 |
| `{"times": {"of": "q_unit", "count": 12}}` | `MulValue` | Nhân số nguyên | `count` xuất hiện trong evidence |
| `{"fraction": {"of": "q_total", "num": 1, "den": 2}}` | `MulValue` + `DivValue` | Một phần, phần trăm (`num:5, den:100`), lãi | `num/den` có trong evidence; chia hết |
| `{"unknown": true}` | — | Không có trong nguồn | Thành claim `unresolved` + câu hỏi |

`NegValue` không có dạng riêng: số tiền nạp/trả âm không hợp lệ trong Marlowe,
còn số âm trung gian chỉ xuất hiện bên trong `subtract`.

Mốc thời gian (`instants.expr`), kết quả là POSIX ms:

| Dạng | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| `{"date": {"y":2027,"m":1,"d":5,"h":0,"min":0,"tz":"+07:00"}}` | Mốc tuyệt đối | Ngày/giờ có trong span; `tz` chỉ khi nguồn nêu, nếu không thì `null` |
| `{"offset": {"from": "i_d1", "days": 7}}` | Tương đối | Cụm "N ngày sau …" có trong evidence |
| `{"unknown": true}` | Thiếu | `unresolved` + câu hỏi |

Builder không tự đoán múi giờ hay giờ trong ngày. Thiếu `tz` hoặc giờ thì
mốc là `unresolved`, giữ quy ước hiện tại. Tham chiếu vòng → lỗi draft.

## 5. Builder (tất định)

1. **Kiểm draft:** ID duy nhất, mọi tham chiếu tồn tại, mọi span có nguyên văn
   trong history, mọi literal (số ADA, số ngày, tên) nằm trong span của nó.
   Lỗi ở đây là lỗi model và được trả về cho repair theo **mục nguyên tử**.
2. **Tính giá trị:** đánh giá biểu thức bằng số nguyên chính xác; truyền
   `unknown` lên mọi biểu thức phụ thuộc.
3. **Dựng scope:** mỗi `deposit`/`choice`/`notify` → transition; mỗi `guard`
   → branch (`choice_guard`); mỗi `deadline` → timeout scope có
   `deadline_claim_id`; mỗi nhóm outcome → terminal outcome; nối
   `continuation_scope_id` theo `then`/`on_timeout`. ID scope sinh tất định từ
   ID bước.
4. **Sinh claim v4:** hằng → `explicit` (ADA quy đổi → `derived` với basis
   "1 ADA = 1000000 lovelace", như hiện nay); `fraction`/`subtract`/`offset` →
   `derived` với `derived_from` trỏ tới claim nguồn **cùng kind**, evidence
   gồm span của nguồn và span toán tử (thỏa luật span chung của v4), và
   `normalization_basis` mô tả phép tính. Người nhận/chủ tài khoản lấy evidence
   từ span đặt tên của party, nên luật "recipient phải có trong evidence" được
   thỏa nhờ tham chiếu ID thay vì chép span.
5. **Resolution:** builder quyết định, model chỉ gợi ý. `unsupported` có bằng
   chứng → `unsupported_for_current_study`; còn claim tài chính `unresolved` →
   `clarification_required` (giữ câu hỏi của model, nếu thiếu thì sinh câu
   hỏi mẫu theo ngôn ngữ prompt); ngược lại → `accepted_interpretation`.
6. **Chạy validator v4 hiện có.** Lỗi ở bước này là **lỗi builder** (bug của
   ta), không gửi cho model.

## 6. Thứ được bỏ hoặc thu nhỏ

- Phần lớn `core_draft.py`: chuẩn hóa thời gian (6 đường), retarget evidence,
  sửa choice metadata, nối outcome bị bỏ sót, gỡ branch tự động.
- Repair theo nhóm lỗi đồ thị trong `shadow_extractor.py`; repair còn lại chỉ
  ở mức mục nguyên tử (span sai, tham chiếu thiếu).
- Prompt Stage 2B: thay ~18,5 nghìn ký tự luật bằng schema v5 và 2–3 ví dụ
  **tổng hợp** (không lấy từ case dev hay test).

Code cũ giữ nguyên cho nhánh BASE cho đến khi có quyết định cuối.

## 7. Ví dụ tổng hợp (không thuộc dataset)

Prompt: "Lan thuê Tú làm hai giai đoạn, tổng 60 ADA, Lan nạp trước 00:00 ngày
02/03/2027 (UTC+7). Lan duyệt giai đoạn một trong năm ngày sau hạn nạp thì Tú
nhận một nửa; duyệt phần còn lại trong mười ngày sau hạn nạp thì nhận nốt.
Phần chưa duyệt hoàn cho Lan."

Model xuất (rút gọn): `q_total={"ada":"60"}`, `q_half={"fraction":{"of":"q_total","num":1,"den":2}}`,
`q_rest={"subtract":{"from":"q_total","minus":["q_half"]}}`,
`i_d1={"date":{...,"tz":"+07:00"}}`, `i_d2={"offset":{"from":"i_d1","days":5}}`,
`i_d3={"offset":{"from":"i_d1","days":10}}`, các bước deposit → choice(s2) →
choice(s3) và outcome trả/hoàn.

Builder tính 30.000.000 / 30.000.000 lovelace và ba mốc ms, dựng 2 transition
choice, 2 branch, 3 timeout, 4 terminal outcome, rồi đưa core v4 qua validator.
Con số nào cũng do code tính, model không phải tự làm phép tính.

## 8. Rủi ro và cách khắc phục

Cả bốn rủi ro đều có trong pipeline v4 ở dạng ẩn (lỗi validator, vòng repair,
hoặc việc bị đẩy sang người viết roleplay). A2 đưa chúng về dạng đo được và
chặn được.

### 8.1 Ngôn ngữ biểu thức không đủ

- **Nguyên nhân:** ngôn ngữ đóng chỉ diễn đạt được những phép đã liệt kê.
- **Ở v4:** nặng hơn — v4 không có phép tính; số suy ra phải bám literal, nên
  "một nửa" thất bại và người viết roleplay phải tự tính.
- **Khắc phục:** neo phạm vi vào đại số `Value` của Marlowe (mục 4), nên độ phủ
  bị chặn trên bởi chính Marlowe. Ngoài phạm vi → `notes.unsupported`, dừng
  hoặc hỏi lại. Đo ma trận độ phủ trên các họ hợp đồng bằng draft **tổng hợp**
  trước khi chạy live.

### 8.2 Model xếp sai bước hoặc sai nhánh

- **Nguyên nhân:** validator kiểm tính nhất quán bên trong, không kiểm độ
  trung thành với văn bản.
- **Ở v4:** y hệt; vòng repair còn đẩy model về phía "sửa cho qua validator".
- **Khắc phục (ba lớp):**
  1. *Bất biến tất định* builder kiểm mà không cần đáp án: bảo toàn tiền trên
     mọi đường (tổng chi ≤ tổng nạp, phần dư có đích); mốc thời gian không
     giảm dọc đường đi; mọi bên và mọi số tiền xuất hiện trong văn bản đều
     được dùng; mọi nhánh có kết cục. Vi phạm → hỏi lại, không chấp nhận.
  2. *Kiểm chéo bằng kịch bản:* cùng lượt gọi, model trả lời vài câu hỏi cụ
     thể ("không ai duyệt trước hạn 2 thì ai nhận bao nhiêu?"); builder chạy
     draft trên đúng kịch bản đó. Không khớp → hỏi lại. Đây cũng là nền của B3.
  3. *Diễn đạt ngược* intent thành văn bản theo mẫu tất định cho Stage 2C, để
     người duyệt đọc câu thay vì JSON.

### 8.3 Bug builder thành lỗi hệ thống

- **Nguyên nhân:** code tất định sai cùng một kiểu ở mọi case.
- **Ở v4:** cũng có (~1.000 dòng normalizer, projector, gợi ý vá trong
  `cli_runner`), nhưng là luật vá rời rạc nên khó kiểm thử có hệ thống.
- **Khắc phục:**
  1. *Hai cài đặt độc lập:* builder dựng, validator v4 (viết riêng, trước đó)
     kiểm; bug phải trùng ở cả hai mới lọt.
  2. *Property test:* draft hợp lệ sinh ngẫu nhiên → builder → luôn qua
     validator và luôn thỏa bất biến 8.2; khứ hồi core → draft → core không đổi.
  3. *Differential test:* contract hạ cấp từ intent và kịch bản sinh trực
     tiếp từ draft chạy qua Marlowe reference đã pin phải khớp.
  4. *Builder là hàm thuần, toàn phần, không heuristic:* mỗi loại bước đúng một
     luật dựng, nên về nguyên tắc đặc tả và chứng minh hình thức được.

### 8.4 Không tương thích với luật v4

- **Nguyên nhân:** luật v4 được viết để chống model tự soạn core bịa dữ kiện;
  với core do builder soạn, có luật thành vô nghĩa và có thể ép builder làm
  đẹp evidence.
- **Ở v4:** chính các luật này gây nhiều lỗi hiện nay (prompt nói "người làm
  nhận" thay vì tên người nhận).
- **Khắc phục:** phân mỗi luật v4 thành *chống bịa* hoặc *cấu trúc*. Luật chống
  bịa chuyển xuống kiểm ở mức draft v5 (literal nằm trong span, tên gắn span
  đặt tên, đồng tham chiếu qua ID). Luật cấu trúc giữ trên core. Nếu draft thỏa
  chống bịa và builder trung thành (8.3) thì core thỏa chống bịa do cách xây
  dựng. Giai đoạn đầu vẫn chạy đủ validator v4 để M1 so được với BASE; xung
  đột được ghi nhận, không vá bằng evidence giả.

## 9. Kế hoạch triển khai

1. **Spike:** viết builder tối thiểu cho deposit + choice + outcome, dựng tay
   ví dụ tổng hợp ở mục 7, chứng minh validator v4 chấp nhận output. Đồng thời
   phân loại các luật v4 thành chống bịa/cấu trúc (8.4) và ghi lại xung đột.
2. Module mới: `research/stage2b/fact_draft.py` (schema + kiểm draft, gồm luật
   chống bịa), `fact_expressions.py` (đánh giá biểu thức), `fact_builder.py`
   (dựng core), `fact_invariants.py` (bất biến 8.2), `fact_prompt.py`.
   `IntentShadowExtractor` nhận `core_schema_version="stage2b-fact-draft-v5"`
   để chọn đường mới.
3. Test:
   - đơn vị cho từng biểu thức, luật kiểm draft và từng bất biến;
   - property test: draft hợp lệ ngẫu nhiên → core qua validator v4 và thỏa
     mọi bất biến; khứ hồi core → draft → core;
   - ma trận độ phủ họ hợp đồng bằng draft viết tay cho mẫu **tổng hợp**.
4. Kiểm chéo bằng kịch bản (8.2 lớp 2) và diễn đạt ngược cho Stage 2C (8.2 lớp
   3). Kiểm chéo bằng kịch bản tốn thêm token đầu ra nhưng không thêm request.
5. `stage2b_eval --arm A2` trên cùng case dev, chấm bằng `stage2b_score`.
6. Differential test với Marlowe reference (8.3 mục 3) gộp vào B3.

## 10. Quyết định (chốt 2026-10-29)

1. **Builder xuất core v4.** Validator, projector, Stage 2C và Stage 3 giữ
   nguyên; BASE và A2 chấm bằng cùng validator nên M1 so trực tiếp được.
   Validator v5 riêng chỉ xét lại khi giai đoạn 2 của mục 4 cần kind claim mới.
2. **Resolution do builder quyết định** từ trạng thái dữ kiện (mục 5 bước 5).
   Model chỉ soạn câu hỏi, gợi ý `resolution_hint`, và báo mâu thuẫn hoặc
   ngoài phạm vi kèm trích dẫn để builder kiểm.
3. **Không suy múi giờ/giờ trong ngày** khi nguồn không nêu; mốc đó
   `unresolved`.
4. **Phủ tối đa trong đại số Marlowe, chia hai giai đoạn** (mục 4): giai đoạn 1
   toàn bộ lớp tĩnh trên core v4; giai đoạn 2 lớp động sau khi so xong BASE.
5. **Repair tối đa 3 lần, chỉ ở mức mục nguyên tử**, cùng ngân sách BASE.

## 11. Kết quả spike (2026-10-29)

Code: `research/stage2b/fact_builder.py`, test
`research/stage2b/test_fact_builder.py` (6 test, 0 request model).

Draft tổng hợp ở mục 7, viết tay theo schema v5, đi qua builder rồi qua
validator v4, projector và `validate_intent_spec` **không sửa gì**: kết quả
`PASS`, `accepted_interpretation`. Builder tự tính 60/30/30 ADA, hai khoản hoàn
60 và 30 ADA (số dư còn lại theo từng đường), mốc nạp và hai mốc "+5/+10
ngày". Các test còn kiểm:

- thiếu `tz` → mốc `unresolved`, lan sang mọi mốc dịch từ nó, builder hỏi lại;
- chia không hết (`den: 7`) → câu hỏi làm tròn, không tự áp `quot`;
- literal không có trong span, hoặc span bịa → `DraftError` chỉ đúng ID mục
  (`q_total`, `p_tu`), dùng làm đầu vào repair mức nguyên tử;
- trả vượt số dư (`o_pay2` trả 60 khi tài khoản còn 30) → lỗi bảo toàn tiền.

Phạm vi spike: bước `deposit` và `choice`; chỉ ADA; mỗi bước và outcome chỉ
được tới bằng một đường (cây). Chưa có `notify`, mốc trả sớm nhất, token
native, conflict, `notes.unsupported`, câu hỏi theo ngôn ngữ prompt.

### Phân loại luật v4 (8.4)

| Loại | Luật trong `validate_shadow_semantic_core` | Ở A2 |
| --- | --- | --- |
| Chống bịa | span nguyên văn; claim explicit/derived cần evidence `supports`; người nhận explicit có tên trong span; mốc khớp ngày được trích; `derived_from` cùng kind và chung span; `user_confirmed` phải từ version > 1; `requirement_history` đúng nguồn; tín hiệu unsupported có evidence; `choice_bounds`/`choice_guard` có `source_evidence` | Kiểm ở draft (span, literal, tên gắn party) **và** vẫn chạy lại ở core |
| Cấu trúc | loại/trường scope; ID duy nhất; `decision_id`, `continuation_scope_id`, `parent_scope_id`; một gốc; terminal có cạnh vào; deposit có amount; payout có người nhận cùng scope; `deadline_claim_id` trỏ claim mốc; kind đúng scope; số nguyên; `unresolved` thì `null`; derived tài chính có `normalization_basis` | Builder thỏa theo cách dựng; vi phạm = bug builder |
| Nhất quán resolution | accepted không có claim tài chính không an toàn hay câu hỏi; clarification cần claim `unresolved` hoặc observation; conflict cần hai giá trị cùng scope; unsupported cần tín hiệu | Builder suy ra resolution từ claim nên thỏa theo cách dựng |

### Xung đột đã gặp

1. **Mốc dịch không được trích mốc gốc.** Nếu claim "+5 ngày" trích cả span
   "02/03/2027", luật khớp ngày báo mâu thuẫn (test
   `test_v4_conflict_offset_deadline_cannot_cite_its_base_date`). Builder chỉ
   trích cụm "trong năm ngày sau hạn nạp"; quan hệ với mốc gốc nằm trong
   `normalization_basis` và draft.
2. **`derived_from` không dùng được cho số tính ra.** Nguồn phải là
   explicit/user_confirmed, mà số ADA đã là `derived` (quy đổi lovelace). Builder
   bỏ `derived_from` (v4 cho phép) và gộp evidence của cả cây biểu thức. Truy vết
   đầy đủ nằm ở draft, không ở core.
3. **Luật người nhận cần tên trong span.** Với "thì nhận nốt", builder thêm span
   đặt tên party. Span đó có thật nhưng không nói về khoản trả: đây là đúng loại
   "làm đẹp evidence" mà 8.4 cảnh báo. Ghi nhận, chưa đổi luật.
4. **Unsupported chỉ qua `ledger_history_deletion`.** Giá trị động ở giai đoạn
   1 không thể ra `unsupported_for_current_study`; builder dùng observation +
   clarification (mục 4 đã sửa).
5. **Draft v5 chưa diễn đạt được mâu thuẫn.** v4 cần hai claim `conflicted`
   cùng kind/scope. Cần thêm `alternatives` cho quantity/instant/party trước
   khi chạy live, vì tập dev có case `ambiguous`.

Bước tiếp theo trong mục 9: mở rộng builder (notify, conflict, unsupported,
token native, DAG), viết `fact_prompt.py`, rồi property test và ma trận độ phủ.
