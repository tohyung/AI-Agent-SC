from dataset.v4.build import assemble, display_name


def test_v4_adds_one_scenario_per_other_first_come_buyer_and_splits_every_family():
    cases, errors = assemble()
    assert errors == [] and len(cases) == 100
    case = next(case for case in cases if case["origin"] == "v3-vi-first_come-005")
    names = [item["name"] for item in case["checks"]["scenarios"]]
    assert {"buyer_1_first", "buyer_2_first"} <= set(names)
    families = {case["family"] for case in cases}
    for family in families:
        splits = {case["split"] for case in cases if case["family"] == family}
        members = sum(case["family"] == family for case in cases)
        assert members == 1 or splits == {"dev", "eval"}


def test_display_names_come_from_the_phrase_attached_to_the_token():
    assert display_name("SaoMai", ["Công ty Sao Mai, role SaoMai."]) == "Công ty Sao Mai"
    assert display_name("HyVong", ["Chúng tôi (nhóm Hy Vọng, role HyVong) góp 70 ADA"]) == "nhóm Hy Vọng"
    assert display_name("Kofi", ["contractor: Kofi"]) == "Kofi"
