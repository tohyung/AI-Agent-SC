"""Dataset v3 cases, part B: new families and infeasible requests (written by hand, 2026-11-10)."""

VN = "+07:00"
Z = "+00:00"


def C(**kw):
    return kw


P_CAT = "8f7e6d5c4b3a29180716253443526170819a8b7c6d5e4f30211203f4e5d6c7b8"[:56]
P_VNDC = "9a1d3c5e7f90b2d4f6a8c0e2a4c6e8f0a2b4c6d8e0f2a4b6c8d0e2f4"
P_LAND = "5a2c4e6a8c0e2a4c6e8a0c2e4a6c8e0a2c4e6a8c0e2a4c6e8a0c2e4a"[:56]
P_GEM = "1f3e5d7c9b0a2f4e6d8c0b2a4f6e8d0c2b4a6f8e0d2c4b6a8f0e2d4c"
P_BOOK = "b00cb00cb00cb00cb00cb00cb00cb00cb00cb00cb00cb00cb00cb00c"

CASES = [
    # ------------------------------------------------------------------ installments
    C(id="v3-en-installment-001", language="en", family="installment", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "relative_time", "irregular_intervals"],
      prompt=("Need a contract to sell my motorbike in installments. Buyer is Kevin Tran. Price 600 ADA in 4 equal "
              "monthly payments, first one due April 1, 2027. If he misses a payment the deal stops and I keep "
              "whatever he already paid."),
      spec={"roles": {"buyer": "Kevin Tran", "seller": "Daniel"},
            "installments": [{"by": f"2027-{m:02d}-01T23:59{VN}", "amount": 150} for m in (4, 5, 6, 7)]},
      fact_sheet=[{"topic": "my name", "answer": "Daniel."},
                  {"topic": "time / timezone", "answer": "23:59 Vietnam time (UTC+7) on the 1st of April, May, June and July 2027."},
                  {"topic": "when I get paid", "answer": "Each installment goes to me as soon as Kevin pays it."}],
      adversarial_target=["first_person_party", "fourth_deadline"], author_note="Phải hỏi tên người bán và giờ; tự chia 150."),
    C(id="v3-vi-installment-002", language="vi", family="installment", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "bullet_list", "decimal", "time_of_day", "timezone"],
      prompt=("Hợp đồng bán laptop trả góp:\n- Người mua: Phúc; người bán: tôi (Hiền)\n- 4 kỳ, mỗi kỳ 37,5 ADA, hạn "
              "23:59 ngày 10 hằng tháng từ tháng 2 đến tháng 5/2027 (giờ VN)\n- Phúc nạp kỳ nào thì chuyển cho tôi "
              "luôn kỳ đó\n- Trễ kỳ nào thì dừng, tiền đã trả không hoàn"),
      spec={"roles": {"buyer": "Phúc", "seller": "Hiền"},
            "installments": [{"by": f"2027-{m:02d}-10T23:59{VN}", "amount": "37.5"} for m in (2, 3, 4, 5)]},
      fact_sheet=[], adversarial_target=["decimal_amount", "fourth_deadline"], author_note="Số lẻ 37,5 kiểu Việt."),
    C(id="v3-vi-installment-003", language="vi", family="installment", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "typo", "numbers_in_words", "relative_time", "uneven_amounts"],
      prompt=("Trả góp xe máy cũ cho Tín, tổng 200 ADA chia 3 kỳ: kỳ 1 một trăm ADA trước 18:00 ngày 01/07/2027 "
              "(giờ VN), kỳ 2 là 50 ADA đúng 30 ngày sau hạn kỳ 1, kỳ 3 là 50 ADA đúng 30 ngày sau hạn kỳ 2, cùng giờ. "
              "Mỗi kỳ chuyễn ngay cho tôi (Lụa). Trễ thì dừng."),
      spec={"roles": {"buyer": "Tín", "seller": "Lụa"},
            "installments": [{"by": "2027-07-01T18:00" + VN, "amount": 100}, {"by": "2027-07-31T18:00" + VN, "amount": 50},
                             {"by": "2027-08-30T18:00" + VN, "amount": 50}]},
      fact_sheet=[], adversarial_target=["relative_chain", "third_deadline"], author_note="Hạn tính nối tiếp 30 ngày."),
    C(id="v3-vi-installment-004", language="vi", family="installment", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "bullet_list", "relative_time", "weekly"],
      prompt=("Bán xe đạp cũ cho Liêm, trả theo tuần:\n- 5 kỳ, mỗi kỳ 20 ADA\n- hạn mỗi kỳ là 18:00 thứ Sáu hằng tuần "
              "(giờ VN), kỳ đầu là thứ Sáu 08/01/2027\n- tiền mỗi kỳ chuyển cho tôi (Sa) ngay\n- lỡ một kỳ là dừng"),
      spec={"roles": {"buyer": "Liêm", "seller": "Sa"},
            "installments": [{"by": d + "T18:00" + VN, "amount": 20}
                             for d in ("2027-01-08", "2027-01-15", "2027-01-22", "2027-01-29", "2027-02-05")]},
      fact_sheet=[], adversarial_target=["fifth_deadline", "weekday_arithmetic"], author_note="Phải tự tính 5 ngày thứ Sáu."),
    C(id="v3-vi-installment-005", language="vi", family="installment", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "first_person", "relative_time"],
      prompt="tra gop dien thoai 6 thang, moi thang 25 ADA, nguoi mua la Tuan, toi la Lien, bat dau tu thang 3/2027, tre la dung",
      spec={"roles": {"buyer": "Tuan", "seller": "Lien"},
            "installments": [{"by": f"2027-{m:02d}-01T23:59{VN}", "amount": 25} for m in range(3, 9)]},
      fact_sheet=[{"topic": "ngày nào trong tháng, giờ nào", "answer": "Ngày 1 mỗi tháng, 23:59 giờ VN, từ 01/03 đến 01/08/2027."},
                  {"topic": "tiền mỗi kỳ", "answer": "Chuyển ngay cho tôi."}],
      adversarial_target=["sixth_deadline", "no_diacritics_names"], author_note="Không rõ ngày trong tháng."),
    C(id="v3-en-installment-006", language="en", family="installment", info_mode="conflict",
      expected_behavior="converge", phenomena=["first_person", "self_correction", "bullet_list"],
      prompt=("Installment plan for a guitar:\n- buyer Noel pays me (Ines) 300 ADA in 3 payments of 120 ADA\n- due "
              "2027-02-15, 2027-03-15 and 2027-04-15, 12:00 UTC\n- each payment goes straight to me; a missed payment "
              "ends it\nsorry, I mean 3 payments of 100 ADA."),
      spec={"roles": {"buyer": "Noel", "seller": "Ines"},
            "installments": [{"by": f"2027-{m:02d}-15T12:00{Z}", "amount": 100} for m in (2, 3, 4)]},
      fact_sheet=[], adversarial_target=["late_correction"], author_note="300 vs 3×120; đính chính rõ ở cuối."),
    C(id="v3-vi-installment-007", language="vi", family="installment", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", phenomena=["first_person", "unsupported_extra"],
      prompt=("Bán tủ lạnh trả góp cho chị Hồng: 3 kỳ, mỗi kỳ 40 ADA, hạn 23:59 các ngày 20/02, 20/03 và 20/04/2027 "
              "giờ VN, mỗi kỳ chuyển cho tôi (Trúc). Trễ thì tự động tính lãi 2%/ngày và nhắn Zalo nhắc chị Hồng."),
      spec={"roles": {"buyer": "Hồng", "seller": "Trúc"},
            "installments": [{"by": f"2027-{m:02d}-20T23:59{VN}", "amount": 40} for m in (2, 3, 4)]},
      fact_sheet=[{"topic": "nếu không làm được lãi phạt và Zalo", "answer": "Bỏ hai phần đó, giữ phần còn lại."}],
      adversarial_target=["unsupported_extra_silently_dropped"], author_note="Hai yêu cầu phụ không làm được."),

    # ------------------------------------------------------------------ k of n approvals
    C(id="v3-vi-k_of_n-001", language="vi", family="k_of_n", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "three_contributors", "ambiguous_month_end"],
      prompt=("can hop dong quy chung: Lan, Hoa, Tuan moi nguoi gop 100 ADA truoc 1/4/2027. muon chuyen tien cho nha "
              "cung cap thi can 2 trong 3 nguoi dong y, han dong y la cuoi thang 4. khong du 2 nguoi dong y thi tra lai "
              "tien cho tung nguoi"),
      spec={"roles": {"lan": "Lan", "hoa": "Hoa", "tuan": "Tuan", "recipient": "PhucAn"},
            "funders": [{"role": "lan", "amount": 100}, {"role": "hoa", "amount": 100}, {"role": "tuan", "amount": 100}],
            "approvers": ["lan", "hoa", "tuan"], "k": 2,
            "fund_by": "2027-04-01T00:00" + VN, "approve_by": "2027-04-30T23:59" + VN, "choice": "dong_y"},
      fact_sheet=[{"topic": "nhà cung cấp", "answer": "Role PhucAn."},
                  {"topic": "trước 1/4", "answer": "Trước 00:00 ngày 01/04/2027 giờ VN; ai góp trước cũng được."},
                  {"topic": "cuối tháng 4", "answer": "23:59 ngày 30/04/2027 giờ VN."},
                  {"topic": "có người không góp", "answer": "Trả lại cho những người đã góp."}],
      adversarial_target=["count_approvals", "any_order_deposits", "missing_recipient"],
      author_note="Ba người góp theo thứ tự bất kỳ; đếm 2 trên 3; thiếu người nhận."),
    C(id="v3-vi-k_of_n-002", language="vi", family="k_of_n", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "bullet_list", "numbers_in_words", "timezone"],
      prompt=("Quỹ dự án:\n- tôi (Ánh) nạp một nghìn ADA trước 00:00 ngày 01/02/2027 (UTC+7)\n- chi cho nhà cung cấp "
              "Orbit khi ít nhất 2 trong 3 người Ánh, Nam, Lộc đồng ý trước 00:00 ngày 28/02/2027\n- không đủ người "
              "đồng ý thì tiền về lại tôi"),
      spec={"roles": {"anh": "Ánh", "nam": "Nam", "loc": "Lộc", "recipient": "Orbit"},
            "funders": [{"role": "anh", "amount": 1000}], "approvers": ["anh", "nam", "loc"], "k": 2,
            "fund_by": "2027-02-01T00:00" + VN, "approve_by": "2027-02-28T00:00" + VN, "choice": "dong_y"},
      fact_sheet=[], adversarial_target=["count_approvals", "funder_is_approver"], author_note="Người nạp cũng là người duyệt."),
    C(id="v3-vi-k_of_n-003", language="vi", family="k_of_n", info_mode="complete", expected_behavior="converge",
      phenomena=["long_document", "noise", "typo", "four_approvers"],
      prompt=("Quy chế quỹ lớp 12A (trích):\n1. Lớp trưởng Hạnh nạp 400 ADA vào quỹ trước 23:59 ngày 01/09/2027 (giờ VN).\n"
              "2. Mọi khoản chi cho nhà trường (role: TruongHoc) cần ít nhất 3 trong 4 thành viên ban cán sự (Hạnh, Lộc, "
              "Mai, Nam) đồng ý trước 23:59 ngày 30/09/2027.\n3. Không đủ số người đồng ý trước hạn thì tiền trả lại cho "
              "Hạnh.\n4. Biên bản họp lớp lưu ở sổ đầu bài; ban cán sự họp mỗi thứ Hai, quyế định thu quỹ tháng sau."),
      spec={"roles": {"hanh": "Hạnh", "loc": "Lộc", "mai": "Mai", "nam": "Nam", "recipient": "TruongHoc"},
            "funders": [{"role": "hanh", "amount": 400}], "approvers": ["hanh", "loc", "mai", "nam"], "k": 3,
            "fund_by": "2027-09-01T23:59" + VN, "approve_by": "2027-09-30T23:59" + VN, "choice": "dong_y"},
      fact_sheet=[], adversarial_target=["count_approvals", "noise_in_spec"], author_note="3 trên 4; mục 4 là nhiễu."),
    C(id="v3-en-k_of_n-004", language="en", family="k_of_n", info_mode="missing", expected_behavior="ask_then_converge",
      phenomena=["first_person", "ambiguous_pronoun", "terse", "bullet_list"],
      prompt="Joint account for our band:\n- me, Rita and Sam each put in 50 ADA\n- to pay the studio we need any two of us to agree",
      spec={"roles": {"jo": "Jo", "rita": "Rita", "sam": "Sam", "recipient": "Studio"},
            "funders": [{"role": "jo", "amount": 50}, {"role": "rita", "amount": 50}, {"role": "sam", "amount": 50}],
            "approvers": ["jo", "rita", "sam"], "k": 2,
            "fund_by": "2027-05-01T23:59" + Z, "approve_by": "2027-05-31T23:59" + Z, "choice": "agree"},
      fact_sheet=[{"topic": "my name", "answer": "Jo."}, {"topic": "studio role", "answer": "Studio."},
                  {"topic": "deadlines", "answer": "We all pay in any order by 2027-05-01 23:59 UTC; approvals by 2027-05-31 23:59 UTC."},
                  {"topic": "not enough approvals", "answer": "Everyone gets their 50 ADA back."}],
      adversarial_target=["count_approvals", "any_order_deposits", "missing_deadlines"], author_note="'us' gồm người nói."),
    C(id="v3-vi-k_of_n-005", language="vi", family="k_of_n", info_mode="conflict", expected_behavior="converge",
      phenomena=["self_correction", "timezone"],
      prompt=("Quỹ chung gia đình: bố (role: Bo) nạp 300 ADA trước 23:59 ngày 15/06/2027 giờ VN. Chi cho bệnh viện "
              "(role: BenhVien) khi 2 trong 3 người Bo, Me, Con đồng ý trước 23:59 ngày 30/06/2027. À không, phải cả 3 "
              "người đồng ý mới chi. Không đủ thì trả lại cho bố."),
      spec={"roles": {"bo": "Bo", "me": "Me", "con": "Con", "recipient": "BenhVien"},
            "funders": [{"role": "bo", "amount": 300}], "approvers": ["bo", "me", "con"], "k": 3,
            "fund_by": "2027-06-15T23:59" + VN, "approve_by": "2027-06-30T23:59" + VN, "choice": "dong_y"},
      fact_sheet=[], adversarial_target=["late_correction", "count_approvals"], author_note="2/3 đính chính thành 3/3."),
    C(id="v3-en-k_of_n-006", language="en", family="k_of_n", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["vi_en_mix", "relative_time"],
      prompt=("2-of-3 approval để release 600 ADA cho contractor Vega. Funder Ola deposits 600 ADA by 2027-07-01 "
              "09:00 UTC. Signers: Ola, Pim, Quinn. Approvals within 10 days."),
      spec={"roles": {"ola": "Ola", "pim": "Pim", "quinn": "Quinn", "recipient": "Vega"},
            "funders": [{"role": "ola", "amount": 600}], "approvers": ["ola", "pim", "quinn"], "k": 2,
            "fund_by": "2027-07-01T09:00" + Z, "approve_by": "2027-07-11T09:00" + Z, "choice": "approve"},
      fact_sheet=[{"topic": "10 days from when", "answer": "From the funding deadline: approvals by 2027-07-11 09:00 UTC."},
                  {"topic": "not enough approvals", "answer": "Refund Ola."}],
      adversarial_target=["relative_from_unclear_anchor", "count_approvals"], author_note="'within 10 days' không rõ mốc."),

    # ------------------------------------------------------------------ first come
    C(id="v3-vi-first_come-001", language="vi", family="first_come", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "race", "typo", "time_of_day"],
      prompt=("Bán vé concert giá 50 ADA: ai trong 3 bạn Khôi, Trinh, Đông nạp trước thì mua được, tiền chuyễn cho tôi "
              "(Thái). Hết hạn 20:00 ngày 15/03/2027 giờ VN mà không ai nạp thì thôi."),
      spec={"roles": {"seller": "Thái", "b1": "Khôi", "b2": "Trinh", "b3": "Đông"}, "buyers": ["b1", "b2", "b3"],
            "price": 50, "offer_until": "2027-03-15T20:00" + VN},
      fact_sheet=[], adversarial_target=["race_in_one_when"], author_note="Ba nhánh cạnh tranh."),
    C(id="v3-en-first_come-002", language="en", family="first_come", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "bullet_list", "numbers_in_words", "self_correction", "race"],
      prompt=("First-come sale of a limited print:\n- price fifteen ADA\n- buyers: Aria, Basil, Cora (sorry, and Dmitri "
              "too, so four buyers)\n- the first one to deposit gets it; the money goes to me, Elio\n- offer open until "
              "2027-04-20 21:00 UTC"),
      spec={"roles": {"seller": "Elio", "b1": "Aria", "b2": "Basil", "b3": "Cora", "b4": "Dmitri"},
            "buyers": ["b1", "b2", "b3", "b4"], "price": 15, "offer_until": "2027-04-20T21:00" + Z},
      fact_sheet=[], adversarial_target=["late_correction", "race_in_one_when"], author_note="Thêm người mua giữa câu."),
    C(id="v3-vi-first_come-003", language="vi", family="first_come", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "terse", "race"],
      prompt="ban som doi giay 40 ADA cho ai nap nhanh nhat trong nhom: Hieu, Lam",
      spec={"roles": {"seller": "Phong", "b1": "Hieu", "b2": "Lam"}, "buyers": ["b1", "b2"], "price": 40,
            "offer_until": "2027-05-01T23:59" + VN},
      fact_sheet=[{"topic": "người bán", "answer": "Mình là Phong."},
                  {"topic": "hạn", "answer": "Đến 23:59 ngày 01/05/2027 giờ VN."},
                  {"topic": "không ai nạp", "answer": "Thì thôi, đóng hợp đồng."}],
      adversarial_target=["missing_deadlines"], author_note="Không dấu, thiếu người bán và hạn."),
    C(id="v3-en-first_come-004", language="en", family="first_come", info_mode="complete", expected_behavior="converge",
      phenomena=["vi_en_mix", "lovelace_units", "timezone_non_vn", "first_person", "race"],
      prompt=("first come first serve: Aiko, Bruno, Chen mua slot giá 15000000 lovelace, deadline 2027-05-05 12:00 "
              "UTC+9, tiền về cho tôi (Dara)."),
      spec={"roles": {"seller": "Dara", "b1": "Aiko", "b2": "Bruno", "b3": "Chen"}, "buyers": ["b1", "b2", "b3"],
            "price": 15, "offer_until": "2027-05-05T12:00+09:00"},
      fact_sheet=[], adversarial_target=["lovelace_units", "non_vn_timezone"], author_note="Giá cho bằng lovelace."),
    C(id="v3-vi-first_come-005", language="vi", family="first_come", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["first_person", "relative_time", "race"],
      prompt=("Mình bán lại 1 vé xem phim 12 ADA, ai trong nhóm (Hà, Kỳ, Sương) chuyển trước thì được, trong vòng 3 "
              "ngày kể từ hôm nay. Tiền về mình (Duy)."),
      spec={"roles": {"seller": "Duy", "b1": "Hà", "b2": "Kỳ", "b3": "Sương"}, "buyers": ["b1", "b2", "b3"],
            "price": 12, "offer_until": "2027-06-04T23:59" + VN},
      fact_sheet=[{"topic": "hôm nay là ngày nào", "answer": "Hôm nay là 01/06/2027; hạn là 23:59 ngày 04/06/2027 giờ VN."}],
      adversarial_target=["relative_to_today"], author_note="'hôm nay' không xác định."),

    # ------------------------------------------------------------------ zero-coupon bond
    C(id="v3-en-zero_coupon_bond-001", language="en", family="zero_coupon_bond", info_mode="complete",
      expected_behavior="converge", phenomena=["long_document", "bullet_list", "thousands_separator", "noise"],
      prompt=("Zero-coupon bond, term sheet\nInvestor: Alice. Issuer: Bob.\nPurchase: Alice deposits 1,000 ADA by "
              "2027-05-01 12:00 UTC; it goes straight to Bob.\nMaturity: Bob deposits 1,050 ADA by 2027-11-01 12:00 UTC, "
              "paid to Alice.\nDefault: if Bob doesn't pay, just close; nothing can be recovered on-chain.\nGoverning "
              "law and disclosures: see appendix (not part of the contract)."),
      spec={"roles": {"investor": "Alice", "issuer": "Bob"}, "price": 1000, "buy_by": "2027-05-01T12:00" + Z,
            "payments": [{"by": "2027-11-01T12:00" + Z, "amount": 1050}]},
      fact_sheet=[], adversarial_target=["money_direction_flips", "no_fake_refund"], author_note="Chiều tiền đảo ở bước hai."),
    C(id="v3-vi-zero_coupon_bond-002", language="vi", family="zero_coupon_bond", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "typo", "numbers_in_words", "long_horizon"],
      prompt=("Tôi (Hưng Thịnh) phát hành trái phiếu chiết khấu: nhà đầu tư Uyên nạp 950 ADA trước 09:00 ngày 01/07/2027 "
              "(UTC+7), tiền chuyển cho tôi ngay. Đến 09:00 ngày 01/07/2028 tôi phải nạp một nghìn ADA để trả Uyên. Tôi "
              "khônng nạp thì hợp đồng đóng."),
      spec={"roles": {"investor": "Uyên", "issuer": "Hưng Thịnh"}, "price": 950, "buy_by": "2027-07-01T09:00" + VN,
            "payments": [{"by": "2028-07-01T09:00" + VN, "amount": 1000}]},
      fact_sheet=[], adversarial_target=["first_person_is_issuer"], author_note="Người dùng là bên phát hành."),
    C(id="v3-vi-zero_coupon_bond-003", language="vi", family="zero_coupon_bond", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["vi_en_mix", "terse", "relative_time", "first_person"],
      prompt="Zero-coupon: Priya mua 480 ADA, tôi repay 500 ADA sau 6 tháng.",
      spec={"roles": {"investor": "Priya", "issuer": "Marco"}, "price": 480, "buy_by": "2027-03-01T00:00" + Z,
            "payments": [{"by": "2027-09-01T00:00" + Z, "amount": 500}]},
      fact_sheet=[{"topic": "tên tôi", "answer": "Marco."}, {"topic": "hạn mua", "answer": "Trước 00:00 UTC ngày 01/03/2027."},
                  {"topic": "sau 6 tháng", "answer": "Tính từ hạn mua: trả trước 00:00 UTC ngày 01/09/2027."},
                  {"topic": "không trả", "answer": "Đóng hợp đồng."}],
      adversarial_target=["relative_from_unclear_anchor", "missing_deadlines"], author_note="Thiếu gần hết."),
    C(id="v3-vi-zero_coupon_bond-004", language="vi", family="zero_coupon_bond", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "percentage", "relative_time"],
      prompt="Nhà đầu tư Tín mua trái phiếu của tôi 2000 ADA, sau 1 năm tôi trả lại kèm lãi 8%.",
      spec={"roles": {"investor": "Tín", "issuer": "Nam Phong"}, "price": 2000, "buy_by": "2027-04-01T23:59" + VN,
            "payments": [{"by": "2028-04-01T23:59" + VN, "amount": 2160}]},
      fact_sheet=[{"topic": "tên tôi", "answer": "Nam Phong."}, {"topic": "hạn mua", "answer": "23:59 ngày 01/04/2027 giờ VN."},
                  {"topic": "sau 1 năm", "answer": "23:59 ngày 01/04/2028 giờ VN."},
                  {"topic": "tiền mua", "answer": "Chuyển ngay cho tôi."}],
      adversarial_target=["percentage_arithmetic", "missing_deadlines"], author_note="Phải tính 2 160."),

    # ------------------------------------------------------------------ coupon bond
    C(id="v3-vi-coupon_bond-001", language="vi", family="coupon_bond", info_mode="conflict",
      expected_behavior="converge", phenomena=["first_person", "self_correction", "five_whens"],
      prompt=("Tôi cần phát hành trái phiếu nhỏ. Tôi là bên phát hành (role: AnBinh). Nhà đầu tư Hưng nạp 500 ADA "
              "trước 10/02/2027, số tiền chuyển luôn cho tôi. Tôi trả lãi 10 ADA mỗi quý, 4 kỳ, kỳ đầu hạn 10/05/2027; "
              "kỳ cuối trả lãi cộng 500 ADA gốc. Kỳ nào tôi không nạp đúng hạn thì dừng. À sửa lại: lãi là 12 ADA mỗi "
              "kỳ chứ không phải 10."),
      spec={"roles": {"investor": "Hưng", "issuer": "AnBinh"}, "price": 500, "buy_by": "2027-02-10T23:59" + VN,
            "payments": [{"by": "2027-05-10T23:59" + VN, "amount": 12}, {"by": "2027-08-10T23:59" + VN, "amount": 12},
                         {"by": "2027-11-10T23:59" + VN, "amount": 12}, {"by": "2028-02-10T23:59" + VN, "amount": 512}]},
      fact_sheet=[{"topic": "giờ", "answer": "23:59 giờ VN cho mọi hạn."},
                  {"topic": "các kỳ sau", "answer": "Ngày 10 của tháng 8, 11/2027 và 02/2028."}],
      adversarial_target=["late_correction", "fourth_deadline"], author_note="Đính chính cuối tin; 5 When lồng nhau."),
    C(id="v3-en-coupon_bond-002", language="en", family="coupon_bond", info_mode="complete", expected_behavior="converge",
      phenomena=["long_document", "bullet_list", "thousands_separator"],
      prompt=("Bond term sheet\n- Investor Felix pays 2,000 ADA by 2027-01-15 00:00 UTC; it goes to the issuer, Nadia\n"
              "- Coupons of 60 ADA on 2027-07-15 and 2028-01-15\n- On 2028-07-15 Nadia pays the last 60 ADA coupon plus the "
              "2,000 ADA principal\n- All times 00:00 UTC; any missed payment ends the contract\n- Rating, listing and "
              "tax treatment are outside the contract"),
      spec={"roles": {"investor": "Felix", "issuer": "Nadia"}, "price": 2000, "buy_by": "2027-01-15T00:00" + Z,
            "payments": [{"by": "2027-07-15T00:00" + Z, "amount": 60}, {"by": "2028-01-15T00:00" + Z, "amount": 60},
                         {"by": "2028-07-15T00:00" + Z, "amount": 2060}]},
      fact_sheet=[], adversarial_target=["third_deadline", "noise_in_spec"], author_note="Kỳ cuối cộng gốc."),
    C(id="v3-vi-coupon_bond-003", language="vi", family="coupon_bond", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "percentage", "relative_time", "terse", "typo"],
      prompt="trái phiếu 1000 ADA, lải 5%/năm trả hằng năm, kỳ hạn 3 năm, nhà đầu tư là Khang, tôi phát hành",
      spec={"roles": {"investor": "Khang", "issuer": "SaoMai"}, "price": 1000, "buy_by": "2027-01-10T23:59" + VN,
            "payments": [{"by": "2028-01-10T23:59" + VN, "amount": 50}, {"by": "2029-01-10T23:59" + VN, "amount": 50},
                         {"by": "2030-01-10T23:59" + VN, "amount": 1050}]},
      fact_sheet=[{"topic": "tôi là ai", "answer": "Công ty Sao Mai, role SaoMai."},
                  {"topic": "hạn mua", "answer": "23:59 ngày 10/01/2027 giờ VN."},
                  {"topic": "các kỳ trả", "answer": "23:59 ngày 10/01 các năm 2028, 2029, 2030; kỳ cuối kèm gốc."}],
      adversarial_target=["percentage_arithmetic", "third_deadline", "missing_deadlines"], author_note="Kỳ hạn dài nhiều năm."),
    C(id="v3-en-coupon_bond-004", language="en", family="coupon_bond", info_mode="ambiguous",
      expected_behavior="ask_then_converge", phenomena=["first_person", "relative_time"],
      prompt=("Bond: Lena pays 800 ADA to me (Kurt) when she buys; I pay 20 ADA quarterly for a year and return the "
              "800 at the end. Purchase by March 1, 2027."),
      spec={"roles": {"investor": "Lena", "issuer": "Kurt"}, "price": 800, "buy_by": "2027-03-01T12:00" + Z,
            "payments": [{"by": "2027-06-01T12:00" + Z, "amount": 20}, {"by": "2027-09-01T12:00" + Z, "amount": 20},
                         {"by": "2027-12-01T12:00" + Z, "amount": 20}, {"by": "2028-03-01T12:00" + Z, "amount": 820}]},
      fact_sheet=[{"topic": "time / timezone", "answer": "12:00 UTC for every date."},
                  {"topic": "quarterly dates", "answer": "June 1, Sep 1, Dec 1 2027 and Mar 1 2028; the last includes the 800."}],
      adversarial_target=["fourth_deadline", "relative_from_unclear_anchor"], author_note="Phải hỏi ngày từng kỳ."),
    C(id="v3-vi-coupon_bond-005", language="vi", family="coupon_bond", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", phenomena=["first_person", "conflict_numbers", "percentage", "numbers_in_words"],
      prompt=("Trái phiếu: nhà đầu tư Lam nạp 400 ADA trước 23:59 ngày 01/03/2027 giờ VN, chuyển cho tôi (Quế). Lãi "
              "mỗi kỳ hai mươi lăm ADA, tức 5% trên 400 ADA, trả 2 kỳ vào 23:59 ngày 01/09/2027 và 01/03/2028; kỳ cuối "
              "trả thêm gốc."),
      spec={"roles": {"investor": "Lam", "issuer": "Quế"}, "price": 400, "buy_by": "2027-03-01T23:59" + VN,
            "payments": [{"by": "2027-09-01T23:59" + VN, "amount": 20}, {"by": "2028-03-01T23:59" + VN, "amount": 420}]},
      fact_sheet=[{"topic": "lãi mỗi kỳ", "answer": "20 ADA (5%) là đúng."}],
      adversarial_target=["conflict_ignored"], author_note="25 ADA mâu thuẫn với 5% của 400."),

    # ------------------------------------------------------------------ split
    C(id="v3-vi-split-001", language="vi", family="split", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "long_document", "bullet_list", "percentage", "notify_release", "noise"],
      prompt=("Chia doanh thu show diễn (theo biên bản):\n- Bầu show Kiều (tôi) nạp 1.005 ADA trước 23:00 ngày 30/04/2027 "
              "(giờ VN)\n- Sau khi nạp, bất kỳ ai bấm 'chia tiền' trước 23:00 ngày 07/05/2027 thì chia: ca sĩ Hà 40%, ban "
              "nhạc Sóng 30%, kỹ thuật ánh sáng Phong 20%, tôi 10%\n- Không ai bấm thì hoàn hết cho tôi\n- Ghi chú: hợp "
              "đồng biểu diễn bằng giấy đã ký ngày 01/03, không liên quan"),
      spec={"roles": {"payer": "Kiều", "ha": "Hà", "song": "Sóng", "phong": "Phong"}, "deposit_by": "2027-04-30T23:00" + VN,
            "trigger": "notify", "trigger_by": "2027-05-07T23:00" + VN,
            "shares": [{"role": "ha", "amount": 402}, {"role": "song", "amount": "301.5"}, {"role": "phong", "amount": 201},
                       {"role": "payer", "amount": "100.5"}]},
      fact_sheet=[], adversarial_target=["notify_correct_use", "percentage_arithmetic", "payer_is_recipient"],
      author_note="Người nạp cũng nhận 10%; 1.005 dấu chấm kiểu Việt; phần trăm ra số lẻ."),
    C(id="v3-en-split-002", language="en", family="split", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "bullet_list", "percentage", "decimal", "self_correction", "notify_release"],
      prompt=("Prize pool split:\n- I (Org) fund 250 ADA by 2027-08-20 23:59 UTC\n- shares: Ana 40%, Bo 30%, Cy 15%, "
              "Di 15%; correction: make it Ana 50%, Bo 25%, Cy 12.5%, Di 12.5%\n- anyone can trigger the payout before "
              "2027-08-31 23:59 UTC; if nobody does, it comes back to me"),
      spec={"roles": {"payer": "Org", "ana": "Ana", "bo": "Bo", "cy": "Cy", "di": "Di"},
            "deposit_by": "2027-08-20T23:59" + Z, "trigger": "notify", "trigger_by": "2027-08-31T23:59" + Z,
            "shares": [{"role": "ana", "amount": 125}, {"role": "bo", "amount": "62.5"}, {"role": "cy", "amount": "31.25"},
                       {"role": "di", "amount": "31.25"}]},
      fact_sheet=[], adversarial_target=["late_correction", "decimal_amount"], author_note="Đính chính tỷ lệ; số lẻ 31,25."),
    C(id="v3-vi-split-003", language="vi", family="split", info_mode="missing", expected_behavior="ask_then_converge",
      phenomena=["first_person", "numbers_in_words", "typo", "time_release"],
      prompt=("Tôi nạp sáu trăm ADA, đến 08:00 ngày 01/10/2027 (giờ VN) thì chia đều cho 4 nguời An, Bình, Châu, Dũng, "
              "không cần ai bấm."),
      spec={"roles": {"payer": "Yên", "an": "An", "binh": "Bình", "chau": "Châu", "dung": "Dũng"},
            "deposit_by": "2027-09-25T23:59" + VN, "trigger": "time", "release_at": "2027-10-01T08:00" + VN,
            "shares": [{"role": r, "amount": 150} for r in ("an", "binh", "chau", "dung")]},
      fact_sheet=[{"topic": "tên tôi", "answer": "Yên."}, {"topic": "hạn nạp", "answer": "23:59 ngày 25/09/2027 giờ VN."}],
      adversarial_target=["notify_early_release", "missing_deadlines"], author_note="Trả theo thời gian, không dùng Notify."),
    C(id="v3-en-split-004", language="en", family="split", info_mode="missing", expected_behavior="ask_then_converge",
      phenomena=["vi_en_mix", "terse", "percentage", "first_person", "notify_release", "relative_time"],
      prompt="Commission split: 70% cho agent Leo, 20% to agency Nova, 10% to me.",
      spec={"roles": {"payer": "Rae", "leo": "Leo", "nova": "Nova"}, "deposit_by": "2027-06-01T23:59" + Z,
            "trigger": "notify", "trigger_by": "2027-06-08T23:59" + Z,
            "shares": [{"role": "leo", "amount": 630}, {"role": "nova", "amount": 180}, {"role": "payer", "amount": 90}]},
      fact_sheet=[{"topic": "who pays / total", "answer": "I'm Rae and I deposit 900 ADA."},
                  {"topic": "deadlines", "answer": "I deposit by 2027-06-01 23:59 UTC; anyone can trigger the split within a week after that, by 2027-06-08 23:59 UTC."},
                  {"topic": "nobody triggers", "answer": "Refund me."}],
      adversarial_target=["missing_most_facts", "payer_is_recipient"], author_note="Thiếu tổng tiền và hạn."),
    C(id="v3-vi-split-005", language="vi", family="split", info_mode="missing", expected_behavior="ask_then_converge",
      phenomena=["no_diacritics", "terse", "notify_release"],
      prompt="chia tien thuong cuoi nam 120 ADA cho 4 ban Thu, Ha, Linh, Minh, Thu duoc gap doi moi nguoi con lai",
      spec={"roles": {"payer": "CongTy", "thu": "Thu", "ha": "Ha", "linh": "Linh", "minh": "Minh"},
            "deposit_by": "2027-12-20T23:59" + VN, "trigger": "notify", "trigger_by": "2027-12-31T23:59" + VN,
            "shares": [{"role": "thu", "amount": 48}, {"role": "ha", "amount": 24}, {"role": "linh", "amount": 24},
                       {"role": "minh", "amount": 24}]},
      fact_sheet=[{"topic": "ai nạp", "answer": "Công ty, role CongTy."},
                  {"topic": "hạn", "answer": "Nạp trước 23:59 20/12/2027; ai cũng bấm chia được trước 23:59 31/12/2027, giờ VN."},
                  {"topic": "không ai bấm", "answer": "Hoàn lại công ty."}],
      adversarial_target=["ratio_arithmetic", "no_diacritics_names"], author_note="Thu 48, còn lại 24."),
    C(id="v3-vi-split-006", language="vi", family="split", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", phenomena=["first_person", "ambiguous_pronoun", "unsupported_extra", "notify_release"],
      prompt=("Tôi (Khải) nạp 90 ADA trước 23:59 ngày 05/05/2027 giờ VN, rồi ai cũng bấm 'chia' được trước 23:59 ngày "
              "12/05/2027: Mạnh 60 ADA, bên kia (anh Tuấn) 30 ADA; không ai bấm thì trả tôi. Chia xong thì tự đổi phần "
              "của Tuấn sang USDT giúp mình."),
      spec={"roles": {"payer": "Khải", "manh": "Mạnh", "tuan": "Tuấn"}, "deposit_by": "2027-05-05T23:59" + VN,
            "trigger": "notify", "trigger_by": "2027-05-12T23:59" + VN,
            "shares": [{"role": "manh", "amount": 60}, {"role": "tuan", "amount": 30}]},
      fact_sheet=[{"topic": "nếu không đổi được USDT", "answer": "Thì cứ chuyển ADA cho Tuấn."}],
      adversarial_target=["unsupported_extra_silently_dropped"], author_note="Đổi sang USDT không làm được trong hợp đồng."),

    # ------------------------------------------------------------------ collateral loan
    C(id="v3-en-collateral_loan-001", language="en", family="collateral_loan", info_mode="complete",
      expected_behavior="converge", phenomena=["long_document", "bullet_list", "token_policy", "account_transfer"],
      prompt=("Collateralized loan, term sheet:\n- Borrower Yuki locks 500 CAT (policy " + P_CAT + ", token name CAT) by "
              "2027-02-01 00:00 UTC\n- Lender Omar then sends 300 ADA by 2027-02-03 00:00 UTC, paid to Yuki\n- Yuki repays "
              "315 ADA by 2027-05-01 00:00 UTC: Omar gets the 315, Yuki gets her CAT back\n- If Yuki doesn't repay, Omar "
              "keeps the CAT\n- If Omar never lends, Yuki's CAT goes back to her\n- Credit checks happen offline"),
      spec={"roles": {"borrower": "Yuki", "lender": "Omar"}, "tokens": {"CAT": {"policy": P_CAT, "name": "CAT"}},
            "collateral_token": "CAT", "collateral": 500, "principal": 300, "repay": 315,
            "collateral_by": "2027-02-01T00:00" + Z, "fund_by": "2027-02-03T00:00" + Z, "repay_by": "2027-05-01T00:00" + Z},
      fact_sheet=[], adversarial_target=["collateral_to_lender", "token_identity", "third_deadline"],
      author_note="Hai token; vỡ nợ thì tài sản thế chấp sang bên cho vay."),
    C(id="v3-vi-collateral_loan-002", language="vi", family="collateral_loan", info_mode="complete",
      expected_behavior="converge", phenomena=["first_person", "bullet_list", "typo", "relative_time", "token_policy"],
      prompt=("Cầm cố token:\n- tôi (Tùng) khóa 1000 token VNDC (policy " + P_VNDC + ", tên VNDC) trước 23:59 ngày "
              "01/03/2027 (giờ VN)\n- chị Hảo cho vay 400 ADA, nạp trước 23:59 ngày 03/03/2027, chuyễn cho tôi ngay\n- hạn "
              "trả là 30 ngày sau hạn giải ngân (tức 23:59 ngày 02/04/2027): tôi trả 420 ADA thì chị Hảo nhận tiền, tôi lấy "
              "lại VNDC\n- không trả đúng hạn thì VNDC thuộc về chị Hảo; chị Hảo không cho vay thì tôi lấy lại VNDC"),
      spec={"roles": {"borrower": "Tùng", "lender": "Hảo"}, "tokens": {"VNDC": {"policy": P_VNDC, "name": "VNDC"}},
            "collateral_token": "VNDC", "collateral": 1000, "principal": 400, "repay": 420,
            "collateral_by": "2027-03-01T23:59" + VN, "fund_by": "2027-03-03T23:59" + VN, "repay_by": "2027-04-02T23:59" + VN},
      fact_sheet=[], adversarial_target=["collateral_to_lender", "relative_chain"], author_note="Người dùng là bên vay."),
    C(id="v3-vi-collateral_loan-003", language="vi", family="collateral_loan", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "first_person", "relative_time", "terse"],
      prompt="minh vay 200 ADA cua Quan, the chap 50 token LAND, tra 210 ADA sau 2 thang",
      spec={"roles": {"borrower": "Nhu", "lender": "Quan"}, "tokens": {"LAND": {"policy": P_LAND, "name": "LAND"}},
            "collateral_token": "LAND", "collateral": 50, "principal": 200, "repay": 210,
            "collateral_by": "2027-06-01T23:59" + VN, "fund_by": "2027-06-03T23:59" + VN, "repay_by": "2027-08-03T23:59" + VN},
      fact_sheet=[{"topic": "tên mình", "answer": "Nhu."}, {"topic": "token LAND", "answer": "Policy " + P_LAND + ", tên LAND."},
                  {"topic": "các hạn", "answer": "Mình khóa LAND trước 23:59 01/06/2027; Quan giải ngân trước 23:59 03/06/2027; trả trước 23:59 03/08/2027; giờ VN."},
                  {"topic": "không trả", "answer": "Quan lấy 50 LAND."},
                  {"topic": "Quan không cho vay", "answer": "Trả lại LAND cho mình."}],
      adversarial_target=["missing_most_facts", "collateral_to_lender"], author_note="Thiếu policy và hạn."),
    C(id="v3-en-collateral_loan-004", language="en", family="collateral_loan", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", phenomena=["vi_en_mix", "conflict_numbers", "token_policy"],
      prompt=("Loan with collateral: Zoe khóa 100 GEM (policy " + P_GEM + ", name GEM) by 2027-07-01 12:00 UTC, Ivan "
              "lends 250 ADA by 2027-07-02 12:00 UTC (paid to Zoe), Zoe repays 260 ADA by 2027-09-01 12:00 UTC. Default: "
              "Ivan gets the collateral. Note: collateral là 120 GEM."),
      spec={"roles": {"borrower": "Zoe", "lender": "Ivan"}, "tokens": {"GEM": {"policy": P_GEM, "name": "GEM"}},
            "collateral_token": "GEM", "collateral": 120, "principal": 250, "repay": 260,
            "collateral_by": "2027-07-01T12:00" + Z, "fund_by": "2027-07-02T12:00" + Z, "repay_by": "2027-09-01T12:00" + Z},
      fact_sheet=[{"topic": "collateral amount", "answer": "120 GEM is correct."},
                  {"topic": "Ivan never lends", "answer": "Zoe gets her GEM back."}],
      adversarial_target=["conflict_ignored"], author_note="100 và 120 GEM."),
    C(id="v3-vi-collateral_loan-005", language="vi", family="collateral_loan", info_mode="conflict",
      expected_behavior="converge", phenomena=["first_person", "ambiguous_pronoun", "self_correction", "token_policy"],
      prompt=("Mình (Hiếu) thế chấp 30 token BOOK (policy " + P_BOOK + ", tên BOOK) trước 23:59 ngày 10/08/2027 giờ VN, "
              "bên kia (chị Vy) cho vay 150 ADA trước 23:59 ngày 12/08/2027, tiền chuyển cho mình luôn. Mình trả 160 ADA "
              "trước 23:59 ngày 12/10/2027. Quá hạn thì bên kia lấy 30 BOOK, chị Vy không cho vay thì mình lấy lại BOOK. "
              "À sửa: mình trả 165 ADA chứ không phải 160."),
      spec={"roles": {"borrower": "Hiếu", "lender": "Vy"}, "tokens": {"BOOK": {"policy": P_BOOK, "name": "BOOK"}},
            "collateral_token": "BOOK", "collateral": 30, "principal": 150, "repay": 165,
            "collateral_by": "2027-08-10T23:59" + VN, "fund_by": "2027-08-12T23:59" + VN, "repay_by": "2027-10-12T23:59" + VN},
      fact_sheet=[], adversarial_target=["late_correction", "ambiguous_pronoun"], author_note="'bên kia' là chị Vy."),

    # ------------------------------------------------------------------ deduction chosen by an inspector
    C(id="v3-vi-deduction-001", language="vi", family="deduction", info_mode="complete", expected_behavior="converge",
      phenomena=["first_person", "bullet_list", "numbers_in_words", "lovelace_units", "relative_time"],
      prompt=("Đặt cọc thuê xe máy:\n- tôi (Lực) nạp ba trăm ADA trước 07:00 ngày 01/05/2027 (giờ VN)\n- khi trả xe, "
              "nhân viên kiểm tra Vân nhập số tiền khấu trừ từ 0 đến 100 ADA, nhập theo lovelace, hạn 7 ngày sau hạn nạp "
              "(07:00 ngày 08/05/2027)\n- số khấu trừ chuyển cho cửa hàng (role: XeXanh), phần còn lại hoàn tôi\n- Vân "
              "không nhập thì hoàn đủ cho tôi"),
      spec={"roles": {"payer": "Lực", "keeper": "XeXanh", "inspector": "Vân"}, "amount": 300, "max_deduction": 100,
            "deposit_by": "2027-05-01T07:00" + VN, "decide_by": "2027-05-08T07:00" + VN, "choice": "khau_tru"},
      fact_sheet=[], adversarial_target=["choice_value_as_amount", "lovelace_units"], author_note="Giá trị chọn làm số tiền."),
    C(id="v3-en-deduction-002", language="en", family="deduction", info_mode="complete", expected_behavior="converge",
      phenomena=["long_document", "bullet_list", "lovelace_units", "noise"],
      prompt=("Equipment rental, deposit clause:\n(a) Renter Hollis deposits 500 ADA by 2027-06-01 17:00 UTC.\n(b) "
              "Inspector Quinn enters a deduction between 0 and 200 ADA, expressed in lovelace, by 2027-06-30 17:00 UTC.\n"
              "(c) The deduction goes to RentCo (role: RentCo); the rest goes back to Hollis.\n(d) If Quinn enters "
              "nothing, Hollis gets the full deposit back.\n(e) Late fees and insurance are under section 9 and are not "
              "part of this contract."),
      spec={"roles": {"payer": "Hollis", "keeper": "RentCo", "inspector": "Quinn"}, "amount": 500, "max_deduction": 200,
            "deposit_by": "2027-06-01T17:00" + Z, "decide_by": "2027-06-30T17:00" + Z, "choice": "deduction"},
      fact_sheet=[], adversarial_target=["choice_value_as_amount", "noise_in_spec"], author_note="Mục (e) là nhiễu."),
    C(id="v3-vi-deduction-003", language="vi", family="deduction", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "terse", "ambiguous_pronoun", "relative_time"],
      prompt="coc 80 ADA, ben cho thue kiem tra roi nhap tien phat toi da 30 ADA",
      spec={"roles": {"payer": "Dung", "keeper": "ChoThue", "inspector": "ChoThue"}, "amount": 80, "max_deduction": 30,
            "deposit_by": "2027-09-01T23:59" + VN, "decide_by": "2027-09-15T23:59" + VN, "choice": "tien_phat"},
      fact_sheet=[{"topic": "ai cọc, ai cho thuê", "answer": "Mình là Dung (người cọc); bên cho thuê là role ChoThue, vừa kiểm tra vừa nhận tiền phạt."},
                  {"topic": "hạn", "answer": "Cọc trước 23:59 01/09/2027; nhập tiền phạt trước 23:59 15/09/2027; giờ VN."},
                  {"topic": "đơn vị", "answer": "Nhập theo lovelace."}, {"topic": "không nhập", "answer": "Hoàn đủ cho mình."}],
      adversarial_target=["missing_most_facts", "choice_value_as_amount"], author_note="Bên kiểm tra cũng là bên nhận."),
    C(id="v3-en-deduction-004", language="en", family="deduction", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["vi_en_mix", "first_person", "timezone"],
      prompt=("Deposit 120 ADA cho studio. Inspector Mi nhập deduction tối đa 40 ADA, phần còn lại refund cho tôi (Khanh). "
              "Deposit trước 2027-10-01 12:00 UTC+7, inspection trước 2027-10-05 12:00 UTC+7."),
      spec={"roles": {"payer": "Khanh", "keeper": "Studio", "inspector": "Mi"}, "amount": 120, "max_deduction": 40,
            "deposit_by": "2027-10-01T12:00" + VN, "decide_by": "2027-10-05T12:00" + VN, "choice": "deduction"},
      fact_sheet=[{"topic": "đơn vị deduction", "answer": "Mi nhập theo lovelace."}, {"topic": "studio role", "answer": "Studio."},
                  {"topic": "không nhập", "answer": "Refund đủ cho tôi."}],
      adversarial_target=["ambiguous_units"], author_note="Không nói đơn vị nhập."),
    C(id="v3-vi-deduction-005", language="vi", family="deduction", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", phenomena=["first_person", "conflict_numbers", "lovelace_units"],
      prompt=("Cọc thuê máy quay 160 ADA của tôi (Bình An), nạp trước 23:59 ngày 01/11/2027 giờ VN. Kỹ thuật viên Đông "
              "nhập tiền khấu trừ tối đa 50 ADA (theo lovelace) trước 23:59 ngày 07/11/2027, nhưng không quá 1/4 tiền cọc. "
              "Khấu trừ chuyển cho cửa hàng CamShop, còn lại trả tôi. Không nhập thì trả đủ."),
      spec={"roles": {"payer": "Bình An", "keeper": "CamShop", "inspector": "Đông"}, "amount": 160, "max_deduction": 40,
            "deposit_by": "2027-11-01T23:59" + VN, "decide_by": "2027-11-07T23:59" + VN, "choice": "khau_tru"},
      fact_sheet=[{"topic": "mức tối đa", "answer": "40 ADA (1/4 tiền cọc) là đúng."}],
      adversarial_target=["conflict_ignored"], author_note="50 mâu thuẫn với 1/4 của 160."),

    # ------------------------------------------------------------------ matching donation
    C(id="v3-vi-matching-001", language="vi", family="matching", info_mode="complete", expected_behavior="converge",
      phenomena=["bullet_list", "typo", "numbers_in_words", "relative_time", "four_parties"],
      prompt=("Gây quỹ có tài trợ đối ứng:\n- Hòa góp ba mươi ADA trước 20:00 ngày 01/03/2027 (giờ VN)\n- Kim góp 50 ADA, "
              "hạn 2 ngày sau đó (20:00 ngày 03/03/2027)\n- sau đó nhà tài trợ Sao Việt (role: SaoViet) góp bằng tổng hai "
              "người nhưng tối đa 60 ADA, trước 20:00 ngày 05/03/2027\n- đủ cả thì chuyển hết cho quỹ Mầm Xanh (role: "
              "MamXanh); thiếu bước nào thì hoàn người đã gópp"),
      spec={"roles": {"hoa": "Hòa", "kim": "Kim", "sponsor": "SaoViet", "beneficiary": "MamXanh"},
            "donors": [{"role": "hoa", "amount": 30, "by": "2027-03-01T20:00" + VN},
                       {"role": "kim", "amount": 50, "by": "2027-03-03T20:00" + VN}],
            "cap": 60, "sponsor_by": "2027-03-05T20:00" + VN},
      fact_sheet=[], adversarial_target=["cap_applies", "if_let"], author_note="Tổng 80 vượt trần 60."),
    C(id="v3-en-matching-002", language="en", family="matching", info_mode="complete", expected_behavior="converge",
      phenomena=["long_document", "bullet_list", "self_correction", "five_parties"],
      prompt=("Campaign page, matching rules:\n- Ada gives 100 ADA by 2027-04-01 12:00 UTC, then Ben 120 ADA by "
              "2027-04-02 12:00 UTC, then Cal 80 ADA by 2027-04-03 12:00 UTC\n- The sponsor (role: MatchFund) then matches "
              "the total 1:1, capped at 400 ADA (sorry, the cap is 500 ADA), by 2027-04-05 12:00 UTC\n- Everything goes "
              "to the school (role: School)\n- If any step is missed, whoever already gave is refunded\n- Donor names "
              "are shown on our website (outside the contract)"),
      spec={"roles": {"ada": "Ada", "ben": "Ben", "cal": "Cal", "sponsor": "MatchFund", "beneficiary": "School"},
            "donors": [{"role": "ada", "amount": 100, "by": "2027-04-01T12:00" + Z},
                       {"role": "ben", "amount": 120, "by": "2027-04-02T12:00" + Z},
                       {"role": "cal", "amount": 80, "by": "2027-04-03T12:00" + Z}],
            "cap": 500, "sponsor_by": "2027-04-05T12:00" + Z},
      fact_sheet=[], adversarial_target=["late_correction", "cap_not_reached"], author_note="Tổng 300 dưới trần."),
    C(id="v3-vi-matching-003", language="vi", family="matching", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["no_diacritics", "terse"],
      prompt="goi von tu thien: 2 nguoi gop roi nha tai tro gop bang tong do, toi da 100 ADA, tien chuyen cho chua Phuoc Hai",
      spec={"roles": {"tam": "Tam", "yen": "Yen", "sponsor": "NhaTaiTro", "beneficiary": "PhuocHai"},
            "donors": [{"role": "tam", "amount": 40, "by": "2027-02-10T23:59" + VN},
                       {"role": "yen", "amount": 50, "by": "2027-02-12T23:59" + VN}],
            "cap": 100, "sponsor_by": "2027-02-15T23:59" + VN},
      fact_sheet=[{"topic": "2 người là ai, góp bao nhiêu", "answer": "Tam góp 40 ADA trước, rồi Yen góp 50 ADA."},
                  {"topic": "hạn", "answer": "Tam trước 23:59 10/02, Yen trước 23:59 12/02, nhà tài trợ trước 23:59 15/02/2027; giờ VN."},
                  {"topic": "role", "answer": "Nhà tài trợ: NhaTaiTro; chùa: PhuocHai."},
                  {"topic": "thiếu bước", "answer": "Hoàn cho người đã góp."}],
      adversarial_target=["missing_most_facts"], author_note="Thiếu gần hết."),
    C(id="v3-vi-matching-004", language="vi", family="matching", info_mode="missing",
      expected_behavior="ask_then_converge", phenomena=["first_person", "ambiguous_pronoun", "relative_time"],
      prompt=("Chúng tôi (nhóm Hy Vọng, role HyVong) góp 70 ADA, rồi công ty Đại Dương (role DaiDuong) góp bằng số đó, "
              "tối đa 100 ADA, sau 3 ngày. Tất cả chuyển cho trường làng (role TruongLang)."),
      spec={"roles": {"hv": "HyVong", "sponsor": "DaiDuong", "beneficiary": "TruongLang"},
            "donors": [{"role": "hv", "amount": 70, "by": "2027-02-01T23:59" + VN}],
            "cap": 100, "sponsor_by": "2027-02-04T23:59" + VN},
      fact_sheet=[{"topic": "hạn góp", "answer": "Nhóm góp trước 23:59 01/02/2027; 'sau 3 ngày' là Đại Dương góp trước 23:59 04/02/2027; giờ VN."},
                  {"topic": "Đại Dương không góp", "answer": "Hoàn lại cho nhóm."}],
      adversarial_target=["relative_from_unclear_anchor", "narrator_group"], author_note="'chúng tôi' là một role."),

    # ------------------------------------------------------------------ infeasible or out of scope
    C(id="v3-vi-infeasible-001", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person", "percentage"],
      prompt=("Mình cần hợp đồng gửi tiết kiệm: gửi 200 ADA, lãi kép 0,5%/ngày tự động cộng, rút lúc nào cũng được, và "
              "hợp đồng tự gửi email nhắc khi gần đến hạn."),
      spec={"reason": "no party funds the interest; unbounded daily compounding; no email from a contract"},
      fact_sheet=[], adversarial_target=["infeasible_should_be_unsupported"], author_note="Ba phần đều không làm được."),
    C(id="v3-en-infeasible-002", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt=("Make a contract where I bet 100 ADA against Ken on the BTC/USD price: if BTC is above 100k USD on "
              "2027-12-31, I get his 100 ADA, otherwise he gets mine. Pull the price automatically."),
      spec={"reason": "needs a price oracle, which the system does not support"},
      fact_sheet=[], adversarial_target=["oracle_request"], author_note="Cần oracle giá."),
    C(id="v3-vi-infeasible-003", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt=("Ký quỹ 50 ADA giữa tôi và Thắng như bình thường, nhưng sau khi xong thì xóa hết lịch sử giao dịch trên "
              "chuỗi để không ai tra được."),
      spec={"reason": "on-chain history cannot be deleted"}, fact_sheet=[],
      adversarial_target=["infeasible_should_be_unsupported"], author_note="Phần ký quỹ làm được nhưng yêu cầu chính thì không."),
    C(id="v3-en-infeasible-004", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt=("Escrow 300 ADA from buyer to me, but only after the contract verifies both of our passports (KYC) by "
              "scanning them."),
      spec={"reason": "identity documents cannot be verified by a Marlowe contract"}, fact_sheet=[],
      adversarial_target=["infeasible_should_be_unsupported"], author_note="KYC ngoài chuỗi."),
    C(id="v3-vi-infeasible-005", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt=("Hợp đồng vay 100 ADA giữa mình và Toản, hạn trả 01/06/2027. Nếu Toản gọi điện xin thì mình được sửa hạn "
              "trả trong hợp đồng sau khi nó đã chạy."),
      spec={"reason": "a running Marlowe contract's deadlines cannot be edited; phone consent is off-chain"}, fact_sheet=[],
      adversarial_target=["infeasible_should_be_unsupported"], author_note="Sửa hợp đồng đang chạy."),
    C(id="v3-en-infeasible-006", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person", "terse"],
      prompt="Hold 500 ADA from my client forever until I decide to release it. No deadline at all.",
      spec={"reason": "Marlowe requires a timeout on every wait; 'forever, no deadline' cannot be expressed"},
      fact_sheet=[], adversarial_target=["infeasible_should_be_unsupported"], author_note="Không có hạn."),
    C(id="v3-vi-infeasible-007", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt=("Khách nạp 2 triệu đồng tương đương ADA, hợp đồng tự chuyển tiền vào tài khoản Vietcombank của tôi khi "
              "khách xác nhận."),
      spec={"reason": "a contract cannot pay into a bank account; fiat conversion needs an oracle"}, fact_sheet=[],
      adversarial_target=["infeasible_should_be_unsupported"], author_note="Ngoài chuỗi, cần tỷ giá."),
    C(id="v3-en-infeasible-008", language="en", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt="Rent contract: my tenant pays me 400 ADA on the 1st of every month, forever, starting March 2027.",
      spec={"reason": "unbounded recurring payments cannot be written as a finite Marlowe contract"}, fact_sheet=[],
      adversarial_target=["infeasible_should_be_unsupported"], author_note="Lặp vô hạn."),
    C(id="v3-vi-infeasible-009", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt=("Bảo hiểm mưa: tôi đóng 20 ADA, nếu ngày 15/07/2027 ở Hà Nội mưa trên 50 mm thì bên bảo hiểm Hà An trả "
              "tôi 200 ADA, lượng mưa lấy tự động từ trang khí tượng."),
      spec={"reason": "needs a weather oracle, which the system does not support"}, fact_sheet=[],
      adversarial_target=["oracle_request"], author_note="Cần oracle thời tiết."),
    C(id="v3-vi-infeasible-010", language="vi", family="infeasible", info_mode="infeasible",
      expected_behavior="reject_unsupported", phenomena=["first_person"],
      prompt="Làm hợp đồng ký quỹ 70 ADA với Hương nhưng không ai ngoài hai đứa được thấy số tiền và tên người nhận.",
      spec={"reason": "Marlowe contracts and their state are public on-chain"}, fact_sheet=[],
      adversarial_target=["infeasible_should_be_unsupported"], author_note="Quyền riêng tư."),
]
