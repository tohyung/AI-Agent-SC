"""Dataset v5 cases, part B (written by hand, 2026-11-12, docs/E7-Dataset-v5-Design.md).

milestone (last two), crowdfunding, third_party, rental_deposit, cancellation_fee, installment.
"""

VN = "+07:00"
UTC = "+00:00"
BERLIN_SUMMER = "+02:00"


def C(**kw):
    return kw


CASES = [
    # ------------------------------------------------------------------ milestone (part 2)
    C(id="v5-vi-milestone-003", language="vi", family="milestone", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "relative_time", "time_of_day"],
      prompt=("mình thuê nhóm thợ của anh Đào sơn lại quán, 3 đợt mỗi đợt 50 ADA, mình nạp đủ trước khi khởi "
              "công. Đợt 1 duyệt trước 18:00 ngày 10/03/2027, các đợt sau cách nhau 1 tuần. Đợt nào mình ưng "
              "thì duyệt cho anh Đào nhận tiền đợt đó; một đợt quá hạn chưa duyệt thì dừng luôn, tiền còn lại "
              "về mình."),
      spec={"roles": {"client": "Nhiên", "worker": "Đào"}, "deposit_by": "2027-03-01T08:00" + VN,
            "stages": [{"name": "dot_1", "by": "2027-03-10T18:00" + VN, "amount": 50},
                       {"name": "dot_2", "by": "2027-03-17T18:00" + VN, "amount": 50},
                       {"name": "dot_3", "by": "2027-03-24T18:00" + VN, "amount": 50}]},
      fact_sheet=[{"topic": "tên mình", "answer": "Nhiên."},
                  {"topic": "khởi công lúc nào", "answer": "08:00 ngày 01/03/2027, mình nạp 150 ADA trước giờ đó."},
                  {"topic": "múi giờ", "answer": "Giờ VN."}],
      derived=["2027-03-17", "2027-03-24"],
      adversarial_target=["unanchored_start", "weekly_offsets"],
      author_note="'trước khi khởi công' không có ngày; hai đợt sau tính bằng cộng 7 ngày."),
    C(id="v5-en-milestone-004", language="en", family="milestone", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "time_of_day", "timezone"],
      prompt=("Translation project with Xavier (translator):\n"
              "- I, Yara, deposit 750 ADA by 2027-06-01 00:00 UTC\n"
              "- chapters 1-5 approved by 2027-06-20 00:00 UTC: 250 ADA to Xavier\n"
              "- chapters 6-10 approved by 2027-07-10 00:00 UTC: 250 ADA\n"
              "- final edit approved by 2027-07-31 00:00 UTC: 250 ADA\n"
              "- a missed approval refunds only that part to me; later parts can still be approved"),
      spec={"roles": {"client": "Yara", "worker": "Xavier"}, "deposit_by": "2027-06-01T00:00" + UTC,
            "stages": [{"name": "approve_ch1_5", "by": "2027-06-20T00:00" + UTC, "amount": 250},
                       {"name": "approve_ch6_10", "by": "2027-07-10T00:00" + UTC, "amount": 250},
                       {"name": "approve_final", "by": "2027-07-31T00:00" + UTC, "amount": 250}],
            "independent": True},
      fact_sheet=[], adversarial_target=["independent_stages", "three_deadlines"],
      author_note="Ba chặng độc lập; số chương là nhiễu."),

    # ------------------------------------------------------------------ crowdfunding
    C(id="v5-vi-crowdfunding-001", language="vi", family="crowdfunding", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["time_of_day", "timezone"],
      prompt=("Lớp mình góp tiền mua quà tặng cô chủ nhiệm: Thoa góp 15 ADA trước 22:00 ngày 05/11/2027, Bằng "
              "góp 15 ADA trước 22:00 ngày 06/11/2027, Mơ góp 20 ADA trước 22:00 ngày 07/11/2027 (giờ VN). Góp "
              "đủ thì lớp trưởng Kiệt hay bất kỳ ai cũng bấm 'mua quà' được, trước 22:00 ngày 15/11/2027, tiền "
              "chuyển cho Kiệt. Không ai bấm hoặc thiếu người góp thì trả lại ai đã góp. Quà là bộ ấm trà, Kiệt "
              "sẽ đi mua giúp cả lớp."),
      spec={"roles": {"a": "Thoa", "b": "Bằng", "c": "Mơ", "beneficiary": "Kiệt"},
            "contributions": [{"role": "a", "amount": 15, "by": "2027-11-05T22:00" + VN},
                              {"role": "b", "amount": 15, "by": "2027-11-06T22:00" + VN},
                              {"role": "c", "amount": 20, "by": "2027-11-07T22:00" + VN}],
            "release_by": "2027-11-15T22:00" + VN},
      fact_sheet=[], adversarial_target=["anyone_presses", "beneficiary_also_may_press"],
      author_note="'Kiệt hay bất kỳ ai' vẫn là ai cũng bấm được."),
    C(id="v5-en-crowdfunding-002", language="en", family="crowdfunding", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person"],
      prompt=("Pooling money for a shared 3D printer: Esme puts in 120 ADA, then Dario 80 ADA, then me 100 ADA. "
              "When all three are in, the full amount goes to the seller, Ilya."),
      spec={"roles": {"a": "Esme", "b": "Dario", "c": "Fiona", "beneficiary": "Ilya"},
            "contributions": [{"role": "a", "amount": 120, "by": "2027-01-10T20:00" + UTC},
                              {"role": "b", "amount": 80, "by": "2027-01-12T20:00" + UTC},
                              {"role": "c", "amount": 100, "by": "2027-01-14T20:00" + UTC}]},
      fact_sheet=[{"topic": "your name", "answer": "Fiona."},
                  {"topic": "deadlines", "answer": "Esme by 2027-01-10 20:00 UTC, Dario by 2027-01-12 20:00 UTC, "
                                                   "me by 2027-01-14 20:00 UTC."},
                  {"topic": "if someone does not pay", "answer": "Everyone who paid gets their money back."}],
      adversarial_target=["first_person_contributor", "missing_deadlines"],
      author_note="Người dùng là người góp cuối, chưa nêu tên."),
    C(id="v5-vi-crowdfunding-003", language="vi", family="crowdfunding", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", register="chat",
      phenomena=["self_correction", "time_of_day", "timezone"],
      prompt=("Gom tiền thuê sân bóng: Tài góp 30 ADA trước 19:00 ngày 02/12/2027, Lành góp 30 ADA trước 19:00 "
              "ngày 03/12/2027 (giờ VN), đủ thì chuyển ngay 50 ADA cho chủ sân Vượng. À mà khoan, 50 hay 60 nhỉ, "
              "để mình xem lại."),
      spec={"roles": {"a": "Tài", "b": "Lành", "beneficiary": "Vượng"},
            "contributions": [{"role": "a", "amount": 30, "by": "2027-12-02T19:00" + VN},
                              {"role": "b", "amount": 30, "by": "2027-12-03T19:00" + VN}]},
      fact_sheet=[{"topic": "chuyển bao nhiêu", "answer": "Chuyển hết 60 ADA, mình ghi nhầm."},
                  {"topic": "thiếu người góp", "answer": "Trả lại ai đã góp."}],
      adversarial_target=["sum_contradicts_payout"],
      author_note="30 + 30 = 60, nhưng prompt nói chuyển 50."),
    C(id="v5-en-crowdfunding-004", language="en", family="crowdfunding", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["time_of_day", "timezone"],
      prompt=("Hackathon prize pot: Gus chips in 200 ADA by Mar 3 2027 18:00 UTC, then Orla 150 ADA by Mar 5 "
              "2027 18:00 UTC. Once both are in, anyone can press release before Mar 20 2027 18:00 UTC to send "
              "the 350 ADA to the winner, Nico. If nobody presses, both get refunded."),
      spec={"roles": {"a": "Gus", "b": "Orla", "beneficiary": "Nico"},
            "contributions": [{"role": "a", "amount": 200, "by": "2027-03-03T18:00" + UTC},
                              {"role": "b", "amount": 150, "by": "2027-03-05T18:00" + UTC}],
            "release_by": "2027-03-20T18:00" + UTC},
      fact_sheet=[], adversarial_target=["anyone_presses"],
      author_note="Ai cũng bấm được; không ai bấm thì hoàn cả hai."),

    # ------------------------------------------------------------------ third-party report
    C(id="v5-vi-third_party-001", language="vi", family="third_party", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Mua 200 kg sầu riêng của chú Bách: tôi (Cẩm) nạp 260 ADA trước 06:00 ngày 15/06/2027 giờ VN. "
              "Anh Duẩn bên kiểm định chấm độ chín thang 1 đến 10 trước 18:00 ngày 16/06/2027; từ 7 trở lên "
              "thì chuyển tiền cho chú Bách, dưới 7 thì hoàn tôi. Không chấm thì cũng hoàn tôi."),
      spec={"roles": {"payer": "Cẩm", "payee": "Bách", "reporter": "Duẩn"}, "amount": 260,
            "deposit_by": "2027-06-15T06:00" + VN, "report_by": "2027-06-16T18:00" + VN,
            "low": 1, "high": 10, "threshold": 7, "choice": "do_chin"},
      fact_sheet=[], adversarial_target=["scale_starts_at_one", "honorific_chu"],
      author_note="Thang 1–10, không bắt đầu từ 0; '200 kg' là nhiễu."),
    C(id="v5-en-third_party-002", language="en", family="third_party", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person"],
      prompt=("Pay the contractor Silas only if the inspector Tess scores the roof 80 or higher out of 100. "
              "I'm depositing 500 ADA."),
      spec={"roles": {"payer": "Willa", "payee": "Silas", "reporter": "Tess"}, "amount": 500,
            "deposit_by": "2027-04-01T12:00" + UTC, "report_by": "2027-04-08T12:00" + UTC,
            "low": 0, "high": 100, "threshold": 80, "choice": "roof_score"},
      fact_sheet=[{"topic": "your name", "answer": "Willa."},
                  {"topic": "deadlines", "answer": "I deposit by 2027-04-01 12:00 UTC; Tess scores by "
                                                   "2027-04-08 12:00 UTC."},
                  {"topic": "below 80 or no score", "answer": "Refund me."}],
      adversarial_target=["missing_deadlines", "missing_failure_branch"],
      author_note="Thiếu tên người dùng, hạn và nhánh dưới ngưỡng."),
    C(id="v5-vi-third_party-003", language="vi", family="third_party", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "vi_en_mix", "typo", "time_of_day", "timezone"],
      prompt=("Hợp đồng cho freelancer: tôi (Diễm) nạp 90 ADA trước 9:00 sáng 01/09/2027 (giờ VN), reviewer "
              "Khuyên cho điểm 0–5 trước 9:00 sáng 05/09/2027, đạt 4 điểm trở lên thì trả cho dev Bảo Long, "
              "còn lại hoặc không chấm thì hòan tiền cho tôi."),
      spec={"roles": {"payer": "Diễm", "payee": "Bảo Long", "reporter": "Khuyên"}, "amount": 90,
            "deposit_by": "2027-09-01T09:00" + VN, "report_by": "2027-09-05T09:00" + VN,
            "low": 0, "high": 5, "threshold": 4, "choice": "diem_review"},
      fact_sheet=[], adversarial_target=["two_word_name", "typo"],
      author_note="'hòan' là lỗi gõ; người nhận có tên hai chữ."),
    C(id="v5-en-third_party-004", language="en", family="third_party", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["ambiguous_pronoun", "grouped_number"],
      prompt=("Sponsor deal: our club pays 1,000 ADA to the streamer Kian if his stream hits the target. Rhea "
              "from the agency reports the viewer number, and 50 means the target is reached."),
      spec={"roles": {"payer": "OrbitClub", "payee": "Kian", "reporter": "Rhea"}, "amount": 1000,
            "deposit_by": "2027-10-01T00:00" + UTC, "report_by": "2027-10-31T00:00" + UTC,
            "low": 0, "high": 500, "threshold": 50, "choice": "viewers_k"},
      fact_sheet=[{"topic": "club role", "answer": "Role OrbitClub."},
                  {"topic": "range of the report", "answer": "Rhea reports 0 to 500 (thousands of viewers); 50 "
                                                             "or more pays Kian."},
                  {"topic": "deadlines", "answer": "We deposit by 2027-10-01 00:00 UTC; Rhea reports by "
                                                   "2027-10-31 00:00 UTC."},
                  {"topic": "below target or no report", "answer": "Refund OrbitClub."}],
      adversarial_target=["our_club_as_party", "unclear_scale"],
      author_note="'our club' là một bên; thang đo không rõ."),

    # ------------------------------------------------------------------ rental deposit
    C(id="v5-vi-rental_deposit-001", language="vi", family="rental_deposit", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Cọc thuê căn hộ: tôi (Quyên) nạp cọc 500 ADA trước 12:00 ngày 01/03/2027 (giờ VN). Khi trả "
              "nhà, chủ nhà Sinh chọn trước 12:00 ngày 01/03/2028: 0 là nhà ổn, hoàn đủ cho tôi; 1 là cần sơn "
              "lại, Sinh giữ 120 ADA; 2 là hỏng đồ, Sinh giữ 300 ADA. Sinh không chọn thì hoàn đủ cho tôi."),
      spec={"roles": {"payer": "Quyên", "keeper": "Sinh", "chooser": "Sinh"}, "amount": 500,
            "deposit_by": "2027-03-01T12:00" + VN, "decide_by": "2028-03-01T12:00" + VN,
            "choice": "tinh_trang_nha",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": 120},
                        {"value": 2, "keeper_share": 300}], "on_timeout": 0},
      fact_sheet=[], adversarial_target=["year_long_gap", "three_options"],
      author_note="Hạn chọn cách hạn nạp một năm."),
    C(id="v5-en-rental_deposit-002", language="en", family="rental_deposit", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=[],
      prompt=("Security deposit for the studio flat: Pablo, the tenant, puts down 400 ADA. Landlord Vera keeps "
              "87.5 ADA if there's damage, otherwise Pablo gets everything back."),
      spec={"roles": {"payer": "Pablo", "keeper": "Vera", "chooser": "Vera"}, "amount": 400,
            "deposit_by": "2027-05-01T00:00" + UTC, "decide_by": "2027-11-01T00:00" + UTC,
            "choice": "damage",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": "87.5"}], "on_timeout": 0},
      fact_sheet=[{"topic": "deadlines", "answer": "Pablo deposits by 2027-05-01 00:00 UTC; Vera reports by "
                                                   "2027-11-01 00:00 UTC."},
                  {"topic": "how Vera reports", "answer": "0 = no damage, 1 = damage."},
                  {"topic": "no report", "answer": "Full refund to Pablo."}],
      adversarial_target=["missing_deadlines", "missing_encoding"],
      author_note="Thiếu hạn, cách báo và nhánh không báo."),
    C(id="v5-vi-rental_deposit-003", language="vi", family="rental_deposit", info_mode="conflict",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "self_correction", "time_of_day", "timezone"],
      prompt=("Cọc thuê xe tải: mình (Tường) nạp 150 ADA trước 7h sáng 20/04/2027 giờ VN. Anh Tùy (bên cho "
              "thuê) kiểm tra xe trước 7h sáng 22/04/2027: chọn 0 là xe ổn, hoàn đủ cho mình; chọn 1 là trầy "
              "xước, anh giữ 30 ADA. À không, trầy xước thì anh giữ 40 ADA. Anh không chọn thì hoàn đủ cho mình."),
      spec={"roles": {"payer": "Tường", "keeper": "Tùy", "chooser": "Tùy"}, "amount": 150,
            "deposit_by": "2027-04-20T07:00" + VN, "decide_by": "2027-04-22T07:00" + VN,
            "choice": "kiem_tra_xe",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": 40}], "on_timeout": 0},
      fact_sheet=[{"topic": "giữ bao nhiêu khi trầy xước", "answer": "40 ADA."}],
      adversarial_target=["self_correction_amount", "clock_7h_sang"],
      author_note="'À không' sửa 30 thành 40 ngay trong tin nhắn."),
    C(id="v5-en-rental_deposit-004", language="en", family="rental_deposit", info_mode="complete",
      expected_behavior="converge", register="document",
      phenomena=["long_document", "bullet_list", "time_of_day", "timezone"],
      prompt=("Clause 7 (Deposit) of the booth rental agreement for the Lisbon craft fair:\n"
              "(a) The exhibitor, Ugo, pays a deposit of 250 ADA by 2027-08-15 10:00 UTC.\n"
              "(b) After the fair the organiser (role FairCo) inspects the booth and reports by "
              "2027-08-25 10:00 UTC: 0 = clean, full refund; 1 = minor cleaning, FairCo keeps 25 ADA; "
              "2 = damage, FairCo keeps the whole 250 ADA.\n"
              "(c) No report by then means a full refund.\n"
              "(d) Electricity is billed separately and is not part of this deposit."),
      spec={"roles": {"payer": "Ugo", "keeper": "FairCo", "chooser": "FairCo"}, "amount": 250,
            "deposit_by": "2027-08-15T10:00" + UTC, "decide_by": "2027-08-25T10:00" + UTC,
            "choice": "inspection",
            "options": [{"value": 0, "keeper_share": 0}, {"value": 1, "keeper_share": 25},
                        {"value": 2, "keeper_share": 250}], "on_timeout": 0},
      fact_sheet=[], adversarial_target=["noise_in_document", "keeper_takes_all"],
      author_note="Mục (d) là nhiễu."),

    # ------------------------------------------------------------------ cancellation fee
    C(id="v5-vi-cancellation_fee-001", language="vi", family="cancellation_fee", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "percentage", "vi_en_mix", "time_of_day", "timezone"],
      prompt=("Đặt phòng homestay ở Đà Lạt: tôi (Hân) trả trước 80 ADA trước 12:00 ngày 01/12/2027 giờ VN. "
              "Trước 12:00 ngày 20/12/2027 tôi được chọn cancel (1): homestay Mây Chiều (role: MayChieu) giữ 25% "
              "là 20 ADA, hoàn tôi 60 ADA; hoặc giữ phòng (0): MayChieu nhận đủ 80 ADA. Không chọn gì thì coi "
              "như giữ phòng."),
      spec={"roles": {"payer": "Hân", "keeper": "MayChieu", "chooser": "Hân"}, "amount": 80,
            "deposit_by": "2027-12-01T12:00" + VN, "decide_by": "2027-12-20T12:00" + VN,
            "choice": "huy_phong",
            "options": [{"value": 0, "keeper_share": 80}, {"value": 1, "keeper_share": 20}], "on_timeout": 80},
      fact_sheet=[], adversarial_target=["percentage_fee", "timeout_to_keeper"],
      author_note="Phí 25% có ghi sẵn số; không chọn thì bên giữ nhận hết."),
    C(id="v5-en-cancellation_fee-002", language="en", family="cancellation_fee", info_mode="missing",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person"],
      prompt=("Conference ticket with cancellation: I'm paying 120 ADA to EventHub (role EventHub). If I cancel "
              "they keep a 15 ADA fee and refund the rest; if I don't cancel they keep it all."),
      spec={"roles": {"payer": "Mila", "keeper": "EventHub", "chooser": "Mila"}, "amount": 120,
            "deposit_by": "2027-02-01T09:00" + UTC, "decide_by": "2027-02-20T09:00" + UTC,
            "choice": "cancel",
            "options": [{"value": 0, "keeper_share": 120}, {"value": 1, "keeper_share": 15}], "on_timeout": 120},
      fact_sheet=[{"topic": "your name", "answer": "Mila."},
                  {"topic": "deadlines", "answer": "I pay by 2027-02-01 09:00 UTC; I can cancel until "
                                                   "2027-02-20 09:00 UTC."},
                  {"topic": "how I cancel", "answer": "I choose 1 to cancel or 0 to keep the ticket."},
                  {"topic": "no choice", "answer": "Treat it as keeping the ticket."}],
      adversarial_target=["missing_deadlines", "missing_encoding", "first_person_party"],
      author_note="Thiếu tên, hạn, cách chọn và nhánh không chọn."),
    C(id="v5-vi-cancellation_fee-003", language="vi", family="cancellation_fee", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person"],
      prompt=("Thuê thợ chụp ảnh kỷ yếu, tôi trả cọc 200 ADA cho anh Toại. Nếu tôi hủy thì anh Toại giữ một "
              "phần, còn không hủy thì anh nhận hết."),
      spec={"roles": {"payer": "Vĩnh", "keeper": "Toại", "chooser": "Vĩnh"}, "amount": 200,
            "deposit_by": "2027-04-01T23:59" + VN, "decide_by": "2027-04-15T23:59" + VN,
            "choice": "huy_chup",
            "options": [{"value": 0, "keeper_share": 200}, {"value": 1, "keeper_share": 100}], "on_timeout": 200},
      fact_sheet=[{"topic": "một phần là bao nhiêu", "answer": "Một nửa, 100 ADA."},
                  {"topic": "tên tôi", "answer": "Vĩnh."},
                  {"topic": "hạn", "answer": "Tôi nạp trước 23:59 ngày 01/04/2027, được hủy đến 23:59 ngày "
                                             "15/04/2027, giờ VN."},
                  {"topic": "cách hủy", "answer": "Tôi chọn 1 là hủy, 0 là vẫn chụp."},
                  {"topic": "không chọn", "answer": "Coi như vẫn chụp, anh Toại nhận đủ."}],
      adversarial_target=["vague_fee"],
      author_note="'giữ một phần' không có số."),
    C(id="v5-en-cancellation_fee-004", language="en", family="cancellation_fee", info_mode="extra_unsupported",
      expected_behavior="converge_and_decline_extra", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Gym membership deposit: I (Zane) pay 60 ADA to FitLab (role FitLab) by 2027-03-01 06:00 UTC. "
              "Until 2027-03-08 06:00 UTC I can cancel by choosing 1: FitLab keeps 10 ADA and refunds me 50. "
              "Choosing 0 or doing nothing means FitLab keeps the 60. Also please make the contract send me a "
              "calendar reminder the day before the cancellation deadline."),
      spec={"roles": {"payer": "Zane", "keeper": "FitLab", "chooser": "Zane"}, "amount": 60,
            "deposit_by": "2027-03-01T06:00" + UTC, "decide_by": "2027-03-08T06:00" + UTC,
            "choice": "cancel_membership",
            "options": [{"value": 0, "keeper_share": 60}, {"value": 1, "keeper_share": 10}], "on_timeout": 60},
      fact_sheet=[{"topic": "if reminders are impossible", "answer": "Fine, you can drop the reminder."}],
      adversarial_target=["unsupported_side_effect"],
      author_note="Nhắc lịch không làm được trong hợp đồng."),

    # ------------------------------------------------------------------ installment
    C(id="v5-vi-installment-001", language="vi", family="installment", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone", "relative_time"],
      prompt=("Bán xe đạp điện cho Ý Lan trả góp: 3 kỳ mỗi kỳ 45 ADA, hạn 21:00 ngày 05 các tháng 7, 8 và "
              "9/2027 giờ VN. Ý Lan trả kỳ nào thì tiền chuyển cho tôi (Phấn) luôn kỳ đó. Trễ một kỳ là dừng, "
              "tiền đã trả không hoàn."),
      spec={"roles": {"buyer": "Ý Lan", "seller": "Phấn"},
            "installments": [{"by": "2027-07-05T21:00" + VN, "amount": 45}, {"by": "2027-08-05T21:00" + VN, "amount": 45},
                             {"by": "2027-09-05T21:00" + VN, "amount": 45}]},
      fact_sheet=[], derived=["2027-07-05", "2027-08-05", "2027-09-05"],
      adversarial_target=["same_day_each_month", "one_time_for_a_date_list"],
      author_note="'ngày 05 các tháng 7, 8 và 9' là ba ngày, cùng giờ."),
    C(id="v5-vi-installment-002", language="vi", family="installment", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["no_diacritics", "terse", "first_person"],
      prompt="ban laptop tra gop cho Duong 4 thang, moi thang 70 ADA",
      spec={"roles": {"buyer": "Duong", "seller": "Kỳ Anh"},
            "installments": [{"by": "2028-01-10T23:59" + VN, "amount": 70}, {"by": "2028-02-10T23:59" + VN, "amount": 70},
                             {"by": "2028-03-10T23:59" + VN, "amount": 70}, {"by": "2028-04-10T23:59" + VN, "amount": 70}]},
      fact_sheet=[{"topic": "tên bạn", "answer": "Mình là Kỳ Anh."},
                  {"topic": "hạn", "answer": "23:59 ngày 10 các tháng 1, 2, 3 và 4/2028, giờ VN."},
                  {"topic": "tiền về đâu", "answer": "Mỗi kỳ chuyển ngay cho mình."},
                  {"topic": "trễ hạn", "answer": "Dừng, tiền đã trả không hoàn."}],
      derived=["2028-01-10", "2028-02-10", "2028-03-10", "2028-04-10"],
      adversarial_target=["missing_everything_but_amounts", "no_diacritics"],
      author_note="Chỉ có người mua, số kỳ và số tiền."),
    C(id="v5-vi-installment-003", language="vi", family="installment", info_mode="conflict",
      expected_behavior="flag_conflict_then_converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Trả góp điện thoại: Mỹ Tiên trả tôi (Lũy) 3 kỳ, mỗi kỳ 33 ADA, tổng 100 ADA, hạn 12:00 trưa "
              "các ngày 15/01, 15/02 và 15/03/2028 giờ VN. Kỳ nào trễ thì dừng, tiền về tôi ngay mỗi kỳ."),
      spec={"roles": {"buyer": "Mỹ Tiên", "seller": "Lũy"},
            "installments": [{"by": "2028-01-15T12:00" + VN, "amount": 33}, {"by": "2028-02-15T12:00" + VN, "amount": 33},
                             {"by": "2028-03-15T12:00" + VN, "amount": 33}]},
      fact_sheet=[{"topic": "mỗi kỳ bao nhiêu", "answer": "Mỗi kỳ 33 ADA, tổng 99 ADA là đúng."}],
      adversarial_target=["total_contradicts_parts"],
      author_note="3 × 33 = 99, không phải 100."),
    C(id="v5-vi-installment-004", language="vi", family="installment", info_mode="complete",
      expected_behavior="converge", register="bullets",
      phenomena=["first_person", "bullet_list", "decimal", "time_of_day", "timezone"],
      prompt=("Hợp đồng bán máy pha cà phê:\n"
              "- Bên mua: Thanh Tâm\n"
              "- Bên bán: tôi, Vũ Khang\n"
              "- Giá 157,5 ADA chia 3 kỳ, mỗi kỳ 52,5 ADA\n"
              "- Hạn 18:00 các ngày 01/02, 01/03 và 01/04/2027 (giờ VN)\n"
              "- Mỗi kỳ chuyển ngay cho tôi; trễ kỳ nào thì dừng, không hoàn tiền đã trả"),
      spec={"roles": {"buyer": "Thanh Tâm", "seller": "Vũ Khang"},
            "installments": [{"by": "2027-02-01T18:00" + VN, "amount": "52.5"},
                             {"by": "2027-03-01T18:00" + VN, "amount": "52.5"},
                             {"by": "2027-04-01T18:00" + VN, "amount": "52.5"}]},
      fact_sheet=[], adversarial_target=["vietnamese_decimal_comma", "one_time_for_a_date_list"],
      author_note="'52,5' là số lẻ kiểu Việt."),
    C(id="v5-vi-installment-005", language="vi", family="installment", info_mode="ambiguous",
      expected_behavior="ask_then_converge", register="chat",
      phenomena=["first_person", "relative_time"],
      prompt="góp tiền mua sofa của anh Nghĩa: mình trả 4 lần, mỗi lần 50 ADA, bắt đầu từ cuối tháng này",
      spec={"roles": {"buyer": "Tuyết", "seller": "Nghĩa"},
            "installments": [{"by": "2027-05-31T23:59" + VN, "amount": 50}, {"by": "2027-06-30T23:59" + VN, "amount": 50},
                             {"by": "2027-07-31T23:59" + VN, "amount": 50}, {"by": "2027-08-31T23:59" + VN, "amount": 50}]},
      fact_sheet=[{"topic": "tên mình", "answer": "Tuyết."},
                  {"topic": "cuối tháng này là ngày nào", "answer": "Lần đầu 23:59 ngày 31/05/2027 giờ VN, các lần "
                                                                    "sau 23:59 ngày 30/06, 31/07 và 31/08/2027."},
                  {"topic": "trễ hạn", "answer": "Dừng, tiền đã trả không hoàn."},
                  {"topic": "tiền về đâu", "answer": "Mỗi lần chuyển ngay cho anh Nghĩa."}],
      adversarial_target=["relative_to_today", "first_person_is_buyer"],
      author_note="'cuối tháng này' phụ thuộc hôm nay; người dùng là người mua."),
    C(id="v5-en-installment-006", language="en", family="installment", info_mode="complete",
      expected_behavior="converge", register="chat",
      phenomena=["first_person", "time_of_day", "timezone"],
      prompt=("Installments for my old camera: Lior pays me (Tobias) 3 payments of 40 ADA, due 2027-05-05, "
              "2027-06-05 and 2027-07-05 at 17:00 UTC+2 (Berlin summer time). Each payment comes straight to "
              "me; a missed one ends it."),
      spec={"roles": {"buyer": "Lior", "seller": "Tobias"},
            "installments": [{"by": "2027-05-05T17:00" + BERLIN_SUMMER, "amount": 40},
                             {"by": "2027-06-05T17:00" + BERLIN_SUMMER, "amount": 40},
                             {"by": "2027-07-05T17:00" + BERLIN_SUMMER, "amount": 40}]},
      fact_sheet=[], adversarial_target=["non_vietnam_offset", "one_time_for_a_date_list"],
      author_note="Múi giờ UTC+2."),
    C(id="v5-en-installment-007", language="en", family="installment", info_mode="missing",
      expected_behavior="ask_then_converge", register="terse",
      phenomena=["first_person", "terse", "lovelace_units"],
      prompt="Yusuf buys my e-bike: 5 installments of 30000000 lovelace each, paid to me directly. Stop if he's late.",
      spec={"roles": {"buyer": "Yusuf", "seller": "Amaya"},
            "installments": [{"by": "2027-02-01T23:59" + UTC, "amount": 30}, {"by": "2027-03-01T23:59" + UTC, "amount": 30},
                             {"by": "2027-04-01T23:59" + UTC, "amount": 30}, {"by": "2027-05-01T23:59" + UTC, "amount": 30},
                             {"by": "2027-06-01T23:59" + UTC, "amount": 30}]},
      fact_sheet=[{"topic": "your name", "answer": "Amaya."},
                  {"topic": "due dates", "answer": "The 1st of each month from February to June 2027, 23:59 UTC."}],
      derived=["30", "2027-02-01", "2027-03-01", "2027-04-01", "2027-05-01", "2027-06-01"],
      adversarial_target=["lovelace_units", "monthly_pattern"],
      author_note="Số tiền theo lovelace (30 ADA)."),
]
