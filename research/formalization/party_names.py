"""Party identity shared by the builder, scenario binding and scoring (E7 conventions, Q-TÊN).

A party has a display name (how the user calls it) and a role token (its identifier in the
contract). Two spellings are the same party when their folded forms are equal: "Công ty Sao Mai",
"Sao Mai" and "SaoMai" are one party.
"""

from __future__ import annotations

import re
import unicodedata

# Honorifics and kind words dropped at the start of a name before comparing (Q-TÊN 3).
PREFIXES = ("anh", "chi", "em", "co", "chu", "bac", "ong", "ba", "ban", "cu", "cong ty", "cty",
            "nhom", "ben", "quy", "mr", "mrs", "ms", "dr", "the")
# Pronouns: a party named only so is not identified yet (Q-TÊN 5, 6).
FIRST_PERSON = {"i", "me", "my", "mine", "we", "us", "tôi", "mình", "ta", "tao", "chúng tôi",
                "chúng ta", "toi", "chung toi"}
PRONOUNS = FIRST_PERSON | {"you", "they", "he", "she", "em", "anh ấy", "chị ấy", "họ"}


def strip_marks(text: str) -> str:
    """Lower case without Vietnamese marks (đ -> d), one character per character of `text`."""
    folded = []
    for char in unicodedata.normalize("NFC", text):
        base = "".join(part for part in unicodedata.normalize("NFD", char.lower())
                       if unicodedata.category(part) != "Mn")
        folded.append("d" if base == "đ" else (base[:1] or char))
    return "".join(folded)


def fold_name(name: str) -> str:
    """The comparison key of a party name: no marks, case, honorific prefix, spaces or punctuation."""
    words = re.sub(r"[^\w\s]", " ", strip_marks(name)).split()
    changed = True
    while changed and len(words) > 1:
        changed = False
        for prefix in sorted(PREFIXES, key=len, reverse=True):
            parts = prefix.split()
            if words[:len(parts)] == parts and len(words) > len(parts):
                words = words[len(parts):]
                changed = True
                break
    return "".join(words)


def same_party(first: str, second: str) -> bool:
    return bool(fold_name(first)) and fold_name(first) == fold_name(second)


def role_token(display: str) -> str:
    """A deterministic ASCII role token for a display name: "người thuê" -> "NguoiThue"."""
    words = re.sub(r"[^\w\s]", " ", strip_marks(display)).split()
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return "".join(word[:1].upper() + word[1:] for word in words)


def is_pronoun(name: str) -> bool:
    return unicodedata.normalize("NFC", name).strip().lower() in PRONOUNS


# "role SaoMai", "role: TruongHoc", "(role Studio)": a token the user gives for a party.
ROLE_ANNOTATION = re.compile(r"\brole\s*:?\s*([A-Za-z][A-Za-z0-9_]*)")


def given_role_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(ROLE_ANNOTATION.findall(text)))


# Up to four words; only the leading capitalised ones are kept as the name (see _capitalised).
NAME = r"[^\W\d_]\w*(?:\s+[^\W\d_]\w*){0,3}"
SELF = r"(?i:tôi|mình|toi|minh|me|i)"
_ATTACHED = [
    re.compile(rf"\b{SELF}\s*\(\s*({NAME})\s*\)"),
    re.compile(rf"(?<!\w)({NAME})\s*\(\s*(?:{SELF}|(?i:là tôi|la toi))\s*\)"),
    re.compile(rf"\b(?i:tôi|mình|toi|minh)\s+(?:tên\s+)?là\s+({NAME})"),
    re.compile(rf"\b(?:I am|I'm|(?i:my name is))\s+({NAME})"),
    re.compile(rf"\b(?i:me|tôi|mình)\s*:\s*({NAME})"),
]
_NOT_NAMES = {"I", "Tôi", "Mình", "Toi", "Minh", "Me", "The"}


def _capitalised(text: str, *, from_end: bool = False) -> str:
    """The run of capitalised words at the start (or end) of `text`, pronouns removed."""
    words = text.split()
    if from_end:
        words = words[::-1]
    kept = []
    for word in words:
        if not word[:1].isupper():
            break
        kept.append(word)
    if from_end:
        kept = kept[::-1]
    return " ".join(word for word in kept if word not in _NOT_NAMES)


def first_person_name(texts: list[str]) -> tuple[str, str] | None:
    """(name, matched phrase) when the history attaches exactly one name to the first person:
    "tôi (Hiền)", "Bầu show Kiều (tôi)", "Mình là Phong", "I am Owen". None otherwise."""
    found: dict[str, tuple[str, str]] = {}
    for text in texts:
        for number, pattern in enumerate(_ATTACHED):
            for match in pattern.finditer(text):
                name = _capitalised(match.group(1), from_end=number == 1)
                if name:
                    found.setdefault(fold_name(name), (name, match.group(0)))
    return next(iter(found.values())) if len(found) == 1 else None
