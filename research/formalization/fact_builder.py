"""AFF spike: deterministic FactDraft v5 -> ShadowSemanticCore tagged v4.

The model reads; this module computes. Every lovelace amount, POSIX instant,
scope id and continuation edge is produced here from atomic draft items, so
the existing v4 validator, projector and Synthesis stay unchanged. Spike scope:
deposit and choice steps, static `Value` expressions (design doc section 4).
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from research.formalization.intent_spec import (
    CORE_SCHEMA_VERSION_V4,
    _absolute_deadline_mismatch,
    parse_native_asset_id,
)

FACT_DRAFT_VERSION = "Formalization-FactDraft-v5"
LOVELACE_PER_ADA = 1_000_000
DAY_MS = 86_400_000
ADA_BASIS = "1 ADA = 1000000 lovelace"
OUTCOME_RECIPIENT_KIND = {"payment": "payment_recipient", "refund": "refund_recipient",
                          "release": "release_recipient"}
TZ = re.compile(r"([+-])(\d{2}):(\d{2})\Z")
# A named zone states UTC+7 as clearly as an offset does ("giờ VN", "giờ Việt Nam", "ICT", ...).
VIETNAM_TIME = re.compile(
    r"\b(?:gi[ờo]\s+(?:VN|Vi[ệe]t\s*Nam|H[àa]\s*N[ộo]i|S[àa]i\s*G[òo]n)|"
    r"(?:Vietnam|Viet\s*Nam|Hanoi|Saigon)\s+time|ICT|Asia/Ho_Chi_Minh|Asia/Saigon)\b",
    re.IGNORECASE)
VIETNAMESE_LETTER = re.compile("[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
                               "áàãéèíìóòõúùýđ]", re.IGNORECASE)
# Fallback questions, used only for an item the model wrote no question for.
# Each quotes the request's own words so the user sees which fact is meant.
QUESTIONS = {
    "en": {
        "conflict": "The request gives different values here: {options}. Which one applies?",
        "time": "At what exact time and in which timezone is \"{at}\"?",
        "amount": "What exact amount is \"{at}\"?",
        "policy": "Which policy ID and token name identify {name}?",
        "rounding": "{num}/{den} of \"{at}\" is not a whole number of the smallest unit; "
                    "how should it be rounded?",
        "unsupported": "This part cannot be represented yet: \"{text}\". "
                       "Can it be dropped or restated?",
    },
    "vi": {
        "conflict": "Yêu cầu nêu các giá trị khác nhau: {options}. Giá trị nào áp dụng?",
        "time": "\"{at}\" là chính xác mấy giờ, theo múi giờ nào?",
        "amount": "\"{at}\" cụ thể là bao nhiêu?",
        "policy": "Token {name} có policy ID và tên token là gì?",
        "rounding": "{num}/{den} của \"{at}\" không chia hết đến đơn vị nhỏ nhất; "
                    "làm tròn thế nào?",
        "unsupported": "Phần này chưa biểu diễn được: \"{text}\". "
                       "Có thể bỏ hoặc diễn đạt lại không?",
    },
}


def request_language(messages: list[str]) -> str:
    """"vi" when a fifth of the words carry Vietnamese letters; a Vietnamese name
    inside an English request does not switch the language."""
    words = " ".join(messages).split()
    marked = sum(1 for word in words if VIETNAMESE_LETTER.search(word))
    return "vi" if words and marked * 5 >= len(words) else "en"


def _source_span(span: str, message: str) -> str | None:
    """The exact source text a cited span stands for.

    A model often changes only letter case or spacing when it quotes; such a span is matched
    ignoring case and runs of whitespace, and the source text replaces it, so evidence stays
    verbatim. Any other difference is not a citation.
    """
    if not span.strip():
        return None
    if span in message:
        return span
    words = [re.escape(word) for word in span.split()]
    match = re.search(r"\s+".join(words), message, re.IGNORECASE)
    return match.group(0) if match else None


class DraftError(ValueError):
    """Model-side draft defects, addressed by atomic item id for repair."""

    def __init__(self, problems: list[tuple[str, str]]):
        self.problems = problems
        super().__init__("; ".join(f"{item}: {message}" for item, message in problems))


def _messages(history: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {(version["version"], index): message
            for version in history for index, message in enumerate(version["messages"])}


class _Builder:
    def __init__(self, draft: dict[str, Any], history: list[dict[str, Any]]):
        self.draft = draft
        self.history = history
        self.messages = _messages(history)
        self.language = request_language(list(self.messages.values()))
        self.problems: list[tuple[str, str]] = []
        self.parties = self._index("parties")
        self.assets = self._index("assets")
        self.quantities = self._index("quantities")
        self.instants = self._index("instants")
        self.steps = self._index("steps")
        self.outcomes = self._index("outcomes")
        self.scopes: list[dict[str, Any]] = [{"scope_id": "global", "scope_type": "global"}]
        self.claims: list[dict[str, Any]] = []
        self.questions: list[dict[str, str]] = []
        self.observations: list[dict[str, Any]] = []
        self.used: set[str] = set()
        self._quantity_cache: dict[str, tuple[int | None, str, list[dict[str, Any]]]] = {}
        self._instant_cache: dict[str, tuple[int | None, str | None, list[dict[str, Any]]]] = {}
        # Draft item id -> distinct readings (value, basis, evidence) the source gives.
        self.conflicts: dict[str, list[tuple[Any, Any, list[dict[str, Any]]]]] = {}
        # Quantity id -> "lovelace" or the id of the native asset it counts.
        self.units: dict[str, str] = {}
        self._visiting: set[str] = set()
        self._visits: dict[str, int] = {}
        self._path: set[str] = set()

    # -- draft checks ------------------------------------------------------

    def _index(self, field: str) -> dict[str, dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for item in self.draft.get(field) or []:
            item_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(item_id, str) or not item_id:
                self.problems.append((field, "item without id"))
            elif item_id in items or any(item_id in other for other in (
                    getattr(self, name, {}) for name in
                    ("parties", "assets", "quantities", "instants", "steps", "outcomes"))):
                self.problems.append((item_id, "duplicate id"))
            else:
                items[item_id] = {**item,
                                  "evidence": self._evidence(item_id, item.get("evidence"))}
        return items

    def _evidence(self, item_id: str, evidence: Any) -> list[dict[str, Any]]:
        if not isinstance(evidence, list) or not evidence:
            self.problems.append((item_id, "evidence must be a nonempty list"))
            return []
        cited = []
        for entry in evidence:
            span = entry.get("span") if isinstance(entry, dict) else None
            key = (entry.get("requirement_version"), entry.get("message_index")) \
                if isinstance(entry, dict) else None
            source = (_source_span(span, self.messages.get(key, ""))
                      if isinstance(span, str) else None)
            if source is None:
                self.problems.append((item_id, f"span not found verbatim: {span!r}"))
            elif source != span:
                entry = {**entry, "span": source}
            if isinstance(entry, dict):
                cited.append(entry)
        return [{**entry, "relation": entry.get("relation", "supports")} for entry in cited]

    def _spans(self, item: dict[str, Any]) -> str:
        return " ".join(entry.get("span", "") for entry in item.get("evidence") or []
                        if isinstance(entry, dict))

    def _ref(self, table: dict[str, dict[str, Any]], ref: Any, owner: str) -> dict[str, Any] | None:
        if isinstance(ref, str) and ref in table:
            return table[ref]
        self.problems.append((owner, f"unknown reference {ref!r}"))
        return None

    # -- expressions -------------------------------------------------------

    def _alternatives(self, item_id: str, item: dict[str, Any], evaluate) -> Any:
        """Evaluate each source reading; distinct results become a recorded conflict."""
        readings = []
        for index, alternative in enumerate(item["alternatives"], 1):
            if not isinstance(alternative, dict):
                self.problems.append((item_id, f"alternative {index} must be an object"))
                continue
            evidence = self._evidence(item_id, alternative.get("evidence"))
            readings.append(evaluate(alternative.get("expr") or {}, evidence))
        if len(readings) < 2:
            self.problems.append((item_id, "alternatives need at least two readings"))
            if not readings:
                return None, "", []
        distinct = {reading[0] for reading in readings}
        if len(distinct) > 1 and None not in distinct:
            self.conflicts[item_id] = readings
            merged = [entry for reading in readings for entry in reading[-1]]
            return (None, *readings[0][1:-1], merged)
        # Equal readings agree; an unknown reading leaves the value open.
        return readings[0] if len(distinct) == 1 else (None, *readings[0][1:])

    def quantity(self, qid: str) -> tuple[int | None, str, list[dict[str, Any]]]:
        """Return (lovelace or None if unresolved, basis, evidence of the whole tree)."""
        if qid in self._quantity_cache:
            return self._quantity_cache[qid]
        item = self.quantities[qid]
        if qid in self._visiting:
            self.problems.append((qid, "circular quantity reference"))
            return None, "", []
        self._visiting.add(qid)
        self.used.add(qid)
        if "alternatives" in item:
            result = self._alternatives(qid, item, lambda expr, evidence: self._quantity_expr(
                qid, expr, evidence))
        else:
            result = self._quantity_expr(qid, item.get("expr") or {}, item.get("evidence") or [])
        self._visiting.discard(qid)
        self._quantity_cache[qid] = result
        return result

    def _quantity_expr(self, qid: str, expr: dict[str, Any], item_evidence: list[dict[str, Any]]
                       ) -> tuple[int | None, str, list[dict[str, Any]]]:
        evidence = list(item_evidence)
        value: int | None = None
        basis = ""
        spans = " ".join(entry.get("span", "") for entry in item_evidence)
        units: set[str] = set()

        def sub(ref: Any) -> int | None:
            if self._ref(self.quantities, ref, qid) is None:
                return None
            sub_value, _, sub_evidence = self.quantity(ref)
            evidence.extend(entry for entry in sub_evidence if entry not in evidence)
            units.add(self.units.get(ref, "lovelace"))
            return sub_value

        if "tokens" in expr:
            text = str(expr["tokens"])
            if self._ref(self.assets, expr.get("asset"), qid) is not None:
                self.used.add(expr["asset"])
                units.add(expr["asset"])
            if not re.search(r"(?<![\d.,])" + re.escape(text) + r"(?![\d.,])", spans):
                self.problems.append((qid, f"literal {text} not in evidence"))
            if text.isdigit() and int(text) > 0:
                value = int(text)
            else:
                self.problems.append((qid, f"not a positive whole token quantity: {text}"))
        elif "ada" in expr or "lovelace" in expr:
            unit = "ada" if "ada" in expr else "lovelace"
            text = str(expr[unit])
            pattern = r"(?<![\d.,])" + re.escape(text) + r"\s*" + unit + r"\b"
            if not re.search(pattern, spans, re.IGNORECASE):
                self.problems.append((qid, f"literal {text} {unit} not in evidence"))
            try:
                amount = Decimal(text) * (LOVELACE_PER_ADA if unit == "ada" else 1)
            except InvalidOperation:
                amount = Decimal("NaN")
            if amount.is_finite() and amount == amount.to_integral_value() and amount > 0:
                value = int(amount)
                basis = ADA_BASIS if unit == "ada" else ""
            else:
                self.problems.append((qid, f"not a positive whole lovelace amount: {text}"))
        elif "sum" in expr:
            parts = [sub(ref) for ref in expr["sum"]]
            value = None if None in parts else sum(parts)
            basis = " + ".join(expr["sum"])
        elif "subtract" in expr:
            spec = expr["subtract"]
            base = sub(spec.get("from"))
            minus = [sub(ref) for ref in spec.get("minus") or []]
            if base is not None and None not in minus:
                value = base - sum(minus)
                if value < 0:
                    self.problems.append((qid, "subtraction is negative"))
                    value = None
            basis = f"{spec.get('from')} - " + " - ".join(spec.get("minus") or [])
        elif "times" in expr:
            spec = expr["times"]
            count = spec.get("count")
            if type(count) is not int or count <= 0:
                self.problems.append((qid, "times.count must be a positive integer"))
            base = sub(spec.get("of"))
            value = None if base is None or type(count) is not int else base * count
            basis = f"{spec.get('of')} * {count}"
        elif "fraction" in expr:
            spec = expr["fraction"]
            num, den = spec.get("num"), spec.get("den")
            if type(num) is not int or type(den) is not int or num <= 0 or den <= 0:
                self.problems.append((qid, "fraction needs positive integer num/den"))
                num, den = None, None
            base = sub(spec.get("of"))
            if base is not None and num is not None:
                # Marlowe DivValue truncates (quot); a remainder is a business question.
                if (base * num) % den == 0:
                    value = base * num // den
                else:
                    self.ask(qid, self.question("rounding", num=num, den=den, at=spans))
            basis = f"{spec.get('of')} * {num} / {den} (exact)"
        elif expr.get("unknown") is True or "dynamic" in expr:
            if "asset" in expr and self._ref(self.assets, expr["asset"], qid) is not None:
                self.used.add(expr["asset"])
                units.add(expr["asset"])
            if "dynamic" in expr:
                # Known only while the contract runs (ChoiceValue, Cond, ...): phase 2.
                self.observe(qid, expr["dynamic"], item_evidence)
        else:
            self.problems.append((qid, f"unsupported quantity expression {sorted(expr)}"))
        if len(units) > 1:
            self.problems.append((qid, f"mixes units {sorted(units)}"))
            value = None
        unit = next(iter(units), "lovelace")
        if self.units.setdefault(qid, unit) != unit:
            self.problems.append((qid, "readings use different units"))
        return value, basis, evidence

    def instant(self, iid: str) -> tuple[int | None, str | None, list[dict[str, Any]]]:
        """Return (POSIX ms or None if unresolved, basis or None when explicit, evidence)."""
        if iid in self._instant_cache:
            return self._instant_cache[iid]
        if iid in self._visiting:
            self.problems.append((iid, "circular instant reference"))
            return None, None, []
        self._visiting.add(iid)
        self.used.add(iid)
        item = self.instants[iid]
        if "alternatives" in item:
            result = self._alternatives(iid, item, lambda expr, evidence: (
                *self._instant_expr(iid, expr, evidence), evidence))
        else:
            result = (*self._instant_expr(iid, item.get("expr") or {},
                                          item.get("evidence") or []),
                      list(item.get("evidence") or []))
        self._visiting.discard(iid)
        self._instant_cache[iid] = result
        return result

    def _instant_expr(self, iid: str, expr: dict[str, Any], evidence: list[dict[str, Any]]
                      ) -> tuple[int | None, str | None]:
        value: int | None = None
        basis: str | None = None
        if "date" in expr:
            spec = expr["date"]
            tz = spec.get("tz")
            match = TZ.fullmatch(tz) if isinstance(tz, str) else None
            # Never infer a timezone or time of day the source does not state.
            if match and type(spec.get("h")) is int and type(spec.get("min")) is int:
                spans = " ".join(entry.get("span", "") for entry in evidence)
                self._require_stated_time(iid, spec["h"], match, spans)
                sign = 1 if match.group(1) == "+" else -1
                offset = timezone(sign * timedelta(hours=int(match.group(2)),
                                                   minutes=int(match.group(3))))
                try:
                    moment = datetime(spec["y"], spec["m"], spec["d"], spec["h"],
                                      spec["min"], tzinfo=offset)
                    value = int(moment.timestamp() * 1000)
                    # A misread date is a reading error the model can repair.
                    if _absolute_deadline_mismatch({"value": value, "evidence": evidence},
                                                   self.messages):
                        self.problems.append((iid, "date contradicts the calendar date in its "
                                                   "evidence, read as day/month/year"))
                except (KeyError, TypeError, ValueError):
                    self.problems.append((iid, "invalid calendar date"))
            elif tz is not None and not match:
                self.problems.append((iid, f"invalid tz {tz!r}"))
        elif "offset" in expr:
            spec = expr["offset"]
            days = spec.get("days")
            if type(days) is not int or days <= 0:
                self.problems.append((iid, "offset.days must be a positive integer"))
            elif self._ref(self.instants, spec.get("from"), iid) is not None:
                base = self.instant(spec["from"])[0]
                value = None if base is None else base + days * DAY_MS
                basis = f"{spec['from']} + {days} days"
        elif expr.get("unknown") is not True:
            self.problems.append((iid, f"unsupported instant expression {sorted(expr)}"))
        return value, basis

    def _require_stated_time(self, iid: str, hour: int, tz: re.Match[str], spans: str) -> None:
        """A resolved time decides money, so its hour and timezone must be cited."""
        if not re.search(rf"(?<!\d)0?{hour}(?!\d)", spans):
            self.problems.append((iid, f"hour {hour} not in evidence"))
        offset = int(tz.group(2))
        stated = (re.search(r"\b(?:UTC|GMT)\b", spans, re.IGNORECASE) if offset == 0 else
                  re.search(rf"[+-]\s*0?{offset}(?!\d)", spans))
        if not stated and tz.group(0) == "+07:00":
            stated = VIETNAM_TIME.search(spans)
        if not stated:
            self.problems.append((iid, f"timezone {tz.group(0)} not in evidence"))

    # -- core emission -----------------------------------------------------

    def claim(self, scope_id: str, kind: str, value: Any, evidence: list[dict[str, Any]],
              basis: str | None = None, *, reading: int | None = None) -> str:
        claim_id = f"{scope_id}:{kind}" + (f":{reading}" if reading else "")
        result = {"claim_id": claim_id, "kind": kind, "value": value,
                  "criticality": "financial", "scope_id": scope_id, "evidence": evidence}
        if basis and value is not None:
            result["normalization_basis"] = basis
        if reading:
            result["status"] = "conflicted"
        elif value is None:
            result["status"] = "unresolved"
        else:
            result["status"] = "derived" if basis else "explicit"
        self.claims.append(result)
        return claim_id

    def value_claim(self, scope_id: str, kind: str, ref: str,
                    reading: tuple[Any, Any, list[dict[str, Any]]]) -> str:
        """One claim, or one `conflicted` claim per distinct source reading."""
        if ref not in self.conflicts:
            value, basis, evidence = reading
            return self.claim(scope_id, kind, value, evidence, basis)
        self.ask_conflict(ref)
        claim_ids = [self.claim(scope_id, kind, value, evidence, basis, reading=index)
                     for index, (value, basis, evidence) in enumerate(self.conflicts[ref], 1)]
        return claim_ids[0]

    def ask(self, target_id: str, question: str) -> None:
        if not any(item["target_id"] == target_id for item in self.questions):
            self.questions.append({"target_id": target_id, "question": question})

    def question(self, key: str, **values: Any) -> str:
        return QUESTIONS[self.language][key].format(**values)

    def ask_conflict(self, ref: str) -> None:
        options = []
        for value, _basis, evidence in self.conflicts[ref]:
            # A party reading is its name; any other reading is its own source phrase.
            text = value if isinstance(value, str) else next(
                (entry.get("span") for entry in evidence if entry.get("span")), None)
            if text and f"\"{text}\"" not in options:
                options.append(f"\"{text}\"")
        self.ask(ref, self.question("conflict", options=" / ".join(options)))

    def ask_amount(self, qid: str, seen: frozenset[str] = frozenset()) -> None:
        """Ask about the open quantities an unresolved amount is computed from, not
        about each amount derived from them: half of a disputed total is no question."""
        expr = self.quantities[qid].get("expr") or {}
        spec = next((expr[key] for key in ("sum", "subtract", "times", "fraction")
                     if key in expr), None)
        refs = (spec if isinstance(spec, list) else
                [spec.get("from"), *(spec.get("minus") or [])] if "subtract" in expr else
                [spec.get("of")] if isinstance(spec, dict) else [])
        open_refs = [ref for ref in refs if isinstance(ref, str) and ref in self.quantities
                     and ref not in seen and self.quantity(ref)[0] is None]
        if qid in self.conflicts:
            self.ask_conflict(qid)
        elif not open_refs:
            self.ask(qid, self.question("amount", at=self._spans(self.quantities[qid])))
        for ref in open_refs:
            self.ask_amount(ref, seen | {qid})

    def party_claim(self, scope_id: str, kind: str, party_ref: Any, owner: dict[str, Any]) -> None:
        # A list of party ids means the source names more than one party for this role.
        refs = party_ref if isinstance(party_ref, list) else [party_ref]
        readings = []
        for ref in refs:
            party = self._ref(self.parties, ref, owner.get("id", "?"))
            if party is None:
                continue
            self.used.add(ref)
            evidence = list(owner.get("evidence") or [])
            evidence.extend(entry for entry in party.get("evidence") or [] if entry not in evidence)
            readings.append((party["name"], None, evidence))
        if len({name for name, _, _ in readings}) > 1:
            target = f"{owner.get('id', '?')}:{kind}"
            self.conflicts[target] = readings
            self.value_claim(scope_id, kind, target, readings[0])
        elif readings:
            self.claim(scope_id, kind, readings[0][0], readings[0][2])

    def deadline_claim(self, scope_id: str, kind: str, instant_id: Any, owner: str) -> str | None:
        if self._ref(self.instants, instant_id, owner) is None:
            return None
        reading = self.instant(instant_id)
        if reading[0] is None and instant_id not in self.conflicts:
            # "Seven days after the deadline" is open only because its base is: ask the base.
            root, seen = instant_id, {instant_id}
            while True:
                base = ((self.instants[root].get("expr") or {}).get("offset") or {}).get("from")
                if (base in seen or base not in self.instants
                        or self.instant(base)[0] is not None):
                    break
                root = base
                seen.add(root)
            if root in self.conflicts:
                self.ask_conflict(root)
            else:
                self.ask(root, self.question("time", at=self._spans(self.instants[root])))
        # Cite only the instant's own phrase: a derived deadline citing its base
        # date would contradict that calendar date under the v4 date check.
        return self.value_claim(scope_id, kind, instant_id, reading)

    def amount_claim(self, scope_id: str, amount: Any, owner: dict[str, Any],
                     balances: dict[tuple[str, str], int | None],
                     account: str | None) -> tuple[str, int | None]:
        """Emit the amount (and native asset) claims; return (unit, value or None)."""
        owner_id = owner.get("id", "?")
        if amount == "remaining":
            unit = owner.get("asset") or "lovelace"
            if unit != "lovelace" and (self._ref(self.assets, unit, owner_id) is None
                                       or self.assets[unit].get("ada") is True):
                unit = "lovelace"
            # Nothing deposited in this unit on this path: the account holds 0 lovelace.
            # A token count must be positive in v4, so an empty token account stays open.
            balance = None if account is None else balances.get(
                (account, unit), 0 if unit == "lovelace" else None)
            reading = (balance, "remaining balance of the source account on this path",
                       list(owner.get("evidence") or []))
            ref = None
        elif self._ref(self.quantities, amount, owner_id) is None:
            return "lovelace", None
        else:
            reading = self.quantity(amount)
            unit, ref = self.units.get(amount, "lovelace"), amount
            if reading[0] is None and amount not in self.conflicts:
                self.ask_amount(amount)
        kind = "amount_lovelace"
        if unit != "lovelace":
            kind = "amount_token_units"
            self.used.add(unit)
            asset = self.assets[unit]
            native = asset.get("native")
            if isinstance(native, str) and parse_native_asset_id(native) is not None:
                self.claim(scope_id, "asset", native, list(asset["evidence"]))
            else:
                # v4 backs a token count only beside a full native id (design 11, conflict 6).
                self.claim(scope_id, "asset", None, list(asset["evidence"]))
                self.ask(unit, self.question("policy", name=asset.get("name", unit)))
                reading = (None, *reading[1:])
        if ref is not None and ref in self.conflicts:
            self.value_claim(scope_id, kind, ref, reading)
        else:
            self.claim(scope_id, kind, reading[0], reading[2], reading[1])
        return unit, reading[0]

    def chain(self, parent: dict[str, Any], items: Any, balances: dict[tuple[str, str], int | None],
              owner: str) -> None:
        if items == "end" or items is None:
            return
        if isinstance(items, str):
            items = [items]
        previous = parent
        for position, ref in enumerate(items):
            if ref in self.outcomes:
                scope = self.outcome(ref, previous, balances)
                previous["continuation_scope_id"] = scope["scope_id"]
                previous = scope
            elif ref in self.steps and position == len(items) - 1:
                previous["continuation_scope_id"] = self.step(ref, balances)
            else:
                self.problems.append((owner, f"invalid continuation item {ref!r}"))

    def outcome(self, oid: str, parent: dict[str, Any],
                balances: dict[tuple[str, str], int | None]) -> dict[str, Any]:
        self.used.add(oid)
        item = self.outcomes[oid]
        scope = {"scope_id": self._path_scope_id("o", oid), "scope_type": "terminal_outcome",
                 "outcome_id": oid, "parent_scope_id": parent["scope_id"]}
        self.scopes.append(scope)
        kind = OUTCOME_RECIPIENT_KIND.get(item.get("kind"))
        if kind is None:
            self.problems.append((oid, f"unknown outcome kind {item.get('kind')!r}"))
            return scope
        self.party_claim(scope["scope_id"], "payment_source_account_owner",
                         item.get("from_account"), item)
        self.party_claim(scope["scope_id"], kind, item.get("to"), item)
        source = item.get("from_account") if isinstance(item.get("from_account"), str) else None
        unit, paid = self.amount_claim(scope["scope_id"], item.get("amount"), item,
                                       balances, source)
        if source is None:
            return scope
        balance = balances.get((source, unit))
        if paid is not None and balance is not None:
            if paid > balance:
                self.problems.append((oid, f"pays {paid} but the account holds {balance}"))
            balances[(source, unit)] = balance - paid
        else:
            balances[(source, unit)] = None
        return scope

    def step(self, sid: str, balances: dict[tuple[str, str], int | None]) -> str:
        if sid in self._path:
            self.problems.append((sid, "step loops back to itself; Marlowe contracts are finite"))
            return f"t_{sid}"
        self._path.add(sid)
        try:
            return self._step(sid, balances)
        finally:
            self._path.discard(sid)

    def _path_scope_id(self, prefix: str, item_id: str) -> str:
        """A step or outcome reached by several paths gets one scope per path."""
        self._visits[item_id] = self._visits.get(item_id, 0) + 1
        count = self._visits[item_id]
        return f"{prefix}_{item_id}" + (f"#{count}" if count > 1 else "")

    def _step(self, sid: str, balances: dict[tuple[str, str], int | None]) -> str:
        self.used.add(sid)
        item = self.steps[sid]
        kind = item.get("kind")
        scope = {"scope_id": self._path_scope_id("t", sid), "scope_type": "transition",
                 "transition_kind": kind}
        key = scope["scope_id"][2:]
        self.scopes.append(scope)
        evidence = list(item.get("evidence") or [])
        # The timeout path sees balances before this step: a missed deposit funds nothing.
        before = dict(balances)
        if kind == "deposit":
            self.party_claim(scope["scope_id"], "depositing_party", item.get("by"), item)
            self.party_claim(scope["scope_id"], "destination_account_owner", item.get("into"), item)
            unit, value = self.amount_claim(scope["scope_id"], item.get("amount"), item,
                                            balances, None)
            # A disputed account owner leaves no single account to track.
            account = item.get("into") if isinstance(item.get("into"), str) else None
            if account is not None:
                current = balances.get((account, unit), 0)
                balances[(account, unit)] = (None if value is None or current is None
                                             else current + value)
            deadline_kind = "deposit_deadline_ms"
        elif kind == "choice":
            self.party_claim(scope["scope_id"], "choice_owner", item.get("by"), item)
            bounds = item.get("bounds") or {}
            scope["choice_bounds"] = {"from": bounds.get("from"), "to": bounds.get("to"),
                                      "source_evidence": evidence}
            for index, branch in enumerate(item.get("branches") or [], 1):
                guard = branch.get("guard") or {}
                branch_scope = {"scope_id": f"b_{key}_{index}", "scope_type": "branch",
                                "decision_id": scope["scope_id"], "branch_id": f"{key}_{index}",
                                "choice_guard": {"operator": guard.get("op"),
                                                 "value": guard.get("value"),
                                                 "source_evidence": evidence}}
                self.scopes.append(branch_scope)
                self.chain(branch_scope, branch.get("then"), dict(balances), sid)
            deadline_kind = "choice_deadline_ms"
        elif kind == "notify":
            deadline_kind = "timeout_ms"
        elif kind == "wait_until":
            # Marlowe `When [] t k`: nothing to wait for but time, so no timeout branch.
            scope["transition_kind"] = "payment"
            self.deadline_claim(scope["scope_id"], "payment_release_time_ms",
                                item.get("at"), sid)
            self.chain(scope, item.get("then"), balances, sid)
            return scope["scope_id"]
        else:
            self.problems.append((sid, f"step kind {kind!r} is not supported"))
            return scope["scope_id"]
        deadline_id = self.deadline_claim(scope["scope_id"], deadline_kind,
                                          item.get("deadline"), sid)
        timeout = {"scope_id": f"to_{key}", "scope_type": "timeout", "timeout_id": f"to_{key}",
                   "decision_id": scope["scope_id"]}
        if deadline_id:
            timeout["deadline_claim_id"] = deadline_id
        self.scopes.append(timeout)
        self.chain(timeout, item.get("on_timeout"), before, sid)
        if kind in {"deposit", "notify"}:
            self.chain(scope, item.get("then"), balances, sid)
        return scope["scope_id"]

    def observe(self, owner: str, text: Any, evidence: Any, *, context: bool = False) -> None:
        """Record what the v4 claim taxonomy does not carry. Behavior it cannot
        represent always needs a question; side context creates no obligation."""
        if not isinstance(text, str) or not text.strip():
            self.problems.append((owner, "unsupported item needs a text description"))
            return
        self.observations.append({
            "observation_id": f"obs_{len(self.observations) + 1}", "text": text,
            "reason": "irrelevant_context" if context else "outside_formalization_v4_claim_taxonomy",
            "source_evidence": self._evidence(owner, evidence)})
        if not context:
            self.ask(owner, self.question("unsupported", text=text))

    def gaps(self) -> list[dict[str, Any]]:
        """Observations of contract behavior the core cannot represent."""
        return [item for item in self.observations if item["reason"] != "irrelevant_context"]

    def unsupported(self) -> None:
        notes = self.draft.get("notes") or {}
        for index, item in enumerate(notes.get("unsupported") or [], 1):
            owner = f"unsupported_{index}"
            if not isinstance(item, dict):
                self.problems.append((owner, "unsupported item must be an object"))
            elif item.get("kind") == "ledger_history_deletion":
                # The only v4 signal that yields unsupported_for_current_study.
                evidence = self._evidence(owner, item.get("evidence"))
                claim = next((claim for claim in self.claims
                              if claim["kind"] == "ledger_history_deletion"), None)
                if claim is None:
                    self.claim("global", "ledger_history_deletion", True, evidence)
                else:  # one claim per scope: further mentions add evidence
                    claim["evidence"].extend(entry for entry in evidence
                                             if entry not in claim["evidence"])
            elif item.get("kind") == "context":
                self.observe(owner, item.get("text"), item.get("evidence"), context=True)
            else:
                self.observe(owner, item.get("text"), item.get("evidence"))

    def build(self) -> dict[str, Any]:
        for party_id, party in self.parties.items():
            # Design section 3: a party's name is quoted from its own evidence.
            if party["name"] not in self._spans(party):
                self.problems.append((party_id, f"name {party['name']!r} not in its evidence"))
            if not party["name"][0].isupper():
                self.problems.append((party_id, f"name {party['name']!r} is a role word, not a "
                                                "proper name: use the person it means, or add "
                                                "a note of kind \"other\" if nobody is named"))
        self.unsupported()
        asset = self.draft.get("asset") or {}
        ada = [item for item in self.assets.values() if item.get("ada") is True]
        if asset.get("ada") is True:
            self.claim("global", "asset", "ADA", self._evidence("asset", asset.get("evidence")))
        elif ada:
            self.used.add(ada[0]["id"])
            self.claim("global", "asset", "ADA", list(ada[0]["evidence"]))
        elif asset:
            self.problems.append(("asset", "use assets[] for native tokens"))
        for asset_id, item in self.assets.items():
            if item.get("ada") is True:
                continue
            spans = self._spans(item)
            name, native = item.get("name"), item.get("native")
            if not isinstance(name, str) or not name or name not in spans:
                self.problems.append((asset_id, f"token name {name!r} not in evidence"))
            parsed = parse_native_asset_id(native) if isinstance(native, str) else None
            # The policy id must be in the source; the token name is its hex spelling.
            if native is not None and (parsed is None or parsed[0] not in spans
                                       or bytes.fromhex(parsed[1]).decode("utf-8", "replace")
                                       != name):
                message = "native id must be native:<policy in evidence>/<hex of name>, or null"
                self.problems.append((asset_id, message))
        referenced = {ref for step in self.steps.values()
                      for ref in _step_refs(step)}
        roots = [sid for sid in self.steps if sid not in referenced]
        # A request that is only out of scope may have no steps; anything else needs one root.
        out_of_scope_only = not self.steps and (self.gaps() or any(
            claim["kind"] == "ledger_history_deletion" for claim in self.claims))
        if not out_of_scope_only:
            if len(roots) != 1:
                self.problems.append(("steps", f"expected one first step, found {roots}"))
            else:
                self.step(roots[0], {})
            for table in (self.parties, self.quantities, self.instants, self.steps,
                          self.outcomes):
                for item_id in table:
                    if item_id not in self.used:
                        self.problems.append((item_id, "declared but never used"))
        if self.problems:
            raise DraftError(self.problems)
        return self.core()

    def core(self) -> dict[str, Any]:
        notes = self.draft.get("notes") or {}
        for item in notes.get("clarifications") or []:
            if isinstance(item, dict) and isinstance(item.get("question"), str):
                self.questions = [question for question in self.questions
                                  if question["target_id"] != item.get("target_id")]
                self.questions.append({"target_id": item.get("target_id"),
                                       "question": item["question"]})
        # One question per wording: several items can need the same answer.
        distinct: dict[str, dict[str, str]] = {}
        for question in self.questions:
            distinct.setdefault(" ".join(question["question"].casefold().split()), question)
        self.questions = list(distinct.values())
        unresolved = any(claim["status"] == "unresolved" for claim in self.claims)
        conflicted = any(claim["status"] == "conflicted" for claim in self.claims)
        deletion = any(claim["kind"] == "ledger_history_deletion" for claim in self.claims)
        # Resolution follows from the facts; the model's resolution_hint is advisory only.
        # v4 requires a conflict to be answered before anything else.
        resolution = ("conflict_requires_resolution" if conflicted else
                      "unsupported_for_current_study" if deletion else
                      "clarification_required" if unresolved or self.gaps() else
                      "accepted_interpretation")
        questions = ([question["question"] for question in self.questions]
                     if resolution in {"conflict_requires_resolution",
                                       "clarification_required"} else [])
        return {"schema_version": CORE_SCHEMA_VERSION_V4,
                "requirement_history": self.history,
                "behavior_scopes": self.scopes, "claims": self.claims,
                "required_clarifications": questions,
                "unscored_observations": self.observations,
                "predicted_resolution": resolution}


def _step_refs(step: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for field in ("then", "on_timeout"):
        value = step.get(field)
        refs.update([value] if isinstance(value, str) else value or [])
    for branch in step.get("branches") or []:
        value = branch.get("then")
        refs.update([value] if isinstance(value, str) else value or [])
    return refs


STEP_KINDS = {"deposit", "choice", "notify", "wait_until"}
GUARD_OPERATORS = {"eq", "ge", "gt", "le", "lt"}
QUANTITY_FORMS = {"ada", "lovelace", "tokens", "sum", "subtract", "times", "fraction",
                  "unknown", "dynamic"}


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _party_ref(value: Any) -> bool:
    # One party id, or a nonempty list of them when the source names several.
    return _is_id(value) or (isinstance(value, list) and bool(value)
                             and all(_is_id(item) for item in value))


def _continuation(value: Any) -> bool:
    return value is None or _is_id(value) or (
        isinstance(value, list) and all(_is_id(item) for item in value))


def _quantity_shape(expr: Any) -> str | None:
    if not isinstance(expr, dict) or len(set(expr) & QUANTITY_FORMS) != 1:
        return f"expr must be an object with exactly one of {sorted(QUANTITY_FORMS)}"
    form = next(iter(set(expr) & QUANTITY_FORMS))
    spec = expr[form]
    valid = {
        "ada": isinstance(spec, (str, int)) and type(spec) is not bool,
        "lovelace": isinstance(spec, (str, int)) and type(spec) is not bool,
        "tokens": isinstance(spec, (str, int)) and type(spec) is not bool,
        "sum": isinstance(spec, list) and bool(spec) and all(_is_id(ref) for ref in spec),
        "subtract": isinstance(spec, dict) and _is_id(spec.get("from"))
        and isinstance(spec.get("minus"), list) and all(_is_id(ref) for ref in spec["minus"]),
        "times": isinstance(spec, dict) and _is_id(spec.get("of")),
        "fraction": isinstance(spec, dict) and _is_id(spec.get("of")),
        "unknown": spec is True,
        "dynamic": isinstance(spec, str),
    }[form]
    if not valid or ("asset" in expr and not _is_id(expr["asset"])):
        return f"malformed {form} expression"
    return None


def _instant_shape(expr: Any) -> str | None:
    if not isinstance(expr, dict):
        return "expr must be an object"
    if "date" in expr:
        spec = expr["date"]
        if not isinstance(spec, dict) or any(type(spec.get(key)) is not int
                                             for key in ("y", "m", "d")):
            return "date needs integer y, m, d"
        if any(spec.get(key) is not None and type(spec[key]) is not int for key in ("h", "min")):
            return "date h and min must be integers or null"
        if spec.get("tz") is not None and not isinstance(spec["tz"], str):
            return "date tz must be text or null"
        return None
    if "offset" in expr:
        spec = expr["offset"]
        return None if isinstance(spec, dict) and _is_id(spec.get("from")) else \
            "offset needs a from instant id"
    return None if expr.get("unknown") is True else "expr must be date, offset or unknown"


def _shape_problems(draft: dict[str, Any]) -> list[tuple[str, str]]:
    """Type errors in the model's JSON, found before any value is computed.

    Every later step may then assume well-typed items; a malformed draft is a
    repairable DraftError, never a crash.
    """
    problems: list[tuple[str, str]] = []
    for field in ("parties", "assets", "quantities", "instants", "steps", "outcomes"):
        items = draft.get(field)
        if items is not None and not isinstance(items, list):
            problems.append((field, "must be a list"))
            continue
        for item in items or []:
            if not isinstance(item, dict):
                problems.append((field, "items must be objects"))
                continue
            item_id = item.get("id") if _is_id(item.get("id")) else field
            if field == "parties" and not _is_id(item.get("name")):
                problems.append((item_id, "name must be nonempty text"))
            elif field in {"quantities", "instants"}:
                shape = _quantity_shape if field == "quantities" else _instant_shape
                readings = item.get("alternatives")
                if readings is None:
                    message = shape(item.get("expr"))
                elif isinstance(readings, list) and all(isinstance(entry, dict)
                                                         for entry in readings):
                    message = next((shape(entry.get("expr")) for entry in readings
                                    if shape(entry.get("expr"))), None)
                else:
                    message = "alternatives must be a list of objects"
                if message:
                    problems.append((item_id, message))
            elif field == "steps":
                problems.extend((item_id, message) for message in _step_shape(item))
            elif field == "outcomes":
                if not (isinstance(item.get("kind"), str)
                        and item["kind"] in OUTCOME_RECIPIENT_KIND):
                    problems.append((item_id, f"outcome kind must be one of "
                                              f"{sorted(OUTCOME_RECIPIENT_KIND)}"))
                if not (_party_ref(item.get("from_account")) and _party_ref(item.get("to"))):
                    problems.append((item_id, "from_account and to must be party ids"))
                if not _is_id(item.get("amount")):
                    problems.append((item_id, "amount must be a quantity id or \"remaining\""))
    for key in ("asset", "notes"):
        if draft.get(key) is not None and not isinstance(draft[key], dict):
            problems.append((key, "must be an object"))
    notes = draft.get("notes") if isinstance(draft.get("notes"), dict) else {}
    for key in ("clarifications", "unsupported"):
        if notes.get(key) is not None and not isinstance(notes[key], list):
            problems.append(("notes", f"{key} must be a list"))
    return problems


def _step_shape(step: dict[str, Any]) -> list[str]:
    kind = step.get("kind")
    if not isinstance(kind, str) or kind not in STEP_KINDS:
        return [f"step kind {kind!r} is not supported"]
    problems = []
    if kind in {"deposit", "choice"} and not _party_ref(step.get("by")):
        problems.append("by must be a party id")
    if kind == "deposit" and not (_party_ref(step.get("into")) and _is_id(step.get("amount"))):
        problems.append("deposit needs into and amount ids")
    if not _is_id(step.get("at" if kind == "wait_until" else "deadline")):
        problems.append("needs an instant id")
    if not (_continuation(step.get("then")) and _continuation(step.get("on_timeout"))):
        problems.append("then/on_timeout must be \"end\", an id or a list of ids")
    if kind == "choice":
        bounds = step.get("bounds")
        if not (isinstance(bounds, dict) and type(bounds.get("from")) is int
                and type(bounds.get("to")) is int and bounds["from"] <= bounds["to"]):
            return problems + ["bounds need integers from <= to"]
        branches = step.get("branches")
        if not isinstance(branches, list) or not branches:
            return problems + ["choice needs at least one branch"]
        for index, branch in enumerate(branches, 1):
            guard = branch.get("guard") if isinstance(branch, dict) else None
            if not (isinstance(guard, dict) and isinstance(guard.get("op"), str)
                    and guard["op"] in GUARD_OPERATORS
                    and type(guard.get("value")) is int
                    and bounds["from"] <= guard["value"] <= bounds["to"]):
                problems.append(f"branch {index} needs a guard op in {sorted(GUARD_OPERATORS)} "
                                "with an integer value inside bounds")
            elif not _continuation(branch.get("then")):
                problems.append(f"branch {index} then must be an id or a list of ids")
    return problems


def _readings_evidence(readings: Any) -> list[Any]:
    return [entry for reading in readings if isinstance(reading, dict)
            for entry in reading.get("evidence") or []] if isinstance(readings, list) else []


def _hoist(draft: dict[str, Any], owner: dict[str, Any], field: str, table: str,
           hoisted: dict[str, tuple[str, str]]) -> None:
    """Move a definition written at a reference into `table`, leaving its new id."""
    value = owner.get(field)
    if not isinstance(value, dict):
        return
    readings = value.get("alternatives")
    if isinstance(readings, list):
        # A reading may name a declared quantity; `sum` of one is that quantity.
        readings = [{**reading, "expr": {"sum": [reading["expr"]]}}
                    if isinstance(reading, dict) and table == "quantities"
                    and isinstance(reading.get("expr"), str) else reading
                    for reading in readings]
        item: dict[str, Any] = {"alternatives": readings}
    else:
        item = {"expr": value.get("expr", value)}
    taken = {entry.get("id") for name in ("quantities", "instants", "steps", "outcomes",
                                          "parties", "assets")
             for entry in draft.get(name) or [] if isinstance(entry, dict)}
    item_id = f"{owner.get('id', 'item')}_{field}"
    while item_id in taken:
        item_id += "_"
    item["id"] = item_id
    item["evidence"] = (value.get("evidence") or _readings_evidence(readings)
                        or owner.get("evidence"))
    draft.setdefault(table, []).append(item)
    owner[field] = item_id
    hoisted[item_id] = (str(owner.get("id", "item")), field)


def normalize_draft(draft: dict[str, Any]) -> tuple[dict[str, Any], dict[str, tuple[str, str]]]:
    """The draft with misplaced definitions moved to where the grammar declares them,
    and each new item id mapped to the (item, field) the model wrote it in.

    Only placement changes, never a value, and each move has one reading:
    `alternatives` nested in `expr` belong beside it, and a quantity or instant
    written at a reference is a new declared item. The builder and the formal
    semantics see the canonical grammar only.
    """
    draft = deepcopy(draft)
    hoisted: dict[str, tuple[str, str]] = {}
    if not all(isinstance(draft.get(field) or [], list)
               for field in ("quantities", "instants", "steps", "outcomes")):
        return draft, hoisted  # _shape_problems reports it
    for field in ("quantities", "instants"):
        for item in draft.get(field) or []:
            expr = item.get("expr") if isinstance(item, dict) else None
            if isinstance(expr, dict) and "alternatives" in expr and "alternatives" not in item:
                item["alternatives"] = item.pop("expr")["alternatives"]
                item["evidence"] = (item.get("evidence")
                                    or _readings_evidence(item["alternatives"]))
    for step in list(draft.get("steps") or []):
        if isinstance(step, dict):
            _hoist(draft, step, "amount", "quantities", hoisted)
            _hoist(draft, step, "deadline", "instants", hoisted)
            _hoist(draft, step, "at", "instants", hoisted)
    for outcome in list(draft.get("outcomes") or []):
        if isinstance(outcome, dict):
            _hoist(draft, outcome, "amount", "quantities", hoisted)
    return draft, hoisted


def build_core(draft: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a v4-tagged core or raise DraftError listing atomic-item defects."""
    if draft.get("schema_version") != FACT_DRAFT_VERSION:
        raise DraftError([("schema_version", f"expected {FACT_DRAFT_VERSION}")])
    draft, hoisted = normalize_draft(draft)
    try:
        problems = _shape_problems(draft)
        if problems:
            raise DraftError(problems)
        return _Builder(draft, history).build()
    except DraftError as exc:
        # Repair addresses what the model wrote, not an id it has never seen.
        raise DraftError([(hoisted[item][0], f"{hoisted[item][1]}: {message}")
                          if item in hoisted else (item, message)
                          for item, message in exc.problems]) from None
