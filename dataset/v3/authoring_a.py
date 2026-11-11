"""Dataset v3 cases, part A: the ten families carried over from v2 (written by hand, 2026-11-10).

Each case: prompt as a real user would type it to the system, a structured spec the builders
turn into the reference contract, a fact sheet that answers what the prompt leaves out, and the
known weakness it targets (docs/E6-Dataset-Design.md, section 5).
"""

VN = "+07:00"


def C(**kw):
    return kw


CASES = [
    # ------------------------------------------------------------------ escrow (2 parties)
    C(id="v3-vi-escrow-001", language="vi", family="escrow", info_mode="complete",
      expected_behavior="converge",
      phenomena=["first_person", "time_of_day", "timezone", "absolute_time"],
      prompt=("Tạo giúp tôi hợp đồng ký quỹ mua laptop cũ. Tôi là Minh, người mua, sẽ nạp 45 ADA trước "
              "23:59 ngày 20/03/2027 giờ VN. Người bán là Thảo. Nhận hàng xong tôi bấm xác nhận thì tiền "
              "chuyển cho Thảo. Nếu tôi báo hàng lỗi, hoặc đến 23:59 ngày 25/03/2027 mà tôi chưa xác nhận, "
              "thì hoàn tiền về cho tôi."),
      spec={"roles": {"payer": "Minh", "payee": "Thảo", "decider": "Minh"}, "amount": 45,
            "deposit_by": "2027-03-20T23:59" + VN, "decide_by": "2027-03-25T23:59" + VN, "on_timeout": "payer",
            "options": [{"name": "xac_nhan", "values": [[1, 1]], "to": "payee"},
                        {"name": "bao_loi", "values": [[1, 1]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["first_person_party", "race_in_one_when"],
      author_note="'tôi' phải thành role Minh; xác nhận và báo lỗi là hai nhánh cạnh tranh."),
    C(id="v3-en-escrow-002", language="en", family="escrow", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "terse"],
      prompt=("I'm selling a camera to Jake for 120 ADA. He deposits, confirms once he has it, and the money "
              "comes to me. If he doesn't confirm in time, refund him."),
      spec={"roles": {"payer": "Jake", "payee": "Priya", "decider": "Jake"}, "amount": 120,
            "deposit_by": "2027-04-10T18:00+00:00", "decide_by": "2027-04-17T18:00+00:00", "on_timeout": "payer",
            "options": [{"name": "confirm", "values": [[1, 1]], "to": "payee"}]},
      fact_sheet=[{"topic": "seller name / my name", "answer": "I'm Priya."},
                  {"topic": "deposit deadline", "answer": "Jake deposits by 2027-04-10 18:00 UTC."},
                  {"topic": "confirmation deadline", "answer": "He confirms by 2027-04-17 18:00 UTC."},
                  {"topic": "reject option", "answer": "No separate reject; no confirmation means refund."}],
      adversarial_target=["first_person_party", "missing_deadlines"],
      author_note="Người dùng là người bán nhưng không nêu tên; hệ thống phải hỏi tên và cả hai hạn."),
    C(id="v3-vi-escrow-003", language="vi", family="escrow", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "first_person", "relative_time"],
      prompt=("tao hop dong giu tien: toi (Hai) mua dien thoai cua Quang gia 80 ADA, toi nap truoc 15/5/2027. "
              "neu toi hai long thi chuyen cho Quang, khong thi tra lai toi. han xac nhan 1 tuan"),
      spec={"roles": {"payer": "Hai", "payee": "Quang", "decider": "Hai"}, "amount": 80,
            "deposit_by": "2027-05-15T23:59" + VN, "decide_by": "2027-05-22T23:59" + VN, "on_timeout": "payer",
            "options": [{"name": "danh_gia", "values": [[1, 1]], "to": "payee"},
                        {"name": "danh_gia", "values": [[0, 0]], "to": "payer"}]},
      fact_sheet=[{"topic": "giờ và múi giờ", "answer": "23:59 giờ VN (UTC+7)."},
                  {"topic": "1 tuần tính từ đâu", "answer": "7 ngày tính từ hạn nạp, tức 23:59 ngày 22/05/2027."},
                  {"topic": "không hài lòng", "answer": "Tôi chọn 0 thì hoàn tiền ngay; chọn 1 là hài lòng."}],
      adversarial_target=["relative_from_unclear_anchor", "no_diacritics_names"],
      author_note="'1 tuần' không rõ mốc; viết không dấu; tên role giữ đúng như người dùng gõ (Hai, Quang)."),
    C(id="v3-en-escrow-004", language="en", family="escrow", info_mode="complete",
      expected_behavior="converge", phenomena=["token_policy", "time_of_day", "timeout_to_payee"],
      prompt=("Escrow for a design job. Client Nora pays 300 USDM (policy "
              "c48cbb3d5e57ed56e276bc45f99ab39abe94e6cd7ac39fb402da47ad, token name USDM) by 2027-06-01 "
              "09:00 UTC. Designer Leo gets paid when Nora approves. Nora can also reject, which refunds her. "
              "If Nora does nothing by 2027-06-15 09:00 UTC, release the money to Leo."),
      spec={"roles": {"payer": "Nora", "payee": "Leo", "decider": "Nora"}, "amount": 300, "token": "USDM",
            "tokens": {"USDM": {"policy": "c48cbb3d5e57ed56e276bc45f99ab39abe94e6cd7ac39fb402da47ad", "name": "USDM"}},
            "deposit_by": "2027-06-01T09:00+00:00", "decide_by": "2027-06-15T09:00+00:00", "on_timeout": "payee",
            "options": [{"name": "approve", "values": [[1, 1]], "to": "payee"},
                        {"name": "reject", "values": [[1, 1]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["timeout_goes_to_payee", "token_identity"],
      author_note="Hết hạn thì trả cho người bán, ngược với mặc định thường gặp; token không phải ADA."),
    C(id="v3-vi-escrow-005", language="vi", family="escrow", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", phenomena=["first_person", "unsupported_extra", "name_with_space"],
      prompt=("Mình là Lan Anh, cần hợp đồng giữ tiền khi mua bàn ghế của Bảo: mình nạp 65 ADA trước 22:00 "
              "ngày 12/04/2027 (giờ VN), xác nhận đã nhận hàng trước 22:00 ngày 19/04/2027 thì chuyển cho Bảo, "
              "không xác nhận thì hoàn mình. Nhớ gửi email báo cho mình khi tiền đã chuyển nhé."),
      spec={"roles": {"payer": "Lan Anh", "payee": "Bảo", "decider": "Lan Anh"}, "amount": 65,
            "deposit_by": "2027-04-12T22:00" + VN, "decide_by": "2027-04-19T22:00" + VN, "on_timeout": "payer",
            "options": [{"name": "da_nhan_hang", "values": [[1, 1]], "to": "payee"}]},
      fact_sheet=[], adversarial_target=["unsupported_extra_silently_dropped"],
      author_note="Email không làm được; hệ thống phải nói rõ thay vì im lặng bỏ qua."),

    # ------------------------------------------------------------------ escrow with arbiter
    C(id="v3-vi-escrow_arbiter-001", language="vi", family="escrow_arbiter", info_mode="complete",
      expected_behavior="converge", phenomena=["full_name_role", "time_of_day", "timezone"],
      prompt=("Mình cần hợp đồng có trọng tài: bên mua Trần Vy nạp 150 ADA trước 12:00 ngày 02/04/2027 (UTC+7). "
              "Nếu có tranh chấp, trọng tài Đức chọn 1 để trả cho bên bán Khoa, chọn 2 để hoàn cho Trần Vy, hạn "
              "chọn 12:00 ngày 09/04/2027. Trọng tài không chọn thì hoàn cho Trần Vy."),
      spec={"roles": {"payer": "Trần Vy", "payee": "Khoa", "decider": "Đức"}, "amount": 150,
            "deposit_by": "2027-04-02T12:00" + VN, "decide_by": "2027-04-09T12:00" + VN, "on_timeout": "payer",
            "options": [{"name": "phan_quyet", "values": [[1, 1]], "to": "payee"},
                        {"name": "phan_quyet", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["narrator_not_party", "diacritic_names"],
      author_note="Người viết không phải một bên; tên có dấu và có khoảng trắng."),
    C(id="v3-en-escrow_arbiter-002", language="en", family="escrow_arbiter", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "timezone_non_vn"],
      prompt=("I'm buying a used car from Marcus for 900 ADA. We agreed Sofia, a mechanic, decides whether the "
              "money is released to Marcus or refunded to me. I'll deposit by March 30, 2027."),
      spec={"roles": {"payer": "Ethan", "payee": "Marcus", "decider": "Sofia"}, "amount": 900,
            "deposit_by": "2027-03-30T20:00-05:00", "decide_by": "2027-04-06T20:00-05:00", "on_timeout": "payer",
            "options": [{"name": "verdict", "values": [[1, 1]], "to": "payee"},
                        {"name": "verdict", "values": [[0, 0]], "to": "payer"}]},
      fact_sheet=[{"topic": "my name", "answer": "Ethan."},
                  {"topic": "deposit time / timezone", "answer": "8:00 PM on March 30, 2027, US Eastern (UTC-5)."},
                  {"topic": "decision deadline", "answer": "Sofia decides by 8:00 PM UTC-5 on April 6, 2027."},
                  {"topic": "no decision", "answer": "Refund me."},
                  {"topic": "how Sofia decides", "answer": "1 = release to Marcus, 0 = refund me."}],
      adversarial_target=["missing_deadlines", "non_vn_timezone"],
      author_note="Múi giờ UTC-5; thiếu hạn quyết định và kết cục khi hết hạn."),
    C(id="v3-vi-escrow_arbiter-003", language="vi", family="escrow_arbiter", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", phenomena=["self_correction", "time_of_day"],
      prompt=("Ký quỹ 3 bên: Phương nạp 60 ADA trước 18:00 ngày 10/06/2027 giờ Hà Nội, trọng tài là Sơn, người "
              "bán là Hùng. Sơn quyết định trước 18:00 ngày 17/06/2027: chọn 1 trả Hùng, chọn 2 hoàn Phương. Quá "
              "hạn thì trả cho Hùng. À nhầm, quá hạn thì hoàn cho Phương mới đúng."),
      spec={"roles": {"payer": "Phương", "payee": "Hùng", "decider": "Sơn"}, "amount": 60,
            "deposit_by": "2027-06-10T18:00" + VN, "decide_by": "2027-06-17T18:00" + VN, "on_timeout": "payer",
            "options": [{"name": "quyet_dinh", "values": [[1, 1]], "to": "payee"},
                        {"name": "quyet_dinh", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[{"topic": "quá hạn", "answer": "Hoàn cho Phương (câu đính chính là đúng)."}],
      adversarial_target=["late_correction"],
      author_note="Đính chính ở cuối tin nhắn đảo kết cục khi hết hạn."),
    C(id="v3-en-escrow_arbiter-004", language="en", family="escrow_arbiter", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["relative_time", "terse"],
      prompt=("Escrow with arbiter. Buyer Grace, seller Omar, arbiter Ivy, 75 ADA. Grace deposits within 3 days "
              "of 2027-07-01; Ivy decides within a week after that."),
      spec={"roles": {"payer": "Grace", "payee": "Omar", "decider": "Ivy"}, "amount": 75,
            "deposit_by": "2027-07-04T00:00+00:00", "decide_by": "2027-07-11T00:00+00:00", "on_timeout": "payer",
            "options": [{"name": "ruling", "values": [[1, 1]], "to": "payee"},
                        {"name": "ruling", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[{"topic": "deposit deadline", "answer": "Before 2027-07-04 00:00 UTC."},
                  {"topic": "decision deadline", "answer": "Before 2027-07-11 00:00 UTC (7 days after the deposit deadline)."},
                  {"topic": "ruling encoding", "answer": "1 = pay Omar, 2 = refund Grace."},
                  {"topic": "no ruling", "answer": "Refund Grace."}],
      adversarial_target=["relative_from_unclear_anchor", "second_deadline"],
      author_note="Hai mốc tương đối nối nhau; dễ dời hạn thứ hai."),

    # ------------------------------------------------------------------ swap
    C(id="v3-en-swap-001", language="en", family="swap", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "token_policy", "time_of_day"],
      prompt=("Swap: I (Hana) give 250 ADA, Kenji gives 40 HOSKY (policy "
              "a0028f350aaabe0545fdcb56b039bfb08e4bb4d8c4d7c3c7d481c235, name HOSKY). I deposit first by "
              "2027-08-01 12:00 UTC, Kenji then has until 2027-08-03 12:00 UTC. If he doesn't, I get my ADA back."),
      spec={"roles": {"first": "Hana", "second": "Kenji"},
            "tokens": {"HOSKY": {"policy": "a0028f350aaabe0545fdcb56b039bfb08e4bb4d8c4d7c3c7d481c235", "name": "HOSKY"}},
            "token_a": "ADA", "amount_a": 250, "token_b": "HOSKY", "amount_b": 40,
            "first_by": "2027-08-01T12:00+00:00", "second_by": "2027-08-03T12:00+00:00"},
      fact_sheet=[], adversarial_target=["token_identity", "first_person_party"], author_note="Token có policy thật."),
    C(id="v3-vi-swap-002", language="vi", family="swap", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "token_policy", "hex_token_name", "timezone"],
      prompt=("Đổi token: tôi (Quỳnh) nạp 20 ADA, đổi lấy 500 token của Phát. Token có policy "
              "4be0cdbd1b1f1a1d0c6ef1e5bd3c0a19f0a8a2b0e7d2c3b4a5968778, tên dạng hex 4d454f57 (tức là 'MEOW'). "
              "Tôi nạp trước 21:00 ngày 05/08/2027, Phát nạp trước 21:00 ngày 07/08/2027 (giờ VN). Phát không nạp "
              "thì trả lại ADA cho tôi."),
      spec={"roles": {"first": "Quỳnh", "second": "Phát"},
            "tokens": {"MEOW": {"policy": "4be0cdbd1b1f1a1d0c6ef1e5bd3c0a19f0a8a2b0e7d2c3b4a5968778", "name": "MEOW"}},
            "token_a": "ADA", "amount_a": 20, "token_b": "MEOW", "amount_b": 500,
            "first_by": "2027-08-05T21:00" + VN, "second_by": "2027-08-07T21:00" + VN},
      fact_sheet=[], adversarial_target=["hex_token_name", "diacritic_names"],
      author_note="Tên token đưa dạng hex; hợp đồng phải dùng tên 'MEOW' (token_name là văn bản)."),
    C(id="v3-vi-swap-003", language="vi", family="swap", info_mode="missing", expected_behavior="ask_then_converge",
      phenomena=["first_person", "terse"],
      prompt="Mình muốn đổi 100 ADA lấy token GOLD của bạn Toàn.",
      spec={"roles": {"first": "Ngân", "second": "Toàn"},
            "tokens": {"GOLD": {"policy": "2222222222222222222222222222222222222222222222222222222a", "name": "GOLD"}},
            "token_a": "ADA", "amount_a": 100, "token_b": "GOLD", "amount_b": 30,
            "first_by": "2027-09-01T23:59" + VN, "second_by": "2027-09-03T23:59" + VN},
      fact_sheet=[{"topic": "tên mình", "answer": "Mình là Ngân."},
                  {"topic": "số GOLD", "answer": "30 GOLD."},
                  {"topic": "định danh token", "answer": "Policy 2222222222222222222222222222222222222222222222222222222a, tên GOLD."},
                  {"topic": "ai nạp trước", "answer": "Mình nạp trước."},
                  {"topic": "hạn", "answer": "Mình nạp trước 23:59 01/09/2027, Toàn nạp trước 23:59 03/09/2027, giờ VN."},
                  {"topic": "Toàn không nạp", "answer": "Trả lại ADA cho mình."}],
      adversarial_target=["missing_most_facts"], author_note="Gần như thiếu hết; một câu duy nhất."),
    C(id="v3-en-swap-004", language="en", family="swap", info_mode="complete", expected_behavior="converge",
      phenomena=["vi_en_mix", "token_policy", "timezone"],
      prompt=("Cần swap 2 tokens: Bảo nạp 1000 SNEK (policy 279c909f348e533da5808898f87f9a14bb2c3dfbbacccd631d927a3f, "
              "name SNEK) trước 2027-10-10 10:00 UTC+7, then Mai gửi 75 ADA by 2027-10-12 10:00 UTC+7. "
              "Mai không nạp thì refund SNEK cho Bảo."),
      spec={"roles": {"first": "Bảo", "second": "Mai"},
            "tokens": {"SNEK": {"policy": "279c909f348e533da5808898f87f9a14bb2c3dfbbacccd631d927a3f", "name": "SNEK"}},
            "token_a": "SNEK", "amount_a": 1000, "token_b": "ADA", "amount_b": 75,
            "first_by": "2027-10-10T10:00" + VN, "second_by": "2027-10-12T10:00" + VN},
      fact_sheet=[], adversarial_target=["token_first_ada_second", "vi_en_mix"],
      author_note="Bên nạp trước nạp token, ADA ở bước hai; trộn Việt–Anh."),

    # ------------------------------------------------------------------ loan
    C(id="v3-vi-loan-001", language="vi", family="loan", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Tôi (Hoàng) cho Duyên vay 500 ADA. Tôi nạp trước 23:59 ngày 01/03/2027 (giờ VN), nạp xong chuyển "
              "ngay cho Duyên. Duyên trả 525 ADA trước 23:59 ngày 01/06/2027. Không trả thì thôi, hợp đồng đóng."),
      spec={"roles": {"lender": "Hoàng", "borrower": "Duyên"}, "principal": 500, "repay": 525,
            "fund_by": "2027-03-01T23:59" + VN, "repay_by": "2027-06-01T23:59" + VN},
      fact_sheet=[], adversarial_target=["no_fake_refund"], author_note="Không được bịa khoản hoàn khi vỡ nợ."),
    C(id="v3-en-loan-002", language="en", family="loan", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "percentage", "thousands_separator"],
      prompt=("I need a loan contract. Lender: me, Arjun. Borrower: Wei. Principal 1,200 ADA at 5% flat interest, "
              "repaid in one go by 2027-12-31 23:59 UTC. I'll fund by 2027-07-01 00:00 UTC."),
      spec={"roles": {"lender": "Arjun", "borrower": "Wei"}, "principal": 1200, "repay": 1260,
            "fund_by": "2027-07-01T00:00+00:00", "repay_by": "2027-12-31T23:59+00:00"},
      fact_sheet=[], adversarial_target=["percentage_arithmetic"], author_note="Phải tự tính 1 260 ADA."),
    C(id="v3-vi-loan-003", language="vi", family="loan", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", phenomena=["conflict_numbers"],
      prompt=("Hợp đồng vay: Khánh cho Linh vay 300 ADA trước 10/04/2027, Linh trả 310 ADA trước 10/05/2027. "
              "Tiền Khánh nạp vào thì chuyển luôn cho Linh. Linh nhớ là tổng phải trả là 320 ADA nhé."),
      spec={"roles": {"lender": "Khánh", "borrower": "Linh"}, "principal": 300, "repay": 320,
            "fund_by": "2027-04-10T23:59" + VN, "repay_by": "2027-05-10T23:59" + VN},
      fact_sheet=[{"topic": "số tiền trả", "answer": "320 ADA là đúng."},
                  {"topic": "giờ", "answer": "23:59 giờ VN cả hai mốc."}],
      adversarial_target=["conflict_ignored"], author_note="310 và 320 cùng tồn tại; phải hỏi lại."),
    C(id="v3-en-loan-004", language="en", family="loan", info_mode="complete", expected_behavior="converge",
      phenomena=["numbers_in_words", "decimal"],
      prompt=("Loan: Ruth lends Sam two hundred fifty ADA, Sam repays two hundred sixty-two point five ADA. "
              "Ruth funds by 2027-05-05 12:00 UTC (paid straight to Sam), Sam repays by 2027-08-05 12:00 UTC."),
      spec={"roles": {"lender": "Ruth", "borrower": "Sam"}, "principal": 250, "repay": "262.5",
            "fund_by": "2027-05-05T12:00+00:00", "repay_by": "2027-08-05T12:00+00:00"},
      fact_sheet=[], adversarial_target=["numbers_in_words", "decimal_amount"], author_note="Số viết bằng chữ, có số lẻ."),
    C(id="v3-vi-loan-005", language="vi", family="loan", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", phenomena=["first_person", "unsupported_extra"],
      prompt=("Tôi là Thùy, cho anh Lộc vay 400 ADA: tôi nạp trước 20:00 ngày 05/02/2027 (giờ VN), chuyển ngay "
              "cho Lộc; Lộc trả 420 ADA trước 20:00 ngày 05/05/2027. Nếu trễ thì tự động tính thêm 1% mỗi ngày."),
      spec={"roles": {"lender": "Thùy", "borrower": "Lộc"}, "principal": 400, "repay": 420,
            "fund_by": "2027-02-05T20:00" + VN, "repay_by": "2027-05-05T20:00" + VN},
      fact_sheet=[{"topic": "nếu không làm được phạt theo ngày", "answer": "Vậy bỏ phần phạt, giữ phần còn lại."}],
      adversarial_target=["unsupported_extra_silently_dropped"],
      author_note="Phạt theo ngày không giới hạn: phải nói rõ là không làm được."),

    # ------------------------------------------------------------------ vesting
    C(id="v3-vi-vesting-001", language="vi", family="vesting", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "time_of_day", "irregular_intervals"],
      prompt=("Công ty tôi (role: MocAn) cấp thưởng 90 ADA cho nhân viên Thu: tôi nạp trước 23:59 ngày 31/01/2027 "
              "giờ VN, rồi hợp đồng trả 30 ADA vào mỗi mốc 09:00 sáng các ngày 28/02, 31/03 và 30/04/2027 (giờ VN), "
              "không cần ai bấm duyệt."),
      spec={"roles": {"funder": "MocAn", "worker": "Thu"}, "deposit_by": "2027-01-31T23:59" + VN,
            "parts": [{"at": "2027-02-28T09:00" + VN, "amount": 30}, {"at": "2027-03-31T09:00" + VN, "amount": 30},
                      {"at": "2027-04-30T09:00" + VN, "amount": 30}]},
      fact_sheet=[], adversarial_target=["notify_early_release", "second_deadline"],
      author_note="Ba mốc cách nhau không đều; không được chặn bằng Notify."),
    C(id="v3-en-vesting-002", language="en", family="vesting", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "cancel_race"],
      prompt=("Vesting for contractor Paolo: 410 ADA from me (Elena), four equal quarterly releases on 2027-04-01, "
              "2027-07-01, 2027-10-01 and 2028-01-01 at 08:00 UTC. I can cancel before any release and get the "
              "unreleased part back. I fund by 2027-03-15."),
      spec={"roles": {"funder": "Elena", "worker": "Paolo"}, "deposit_by": "2027-03-15T08:00+00:00",
            "parts": [{"at": "2027-04-01T08:00+00:00", "amount": "102.5"}, {"at": "2027-07-01T08:00+00:00", "amount": "102.5"},
                      {"at": "2027-10-01T08:00+00:00", "amount": "102.5"}, {"at": "2028-01-01T08:00+00:00", "amount": "102.5"}],
            "cancel": {"name": "cancel", "owner": "funder"}},
      fact_sheet=[{"topic": "funding time", "answer": "By 08:00 UTC on 2027-03-15."}],
      adversarial_target=["cancel_refund_rest", "second_deadline"],
      author_note="Hủy giữa chừng phải hoàn đúng phần chưa trả."),
    C(id="v3-vi-vesting-003", language="vi", family="vesting", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "first_person", "relative_time"],
      prompt=("hop dong tra luong theo dot: toi gui 60 ADA cho ban Nhan, chia 2 dot bang nhau, dot 1 sau 1 thang, "
              "dot 2 sau 2 thang ke tu luc toi nap"),
      spec={"roles": {"funder": "Khoa", "worker": "Nhan"}, "deposit_by": "2027-06-01T23:59" + VN,
            "parts": [{"at": "2027-07-01T23:59" + VN, "amount": 30}, {"at": "2027-08-01T23:59" + VN, "amount": 30}]},
      fact_sheet=[{"topic": "tên tôi", "answer": "Khoa."},
                  {"topic": "hạn nạp", "answer": "23:59 ngày 01/06/2027 giờ VN."},
                  {"topic": "tính từ lúc nạp", "answer": "Tính từ hạn nạp: đợt 1 lúc 23:59 01/07, đợt 2 lúc 23:59 01/08/2027."}],
      adversarial_target=["relative_to_event_time"],
      author_note="'kể từ lúc tôi nạp' không biểu diễn được trực tiếp; hệ thống phải hỏi để chốt mốc tuyệt đối."),
    C(id="v3-en-vesting-004", language="en", family="vesting", info_mode="complete", expected_behavior="converge",
      phenomena=["long_document", "noise", "thousands_separator", "cancel_race"],
      prompt=("Token grant policy, excerpt for the contract team:\n"
              "4.1 Grantee: Amara (role: Amara). Funder: Treasury (role: Treasury).\n"
              "4.2 Treasury funds 1,500 ADA no later than 2027-02-01 00:00 UTC.\n"
              "4.3 Nothing vests before the cliff. 500 ADA vests on 2027-08-01, 500 ADA on 2028-02-01 and 500 ADA "
              "on 2028-08-01, each at 00:00 UTC.\n"
              "4.4 Treasury may revoke at any time before a vesting date; unvested amounts return to Treasury.\n"
              "5. (Not for the contract) Amara's manager reviews performance quarterly and HR keeps the paperwork.\n"
              "6. Grants are confidential."),
      spec={"roles": {"funder": "Treasury", "worker": "Amara"}, "deposit_by": "2027-02-01T00:00+00:00",
            "parts": [{"at": "2027-08-01T00:00+00:00", "amount": 500}, {"at": "2028-02-01T00:00+00:00", "amount": 500},
                      {"at": "2028-08-01T00:00+00:00", "amount": 500}],
            "cancel": {"name": "revoke", "owner": "funder"}},
      fact_sheet=[], adversarial_target=["noise_in_spec", "cancel_refund_rest"],
      author_note="Tài liệu dài có mục không liên quan (mục 5, 6 không đưa vào hợp đồng)."),
    C(id="v3-vi-vesting-005", language="vi", family="vesting", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", phenomena=["first_person", "unsupported_extra"],
      prompt=("Mình (Gia Bảo) nạp 50 ADA trước 23:59 ngày 10/03/2027 giờ VN để trả cho em Kha 2 đợt 25 ADA vào "
              "00:00 ngày 10/04 và 10/05/2027. Hợp đồng phải tự chạy, không cần ai gửi giao dịch gì cả."),
      spec={"roles": {"funder": "Gia Bảo", "worker": "Kha"}, "deposit_by": "2027-03-10T23:59" + VN,
            "parts": [{"at": "2027-04-10T00:00" + VN, "amount": 25}, {"at": "2027-05-10T00:00" + VN, "amount": 25}]},
      fact_sheet=[{"topic": "nếu vẫn cần giao dịch", "answer": "Được, cứ để ai đó gửi giao dịch sau mốc là được."}],
      adversarial_target=["autonomous_execution_claim"],
      author_note="Marlowe cần có giao dịch để chạy tiếp; phải nói rõ, không hứa tự chạy."),

    # ------------------------------------------------------------------ milestone
    C(id="v3-vi-milestone-001", language="vi", family="milestone", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "uneven_amounts", "time_of_day"],
      prompt=("Thuê dev làm app 2 giai đoạn: tôi (Quang Huy) nạp 200 ADA trước 08:00 ngày 05/03/2027 (UTC+7). "
              "Duyệt giai đoạn 1 trước 08:00 ngày 05/04/2027 thì trả dev Nhật 80 ADA; duyệt giai đoạn 2 trước 08:00 "
              "ngày 05/05/2027 thì trả nốt 120 ADA. Giai đoạn 1 không được duyệt đúng hạn thì hoàn hết cho tôi; "
              "giai đoạn 2 không được duyệt thì hoàn 120 ADA cho tôi."),
      spec={"roles": {"client": "Quang Huy", "worker": "Nhật"}, "deposit_by": "2027-03-05T08:00" + VN,
            "stages": [{"name": "duyet_gd1", "by": "2027-04-05T08:00" + VN, "amount": 80},
                       {"name": "duyet_gd2", "by": "2027-05-05T08:00" + VN, "amount": 120}]},
      fact_sheet=[], adversarial_target=["uneven_split", "refund_rest"], author_note="Hai giai đoạn không bằng nhau."),
    C(id="v3-en-milestone-002", language="en", family="milestone", info_mode="complete", expected_behavior="converge",
      phenomena=["independent_parts", "time_of_day"],
      prompt=("Two deliverables, each paid on its own. Client Bea deposits 600 ADA by 2027-05-01 17:00 UTC. "
              "Deliverable A (250 ADA to Chidi) is approved by Bea by 2027-05-20 17:00 UTC; deliverable B (350 ADA "
              "to Chidi) by 2027-06-10 17:00 UTC. If A isn't approved in time, A's money goes back to Bea but B can "
              "still be approved. Same for B."),
      spec={"roles": {"client": "Bea", "worker": "Chidi"}, "deposit_by": "2027-05-01T17:00+00:00", "independent": True,
            "stages": [{"name": "approve_a", "by": "2027-05-20T17:00+00:00", "amount": 250},
                       {"name": "approve_b", "by": "2027-06-10T17:00+00:00", "amount": 350}]},
      fact_sheet=[], adversarial_target=["independent_halves"], author_note="Chặng 2 vẫn duyệt được khi chặng 1 trễ."),
    C(id="v3-vi-milestone-003", language="vi", family="milestone", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "terse", "three_stages"],
      prompt="Mình thuê thợ sửa nhà 3 đợt, tổng 90 ADA, mỗi đợt bằng nhau, nghiệm thu đợt nào trả đợt đó.",
      spec={"roles": {"client": "Bích", "worker": "Tâm"}, "deposit_by": "2027-07-01T23:59" + VN,
            "stages": [{"name": "dot_1", "by": "2027-07-15T23:59" + VN, "amount": 30},
                       {"name": "dot_2", "by": "2027-07-31T23:59" + VN, "amount": 30},
                       {"name": "dot_3", "by": "2027-08-15T23:59" + VN, "amount": 30}]},
      fact_sheet=[{"topic": "tên", "answer": "Mình là Bích, thợ là Tâm."},
                  {"topic": "hạn nạp", "answer": "23:59 ngày 01/07/2027 giờ VN."},
                  {"topic": "hạn nghiệm thu", "answer": "23:59 các ngày 15/07, 31/07 và 15/08/2027, giờ VN."},
                  {"topic": "đợt không được nghiệm thu", "answer": "Dừng và hoàn phần còn lại cho mình."}],
      adversarial_target=["missing_most_facts", "third_deadline"], author_note="Ba hạn, thiếu hết dữ kiện."),
    C(id="v3-en-milestone-004", language="en", family="milestone", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["first_person", "percentage", "relative_time", "timezone_non_vn"],
      prompt=("Milestone contract with freelancer Tomás; I'm Ingrid. 1000 ADA total: 40% on design approval, the "
              "rest on final approval. Design approval within 2 weeks, final within a month."),
      spec={"roles": {"client": "Ingrid", "worker": "Tomás"}, "deposit_by": "2027-09-01T12:00+02:00",
            "stages": [{"name": "design", "by": "2027-09-15T12:00+02:00", "amount": 400},
                       {"name": "final", "by": "2027-10-01T12:00+02:00", "amount": 600}]},
      fact_sheet=[{"topic": "deposit", "answer": "I deposit by noon on 2027-09-01, Berlin time (UTC+2)."},
                  {"topic": "from when", "answer": "Both counted from the deposit deadline: design by 2027-09-15 12:00, final by 2027-10-01 12:00 (UTC+2)."},
                  {"topic": "missed approval", "answer": "Refund what's left to me and stop."}],
      adversarial_target=["relative_from_unclear_anchor", "percentage_arithmetic"],
      author_note="'within a month' mơ hồ; phải tự tính 40% và 60%."),

    # ------------------------------------------------------------------ crowdfunding
    C(id="v3-vi-crowdfunding-001", language="vi", family="crowdfunding", info_mode="complete",
      expected_behavior="converge", phenomena=["three_contributors", "notify_release", "time_of_day"],
      prompt=("Gom quỹ mua máy in 3D cho CLB: Ngọc góp 40 ADA trước 20:00 ngày 01/02/2027, rồi Tú góp 40 ADA trước "
              "20:00 ngày 03/02/2027, rồi Vũ góp 20 ADA trước 20:00 ngày 05/02/2027 (giờ VN). Đủ cả ba thì bất kỳ "
              "ai cũng bấm 'giải ngân' được, trước 20:00 ngày 10/02/2027, tiền chuyển cho thủ quỹ Lâm. Không ai bấm "
              "hoặc thiếu người góp thì hoàn tiền ai nấy."),
      spec={"roles": {"a": "Ngọc", "b": "Tú", "c": "Vũ", "beneficiary": "Lâm"},
            "contributions": [{"role": "a", "amount": 40, "by": "2027-02-01T20:00" + VN},
                              {"role": "b", "amount": 40, "by": "2027-02-03T20:00" + VN},
                              {"role": "c", "amount": 20, "by": "2027-02-05T20:00" + VN}],
            "release_by": "2027-02-10T20:00" + VN},
      fact_sheet=[], adversarial_target=["notify_correct_use", "refund_via_close"],
      author_note="Notify dùng đúng chỗ (ai cũng bấm được); không ai bấm thì hoàn."),
    C(id="v3-en-crowdfunding-002", language="en", family="crowdfunding", info_mode="complete",
      expected_behavior="converge", phenomena=["four_contributors", "bullet_list"],
      prompt=("Group gift contract:\n- Anna, Ben, Chloe, Dev each put in 25 ADA, in that order\n- deadlines 18:00 "
              "UTC on 2027-03-01, 03-02, 03-03 and 03-04 respectively\n- once all four are in, send the 100 ADA to "
              "Ezra right away\n- if someone misses their deadline, everyone who already paid gets refunded"),
      spec={"roles": {"a": "Anna", "b": "Ben", "c": "Chloe", "d": "Dev", "beneficiary": "Ezra"},
            "contributions": [{"role": "a", "amount": 25, "by": "2027-03-01T18:00+00:00"},
                              {"role": "b", "amount": 25, "by": "2027-03-02T18:00+00:00"},
                              {"role": "c", "amount": 25, "by": "2027-03-03T18:00+00:00"},
                              {"role": "d", "amount": 25, "by": "2027-03-04T18:00+00:00"}]},
      fact_sheet=[], adversarial_target=["many_parties", "fourth_deadline"], author_note="5 bên, 4 hạn."),
    C(id="v3-vi-crowdfunding-003", language="vi", family="crowdfunding", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "terse"],
      prompt=("Mình góp vốn chung với Hằng để thuê gian hàng hội chợ, mỗi người một nửa, tổng 160 ADA, đủ thì trả "
              "cho ban tổ chức."),
      spec={"roles": {"a": "Oanh", "b": "Hằng", "beneficiary": "BTC"},
            "contributions": [{"role": "a", "amount": 80, "by": "2027-04-01T23:59" + VN},
                              {"role": "b", "amount": 80, "by": "2027-04-03T23:59" + VN}]},
      fact_sheet=[{"topic": "tên mình", "answer": "Oanh."}, {"topic": "ai góp trước", "answer": "Mình góp trước."},
                  {"topic": "hạn", "answer": "Mình trước 23:59 01/04/2027, Hằng trước 23:59 03/04/2027, giờ VN."},
                  {"topic": "ban tổ chức", "answer": "Role là BTC."},
                  {"topic": "thiếu người góp", "answer": "Hoàn lại cho người đã góp."}],
      adversarial_target=["first_person_party", "missing_most_facts"], author_note="Phải hỏi tên, thứ tự, hạn, người nhận."),
    C(id="v3-en-crowdfunding-004", language="en", family="crowdfunding", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["notify_release", "timezone_missing"],
      prompt=("Fund a hackathon prize: Ming puts in 300 ADA by Nov 1, then Zara 200 ADA by Nov 8. Once both are in, "
              "anyone can trigger the payout to the winner (role: Winner) until the end of November; if nobody "
              "triggers it, refund both."),
      spec={"roles": {"a": "Ming", "b": "Zara", "beneficiary": "Winner"},
            "contributions": [{"role": "a", "amount": 300, "by": "2027-11-01T23:59+00:00"},
                              {"role": "b", "amount": 200, "by": "2027-11-08T23:59+00:00"}],
            "release_by": "2027-11-30T23:59+00:00"},
      fact_sheet=[{"topic": "year / time / timezone", "answer": "2027, 23:59 UTC for every deadline."},
                  {"topic": "end of November", "answer": "2027-11-30 23:59 UTC."}],
      adversarial_target=["notify_correct_use", "ambiguous_month_end"], author_note="Không nêu năm, giờ, múi giờ."),

    # ------------------------------------------------------------------ third party reports a number
    C(id="v3-vi-third_party-001", language="vi", family="third_party", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "threshold", "time_of_day"],
      prompt=("Mua lô cà phê: tôi (Đạt) nạp 120 ADA trước 12:00 ngày 01/03/2027 giờ VN. Chị Ngân bên kiểm định "
              "chấm chất lượng từ 0 đến 100 trước 12:00 ngày 08/03/2027; từ 70 điểm trở lên thì tiền chuyển cho bên "
              "bán Hữu, dưới 70 thì hoàn cho tôi. Không chấm thì cũng hoàn tôi."),
      spec={"roles": {"payer": "Đạt", "payee": "Hữu", "reporter": "Ngân"}, "amount": 120,
            "deposit_by": "2027-03-01T12:00" + VN, "report_by": "2027-03-08T12:00" + VN,
            "low": 0, "high": 100, "threshold": 70, "choice": "diem_chat_luong"},
      fact_sheet=[], adversarial_target=["threshold_boundary"], author_note="Ranh giới 70 là 'trở lên'."),
    C(id="v3-en-third_party-002", language="en", family="third_party", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "threshold", "small_range"],
      prompt=("Pay the contractor only if the inspector's score is at least 8 out of 10.\n- me: Owen, I deposit 452.5 "
              "ADA by 2027-04-04 15:00 UTC\n- inspector: Lucia, scores 0–10 by 2027-04-11 15:00 UTC\n- contractor: Kofi\n"
              "- otherwise I get the money back"),
      spec={"roles": {"payer": "Owen", "payee": "Kofi", "reporter": "Lucia"}, "amount": "452.5",
            "deposit_by": "2027-04-04T15:00+00:00", "report_by": "2027-04-11T15:00+00:00",
            "low": 0, "high": 10, "threshold": 8, "choice": "score"},
      fact_sheet=[], adversarial_target=["threshold_boundary"], author_note="Thang điểm 0–10."),
    C(id="v3-vi-third_party-003", language="vi", family="third_party", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["threshold", "ambiguous_comparison"],
      prompt=("Cuộc thi thiết kế logo: ban tổ chức (role: BTC) nạp 200 ADA trước 18:00 ngày 15/05/2027 giờ VN. Giám "
              "khảo Thịnh cho điểm 0–100 trước 18:00 ngày 22/05/2027, điểm trên 50 thì trả cho thí sinh Vân, không thì "
              "hoàn BTC. Không có điểm thì hoàn BTC."),
      spec={"roles": {"payer": "BTC", "payee": "Vân", "reporter": "Thịnh"}, "amount": 200,
            "deposit_by": "2027-05-15T18:00" + VN, "report_by": "2027-05-22T18:00" + VN,
            "low": 0, "high": 100, "threshold": 51, "choice": "diem"},
      fact_sheet=[{"topic": "trên 50", "answer": "Trên 50 nghĩa là từ 51 trở lên; đúng 50 thì không đạt."}],
      adversarial_target=["threshold_boundary", "ambiguous_comparison"], author_note="'trên 50' phải hỏi rõ."),
    C(id="v3-en-third_party-004", language="en", family="third_party", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["vi_en_mix", "small_range"],
      prompt="Need hợp đồng: Pham deposits 80 ADA, reviewer Kim cho rating 1–5, rating ≥ 4 thì pay cho designer Lee, else refund.",
      spec={"roles": {"payer": "Pham", "payee": "Lee", "reporter": "Kim"}, "amount": 80,
            "deposit_by": "2027-06-20T23:59" + VN, "report_by": "2027-06-27T23:59" + VN,
            "low": 1, "high": 5, "threshold": 4, "choice": "rating"},
      fact_sheet=[{"topic": "deadlines", "answer": "Pham deposits by 23:59 2027-06-20, Kim rates by 23:59 2027-06-27, Vietnam time."},
                  {"topic": "no rating", "answer": "Refund Pham."}],
      adversarial_target=["missing_deadlines", "vi_en_mix"], author_note="Thiếu hạn; thang 1–5."),

    # ------------------------------------------------------------------ rental deposit
    C(id="v3-vi-rental_deposit-001", language="vi", family="rental_deposit", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "three_options", "long_horizon"],
      prompt=("Đặt cọc thuê nhà: tôi (Thanh) nạp cọc 200 ADA trước 23:59 ngày 31/03/2027 giờ VN. Chủ nhà Kiên kiểm tra "
              "khi trả nhà, trước 23:59 ngày 30/09/2027: chọn 0 nếu không hư hại (hoàn đủ cho tôi), chọn 1 nếu hư hại "
              "nhẹ (Kiên giữ 50 ADA, phần còn lại hoàn tôi), chọn 2 nếu hư hại nặng (Kiên giữ hết). Kiên không chọn thì "
              "hoàn đủ cho tôi."),
      spec={"roles": {"payer": "Thanh", "keeper": "Kiên", "chooser": "Kiên"}, "amount": 200,
            "deposit_by": "2027-03-31T23:59" + VN, "decide_by": "2027-09-30T23:59" + VN, "choice": "tinh_trang",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": 50},
                        {"value": 2, "keeper_share": 200}], "on_timeout": 0},
      fact_sheet=[], adversarial_target=["refund_via_close", "three_way_choice"], author_note="Ba mức, có giữ một phần."),
    C(id="v3-en-rental_deposit-002", language="en", family="rental_deposit", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "percentage", "thousands_separator"],
      prompt=("Security deposit: I'm Maya, the tenant, and I deposit 1,050 ADA by 2027-06-01 00:00 UTC. Landlord "
              "Victor reports by 2027-12-01 00:00 UTC: 0 = no damage, full refund; 1 = damage, he keeps 15% and I "
              "get the rest. No report means full refund."),
      spec={"roles": {"payer": "Maya", "keeper": "Victor", "chooser": "Victor"}, "amount": 1050,
            "deposit_by": "2027-06-01T00:00+00:00", "decide_by": "2027-12-01T00:00+00:00", "choice": "report",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": "157.5"}], "on_timeout": 0},
      fact_sheet=[], adversarial_target=["percentage_arithmetic", "refund_via_close"], author_note="15% của 1 050 = 157,5."),
    C(id="v3-vi-rental_deposit-003", language="vi", family="rental_deposit", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "terse"],
      prompt="coc thue phong 30 ADA, chu nha giu 5 ADA neu co hu hai, khong thi tra lai",
      spec={"roles": {"payer": "Nhi", "keeper": "Cuong", "chooser": "Cuong"}, "amount": 30,
            "deposit_by": "2027-08-01T23:59" + VN, "decide_by": "2027-12-31T23:59" + VN, "choice": "hu_hai",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": 5}], "on_timeout": 0},
      fact_sheet=[{"topic": "ai thuê, ai là chủ nhà", "answer": "Mình là Nhi (người thuê), chủ nhà là Cuong."},
                  {"topic": "hạn", "answer": "Mình nạp trước 23:59 01/08/2027; Cuong báo trước 23:59 31/12/2027, giờ VN."},
                  {"topic": "ai báo hư hại", "answer": "Cuong chọn: 0 không hư hại, 1 có hư hại."},
                  {"topic": "không báo", "answer": "Trả lại đủ cho mình."}],
      adversarial_target=["missing_most_facts", "no_diacritics_names"], author_note="Không dấu, thiếu hết."),
    C(id="v3-en-rental_deposit-004", language="en", family="rental_deposit", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["ambiguous_pronoun", "timezone_non_vn"],
      prompt=("Our team is renting a booth. We deposit 120 ADA; the organizer keeps 20 ADA if we leave a mess, "
              "otherwise we get it all back. Deposit by 2027-05-10 09:00 UTC+8, inspection result by 2027-05-13 "
              "09:00 UTC+8."),
      spec={"roles": {"payer": "BoothTeam", "keeper": "Organizer", "chooser": "Organizer"}, "amount": 120,
            "deposit_by": "2027-05-10T09:00+08:00", "decide_by": "2027-05-13T09:00+08:00", "choice": "inspection",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": 20}], "on_timeout": 0},
      fact_sheet=[{"topic": "who is 'we'", "answer": "Use one role BoothTeam for our team; the organizer's role is Organizer."},
                  {"topic": "who reports", "answer": "Organizer: 0 = clean, 1 = mess."},
                  {"topic": "no result", "answer": "Full refund to BoothTeam."}],
      adversarial_target=["ambiguous_pronoun", "narrator_group"], author_note="'we' là một nhóm, phải hỏi role."),

    # ------------------------------------------------------------------ cancellation fee
    C(id="v3-vi-cancellation_fee-001", language="vi", family="cancellation_fee", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "timeout_to_keeper"],
      prompt=("Đặt tour: tôi (Mỹ Duyên) trả trước 300 ADA trước 10:00 ngày 01/06/2027 (giờ VN). Trước 10:00 ngày "
              "15/06/2027 tôi chọn: 1 = hủy (công ty tour VietGo giữ phí 30 ADA, hoàn tôi 270 ADA), 0 = đi (VietGo "
              "nhận đủ 300 ADA). Tôi không chọn gì thì coi như đi."),
      spec={"roles": {"payer": "Mỹ Duyên", "keeper": "VietGo", "chooser": "Mỹ Duyên"}, "amount": 300,
            "deposit_by": "2027-06-01T10:00" + VN, "decide_by": "2027-06-15T10:00" + VN, "choice": "huy_hay_di",
            "options": [{"value": 0, "keeper_share": 300}, {"value": 1, "keeper_share": 30}], "on_timeout": 300},
      fact_sheet=[], adversarial_target=["timeout_goes_to_keeper"], author_note="Hết hạn thì trả cho công ty, không hoàn."),
    C(id="v3-en-cancellation_fee-002", language="en", family="cancellation_fee", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "percentage"],
      prompt=("Ticket resale with a 10% cancellation fee: I'm Hugo, the buyer; I deposit 85 ADA by 2027-07-07 "
              "19:00 UTC. Until 2027-07-20 19:00 UTC I can cancel (10% to the seller Iris, the rest back to me) or "
              "confirm (everything to Iris). If I do nothing, treat it as confirmed."),
      spec={"roles": {"payer": "Hugo", "keeper": "Iris", "chooser": "Hugo"}, "amount": 85,
            "deposit_by": "2027-07-07T19:00+00:00", "decide_by": "2027-07-20T19:00+00:00", "choice": "decision",
            "options": [{"value": 0, "keeper_share": 85}, {"value": 1, "keeper_share": "8.5"}], "on_timeout": 85},
      fact_sheet=[{"topic": "how to encode", "answer": "1 = cancel, 0 = confirm."}],
      adversarial_target=["percentage_arithmetic", "timeout_goes_to_keeper"], author_note="10% của 85 = 8,5."),
    C(id="v3-vi-cancellation_fee-003", language="vi", family="cancellation_fee", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", phenomena=["first_person", "conflict_numbers", "percentage"],
      prompt=("Đặt phòng khách sạn: tôi nạp 150 ADA, nếu hủy thì mất phí 10%, không hủy thì khách sạn nhận đủ. "
              "Nói rõ hơn là hủy thì khách sạn giữ 20 ADA."),
      spec={"roles": {"payer": "Bảo Ngọc", "keeper": "SeaHotel", "chooser": "Bảo Ngọc"}, "amount": 150,
            "deposit_by": "2027-08-01T12:00" + VN, "decide_by": "2027-08-10T12:00" + VN, "choice": "huy",
            "options": [{"value": 0, "keeper_share": 150}, {"value": 1, "keeper_share": 20}], "on_timeout": 150},
      fact_sheet=[{"topic": "phí hủy", "answer": "20 ADA là đúng."}, {"topic": "tên", "answer": "Tôi là Bảo Ngọc; khách sạn role SeaHotel."},
                  {"topic": "hạn", "answer": "Nạp trước 12:00 01/08/2027, quyết định trước 12:00 10/08/2027, giờ VN."},
                  {"topic": "mã hóa", "answer": "1 = hủy, 0 = không hủy; không chọn gì thì coi như không hủy."}],
      adversarial_target=["conflict_ignored"], author_note="10% (15 ADA) mâu thuẫn với 20 ADA."),
    C(id="v3-en-cancellation_fee-004", language="en", family="cancellation_fee", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "terse"],
      prompt="Booking a photographer for my wedding, 600 ADA. If I cancel, she keeps 100 ADA.",
      spec={"roles": {"payer": "Alicia", "keeper": "Rosa", "chooser": "Alicia"}, "amount": 600,
            "deposit_by": "2027-09-01T12:00+00:00", "decide_by": "2027-10-01T12:00+00:00", "choice": "cancel",
            "options": [{"value": 0, "keeper_share": 600}, {"value": 1, "keeper_share": 100}], "on_timeout": 600},
      fact_sheet=[{"topic": "names", "answer": "I'm Alicia; the photographer is Rosa."},
                  {"topic": "deadlines", "answer": "I pay by 2027-09-01 12:00 UTC; I can cancel until 2027-10-01 12:00 UTC."},
                  {"topic": "no decision", "answer": "Rosa gets all 600 ADA."},
                  {"topic": "encoding", "answer": "1 = cancel, 0 = go ahead."}],
      adversarial_target=["missing_most_facts", "timeout_goes_to_keeper"], author_note="Thiếu hết, kết cục hết hạn trái trực giác."),
]
