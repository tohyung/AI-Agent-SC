"""Builder evidence checks accept ordinary ways of writing what the request states."""

import pytest

from research.formalization.fact_builder import (_fold, _same_name, _searchable, _source_span,
                                                 _zones)
from research.formalization.number_words import digits_for_words


@pytest.mark.parametrize("text, digits", [
    ("two hundred fifty ADA", "250 ADA"),
    ("two hundred sixty-two point five ADA", "262.5 ADA"),
    ("one thousand two hundred ADA", "1200 ADA"),
    ("bảy mươi ADA", "70 ADA"),
    ("kỳ 1 một trăm ADA", "kỳ 1 100 ADA"),
    ("hai mươi lăm ADA", "25 ADA"),
    ("ba trăm linh năm ADA", "305 ADA"),
    ("một nghìn rưỡi ADA", "1500 ADA"),
    ("bay muoi ADA", "70 ADA"),
    ("từ 0 đến 100", "từ 0 đến 100"),
])
def test_number_words_become_digits(text, digits):
    assert digits_for_words(text) == digits


def test_searchable_text_states_grouped_decimal_and_worded_literals():
    assert "1200 ADA" in _searchable("1,200 ADA")
    assert "1.5 ADA" in _searchable("1,5 ADA")
    assert "250 ADA" in _searchable("two hundred fifty ADA")
    assert _searchable("45 ADA").startswith("45 ADA")


def test_a_span_differing_only_in_vietnamese_marks_cites_the_source_text():
    message = "toi (Hai) mua dien thoai cua Quang gia 80 ADA"
    assert _source_span("tôi (Hai) mua điện thoại", message) == "toi (Hai) mua dien thoai"
    assert _source_span("Tôi MUA điện thoại", "Tôi mua điện thoại của Quang") == "Tôi mua điện thoại"
    assert _source_span("tôi bán điện thoại", message) is None
    assert len(_fold("Đặng Thị Ánh")) == len("Đặng Thị Ánh")


def test_party_names_ignore_case_and_marks():
    assert _same_name("Hải", "toi (Hai) mua")
    assert not _same_name("Hùng", "toi (Hai) mua")


@pytest.mark.parametrize("name", ["I", "Me", "Tôi", "Mình", "Buyer", "Người mua"])
def test_capitalized_pronouns_and_role_nouns_are_not_names(name):
    from research.formalization.fact_builder import ROLE_WORDS

    assert name.lower() in ROLE_WORDS


@pytest.mark.parametrize("name", ["Ethan", "Minh", "Lan Anh", "Tín"])
def test_proper_names_are_not_role_words(name):
    from research.formalization.fact_builder import ROLE_WORDS

    assert name.lower() not in ROLE_WORDS


@pytest.mark.parametrize("text, zones", [
    ("trước 23:59 ngày 20/03/2027 giờ VN", {7}),
    ("by 2027-04-10 18:00 UTC", {0}),
    ("8:00 PM on March 30, 2027, US Eastern (UTC-5)", {-5}),
    ("trước 2027-10-10 10:00 UTC+7", {7}),
    ("2027-04-10T18:00+00:00", {0}),
    ("giờ VN, còn bên kia theo UTC", {0, 7}),
    ("trước 15/5/2027", set()),
])
def test_zones_stated_by_offset_or_name(text, zones):
    assert _zones(text) == zones
