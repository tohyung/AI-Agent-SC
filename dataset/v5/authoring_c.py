"""Dataset v5 cases, part C (written by hand, 2026-11-12, docs/archive/E7-Dataset-v5-Design.md).

k_of_n, first_come, zero_coupon_bond, coupon_bond and the first five split cases.
"""

VN = "+07:00"
UTC = "+00:00"


def C(**kw):
    return kw


CASES = [
    # ------------------------------------------------------------------ k of n approval
    C(id="v5-vi-k_of_n-001", language="vi", family="k_of_n", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "time_of_day", "timezone"],
      prompt=("Quỹ chung của nhóm leo núi:\n"
              "- Trọng, Viên và Ngọc Ánh mỗi người góp 120 ADA trước 20:00 ngày 01/06/2027 (giờ VN)\n"
              "- Chi 360 ADA cho cửa hàng đồ leo núi Đỉnh Cao (role: DinhCao) khi có ít nhất 2 trong 3 người "
              "đồng ý, trước 20:00 ngày 15/06/2027\n"
              "- Không đủ 2 người đồng ý thì ai góp bao nhiêu nhận lại bấy nhiêu"),
      spec={"roles": {"trong": "Trọng", "vien": "Viên", "anh": "Ngọc Ánh", "recipient": "DinhCao"},
            "funders": [{"role": "trong", "amount": 120}, {"role": "vien", "amount": 120},
                        {"role": "anh", "amount": 120}],
            "approvers": ["trong", "vien", "anh"], "k": 2,
            "fund_by": "2027-06-01T20:00" + VN, "approve_by": "2027-06-15T20:00" + VN, "choice": "dong_y"},
      fact_sheet=[], adversarial_target=["k_of_n", "two_word_name"],
      author_note="2 trong 3; mỗi người góp ngang nhau."),
    C(id="v5-vi-k_of_n-002", language="vi", family="k_of_n", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["no_diacritics"],
      prompt=("quy chung 3 nguoi Sy, Bin, Ti, moi nguoi nap 50 ADA. muon rut tien tra cho tiem sach thi can it "
              "nhat 2 nguoi dong y"),
      spec={"roles": {"sy": "Sy", "bin": "Bin", "ti": "Ti", "recipient": "TiemSach"},
            "funders": [{"role": "sy", "amount": 50}, {"role": "bin", "amount": 50}, {"role": "ti", "amount": 50}],
            "approvers": ["sy", "bin", "ti"], "k": 2,
            "fund_by": "2027-08-10T21:00" + VN, "approve_by": "2027-08-20T21:00" + VN, "choice": "dong_y"},
      fact_sheet=[{"topic": "tiệm sách", "answer": "Role TiemSach."},
                  {"topic": "hạn nạp", "answer": "Trước 21:00 ngày 10/08/2027 giờ VN, ai nạp trước cũng được."},
                  {"topic": "hạn đồng ý", "answer": "Trước 21:00 ngày 20/08/2027."},
                  {"topic": "không đủ người đồng ý", "answer": "Trả lại tiền cho từng người."}],
      adversarial_target=["k_of_n", "missing_recipient_role", "no_diacritics"],
      author_note="Thiếu role người nhận, hạn và nhánh không đủ người."),
    C(id="v5-en-k_of_n-003", language="en", family="k_of_n", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "time_of_day", "timezone"],
      prompt=("Band fund:\n"
              "- Oren, Pia and Quill each deposit 40 ADA by 2027-09-01 21:00 UTC\n"
              "- paying the studio (role SoundBox) needs all three of them to approve by 2027-09-15 21:00 UTC\n"
              "- if anyone holds out, everyone gets their 40 ADA back"),
      spec={"roles": {"oren": "Oren", "pia": "Pia", "quill": "Quill", "recipient": "SoundBox"},
            "funders": [{"role": "oren", "amount": 40}, {"role": "pia", "amount": 40}, {"role": "quill", "amount": 40}],
            "approvers": ["oren", "pia", "quill"], "k": 3,
            "fund_by": "2027-09-01T21:00" + UTC, "approve_by": "2027-09-15T21:00" + UTC, "choice": "approve"},
      fact_sheet=[], adversarial_target=["unanimous_approval"],
      author_note="Cần cả 3 người (k = n)."),
    C(id="v5-vi-k_of_n-004", language="vi", family="k_of_n", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", register="chat",
      phenomena=["time_of_day", "timezone"],
      prompt=("Quỹ từ thiện của nhóm: Thắm góp 200 ADA, Lư góp 100 ADA, Mến góp 100 ADA, trước 23:59 ngày "
              "30/09/2027 giờ VN. Chuyển 400 ADA cho mái ấm Hoa Sen (role: HoaSen) khi đủ 2 trong 3 người "
              "duyệt, hạn duyệt 23:59 ngày 10/10/2027. Không đủ thì trả lại. Duyệt thì cần cả 3 người nhé."),
      spec={"roles": {"tham": "Thắm", "lu": "Lư", "men": "Mến", "recipient": "HoaSen"},
            "funders": [{"role": "tham", "amount": 200}, {"role": "lu", "amount": 100}, {"role": "men", "amount": 100}],
            "approvers": ["tham", "lu", "men"], "k": 2,
            "fund_by": "2027-09-30T23:59" + VN, "approve_by": "2027-10-10T23:59" + VN, "choice": "duyet"},
      fact_sheet=[{"topic": "cần mấy người duyệt", "answer": "2 trong 3 người là đủ."}],
      adversarial_target=["k_contradiction", "unequal_funders"],
      author_note="'2 trong 3' rồi 'cần cả 3' mâu thuẫn."),
    C(id="v5-vi-k_of_n-005", language="vi", family="k_of_n", info_mode="complete",
      expected_behavior="converge", register="document",
      phenomena=["long_document", "bullet_list", "time_of_day", "timezone"],
      prompt=("Trích quy chế quỹ phòng (bản sửa 03/2027):\n"
              "Điều 1. Quỹ do 4 thành viên Hoài, Tịnh, Uy, Bắc góp, mỗi người 25 ADA, trước 18:00 ngày "
              "28/02/2027 (UTC+7).\n"
              "Điều 2. Mọi khoản chi cho chủ nhà (role: ChuNha) cần ít nhất 3 trong 4 thành viên đồng ý, trước "
              "18:00 ngày 31/03/2027.\n"
              "Điều 3. Không đủ người đồng ý trước hạn thì quỹ trả lại từng người.\n"
              "Điều 4. Họp quỹ vào tối thứ Sáu đầu tháng; biên bản do Tịnh giữ."),
      spec={"roles": {"hoai": "Hoài", "tinh": "Tịnh", "uy": "Uy", "bac": "Bắc", "recipient": "ChuNha"},
            "funders": [{"role": "hoai", "amount": 25}, {"role": "tinh", "amount": 25},
                        {"role": "uy", "amount": 25}, {"role": "bac", "amount": 25}],
            "approvers": ["hoai", "tinh", "uy", "bac"], "k": 3,
            "fund_by": "2027-02-28T18:00" + VN, "approve_by": "2027-03-31T18:00" + VN, "choice": "dong_y"},
      fact_sheet=[], adversarial_target=["k_of_n", "noise_in_document"],
      author_note="3 trên 4; điều 4 là nhiễu."),
    C(id="v5-en-k_of_n-006", language="en", family="k_of_n", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "ambiguous_pronoun"],
      prompt=("Our family savings pot for Grandma's surgery: me, my brother Ravi and my sister Ama put in 300 "
              "ADA each. The hospital (role CityHospital) gets paid if at least two of us agree."),
      spec={"roles": {"me": "Suri", "ravi": "Ravi", "ama": "Ama", "recipient": "CityHospital"},
            "funders": [{"role": "me", "amount": 300}, {"role": "ravi", "amount": 300}, {"role": "ama", "amount": 300}],
            "approvers": ["me", "ravi", "ama"], "k": 2,
            "fund_by": "2027-11-01T00:00" + UTC, "approve_by": "2027-11-20T00:00" + UTC, "choice": "agree"},
      fact_sheet=[{"topic": "your name", "answer": "Suri."},
                  {"topic": "deadlines", "answer": "We each deposit by 2027-11-01 00:00 UTC; agreement by "
                                                   "2027-11-20 00:00 UTC."},
                  {"topic": "if fewer than two agree", "answer": "Everyone gets their 300 ADA back."}],
      adversarial_target=["first_person_in_a_group", "missing_deadlines"],
      author_note="'us' gồm người dùng; người dùng chưa nêu tên."),

    # ------------------------------------------------------------------ first come
    C(id="v5-vi-first_come-001", language="vi", family="first_come", info_mode="complete",
      expected_behavior="converge", register="terse",
      phenomena=["first_person", "terse", "time_of_day", "timezone"],
      prompt=("Pass vé xe Tết 18 ADA: Trí, Lệ hoặc Ninh ai chuyển trước thì lấy, tiền về mình (Đan). Hết "
              "20:00 ngày 25/01/2028 giờ VN thì thôi."),
      spec={"roles": {"seller": "Đan", "b1": "Trí", "b2": "Lệ", "b3": "Ninh"}, "buyers": ["b1", "b2", "b3"],
            "price": 18, "offer_until": "2028-01-25T20:00" + VN},
      fact_sheet=[], adversarial_target=["race_any_buyer"],
      author_note="Ai trong ba người cũng có thể mua."),
    C(id="v5-en-first_come-002", language="en", family="first_come", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("First come, first served: whoever of Jonah, Leif and Mira deposits 25 ADA first gets my spare "
              "festival wristband. The money goes to me. The offer ends 2027-07-20 12:00 UTC."),
      spec={"roles": {"seller": "Talia", "b1": "Jonah", "b2": "Leif", "b3": "Mira"}, "buyers": ["b1", "b2", "b3"],
            "price": 25, "offer_until": "2027-07-20T12:00" + UTC},
      fact_sheet=[{"topic": "your name", "answer": "Talia."},
                  {"topic": "if nobody deposits", "answer": "Nothing happens, the offer just ends."}],
      adversarial_target=["race_any_buyer", "first_person_seller"],
      author_note="Ba người mua cạnh tranh; người bán là người dùng, chưa nêu tên."),
    C(id="v5-vi-first_come-003", language="vi", family="first_come", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["no_diacritics", "terse"],
      prompt="ban lai ban phim co 35 ADA cho ai nap truoc trong nhom: Ngo, Lap, Quy",
      spec={"roles": {"seller": "Phi", "b1": "Ngo", "b2": "Lap", "b3": "Quy"}, "buyers": ["b1", "b2", "b3"],
            "price": 35, "offer_until": "2027-12-12T21:00" + VN},
      fact_sheet=[{"topic": "người bán", "answer": "Mình là Phi."},
                  {"topic": "hạn", "answer": "Đến 21:00 ngày 12/12/2027 giờ VN."},
                  {"topic": "không ai nạp", "answer": "Thì thôi."}],
      adversarial_target=["missing_seller", "missing_deadline", "no_diacritics"],
      author_note="Thiếu người bán và hạn."),
    C(id="v5-vi-first_come-004", language="vi", family="first_come", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Bán lại suất học bơi 50 ADA: trong ba bạn Ngân Hà, Bích Thủy, Thảo Vy, ai chuyển trước 08:00 "
              "ngày 03/07/2027 (giờ VN) thì được, tiền về tôi (Kim Chi). Bạn nào mua được thì hợp đồng gửi email "
              "báo cho bạn ấy giúp tôi."),
      spec={"roles": {"seller": "Kim Chi", "b1": "Ngân Hà", "b2": "Bích Thủy", "b3": "Thảo Vy"},
            "buyers": ["b1", "b2", "b3"], "price": 50, "offer_until": "2027-07-03T08:00" + VN},
      fact_sheet=[{"topic": "email", "answer": "Có thể bỏ phần email."},
                  {"topic": "không ai chuyển", "answer": "Thì thôi."}],
      adversarial_target=["unsupported_side_effect", "two_word_names"],
      author_note="Gửi email không làm được trong hợp đồng."),
    C(id="v5-en-first_come-005", language="en", family="first_come", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "relative_time"],
      prompt="Selling my spare GPU for 400 ADA to whichever of Nadir, Oto or Zev pays first. Open until Friday.",
      spec={"roles": {"seller": "Bram", "b1": "Nadir", "b2": "Oto", "b3": "Zev"}, "buyers": ["b1", "b2", "b3"],
            "price": 400, "offer_until": "2027-04-09T18:00" + UTC},
      fact_sheet=[{"topic": "your name", "answer": "Bram."},
                  {"topic": "which Friday", "answer": "Friday 2027-04-09, 18:00 UTC."},
                  {"topic": "if nobody pays", "answer": "Just close it."}],
      adversarial_target=["weekday_without_date"],
      author_note="'Friday' không rõ tuần nào, giờ nào."),

    # ------------------------------------------------------------------ zero-coupon bond
    C(id="v5-vi-zero_coupon_bond-001", language="vi", family="zero_coupon_bond", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "time_of_day", "timezone", "grouped_number"],
      prompt=("Trái phiếu chiết khấu:\n"
              "- Nhà đầu tư: Gia Hân\n"
              "- Bên phát hành: Công ty Phúc Lộc (role: PhucLoc)\n"
              "- Gia Hân nạp 950 ADA trước 10:00 ngày 01/03/2027 (giờ VN), chuyển ngay cho PhucLoc\n"
              "- Đáo hạn: PhucLoc trả 1.000 ADA trước 10:00 ngày 01/03/2028\n"
              "- PhucLoc không trả thì hợp đồng đóng"),
      spec={"roles": {"investor": "Gia Hân", "issuer": "PhucLoc"}, "price": 950,
            "buy_by": "2027-03-01T10:00" + VN, "payments": [{"by": "2028-03-01T10:00" + VN, "amount": 1000}]},
      fact_sheet=[], adversarial_target=["vietnamese_thousands_dot", "user_role_token"],
      author_note="'1.000 ADA' là một nghìn."),
    C(id="v5-vi-zero_coupon_bond-002", language="vi", family="zero_coupon_bond", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "relative_time"],
      prompt="phát hành trái phiếu 1 năm cho anh Lượng: anh ấy mua 800 ADA, đáo hạn tôi trả lại 880 ADA",
      spec={"roles": {"investor": "Lượng", "issuer": "AnhDuong"}, "price": 800,
            "buy_by": "2027-05-15T23:59" + VN, "payments": [{"by": "2028-05-15T23:59" + VN, "amount": 880}]},
      fact_sheet=[{"topic": "tên tôi", "answer": "Công ty Ánh Dương, role AnhDuong."},
                  {"topic": "hạn mua", "answer": "23:59 ngày 15/05/2027 giờ VN."},
                  {"topic": "đáo hạn", "answer": "23:59 ngày 15/05/2028 giờ VN."},
                  {"topic": "tiền mua", "answer": "Chuyển ngay cho tôi."}],
      adversarial_target=["issuer_is_first_person", "missing_dates"],
      author_note="Người dùng là bên phát hành; thiếu ngày."),
    C(id="v5-en-zero_coupon_bond-003", language="en", family="zero_coupon_bond", info_mode="conflict",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "self_correction", "percentage", "time_of_day", "timezone", "grouped_number"],
      prompt=("Zero-coupon note: investor Halima buys from me (Corin) for 2,000 ADA by 2027-06-30 16:00 UTC, "
              "paid to me right away. At maturity, 2028-06-30 16:00 UTC, I repay 2,150 ADA. Sorry, typo: the "
              "repayment is 2,160 ADA (8%)."),
      spec={"roles": {"investor": "Halima", "issuer": "Corin"}, "price": 2000,
            "buy_by": "2027-06-30T16:00" + UTC, "payments": [{"by": "2028-06-30T16:00" + UTC, "amount": 2160}]},
      fact_sheet=[{"topic": "repayment", "answer": "2,160 ADA."}],
      adversarial_target=["self_correction_amount"],
      author_note="Người dùng tự sửa số trả."),
    C(id="v5-vi-zero_coupon_bond-004", language="vi", family="zero_coupon_bond", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "vi_en_mix", "decimal", "time_of_day", "timezone"],
      prompt=("Mình (Diệu) phát hành discount bond cho Hải Yến: Hải Yến mua với giá 487,5 ADA trước 20:00 ngày "
              "05/09/2027 giờ VN, tiền về mình luôn; maturity 20:00 ngày 05/03/2028 mình trả 500 ADA."),
      spec={"roles": {"investor": "Hải Yến", "issuer": "Diệu"}, "price": "487.5",
            "buy_by": "2027-09-05T20:00" + VN, "payments": [{"by": "2028-03-05T20:00" + VN, "amount": 500}]},
      fact_sheet=[{"topic": "mình không trả", "answer": "Thì hợp đồng đóng."}],
      adversarial_target=["vietnamese_decimal_comma", "vi_en_mix"],
      author_note="Giá có số lẻ kiểu Việt."),

    # ------------------------------------------------------------------ coupon bond
    C(id="v5-vi-coupon_bond-001", language="vi", family="coupon_bond", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["bullet_list", "percentage", "time_of_day", "timezone", "grouped_number"],
      prompt=("Trái phiếu có lãi:\n"
              "- Nhà đầu tư Đăng Khoa nạp 1.200 ADA trước 09:00 ngày 01/01/2027 (giờ VN), chuyển ngay cho bên "
              "phát hành Sông Hàn (role: SongHan)\n"
              "- Lãi 5%/kỳ, tức 60 ADA, trả lúc 09:00 các ngày 01/07/2027 và 01/01/2028\n"
              "- Kỳ cuối trả lãi cộng gốc: 1.260 ADA\n"
              "- SongHan trễ kỳ nào thì dừng"),
      spec={"roles": {"investor": "Đăng Khoa", "issuer": "SongHan"}, "price": 1200,
            "buy_by": "2027-01-01T09:00" + VN,
            "payments": [{"by": "2027-07-01T09:00" + VN, "amount": 60},
                         {"by": "2028-01-01T09:00" + VN, "amount": 1260}]},
      fact_sheet=[], adversarial_target=["coupon_plus_principal", "one_time_for_a_date_list"],
      author_note="Kỳ cuối gộp lãi và gốc."),
    C(id="v5-en-coupon_bond-002", language="en", family="coupon_bond", info_mode="missing",
      expected_behavior="ask_then_converge", register="bullets",
      phenomena=["first_person", "bullet_list", "percentage", "relative_time"],
      prompt=("Coupon bond for my project:\n"
              "- Noor invests 1000 ADA\n"
              "- 4% coupon every 6 months for 1 year\n"
              "- principal back at the end"),
      spec={"roles": {"investor": "Noor", "issuer": "BrightPath"}, "price": 1000,
            "buy_by": "2027-03-01T00:00" + UTC,
            "payments": [{"by": "2027-09-01T00:00" + UTC, "amount": 40},
                         {"by": "2028-03-01T00:00" + UTC, "amount": 1040}]},
      fact_sheet=[{"topic": "your name / role", "answer": "Role BrightPath."},
                  {"topic": "purchase deadline", "answer": "Noor buys by 2027-03-01 00:00 UTC; the money goes to "
                                                           "BrightPath."},
                  {"topic": "coupon dates", "answer": "40 ADA by 2027-09-01 00:00 UTC, then 1040 ADA by "
                                                      "2028-03-01 00:00 UTC."},
                  {"topic": "missed payment", "answer": "The contract ends."}],
      adversarial_target=["percentage_coupon", "missing_dates"],
      author_note="Thiếu ngày và tên bên phát hành."),
    C(id="v5-vi-coupon_bond-003", language="vi", family="coupon_bond", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", register="chat",
      phenomena=["first_person", "percentage", "self_correction", "time_of_day", "timezone"],
      prompt=("Trái phiếu nhỏ: nhà đầu tư Lan Chi nạp 300 ADA trước 23:59 ngày 10/04/2027 giờ VN cho tôi "
              "(role: VietSen). Lãi mỗi quý 6 ADA, tức 3% một quý, trả 23:59 các ngày 10/07 và 10/10/2027; kỳ "
              "10/10 trả thêm gốc. À, hay lãi là 9 ADA nhỉ?"),
      spec={"roles": {"investor": "Lan Chi", "issuer": "VietSen"}, "price": 300,
            "buy_by": "2027-04-10T23:59" + VN,
            "payments": [{"by": "2027-07-10T23:59" + VN, "amount": 6},
                         {"by": "2027-10-10T23:59" + VN, "amount": 306}]},
      fact_sheet=[{"topic": "lãi mỗi quý", "answer": "6 ADA là đúng (2%)."},
                  {"topic": "tôi trễ kỳ", "answer": "Dừng."}],
      derived=["306"],
      adversarial_target=["percentage_contradicts_amount"],
      author_note="3% của 300 là 9, không phải 6."),
    C(id="v5-vi-coupon_bond-004", language="vi", family="coupon_bond", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "relative_time"],
      prompt=("Phát hành trái phiếu cho bà Mười: bà mua 600 ADA, mỗi năm tôi trả lãi 30 ADA, trả 2 năm, năm "
              "cuối trả luôn tiền gốc. Bắt đầu từ đầu năm sau."),
      spec={"roles": {"investor": "Mười", "issuer": "HoangGia"}, "price": 600,
            "buy_by": "2027-01-05T23:59" + VN,
            "payments": [{"by": "2028-01-05T23:59" + VN, "amount": 30},
                         {"by": "2029-01-05T23:59" + VN, "amount": 630}]},
      fact_sheet=[{"topic": "tên tôi", "answer": "Role HoangGia."},
                  {"topic": "hạn mua", "answer": "23:59 ngày 05/01/2027 giờ VN, tiền chuyển ngay cho tôi."},
                  {"topic": "các kỳ trả", "answer": "23:59 ngày 05/01/2028 trả 30 ADA; 23:59 ngày 05/01/2029 trả 630 ADA."},
                  {"topic": "trễ", "answer": "Dừng."}],
      adversarial_target=["relative_to_today", "issuer_is_first_person"],
      author_note="'đầu năm sau' phụ thuộc hôm nay; kỳ cuối gộp gốc. Hạn 2029 nằm ngoài V-8: ngoại lệ có chủ ý."),
    C(id="v5-en-coupon_bond-005", language="en", family="coupon_bond", info_mode="complete",
      expected_behavior="converge", register="document",
      phenomena=["long_document", "decimal", "time_of_day", "timezone", "grouped_number"],
      prompt=("Term sheet, Series A community bond (summary)\n"
              "Issuer: Greenhouse Collective (role Greenhouse)\n"
              "Investor: Marisol\n"
              "Issue price: 2,500 ADA, deposited by Marisol by 2027-04-01 15:00 UTC and paid to the issuer at once\n"
              "Coupons: 62.5 ADA on 2027-10-01 and 2028-04-01, 15:00 UTC; the second coupon is paid together "
              "with the 2,500 ADA principal\n"
              "Default: a missed payment ends the contract\n"
              "Transfer: the bond cannot be sold on to another investor\n"
              "Use of proceeds: greenhouse heating and two new irrigation pumps (for information only)\n"
              "Reporting: the issuer sends a short progress note to the investor every quarter"),
      spec={"roles": {"investor": "Marisol", "issuer": "Greenhouse"}, "price": 2500,
            "buy_by": "2027-04-01T15:00" + UTC,
            "payments": [{"by": "2027-10-01T15:00" + UTC, "amount": "62.5"},
                         {"by": "2028-04-01T15:00" + UTC, "amount": "2562.5"}]},
      fact_sheet=[], derived=["2562.5"],
      adversarial_target=["coupon_plus_principal", "decimal_coupon", "noise_in_document"],
      author_note="Kỳ hai = 62,5 + 2.500."),

    # ------------------------------------------------------------------ split (part 1)
    C(id="v5-vi-split-001", language="vi", family="split", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "percentage", "time_of_day", "timezone", "grouped_number"],
      prompt=("Chia tiền bán tranh:\n"
              "- tôi (Hữu Phước) nạp 1.000 ADA trước 21:00 ngày 30/05/2027 (giờ VN)\n"
              "- sau đó ai cũng có thể bấm 'chia' trước 21:00 ngày 06/06/2027: họa sĩ Mỹ Linh 60%, phòng tranh "
              "Lam Sơn (role: LamSon) 30%, tôi 10%\n"
              "- không ai bấm thì hoàn hết cho tôi"),
      spec={"roles": {"payer": "Hữu Phước", "linh": "Mỹ Linh", "lamson": "LamSon"},
            "deposit_by": "2027-05-30T21:00" + VN, "trigger": "notify", "trigger_by": "2027-06-06T21:00" + VN,
            "shares": [{"role": "linh", "amount": 600}, {"role": "lamson", "amount": 300},
                       {"role": "payer", "amount": 100}]},
      fact_sheet=[], derived=["600", "300", "100"],
      adversarial_target=["percent_shares", "payer_also_receives", "anyone_presses"],
      author_note="Người nạp nhận 10%; ai cũng bấm được."),
    C(id="v5-en-split-002", language="en", family="split", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "decimal", "time_of_day", "timezone"],
      prompt=("Bounty split after the bug bash:\n"
              "- I (Kenzo) deposit 125 ADA by 2027-02-14 12:00 UTC\n"
              "- after that anyone can trigger the payout until 2027-02-21 12:00 UTC\n"
              "- payout: Aditi 62.5 ADA, Brice 37.5 ADA, Cyrus 25 ADA\n"
              "- no trigger by then: refund me"),
      spec={"roles": {"payer": "Kenzo", "aditi": "Aditi", "brice": "Brice", "cyrus": "Cyrus"},
            "deposit_by": "2027-02-14T12:00" + UTC, "trigger": "notify", "trigger_by": "2027-02-21T12:00" + UTC,
            "shares": [{"role": "aditi", "amount": "62.5"}, {"role": "brice", "amount": "37.5"},
                       {"role": "cyrus", "amount": 25}]},
      fact_sheet=[], adversarial_target=["decimal_shares", "anyone_presses"],
      author_note="Các phần có số lẻ, cộng đủ 125."),
    C(id="v5-vi-split-003", language="vi", family="split", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["terse"],
      prompt="chia 90 ADA tiền thưởng: Nhã 40, Tân 30, Lữ 20",
      spec={"roles": {"payer": "NhaSach", "nha": "Nhã", "tan": "Tân", "lu": "Lữ"},
            "deposit_by": "2027-08-01T17:00" + VN,
            "shares": [{"role": "nha", "amount": 40}, {"role": "tan", "amount": 30}, {"role": "lu", "amount": 20}]},
      fact_sheet=[{"topic": "ai nạp", "answer": "Mình nạp, role là NhaSach."},
                  {"topic": "hạn", "answer": "Nạp trước 17:00 ngày 01/08/2027 giờ VN; nạp xong chia luôn, không "
                                             "cần ai bấm."},
                  {"topic": "không nạp", "answer": "Thì thôi."}],
      adversarial_target=["missing_payer", "missing_deadline"],
      author_note="Chỉ có số chia, thiếu người nạp và hạn."),
    C(id="v5-vi-split-004", language="vi", family="split", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Tôi (Gấm) nạp 300 ADA trước 08:00 ngày 01/10/2027 giờ VN để chia lương thời vụ: đúng 08:00 ngày "
              "15/10/2027 hợp đồng tự trả Hà My 180 ADA và Quang Vinh 120 ADA, không cần ai bấm. Trả xong thì "
              "hợp đồng tự xuất hóa đơn VAT giúp tôi."),
      spec={"roles": {"payer": "Gấm", "hamy": "Hà My", "vinh": "Quang Vinh"},
            "deposit_by": "2027-10-01T08:00" + VN, "trigger": "time", "release_at": "2027-10-15T08:00" + VN,
            "shares": [{"role": "hamy", "amount": 180}, {"role": "vinh", "amount": 120}]},
      fact_sheet=[{"topic": "hóa đơn", "answer": "Có thể bỏ phần hóa đơn."},
                  {"topic": "không nạp", "answer": "Thì thôi."}],
      adversarial_target=["release_at_time_no_action", "unsupported_side_effect"],
      author_note="Trả theo giờ, không ai bấm; xuất hóa đơn không làm được."),
    C(id="v5-en-split-005", language="en", family="split", info_mode="conflict",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "self_correction", "time_of_day", "timezone"],
      prompt=("Tip jar split: I (Lars) deposit 200 ADA by 2027-12-24 20:00 UTC, and anyone can press split "
              "before 2027-12-31 20:00 UTC: Mina 100, Joss 60, Pip 40. Wait, Joss and Pip should get 50 each. "
              "If nobody presses, it comes back to me."),
      spec={"roles": {"payer": "Lars", "mina": "Mina", "joss": "Joss", "pip": "Pip"},
            "deposit_by": "2027-12-24T20:00" + UTC, "trigger": "notify", "trigger_by": "2027-12-31T20:00" + UTC,
            "shares": [{"role": "mina", "amount": 100}, {"role": "joss", "amount": 50}, {"role": "pip", "amount": 50}]},
      fact_sheet=[{"topic": "final shares", "answer": "Mina 100, Joss 50, Pip 50 ADA."}],
      adversarial_target=["self_correction_shares", "anyone_presses"],
      author_note="Người dùng sửa phần chia trong cùng tin nhắn."),
]
