"""Dataset v5 cases, part D (written by hand, 2026-11-12, docs/archive/E7-Dataset-v5-Design.md).

The last split case, collateral_loan, deduction, matching and the ten infeasible requests.
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
    # ------------------------------------------------------------------ split (part 2)
    C(id="v5-vi-split-006", language="vi", family="split", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "numbers_in_words", "vi_en_mix", "time_of_day", "timezone"],
      prompt=("Chia tiền trúng giải bốc thăm:\n"
              "- mình (Lâm Oanh) nạp hai trăm bốn mươi ADA trước 22:00 ngày 14/02/2028 giờ VN\n"
              "- sau đó bất kỳ ai bấm 'split' trước 22:00 ngày 21/02/2028 thì chia đều cho ba bạn Ngọc Hà, Đức "
              "Anh và Thiên Ân, mỗi người 80 ADA\n"
              "- không ai bấm thì trả lại mình"),
      spec={"roles": {"payer": "Lâm Oanh", "ha": "Ngọc Hà", "ducanh": "Đức Anh", "an": "Thiên Ân"},
            "deposit_by": "2028-02-14T22:00" + VN, "trigger": "notify", "trigger_by": "2028-02-21T22:00" + VN,
            "shares": [{"role": "ha", "amount": 80}, {"role": "ducanh", "amount": 80}, {"role": "an", "amount": 80}]},
      fact_sheet=[], adversarial_target=["numbers_in_words", "anyone_presses", "payer_not_a_recipient"],
      author_note="Người nạp không nhận phần nào; 240 viết bằng chữ."),

    # ------------------------------------------------------------------ collateral loan
    C(id="v5-vi-collateral_loan-001", language="vi", family="collateral_loan", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "numbers_in_words", "token_policy", "time_of_day", "timezone"],
      prompt=("Vay thế chấp:\n"
              f"- tôi (Hữu Tài) khóa hai mươi token SEN (policy {P('SEN')}, tên SEN) trước 10:00 ngày "
              "02/02/2027 (giờ VN)\n"
              "- chị Diệu Linh cho vay 400 ADA trước 10:00 ngày 03/02/2027, tiền chuyển thẳng cho tôi\n"
              "- tôi trả 420 ADA trước 10:00 ngày 03/05/2027 thì lấy lại 20 SEN\n"
              "- quá hạn thì chị Diệu Linh lấy 20 SEN; chị không cho vay thì tôi lấy lại SEN"),
      spec={"roles": {"borrower": "Hữu Tài", "lender": "Diệu Linh"},
            "tokens": {"SEN": {"policy": P("SEN"), "name": "SEN"}}, "collateral_token": "SEN",
            "collateral": 20, "principal": 400, "repay": 420, "collateral_by": "2027-02-02T10:00" + VN,
            "fund_by": "2027-02-03T10:00" + VN, "repay_by": "2027-05-03T10:00" + VN},
      fact_sheet=[], adversarial_target=["native_collateral", "default_moves_collateral"],
      author_note="Ba hạn; quá hạn thì tài sản chuyển cho người cho vay."),
    C(id="v5-en-collateral_loan-002", language="en", family="collateral_loan", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "ambiguous_pronoun"],
      prompt=("I want to borrow 250 ADA from Tamsin and lock my 1000 HUNT tokens as collateral. I'll pay back "
              "265 ADA. If I don't, she keeps the tokens."),
      spec={"roles": {"borrower": "Ossian", "lender": "Tamsin"},
            "tokens": {"HUNT": {"policy": P("HUNT"), "name": "HUNT"}}, "collateral_token": "HUNT",
            "collateral": 1000, "principal": 250, "repay": 265, "collateral_by": "2027-06-01T08:00" + UTC,
            "fund_by": "2027-06-03T08:00" + UTC, "repay_by": "2027-09-01T08:00" + UTC},
      fact_sheet=[{"topic": "your name", "answer": "Ossian."},
                  {"topic": "HUNT token", "answer": f"Policy {P('HUNT')}, token name HUNT."},
                  {"topic": "deadlines", "answer": "I lock the tokens by 2027-06-01 08:00 UTC, Tamsin lends by "
                                                   "2027-06-03 08:00 UTC, I repay by 2027-09-01 08:00 UTC."},
                  {"topic": "if Tamsin does not lend", "answer": "I get my tokens back."}],
      adversarial_target=["missing_policy", "missing_deadlines"],
      author_note="Thiếu tên, policy, ba hạn và nhánh không cho vay."),
    C(id="v5-vi-collateral_loan-003", language="vi", family="collateral_loan", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["no_diacritics", "terse", "typo", "first_person"],
      prompt="vay 100 ADA cua chi Nhu Y, the chap 5 token PUNK, tra 105 ADA sau 1 thang, ko tra thi chi giu token",
      spec={"roles": {"borrower": "Luyến", "lender": "Nhu Y"},
            "tokens": {"PUNK": {"policy": P("PUNK"), "name": "PUNK"}}, "collateral_token": "PUNK",
            "collateral": 5, "principal": 100, "repay": 105, "collateral_by": "2027-10-10T23:59" + VN,
            "fund_by": "2027-10-11T23:59" + VN, "repay_by": "2027-11-11T23:59" + VN},
      fact_sheet=[{"topic": "tên", "answer": "Mình là Luyến."},
                  {"topic": "token PUNK", "answer": f"Policy {P('PUNK')}, tên token PUNK."},
                  {"topic": "hạn", "answer": "Mình khóa token trước 23:59 ngày 10/10/2027, chị Nhu Y giải ngân "
                                             "trước 23:59 ngày 11/10/2027, mình trả trước 23:59 ngày 11/11/2027, "
                                             "giờ VN."},
                  {"topic": "chị không cho vay", "answer": "Trả lại token cho mình."}],
      adversarial_target=["missing_policy", "relative_duration_no_anchor", "no_diacritics"],
      author_note="'ko' là viết tắt; 'sau 1 tháng' không có mốc."),
    C(id="v5-vi-collateral_loan-004", language="vi", family="collateral_loan", info_mode="complete",
      expected_behavior="converge", register="document",
      phenomena=["long_document", "token_policy", "percentage", "time_of_day", "timezone", "grouped_number"],
      prompt=("Hợp đồng cầm cố (bản tóm tắt gửi luật sư):\n"
              "Bên vay: Hoài Nam. Bên cho vay: Công ty tài chính Bến Thành (role: BenThanh).\n"
              f"Tài sản đảm bảo: 3 token LANDX (policy {P('LANDX')}, tên LANDX), khóa trước 14:00 ngày "
              "01/04/2027 (UTC+7).\n"
              "Giải ngân: 1.500 ADA trước 14:00 ngày 02/04/2027, chuyển ngay cho bên vay.\n"
              "Hoàn trả: 1.575 ADA (gốc cộng 5%) trước 14:00 ngày 02/10/2027; trả đủ thì bên vay nhận lại 3 LANDX.\n"
              "Quá hạn: BenThanh nhận 3 LANDX. BenThanh không giải ngân: trả lại tài sản cho bên vay.\n"
              "Phí công chứng do bên vay chịu, nằm ngoài hợp đồng."),
      spec={"roles": {"borrower": "Hoài Nam", "lender": "BenThanh"},
            "tokens": {"LANDX": {"policy": P("LANDX"), "name": "LANDX"}}, "collateral_token": "LANDX",
            "collateral": 3, "principal": 1500, "repay": 1575, "collateral_by": "2027-04-01T14:00" + VN,
            "fund_by": "2027-04-02T14:00" + VN, "repay_by": "2027-10-02T14:00" + VN},
      fact_sheet=[], adversarial_target=["vietnamese_thousands_dot", "noise_in_document"],
      author_note="1.500 và 1.575 dùng dấu chấm nhóm; phí công chứng là nhiễu."),
    C(id="v5-en-collateral_loan-005", language="en", family="collateral_loan", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "decimal", "numbers_in_words", "token_policy", "time_of_day", "timezone"],
      prompt=("Collateral loan:\n"
              f"- borrower Quincy locks seventy-five MOON (policy {P('MOON')}, token MOON) by 2027-08-01 00:00 UTC\n"
              "- lender Saoirse sends 120 ADA by 2027-08-02 00:00 UTC, paid straight to Quincy\n"
              "- Quincy repays 126.5 ADA by 2027-11-01 00:00 UTC and gets the MOON back\n"
              "- default: Saoirse takes the MOON; no loan: Quincy takes the MOON back"),
      spec={"roles": {"borrower": "Quincy", "lender": "Saoirse"},
            "tokens": {"MOON": {"policy": P("MOON"), "name": "MOON"}}, "collateral_token": "MOON",
            "collateral": 75, "principal": 120, "repay": "126.5", "collateral_by": "2027-08-01T00:00" + UTC,
            "fund_by": "2027-08-02T00:00" + UTC, "repay_by": "2027-11-01T00:00" + UTC},
      fact_sheet=[], adversarial_target=["decimal_repayment", "numbers_in_words"],
      author_note="Số lượng token viết bằng chữ; khoản trả có số lẻ."),

    # ------------------------------------------------------------------ deduction
    C(id="v5-vi-deduction-001", language="vi", family="deduction", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "lovelace_units", "vi_en_mix", "time_of_day", "timezone"],
      prompt=("Cọc thuê máy chiếu cho hội thảo:\n"
              "- tôi (Kiều My) deposit 120 ADA trước 08:00 ngày 10/06/2027 (giờ VN)\n"
              "- kỹ thuật viên Hoàng Long nhập số tiền khấu trừ, tính bằng lovelace, từ 0 đến 50 ADA, trước "
              "08:00 ngày 12/06/2027\n"
              "- số khấu trừ chuyển cho công ty AV Pro (role: AVPro), phần còn lại hoàn tôi\n"
              "- không nhập thì hoàn đủ cho tôi\n"
              "- máy chiếu là loại Epson 4K, bên AV Pro giao và lắp tận nơi, tôi tự lo dây HDMI"),
      spec={"roles": {"payer": "Kiều My", "keeper": "AVPro", "inspector": "Hoàng Long"}, "amount": 120,
            "max_deduction": 50, "deposit_by": "2027-06-10T08:00" + VN, "decide_by": "2027-06-12T08:00" + VN,
            "choice": "khau_tru"},
      fact_sheet=[], adversarial_target=["chosen_amount", "lovelace_input"],
      author_note="Số người kiểm tra nhập là số tiền chuyển đi."),
    C(id="v5-en-deduction-002", language="en", family="deduction", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["first_person", "terse", "typo", "lovelace_units"],
      prompt="deposit 300 ADA for the drone rentl, Odile checks it and enters a deduction up to 100 ADA (in lovelace), rest back to me",
      spec={"roles": {"payer": "Pascal", "keeper": "SkyRent", "inspector": "Odile"}, "amount": 300,
            "max_deduction": 100, "deposit_by": "2027-05-05T09:00" + UTC, "decide_by": "2027-05-12T09:00" + UTC,
            "choice": "deduction"},
      fact_sheet=[{"topic": "your name", "answer": "Pascal."},
                  {"topic": "who gets the deduction", "answer": "The shop, role SkyRent."},
                  {"topic": "deadlines", "answer": "I deposit by 2027-05-05 09:00 UTC; Odile enters it by "
                                                   "2027-05-12 09:00 UTC."},
                  {"topic": "no entry", "answer": "Full refund to me."}],
      adversarial_target=["missing_keeper", "missing_deadlines"],
      author_note="'rentl' là lỗi gõ; thiếu người nhận khấu trừ."),
    C(id="v5-vi-deduction-003", language="vi", family="deduction", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["no_diacritics", "numbers_in_words", "lovelace_units", "first_person"],
      prompt=("coc 60 ADA thue do cam trai, anh Quang Hai kiem tra xong nhap tien phat (tinh bang lovelace), "
              "toi da mot nua tien coc, con lai tra minh"),
      spec={"roles": {"payer": "Thục Đoan", "keeper": "CamTrai", "inspector": "Quang Hai"}, "amount": 60,
            "max_deduction": 30, "deposit_by": "2027-07-01T23:59" + VN, "decide_by": "2027-07-05T23:59" + VN,
            "choice": "tien_phat"},
      fact_sheet=[{"topic": "tên", "answer": "Mình là Thục Đoan."},
                  {"topic": "ai nhận tiền phạt", "answer": "Cửa hàng, role CamTrai."},
                  {"topic": "hạn", "answer": "Mình nạp trước 23:59 ngày 01/07/2027, anh Quang Hai nhập trước "
                                             "23:59 ngày 05/07/2027, giờ VN."},
                  {"topic": "tối đa bao nhiêu", "answer": "30 ADA."},
                  {"topic": "không nhập", "answer": "Hoàn đủ cho mình."}],
      adversarial_target=["fraction_cap", "missing_keeper", "no_diacritics"],
      author_note="'tối đa một nửa' là 30; không rõ ai nhận tiền phạt."),
    C(id="v5-vi-deduction-004", language="vi", family="deduction", info_mode="complete",
      expected_behavior="converge", register="document",
      phenomena=["first_person", "long_document", "numbers_in_words", "lovelace_units", "time_of_day", "timezone"],
      prompt=("PHIẾU ĐẶT CỌC THUÊ VÁY CƯỚI (bản chụp, mình gõ lại):\n"
              "Khách: tôi, Bảo Vy. Tiền cọc: hai trăm ADA, nạp trước 18:00 ngày 20/03/2027 giờ VN.\n"
              "Trả váy xong, chị Hạnh Dung bên tiệm kiểm tra rồi nhập số tiền khấu trừ theo lovelace, tối đa "
              "tám mươi ADA, trước 18:00 ngày 27/03/2027.\n"
              "Số khấu trừ chuyển cho tiệm Ngọc Trai (role: NgocTrai), còn lại hoàn cho tôi. Không nhập thì "
              "hoàn đủ.\n"
              "Ghi chú của tiệm: giặt hấp miễn phí, giữ váy tối đa 3 ngày."),
      spec={"roles": {"payer": "Bảo Vy", "keeper": "NgocTrai", "inspector": "Hạnh Dung"}, "amount": 200,
            "max_deduction": 80, "deposit_by": "2027-03-20T18:00" + VN, "decide_by": "2027-03-27T18:00" + VN,
            "choice": "khau_tru"},
      fact_sheet=[], adversarial_target=["numbers_in_words", "noise_in_document"],
      author_note="Số viết bằng chữ; ghi chú của tiệm là nhiễu."),
    C(id="v5-en-deduction-005", language="en", family="deduction", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", register="bullets",
      phenomena=["first_person", "bullet_list", "lovelace_units", "time_of_day", "timezone"],
      prompt=("Equipment deposit:\n"
              "- I (Saskia) deposit 500 ADA by 2027-10-01 12:00 UTC\n"
              "- the inspector, Lukas, enters a deduction between 0 and 150 ADA (as lovelace) by 2027-10-08 "
              "12:00 UTC\n"
              "- the deduction goes to RentWell (role RentWell), the rest comes back to me; nothing entered "
              "means I get it all back\n"
              "- and can the contract convert my refund to USDC automatically?"),
      spec={"roles": {"payer": "Saskia", "keeper": "RentWell", "inspector": "Lukas"}, "amount": 500,
            "max_deduction": 150, "deposit_by": "2027-10-01T12:00" + UTC, "decide_by": "2027-10-08T12:00" + UTC,
            "choice": "deduction"},
      fact_sheet=[{"topic": "if the USDC conversion is impossible", "answer": "Drop it and refund in ADA."}],
      adversarial_target=["unsupported_conversion"],
      author_note="Đổi sang USDC không làm được."),

    # ------------------------------------------------------------------ matching donation
    C(id="v5-vi-matching-001", language="vi", family="matching", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "numbers_in_words", "time_of_day", "timezone"],
      prompt=("Gây quỹ sửa đường làng:\n"
              "- ông Bảy góp bốn mươi ADA trước 19:00 ngày 01/04/2027 (giờ VN), rồi ông Chín góp 60 ADA trước "
              "19:00 ngày 03/04/2027\n"
              "- doanh nghiệp Mekong Xanh (role: MekongXanh) góp bằng tổng hai người nhưng không quá 80 ADA, "
              "trước 19:00 ngày 06/04/2027\n"
              "- đủ cả thì chuyển hết cho ban xây dựng (role: BanXayDung)\n"
              "- thiếu bước nào thì hoàn cho người đã góp"),
      spec={"roles": {"bay": "Bảy", "chin": "Chín", "sponsor": "MekongXanh", "beneficiary": "BanXayDung"},
            "donors": [{"role": "bay", "amount": 40, "by": "2027-04-01T19:00" + VN},
                       {"role": "chin", "amount": 60, "by": "2027-04-03T19:00" + VN}],
            "cap": 80, "sponsor_by": "2027-04-06T19:00" + VN},
      fact_sheet=[], adversarial_target=["cap_binds", "honorific_ong"],
      author_note="Tổng 100 vượt trần 80, nên nhà tài trợ góp 80."),
    C(id="v5-vi-matching-002", language="vi", family="matching", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["ambiguous_pronoun", "typo"],
      prompt=("chúng tôi gây quỹ cho thư viện xả, mỗi khoản góp sẽ được nhà tài trợ góp thêm bằng đúng số "
              "đó"),
      spec={"roles": {"thuc": "Hiền Thục", "phuong": "Mai Phương", "sponsor": "SachXanh",
                      "beneficiary": "ThuVienXa"},
            "donors": [{"role": "thuc", "amount": 25, "by": "2027-05-10T20:00" + VN},
                       {"role": "phuong", "amount": 35, "by": "2027-05-12T20:00" + VN}],
            "cap": 100, "sponsor_by": "2027-05-15T20:00" + VN},
      fact_sheet=[{"topic": "ai góp, bao nhiêu", "answer": "Hiền Thục góp 25 ADA trước, rồi Mai Phương góp 35 ADA."},
                  {"topic": "hạn", "answer": "Hiền Thục trước 20:00 ngày 10/05/2027, Mai Phương trước 20:00 "
                                             "ngày 12/05/2027, nhà tài trợ trước 20:00 ngày 15/05/2027; giờ VN."},
                  {"topic": "nhà tài trợ", "answer": "Role SachXanh, góp tối đa 100 ADA."},
                  {"topic": "thư viện", "answer": "Role ThuVienXa."},
                  {"topic": "thiếu bước", "answer": "Hoàn cho người đã góp."}],
      adversarial_target=["we_is_a_group", "missing_everything"],
      author_note="'chúng tôi' là nhóm người góp; 'xả' là lỗi gõ của 'xã'."),
    C(id="v5-en-matching-003", language="en", family="matching", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "decimal", "ambiguous_pronoun", "time_of_day", "timezone"],
      prompt=("Matching drive for the animal shelter (role PawsHome):\n"
              "- Linnea gives 45.5 ADA by 2027-09-10 18:00 UTC, then Teodor 54.5 ADA by 2027-09-12 18:00 UTC\n"
              "- then our sponsor GoodCo (role GoodCo) matches the total, capped at 75 ADA, by 2027-09-15 18:00 UTC\n"
              "- everything goes to PawsHome; if a step is missed, whoever paid gets refunded"),
      spec={"roles": {"linnea": "Linnea", "teodor": "Teodor", "sponsor": "GoodCo", "beneficiary": "PawsHome"},
            "donors": [{"role": "linnea", "amount": "45.5", "by": "2027-09-10T18:00" + UTC},
                       {"role": "teodor", "amount": "54.5", "by": "2027-09-12T18:00" + UTC}],
            "cap": 75, "sponsor_by": "2027-09-15T18:00" + UTC},
      fact_sheet=[], adversarial_target=["decimal_donations", "cap_binds"],
      author_note="45,5 + 54,5 = 100 > 75."),
    C(id="v5-vi-matching-004", language="vi", family="matching", info_mode="missing",
      expected_behavior="ask_then_converge", register="bullets",
      phenomena=["bullet_list", "vi_en_mix", "time_of_day", "timezone"],
      prompt=("Matching fund cho CLB robotics:\n"
              "- Duy Khánh góp 70 ADA trước 9h sáng 02/11/2027 giờ VN\n"
              "- sponsor TechViet (role: TechViet) match bằng số đó, tối đa 100 ADA\n"
              "- tất cả chuyển cho CLB (role: RoboClub); sponsor không match thì refund cho Duy Khánh"),
      spec={"roles": {"khanh": "Duy Khánh", "sponsor": "TechViet", "beneficiary": "RoboClub"},
            "donors": [{"role": "khanh", "amount": 70, "by": "2027-11-02T09:00" + VN}],
            "cap": 100, "sponsor_by": "2027-11-05T09:00" + VN},
      fact_sheet=[{"topic": "hạn của sponsor", "answer": "Trước 9h sáng 05/11/2027 giờ VN."}],
      adversarial_target=["cap_does_not_bind", "vi_en_mix", "missing_second_deadline"],
      author_note="Một người góp; 70 dưới trần 100."),

    # ------------------------------------------------------------------ infeasible
    C(id="v5-vi-infeasible-001", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="terse",
      phenomena=["no_diacritics", "terse", "percentage"],
      prompt="hop dong tu dong ban het ADA cua minh khi gia len 10%",
      spec={"reason": "needs a price feed (oracle) that no party supplies"}, fact_sheet=[],
      adversarial_target=["oracle"], author_note="Cần giá thị trường từ bên ngoài."),
    C(id="v5-vi-infeasible-002", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="document",
      phenomena=["first_person", "long_document"],
      prompt=("Đề xuất cho dự án gia đình (mình viết nháp, bạn góp ý giúp):\n"
              "Mục tiêu: lưu hồ sơ bệnh án của mẹ mình trên blockchain để không bị mất.\n"
              "Yêu cầu 1: chỉ bác sĩ điều trị xem được nội dung, người khác chỉ thấy là có hồ sơ.\n"
              "Yêu cầu 2: khi mình gọi điện cho tổng đài thì hợp đồng mở quyền xem cho người nhà.\n"
              "Yêu cầu 3: tự xóa hồ sơ sau 10 năm.\n"
              "Kinh phí dự kiến khoảng 50 ADA mỗi năm."),
      spec={"reason": "private data storage, phone calls and deleting data are outside a Marlowe contract"},
      fact_sheet=[], adversarial_target=["privacy", "off_chain_trigger"],
      author_note="Không có phần tiền tệ nào làm được."),
    C(id="v5-en-infeasible-003", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="bullets",
      phenomena=["bullet_list", "relative_time"],
      prompt=("Payroll contract:\n"
              "- pays every employee every Friday, forever\n"
              "- the amount follows the official minimum wage each year\n"
              "- employees can join and leave at any time"),
      spec={"reason": "unbounded repetition, external wage data and parties that change"}, fact_sheet=[],
      adversarial_target=["unbounded", "oracle", "dynamic_parties"],
      author_note="Lặp vô hạn, dữ liệu ngoài, danh sách bên thay đổi."),
    C(id="v5-vi-infeasible-004", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="chat",
      phenomena=["first_person", "vi_en_mix", "typo"],
      prompt=("Tạo smart contract cho tôi rút tiền mặt từ ATM Vietcombank bằng ví Cardano, mỗi lần rút 1 triệu "
              "đồng, kô cần ngân hàng xác nhận."),
      spec={"reason": "off-chain bank withdrawals"}, fact_sheet=[],
      adversarial_target=["off_chain_bank"], author_note="Rút tiền ngân hàng nằm ngoài chuỗi; 'kô' là lỗi gõ."),
    C(id="v5-en-infeasible-005", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="document",
      phenomena=["long_document"],
      prompt=("Clause 12 (Disputes) of our marketplace terms, which the contract must enforce:\n"
              "12.1 Any payment disputed within 30 days shall be reversed by the contract, including payments "
              "already sent to other wallets.\n"
              "12.2 The reversal also applies to payments made by other contracts on the buyer's behalf.\n"
              "12.3 Disputes are decided by our support team by email.\n"
              "12.4 This clause survives termination of the agreement.\n"
              "12.5 Notices under this clause go to the address in the seller profile and count as "
              "received the next business day."),
      spec={"reason": "reversing payments already made and email decisions"}, fact_sheet=[],
      adversarial_target=["reverse_history"], author_note="Không thể đảo giao dịch đã thực hiện."),
    C(id="v5-vi-infeasible-006", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="bullets",
      phenomena=["bullet_list", "numbers_in_words", "self_correction", "percentage", "relative_time"],
      prompt=("Quỹ tiết kiệm của cả nhà:\n"
              "- mỗi người góp một trăm ADA mỗi tuần, à nhầm, mỗi ngày\n"
              "- hợp đồng tự cộng lãi 1%/ngày, không ai phải bỏ tiền lãi\n"
              "- muốn rút bao nhiêu thì rút, không cần hạn"),
      spec={"reason": "interest nobody funds, unbounded repetition, no deadline"}, fact_sheet=[],
      adversarial_target=["unfunded_interest", "no_timeout"],
      author_note="Lãi không ai trả; không có hạn."),
    C(id="v5-en-infeasible-007", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="chat",
      phenomena=["first_person", "typo"],
      prompt=("Make a contract that keeps my 300 ADA hiden so nobody on the chain can see the balance or who I "
              "pay."),
      spec={"reason": "on-chain amounts and recipients are public"}, fact_sheet=[],
      adversarial_target=["privacy"], author_note="'hiden' là lỗi gõ."),
    C(id="v5-vi-infeasible-008", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="chat",
      phenomena=["no_diacritics", "typo"],
      prompt=("hop dong cho thue nah, tien thue tu tang theo lam phat hang nam do Tong cuc Thong ke cong bo"),
      spec={"reason": "needs official inflation data (oracle)"}, fact_sheet=[],
      adversarial_target=["oracle"], author_note="'nah' là lỗi gõ của 'nhà'."),
    C(id="v5-vi-infeasible-009", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="terse",
      phenomena=["no_diacritics", "terse", "first_person"],
      prompt="hop dong xoa giao dich ma minh gui nham hom qua",
      spec={"reason": "deleting chain history"}, fact_sheet=[],
      adversarial_target=["ledger_history_deletion"], author_note="Xóa lịch sử chuỗi."),
    C(id="v5-en-infeasible-010", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", register="terse",
      phenomena=["terse", "first_person"],
      prompt="a contract that never expires and holds my ADA until I say so, no deadline ever",
      spec={"reason": "every wait needs a deadline"}, fact_sheet=[],
      adversarial_target=["no_timeout"], author_note="Không có hạn."),
]
