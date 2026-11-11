"""Numbers written in words (English and Vietnamese), rewritten as digits for evidence checks.

Only used to decide whether a cited span states a literal: "two hundred fifty ADA" states 250,
"bảy mươi ADA" states 70. The rewritten text is searched in addition to the original, never
instead of it.
"""

from __future__ import annotations

from decimal import Decimal
import re

_EN_UNITS = {word: value for value, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_EN_TENS = {word: 10 * value for value, word in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if word != "_"}
_EN_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}
_EN_POINT = {"point"}
_EN_FILLERS = {"and"}

# Vietnamese, with and without diacritics. "tư" (4) only with its mark: unmarked "tu" is "từ".
_VI_UNITS = {"không": 0, "khong": 0, "một": 1, "mot": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4,
             "bon": 4, "tư": 4, "năm": 5, "nam": 5, "lăm": 5, "lam": 5, "nhăm": 5, "sáu": 6,
             "sau": 6, "bảy": 7, "bay": 7, "bẩy": 7, "tám": 8, "tam": 8, "chín": 9, "chin": 9}
_VI_TEN = {"mười": 10}           # "mười" is ten itself
_VI_TENS = {"mươi": 10}          # "hai mươi": times ten
_VI_TEN_EITHER = {"muoi": 10}    # unmarked: ten alone, times ten after a unit
_VI_SCALES = {"trăm": 100, "tram": 100, "nghìn": 1_000, "nghin": 1_000, "ngàn": 1_000,
              "ngan": 1_000, "triệu": 1_000_000, "trieu": 1_000_000}
_VI_POINT = {"phẩy", "phay"}
_VI_FILLERS = {"linh", "lẻ", "le"}
_VI_HALF = {"rưỡi", "ruoi"}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _is_number_word(word: str) -> bool:
    return word in (_EN_UNITS.keys() | _EN_TENS.keys() | _EN_SCALES.keys() | _VI_UNITS.keys()
                    | _VI_TEN.keys() | _VI_TENS.keys() | _VI_TEN_EITHER.keys()
                    | _VI_SCALES.keys() | _VI_HALF)


def _value(words: list[str]) -> Decimal | None:
    total, current, last_scale = Decimal(0), Decimal(0), 1
    decimals: list[int] | None = None
    seen_value = False
    for word in words:
        if decimals is not None:
            digit = _EN_UNITS.get(word, _VI_UNITS.get(word))
            if digit is None or digit > 9:
                return None
            decimals.append(digit)
        elif word in _EN_POINT or word in _VI_POINT:
            decimals = []
        elif word in _EN_FILLERS or word in _VI_FILLERS:
            continue
        elif word in _EN_UNITS or word in _VI_UNITS:
            current += _EN_UNITS.get(word, _VI_UNITS.get(word, 0))
            seen_value = True
        elif word in _EN_TENS:
            current += _EN_TENS[word]
            seen_value = True
        elif word in _VI_TEN:
            current += 10
            seen_value = True
        elif word in _VI_TENS or word in _VI_TEN_EITHER:
            if current % 100 == 0 and word in _VI_TEN_EITHER:
                current += 10
            else:
                current = current - current % 10 + (current % 10) * 10
            seen_value = True
        elif word in _EN_SCALES or word in _VI_SCALES:
            scale = _EN_SCALES.get(word, _VI_SCALES.get(word))
            if scale == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * scale
                current = Decimal(0)
            last_scale = scale
            seen_value = True
        elif word in _VI_HALF:
            current += Decimal(last_scale) / 2 if last_scale > 1 else Decimal("0.5")
        else:
            return None
    if not seen_value:
        return None
    value = total + current
    if decimals:
        value += Decimal("0." + "".join(str(digit) for digit in decimals))
    return value


def digits_for_words(text: str) -> str:
    """`text` with each run of number words replaced by its value in digits."""
    tokens = list(_WORD.finditer(text))
    pieces, cursor, index = [], 0, 0
    while index < len(tokens):
        token = tokens[index]
        if not _is_number_word(token.group(0).lower()):
            index += 1
            continue
        end = index
        # Extend over number words, fillers and a decimal point, joined by spaces or hyphens.
        while end + 1 < len(tokens):
            gap = text[tokens[end].end():tokens[end + 1].start()]
            following = tokens[end + 1].group(0).lower()
            if gap.strip(" -") or not (_is_number_word(following) or following in
                                       _EN_FILLERS | _VI_FILLERS | _EN_POINT | _VI_POINT):
                break
            end += 1
        words = [item.group(0).lower() for item in tokens[index:end + 1]]
        while words and words[-1] in _EN_FILLERS | _VI_FILLERS | _EN_POINT | _VI_POINT:
            words.pop()
            end -= 1
        value = _value(words)
        if value is not None:
            pieces.append(text[cursor:tokens[index].start()])
            pieces.append(format(value.normalize(), "f"))
            cursor = tokens[end].end()
        index = end + 1
    pieces.append(text[cursor:])
    return "".join(pieces)
