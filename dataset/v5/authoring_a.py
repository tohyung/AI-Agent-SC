"""Dataset v5 cases, part A (written by hand, 2026-11-12, docs/archive/E7-Dataset-v5-Design.md).

escrow, escrow_arbiter, swap, loan, vesting and the first two milestone cases.
`register` is the writing style (V-3): chat, bullets, terse or document.
`derived` lists values the case states only through arithmetic the prompt spells out (C-3).
"""

import hashlib

VN = "+07:00"
UTC = "+00:00"


def P(name: str) -> str:
    """A 56-hex policy id for a made-up token (not a real policy)."""
    return hashlib.sha224(("v5-policy-" + name).encode()).hexdigest()


def C(**kw):
    return kw


CASES = [
    # ------------------------------------------------------------------ escrow
    C(id="v5-vi-escrow-001", language="vi", family="escrow", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Mình mua lại cây guitar của anh Thắng giá 85 ADA. Mình (Nhung) nạp trước 21:00 ngày "
              "14/02/2027 giờ VN. Nhận đàn xong mình bấm 'đã nhận' thì tiền về anh Thắng; còn nếu đàn "
              "bị nứt mình bấm 'trả hàng' thì tiền về lại mình. Quá 21:00 ngày 18/02/2027 mà mình chưa "
              "bấm gì thì cứ chuyển cho anh Thắng."),
      spec={"roles": {"payer": "Nhung", "payee": "Thắng", "decider": "Nhung"}, "amount": 85,
            "deposit_by": "2027-02-14T21:00" + VN, "decide_by": "2027-02-18T21:00" + VN,
            "on_timeout": "payee",
            "options": [{"name": "da_nhan", "values": [[1, 1]], "to": "payee"},
                        {"name": "tra_hang", "values": [[1, 1]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["timeout_to_payee", "first_person_with_name"],
      author_note="Hết hạn thì trả người bán, ngược với thói quen hoàn người mua."),
    C(id="v5-en-escrow-002", language="en", family="escrow", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["first_person", "terse", "typo"],
      prompt=("escrow pls: Bianca pays me 60 ADA for the bike, she confirms when she picks it up and the "
              "money comes to me. no confirm = she gets refuneded"),
      spec={"roles": {"payer": "Bianca", "payee": "Caleb", "decider": "Bianca"}, "amount": 60,
            "deposit_by": "2027-03-06T17:00" + UTC, "decide_by": "2027-03-09T17:00" + UTC,
            "on_timeout": "payer",
            "options": [{"name": "confirm", "values": [[1, 1]], "to": "payee"}]},
      fact_sheet=[{"topic": "my name", "answer": "Caleb."},
                  {"topic": "deadlines", "answer": "Bianca deposits by 2027-03-06 17:00 UTC and confirms by "
                                                   "2027-03-09 17:00 UTC."}],
      adversarial_target=["first_person_party", "missing_deadlines"],
      author_note="Người dùng là người bán, không nêu tên và hạn."),
    C(id="v5-vi-escrow-003", language="vi", family="escrow", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["no_diacritics", "first_person", "relative_time"],
      prompt=("lam hop dong giu tien giup minh: minh la Khue, mua may anh cua Vinh 140 ADA, nap truoc ngay "
              "3/4/2027. nhan may thay on thi minh chon 1 chuyen cho Vinh, chon 0 la tra lai minh. han xac "
              "nhan la 5 ngay sau khi nap"),
      spec={"roles": {"payer": "Khue", "payee": "Vinh", "decider": "Khue"}, "amount": 140,
            "deposit_by": "2027-04-03T23:59" + VN, "decide_by": "2027-04-08T23:59" + VN,
            "on_timeout": "payer",
            "options": [{"name": "danh_gia", "values": [[1, 1]], "to": "payee"},
                        {"name": "danh_gia", "values": [[0, 0]], "to": "payer"}]},
      fact_sheet=[{"topic": "giờ và múi giờ", "answer": "23:59 giờ VN."},
                  {"topic": "5 ngày tính từ đâu", "answer": "Từ hạn nạp, tức 23:59 ngày 08/04/2027."},
                  {"topic": "không chọn gì", "answer": "Trả lại cho mình."}],
      adversarial_target=["relative_from_unclear_anchor", "no_diacritics_names"],
      author_note="'5 ngày sau khi nạp' không rõ mốc; tên giữ như người dùng gõ (Khue, Vinh)."),
    C(id="v5-en-escrow-004", language="en", family="escrow", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "token_policy", "time_of_day", "timezone", "timeout_to_payee"],
      prompt=("Escrow for a logo commission:\n"
              f"- Client Delia deposits 450 DJED (policy {P('DJED')}, token name DJED) by 2027-05-03 09:00 UTC\n"
              "- Designer Gideon gets the 450 DJED when Delia approves\n"
              "- Delia may reject instead, which refunds her\n"
              "- If Delia does nothing by 2027-05-17 09:00 UTC, Gideon is paid anyway"),
      spec={"roles": {"payer": "Delia", "payee": "Gideon", "decider": "Delia"},
            "tokens": {"DJED": {"policy": P("DJED"), "name": "DJED"}}, "token": "DJED", "amount": 450,
            "deposit_by": "2027-05-03T09:00" + UTC, "decide_by": "2027-05-17T09:00" + UTC,
            "on_timeout": "payee",
            "options": [{"name": "approve", "values": [[1, 1]], "to": "payee"},
                        {"name": "reject", "values": [[1, 1]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["native_token", "timeout_to_payee"],
      author_note="Ký quỹ bằng token, hết hạn trả người làm."),
    C(id="v5-vi-escrow-005", language="vi", family="escrow", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Tôi là Trâm, mua bộ bàn ghế của Luân 230 ADA. Tôi nạp trước 18:00 ngày 22/05/2027 giờ VN, "
              "nhận hàng xong tôi xác nhận thì tiền chuyển cho Luân, hạn xác nhận 18:00 ngày 29/05/2027, "
              "quá hạn thì hoàn tôi. Nhờ hợp đồng gửi tin nhắn Messenger cho Luân khi tôi đã nạp tiền nhé."),
      spec={"roles": {"payer": "Trâm", "payee": "Luân", "decider": "Trâm"}, "amount": 230,
            "deposit_by": "2027-05-22T18:00" + VN, "decide_by": "2027-05-29T18:00" + VN,
            "on_timeout": "payer",
            "options": [{"name": "xac_nhan", "values": [[1, 1]], "to": "payee"}]},
      fact_sheet=[{"topic": "nếu không gửi tin nhắn được",
                   "answer": "Không sao, có thể bỏ phần nhắn tin, phần còn lại giữ nguyên."}],
      adversarial_target=["unsupported_side_effect"],
      author_note="Nhắn tin ra ngoài chuỗi không làm được; phần ký quỹ thì làm được."),

    # ------------------------------------------------------------------ escrow with arbiter
    C(id="v5-vi-escrow_arbiter-001", language="vi", family="escrow_arbiter", info_mode="complete",
      expected_behavior="converge", register="document",
      phenomena=["long_document", "bullet_list", "time_of_day", "timezone"],
      prompt=("Theo biên bản ngày 02/06 giữa hai bên:\n"
              "1. Bên mua là Diệp, đặt 320 ADA vào hợp đồng trước 10:00 ngày 10/06/2027 (UTC+7).\n"
              "2. Bên bán là Tấn, giao 50 bao gạo trong tuần.\n"
              "3. Nếu hai bên không thống nhất, anh Hậu làm trọng tài: chọn 1 thì tiền giao cho Tấn, chọn 2 "
              "thì tiền trả lại Diệp. Hạn cho trọng tài là 10:00 ngày 20/06/2027.\n"
              "4. Trọng tài không chọn thì trả lại Diệp.\n"
              "5. Chi phí vận chuyển hai bên tự chia, không đưa vào hợp đồng."),
      spec={"roles": {"payer": "Diệp", "payee": "Tấn", "decider": "Hậu"}, "amount": 320,
            "deposit_by": "2027-06-10T10:00" + VN, "decide_by": "2027-06-20T10:00" + VN,
            "on_timeout": "payer",
            "options": [{"name": "phan_xu", "values": [[1, 1]], "to": "payee"},
                        {"name": "phan_xu", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["noise_in_document", "third_party_decider"],
      author_note="Mục 2 và 5 là nhiễu; ngày 02/06 không phải hạn."),
    C(id="v5-en-escrow_arbiter-002", language="en", family="escrow_arbiter", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["missing_deadlines"],
      prompt=("We need an arbiter escrow. Buyer is Farah, seller is Emeka, 75 ADA. If they disagree, Imani "
              "decides who gets it. If Imani never decides, the money goes back to Farah."),
      spec={"roles": {"payer": "Farah", "payee": "Emeka", "decider": "Imani"}, "amount": 75,
            "deposit_by": "2027-07-01T12:00" + UTC, "decide_by": "2027-07-15T12:00" + UTC,
            "on_timeout": "payer",
            "options": [{"name": "ruling", "values": [[1, 1]], "to": "payee"},
                        {"name": "ruling", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[{"topic": "deadlines", "answer": "Farah deposits by 2027-07-01 12:00 UTC; Imani has until "
                                                   "2027-07-15 12:00 UTC."},
                  {"topic": "how Imani decides", "answer": "Imani picks 1 to pay Emeka or 2 to refund Farah."}],
      adversarial_target=["writer_not_a_party", "missing_deadlines"],
      author_note="'We' là người soạn, không phải một bên."),
    C(id="v5-vi-escrow_arbiter-003", language="vi", family="escrow_arbiter", info_mode="conflict",
      expected_behavior="converge", register="chat",
      phenomena=["self_correction", "time_of_day", "timezone"],
      prompt=("Ký quỹ có trọng tài: Thục mua lô hoa lan của Khiêm, 410 ADA, Thục nạp trước 12:00 ngày "
              "03/08/2027 (giờ VN). Trọng tài là chị Thy: chọn 1 trả cho Khiêm, chọn 2 hoàn cho Thục, hạn "
              "12:00 ngày 13/08/2027. Thy không quyết thì trả Khiêm luôn. Mà khoan, không quyết thì hoàn cho "
              "Thục mới đúng."),
      spec={"roles": {"payer": "Thục", "payee": "Khiêm", "decider": "Thy"}, "amount": 410,
            "deposit_by": "2027-08-03T12:00" + VN, "decide_by": "2027-08-13T12:00" + VN,
            "on_timeout": "payer",
            "options": [{"name": "quyet_dinh", "values": [[1, 1]], "to": "payee"},
                        {"name": "quyet_dinh", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[{"topic": "nếu trọng tài không quyết", "answer": "Hoàn cho Thục."}],
      adversarial_target=["self_correction_timeout_branch"],
      author_note="Người dùng tự sửa nhánh hết hạn trong cùng tin nhắn; câu sau là đúng."),
    C(id="v5-en-escrow_arbiter-004", language="en", family="escrow_arbiter", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["time_of_day", "timezone", "grouped_number", "timeout_to_payee"],
      prompt=("Arbitrated escrow for 1,250 ADA: Oskar (buyer) deposits by Sept 1, 2027 08:00 UTC; the seller "
              "is Petra. Rafael arbitrates until Sept 8, 2027 08:00 UTC: option 1 releases to Petra, option 2 "
              "refunds Oskar. If Rafael stays silent, release to Petra."),
      spec={"roles": {"payer": "Oskar", "payee": "Petra", "decider": "Rafael"}, "amount": 1250,
            "deposit_by": "2027-09-01T08:00" + UTC, "decide_by": "2027-09-08T08:00" + UTC,
            "on_timeout": "payee",
            "options": [{"name": "ruling", "values": [[1, 1]], "to": "payee"},
                        {"name": "ruling", "values": [[2, 2]], "to": "payer"}]},
      fact_sheet=[], adversarial_target=["grouped_number", "timeout_to_payee"],
      author_note="1,250 có dấu phẩy nhóm; hết hạn trả người bán."),

    # ------------------------------------------------------------------ swap
    C(id="v5-en-swap-001", language="en", family="swap", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "token_policy", "time_of_day", "timezone", "grouped_number"],
      prompt=(f"Token swap: Selin sends 3,000 SNEK (policy {P('SNEK')}, name SNEK) and I (Theo) send 95 ADA. "
              "Selin goes first, by 2027-03-20 15:00 UTC; I then deposit by 2027-03-21 15:00 UTC. If I don't, "
              "Selin gets her SNEK back."),
      spec={"roles": {"first": "Selin", "second": "Theo"},
            "tokens": {"SNEK": {"policy": P("SNEK"), "name": "SNEK"}},
            "token_a": "SNEK", "amount_a": 3000, "token_b": "ADA", "amount_b": 95,
            "first_by": "2027-03-20T15:00" + UTC, "second_by": "2027-03-21T15:00" + UTC},
      fact_sheet=[], adversarial_target=["token_first", "first_person_second_mover"],
      author_note="Token đi trước, người dùng là bên thứ hai."),
    C(id="v5-vi-swap-002", language="vi", family="swap", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["first_person", "terse"],
      prompt="đổi token với Bửu: tôi đưa 120 ADA, Bửu đưa lại 800 token MIN. tôi nạp trước.",
      spec={"roles": {"first": "Mẫn", "second": "Bửu"},
            "tokens": {"MIN": {"policy": P("MIN"), "name": "MIN"}},
            "token_a": "ADA", "amount_a": 120, "token_b": "MIN", "amount_b": 800,
            "first_by": "2027-04-05T20:00" + VN, "second_by": "2027-04-06T20:00" + VN},
      fact_sheet=[{"topic": "tên tôi", "answer": "Mẫn."},
                  {"topic": "token MIN", "answer": f"Policy {P('MIN')}, tên token MIN."},
                  {"topic": "hạn", "answer": "Tôi nạp trước 20:00 ngày 05/04/2027, Bửu nạp trước 20:00 ngày "
                                             "06/04/2027, giờ VN."},
                  {"topic": "Bửu không nạp", "answer": "Trả lại ADA cho tôi."}],
      adversarial_target=["missing_policy", "missing_deadlines", "first_person_party"],
      author_note="Thiếu tên người dùng, policy và hai hạn."),
    C(id="v5-vi-swap-003", language="vi", family="swap", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "vi_en_mix", "time_of_day", "timezone", "token_policy", "grouped_number"],
      prompt=("Swap giúp mình: mình (Tiến) deposit 2.500 ADA trước 9h sáng 12/05/2027 giờ VN, sau đó Lộ "
              f"deposit 40 token GOLDX (policy {P('GOLDX')}, name GOLDX) trước 9h sáng 13/05/2027. Lộ không "
              "deposit thì refund ADA cho mình."),
      spec={"roles": {"first": "Tiến", "second": "Lộ"},
            "tokens": {"GOLDX": {"policy": P("GOLDX"), "name": "GOLDX"}},
            "token_a": "ADA", "amount_a": 2500, "token_b": "GOLDX", "amount_b": 40,
            "first_by": "2027-05-12T09:00" + VN, "second_by": "2027-05-13T09:00" + VN},
      fact_sheet=[], adversarial_target=["vietnamese_thousands_dot", "clock_9h_sang"],
      author_note="'2.500 ADA' là hai nghìn rưỡi theo cách viết Việt."),
    C(id="v5-en-swap-004", language="en", family="swap", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["first_person", "terse", "token_policy"],
      prompt=f"Swap with Viktor: 50 ADA from me for 10 WMT from him (policy {P('WMT')}, token WMT). Before end of month.",
      spec={"roles": {"first": "Wren", "second": "Viktor"},
            "tokens": {"WMT": {"policy": P("WMT"), "name": "WMT"}},
            "token_a": "ADA", "amount_a": 50, "token_b": "WMT", "amount_b": 10,
            "first_by": "2027-06-29T23:59" + UTC, "second_by": "2027-06-30T23:59" + UTC},
      fact_sheet=[{"topic": "my name", "answer": "Wren."},
                  {"topic": "order and deadlines", "answer": "I deposit first by 2027-06-29 23:59 UTC; Viktor "
                                                             "deposits by 2027-06-30 23:59 UTC."},
                  {"topic": "if Viktor doesn't deposit", "answer": "Refund my ADA."}],
      adversarial_target=["unclear_month", "unclear_order"],
      author_note="Không rõ tháng nào, ai nạp trước."),

    # ------------------------------------------------------------------ loan
    C(id="v5-vi-loan-001", language="vi", family="loan", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Cho em Nguyệt vay 600 ADA: mình (Định) nạp trước 20:00 ngày 01/07/2027 giờ VN, tiền chuyển "
              "thẳng cho Nguyệt. Nguyệt trả mình 630 ADA trước 20:00 ngày 01/10/2027. Không trả thì thôi."),
      spec={"roles": {"lender": "Định", "borrower": "Nguyệt"}, "principal": 600, "repay": 630,
            "fund_by": "2027-07-01T20:00" + VN, "repay_by": "2027-10-01T20:00" + VN},
      fact_sheet=[], adversarial_target=["em_as_honorific"],
      author_note="'em Nguyệt': 'em' là xưng hô, tên là Nguyệt."),
    C(id="v5-en-loan-002", language="en", family="loan", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["terse", "relative_time"],
      prompt="loan contract: Abel lends Juno 1000 ADA, Juno pays back 1080 ADA in 6 months",
      spec={"roles": {"lender": "Abel", "borrower": "Juno"}, "principal": 1000, "repay": 1080,
            "fund_by": "2027-02-15T12:00" + UTC, "repay_by": "2027-08-15T12:00" + UTC},
      fact_sheet=[{"topic": "funding deadline", "answer": "Abel funds by 2027-02-15 12:00 UTC."},
                  {"topic": "6 months from when", "answer": "Repayment due 2027-08-15 12:00 UTC."},
                  {"topic": "late repayment", "answer": "The contract just ends."}],
      adversarial_target=["relative_duration_no_anchor"],
      author_note="'in 6 months' không có mốc."),
    C(id="v5-vi-loan-003", language="vi", family="loan", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", register="chat",
      phenomena=["percentage", "time_of_day", "timezone"],
      prompt=("Hợp đồng vay: Sang cho Tuệ vay 250 ADA, Sang nạp trước 23:59 ngày 10/03/2027 (giờ VN), nạp xong "
              "chuyển cho Tuệ. Tuệ trả 270 ADA trước 23:59 ngày 10/06/2027. Lãi 10% nhé."),
      spec={"roles": {"lender": "Sang", "borrower": "Tuệ"}, "principal": 250, "repay": 270,
            "fund_by": "2027-03-10T23:59" + VN, "repay_by": "2027-06-10T23:59" + VN},
      fact_sheet=[{"topic": "trả bao nhiêu", "answer": "270 ADA là đúng, lãi 8%."}],
      adversarial_target=["percentage_contradicts_amount"],
      author_note="10% của 250 là 275, mâu thuẫn với 270."),
    C(id="v5-vi-loan-004", language="vi", family="loan", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "numbers_in_words", "relative_time"],
      prompt=("Mình là Thơ, cho bạn Xuân mượn năm trăm ADA, mình nạp trước ngày 20/09/2027, Xuân trả đủ năm "
              "trăm hai mươi ADA sau ba tháng."),
      spec={"roles": {"lender": "Thơ", "borrower": "Xuân"}, "principal": 500, "repay": 520,
            "fund_by": "2027-09-20T23:59" + VN, "repay_by": "2027-12-20T23:59" + VN},
      fact_sheet=[{"topic": "giờ", "answer": "23:59 giờ VN."},
                  {"topic": "ba tháng tính từ đâu", "answer": "Từ hạn nạp: trả trước 23:59 ngày 20/12/2027."}],
      adversarial_target=["numbers_in_words", "relative_duration_no_anchor"],
      author_note="Số viết bằng chữ; 'sau ba tháng' không rõ mốc."),
    C(id="v5-en-loan-005", language="en", family="loan", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "decimal", "time_of_day", "timezone"],
      prompt=("Bridge loan: I'm Uma. I fund 300 ADA for Kaito by 2027-04-10 18:00 UTC, paid straight to him. "
              "Kaito repays 312.5 ADA by 2027-05-10 18:00 UTC. If he misses it, it just ends."),
      spec={"roles": {"lender": "Uma", "borrower": "Kaito"}, "principal": 300, "repay": "312.5",
            "fund_by": "2027-04-10T18:00" + UTC, "repay_by": "2027-05-10T18:00" + UTC},
      fact_sheet=[], adversarial_target=["decimal_amount"],
      author_note="Khoản trả có phần lẻ."),

    # ------------------------------------------------------------------ vesting
    C(id="v5-vi-vesting-001", language="vi", family="vesting", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Mình (role: TanPhat) thưởng cho bạn Ngà 120 ADA chia 3 đợt: mình nạp trước 17:00 ngày "
              "30/06/2027 giờ VN, hợp đồng tự trả 40 ADA vào 17:00 các ngày 31/07, 31/08 và 30/09/2027, không "
              "ai phải bấm gì."),
      spec={"roles": {"funder": "TanPhat", "worker": "Ngà"}, "deposit_by": "2027-06-30T17:00" + VN,
            "parts": [{"at": "2027-07-31T17:00" + VN, "amount": 40}, {"at": "2027-08-31T17:00" + VN, "amount": 40},
                      {"at": "2027-09-30T17:00" + VN, "amount": 40}]},
      fact_sheet=[], adversarial_target=["one_time_for_a_date_list", "no_one_acts"],
      author_note="Một giờ ghi một lần cho cả danh sách ngày; trả tự động."),
    C(id="v5-en-vesting-002", language="en", family="vesting", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["ambiguous_pronoun", "relative_time"],
      prompt=("Vesting for our new hire Leila: 900 ADA total, a quarter every quarter starting next year. Our "
              "company funds it."),
      spec={"roles": {"funder": "NorthBay", "worker": "Leila"}, "deposit_by": "2027-01-15T00:00" + UTC,
            "parts": [{"at": "2027-03-31T00:00" + UTC, "amount": 225}, {"at": "2027-06-30T00:00" + UTC, "amount": 225},
                      {"at": "2027-09-30T00:00" + UTC, "amount": 225}, {"at": "2027-12-31T00:00" + UTC, "amount": 225}]},
      fact_sheet=[{"topic": "company role", "answer": "Use role NorthBay."},
                  {"topic": "deposit deadline", "answer": "NorthBay funds by 2027-01-15 00:00 UTC."},
                  {"topic": "release dates", "answer": "225 ADA each at 00:00 UTC on 2027-03-31, 2027-06-30, "
                                                       "2027-09-30 and 2027-12-31."},
                  {"topic": "cancellation", "answer": "No cancellation."}],
      adversarial_target=["our_company_as_party", "missing_dates"],
      author_note="'Our company' là một bên chưa có tên."),
    C(id="v5-vi-vesting-003", language="vi", family="vesting", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["time_of_day", "timezone"],
      prompt=("Hợp đồng trả lương theo mốc cho Trang: Công ty Lotus (role: LotusCo) nạp 300 ADA trước 08:00 "
              "ngày 01/02/2027 (giờ VN). Hợp đồng tự trả cho Trang 100 ADA lúc 08:00 các ngày 01/03, 01/04 và "
              "01/05/2027. Trước mỗi mốc, LotusCo có thể bấm dừng; dừng thì phần chưa trả về lại LotusCo."),
      spec={"roles": {"funder": "LotusCo", "worker": "Trang"}, "deposit_by": "2027-02-01T08:00" + VN,
            "parts": [{"at": "2027-03-01T08:00" + VN, "amount": 100}, {"at": "2027-04-01T08:00" + VN, "amount": 100},
                      {"at": "2027-05-01T08:00" + VN, "amount": 100}],
            "cancel": {"name": "dung", "owner": "funder"}},
      fact_sheet=[], adversarial_target=["cancel_before_each_release", "user_role_token"],
      author_note="Có nút dừng trước mỗi mốc; trả tự động nếu không dừng."),
    C(id="v5-en-vesting-004", language="en", family="vesting", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", register="chat",
      phenomena=["self_correction", "time_of_day", "timezone"],
      prompt=("Grant vesting: Bodhi Foundation (role BodhiFdn) deposits 600 ADA by 2027-08-01 12:00 UTC for "
              "Celia, released automatically in 3 equal parts of 250 ADA on Sep 1, Oct 1 and Nov 1 2027 at "
              "12:00 UTC. Hmm, or was it 200 each?"),
      spec={"roles": {"funder": "BodhiFdn", "worker": "Celia"}, "deposit_by": "2027-08-01T12:00" + UTC,
            "parts": [{"at": "2027-09-01T12:00" + UTC, "amount": 200}, {"at": "2027-10-01T12:00" + UTC, "amount": 200},
                      {"at": "2027-11-01T12:00" + UTC, "amount": 200}]},
      fact_sheet=[{"topic": "which total is right", "answer": "600 ADA total, 200 ADA per part."}],
      adversarial_target=["parts_do_not_sum"],
      author_note="3 phần 250 là 750, mâu thuẫn với 600."),
    C(id="v5-vi-vesting-005", language="vi", family="vesting", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["no_diacritics", "terse", "ambiguous_pronoun", "relative_time"],
      prompt="chuyen tien thuong cho nhan vien Hoan: cong ty minh nap 60 ADA, tra dan 20 ADA moi thang trong 3 thang toi",
      spec={"roles": {"funder": "BinhMinh", "worker": "Hoan"}, "deposit_by": "2027-10-31T23:59" + VN,
            "parts": [{"at": "2027-11-30T23:59" + VN, "amount": 20}, {"at": "2027-12-31T23:59" + VN, "amount": 20},
                      {"at": "2028-01-31T23:59" + VN, "amount": 20}]},
      fact_sheet=[{"topic": "công ty là ai", "answer": "Role BinhMinh."},
                  {"topic": "hạn nạp", "answer": "Trước 23:59 ngày 31/10/2027 giờ VN."},
                  {"topic": "các mốc trả", "answer": "23:59 các ngày 30/11, 31/12/2027 và 31/01/2028, giờ VN."}],
      adversarial_target=["company_as_party", "missing_dates", "no_diacritics"],
      author_note="'cong ty minh' là một bên; các mốc trả vắt qua năm mới."),

    # ------------------------------------------------------------------ milestone (part 1)
    C(id="v5-vi-milestone-001", language="vi", family="milestone", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Thuê Lợi quay video cưới 2 phần: tôi (Phú) nạp 180 ADA trước 20:00 ngày 05/10/2027 (giờ VN). "
              "Phần quay: tôi duyệt trước 20:00 ngày 20/10/2027 thì trả Lợi 120 ADA. Phần dựng: duyệt trước "
              "20:00 ngày 05/11/2027 thì trả 60 ADA. Phần nào không duyệt kịp thì hoàn tiền phần đó cho tôi, "
              "phần sau vẫn tính bình thường."),
      spec={"roles": {"client": "Phú", "worker": "Lợi"}, "deposit_by": "2027-10-05T20:00" + VN,
            "stages": [{"name": "duyet_quay", "by": "2027-10-20T20:00" + VN, "amount": 120},
                       {"name": "duyet_dung", "by": "2027-11-05T20:00" + VN, "amount": 60}],
            "independent": True},
      fact_sheet=[], adversarial_target=["independent_stages"],
      author_note="Các phần độc lập: trễ phần 1 vẫn duyệt được phần 2."),
    C(id="v5-en-milestone-002", language="en", family="milestone", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person"],
      prompt=("Website job for Mateo: 2 milestones, 400 ADA then 600 ADA. I'm the client and I approve each "
              "one. If I don't approve a milestone in time, the remaining money comes back to me."),
      spec={"roles": {"client": "Hazel", "worker": "Mateo"}, "deposit_by": "2027-02-01T10:00" + UTC,
            "stages": [{"name": "approve_m1", "by": "2027-03-01T10:00" + UTC, "amount": 400},
                       {"name": "approve_m2", "by": "2027-04-01T10:00" + UTC, "amount": 600}]},
      fact_sheet=[{"topic": "your name", "answer": "Hazel."},
                  {"topic": "deadlines", "answer": "I deposit 1000 ADA by 2027-02-01 10:00 UTC; milestone 1 "
                                                   "approval by 2027-03-01 10:00 UTC; milestone 2 by 2027-04-01 "
                                                   "10:00 UTC."}],
      adversarial_target=["missing_deadlines", "first_person_party"],
      author_note="Trễ chặng thì phần còn lại về khách (không độc lập)."),
]
