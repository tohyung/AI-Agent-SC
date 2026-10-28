"""A2 spike: deterministic FactDraft v5 -> ShadowSemanticCore tagged v4.

The model reads; this module computes. Every lovelace amount, POSIX instant,
scope id and continuation edge is produced here from atomic draft items, so
the existing v4 validator, projector and Stage 3 stay unchanged. Spike scope:
deposit and choice steps, static `Value` expressions (design doc section 4).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V4

FACT_DRAFT_VERSION = "stage2b-fact-draft-v5"
LOVELACE_PER_ADA = 1_000_000
DAY_MS = 86_400_000
ADA_BASIS = "1 ADA = 1000000 lovelace"
OUTCOME_RECIPIENT_KIND = {"payment": "payment_recipient", "refund": "refund_recipient",
                          "release": "release_recipient"}
TZ = re.compile(r"([+-])(\d{2}):(\d{2})\Z")


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
        self.problems: list[tuple[str, str]] = []
        self.parties = self._index("parties")
        self.quantities = self._index("quantities")
        self.instants = self._index("instants")
        self.steps = self._index("steps")
        self.outcomes = self._index("outcomes")
        self.scopes: list[dict[str, Any]] = [{"scope_id": "global", "scope_type": "global"}]
        self.claims: list[dict[str, Any]] = []
        self.questions: list[dict[str, str]] = []
        self.used: set[str] = set()
        self._quantity_cache: dict[str, tuple[int | None, str, list[dict[str, Any]]]] = {}
        self._instant_cache: dict[str, tuple[int | None, str | None]] = {}
        self._visiting: set[str] = set()

    # -- draft checks ------------------------------------------------------

    def _index(self, field: str) -> dict[str, dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for item in self.draft.get(field) or []:
            item_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(item_id, str) or not item_id:
                self.problems.append((field, "item without id"))
            elif item_id in items or any(item_id in other for other in (
                    getattr(self, name, {}) for name in
                    ("parties", "quantities", "instants", "steps", "outcomes"))):
                self.problems.append((item_id, "duplicate id"))
            else:
                items[item_id] = {**item,
                                  "evidence": self._evidence(item_id, item.get("evidence"))}
        return items

    def _evidence(self, item_id: str, evidence: Any) -> list[dict[str, Any]]:
        if not isinstance(evidence, list) or not evidence:
            self.problems.append((item_id, "evidence must be a nonempty list"))
            return []
        for entry in evidence:
            span = entry.get("span") if isinstance(entry, dict) else None
            key = (entry.get("requirement_version"), entry.get("message_index")) \
                if isinstance(entry, dict) else None
            if not isinstance(span, str) or not span or span not in self.messages.get(key, ""):
                self.problems.append((item_id, f"span not found verbatim: {span!r}"))
        return [{**entry, "relation": entry.get("relation", "supports")} for entry in evidence
                if isinstance(entry, dict)]

    def _spans(self, item: dict[str, Any]) -> str:
        return " ".join(entry.get("span", "") for entry in item.get("evidence") or []
                        if isinstance(entry, dict))

    def _ref(self, table: dict[str, dict[str, Any]], ref: Any, owner: str) -> dict[str, Any] | None:
        if isinstance(ref, str) and ref in table:
            return table[ref]
        self.problems.append((owner, f"unknown reference {ref!r}"))
        return None

    # -- expressions -------------------------------------------------------

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
        expr = item.get("expr") or {}
        evidence = list(item.get("evidence") or [])
        value: int | None = None
        basis = ""
        spans = self._spans(item)

        def sub(ref: Any) -> int | None:
            if self._ref(self.quantities, ref, qid) is None:
                return None
            sub_value, _, sub_evidence = self.quantity(ref)
            evidence.extend(entry for entry in sub_evidence if entry not in evidence)
            return sub_value

        if "ada" in expr or "lovelace" in expr:
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
                    self.questions.append({"target_id": qid, "question": (
                        f"{base * num / den / LOVELACE_PER_ADA} ADA is not a whole lovelace "
                        "amount; how should it be rounded?")})
            basis = f"{spec.get('of')} * {num} / {den} (exact)"
        elif expr.get("unknown") is True:
            value = None
        else:
            self.problems.append((qid, f"unsupported quantity expression {sorted(expr)}"))
        self._visiting.discard(qid)
        self._quantity_cache[qid] = (value, basis, evidence)
        return value, basis, evidence

    def instant(self, iid: str) -> tuple[int | None, str | None]:
        """Return (POSIX ms or None if unresolved, basis or None when explicit)."""
        if iid in self._instant_cache:
            return self._instant_cache[iid]
        if iid in self._visiting:
            self.problems.append((iid, "circular instant reference"))
            return None, None
        self._visiting.add(iid)
        self.used.add(iid)
        expr = self.instants[iid].get("expr") or {}
        value: int | None = None
        basis: str | None = None
        if "date" in expr:
            spec = expr["date"]
            tz = spec.get("tz")
            match = TZ.fullmatch(tz) if isinstance(tz, str) else None
            # Never infer a timezone or time of day the source does not state.
            if match and type(spec.get("h")) is int and type(spec.get("min")) is int:
                sign = 1 if match.group(1) == "+" else -1
                offset = timezone(sign * timedelta(hours=int(match.group(2)),
                                                   minutes=int(match.group(3))))
                try:
                    moment = datetime(spec["y"], spec["m"], spec["d"], spec["h"],
                                      spec["min"], tzinfo=offset)
                    value = int(moment.timestamp() * 1000)
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
                base, _ = self.instant(spec["from"])
                value = None if base is None else base + days * DAY_MS
                basis = f"{spec['from']} + {days} days"
        elif expr.get("unknown") is not True:
            self.problems.append((iid, f"unsupported instant expression {sorted(expr)}"))
        self._visiting.discard(iid)
        self._instant_cache[iid] = (value, basis)
        return value, basis

    # -- core emission -----------------------------------------------------

    def claim(self, scope_id: str, kind: str, value: Any, evidence: list[dict[str, Any]],
              basis: str | None = None) -> str:
        claim_id = f"{scope_id}:{kind}"
        result = {"claim_id": claim_id, "kind": kind, "value": value,
                  "criticality": "financial", "scope_id": scope_id, "evidence": evidence}
        if value is None:
            result["status"] = "unresolved"
        elif basis:
            result["status"] = "derived"
            result["normalization_basis"] = basis
        else:
            result["status"] = "explicit"
        self.claims.append(result)
        return claim_id

    def party_claim(self, scope_id: str, kind: str, party_id: Any, owner: dict[str, Any]) -> None:
        party = self._ref(self.parties, party_id, owner.get("id", "?"))
        if party is None:
            return
        self.used.add(party_id)
        evidence = list(owner.get("evidence") or [])
        evidence.extend(entry for entry in party.get("evidence") or [] if entry not in evidence)
        self.claim(scope_id, kind, party["name"], evidence)

    def deadline_claim(self, scope_id: str, kind: str, instant_id: Any, owner: str) -> str | None:
        item = self._ref(self.instants, instant_id, owner)
        if item is None:
            return None
        value, basis = self.instant(instant_id)
        if value is None:
            self.questions.append({"target_id": instant_id,
                                   "question": "Which exact time and timezone is this deadline?"})
        # Cite only the instant's own phrase: a derived deadline citing its base
        # date would contradict that calendar date under the v4 date check.
        return self.claim(scope_id, kind, value, list(item.get("evidence") or []), basis)

    def amount_claim(self, scope_id: str, amount: Any, owner: dict[str, Any],
                     balance: int | None) -> int | None:
        if amount == "remaining":
            evidence = list(owner.get("evidence") or [])
            self.claim(scope_id, "amount_lovelace", balance, evidence,
                       "remaining balance of the source account on this path")
            return balance
        if self._ref(self.quantities, amount, owner.get("id", "?")) is None:
            return None
        value, basis, evidence = self.quantity(amount)
        self.claim(scope_id, "amount_lovelace", value, evidence, basis)
        return value

    def chain(self, parent: dict[str, Any], items: Any, balances: dict[str, int | None],
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
                balances: dict[str, int | None]) -> dict[str, Any]:
        if oid in self.used:
            self.problems.append((oid, "outcome reached by more than one path"))
        self.used.add(oid)
        item = self.outcomes[oid]
        scope = {"scope_id": f"o_{oid}", "scope_type": "terminal_outcome",
                 "outcome_id": oid, "parent_scope_id": parent["scope_id"]}
        self.scopes.append(scope)
        kind = OUTCOME_RECIPIENT_KIND.get(item.get("kind"))
        if kind is None:
            self.problems.append((oid, f"unknown outcome kind {item.get('kind')!r}"))
            return scope
        source = item.get("from_account")
        self.party_claim(scope["scope_id"], "payment_source_account_owner", source, item)
        self.party_claim(scope["scope_id"], kind, item.get("to"), item)
        balance = balances.get(source)
        paid = self.amount_claim(scope["scope_id"], item.get("amount"), item, balance)
        if paid is not None and balance is not None:
            if paid > balance:
                self.problems.append((oid, f"pays {paid} but the account holds {balance}"))
            balances[source] = balance - paid
        else:
            balances[source] = None
        return scope

    def step(self, sid: str, balances: dict[str, int | None]) -> str:
        if sid in self.used:
            self.problems.append((sid, "step reached by more than one path"))
        self.used.add(sid)
        item = self.steps[sid]
        kind = item.get("kind")
        scope = {"scope_id": f"t_{sid}", "scope_type": "transition", "transition_kind": kind}
        self.scopes.append(scope)
        evidence = list(item.get("evidence") or [])
        # The timeout path sees balances before this step: a missed deposit funds nothing.
        before = dict(balances)
        if kind == "deposit":
            self.party_claim(scope["scope_id"], "depositing_party", item.get("by"), item)
            self.party_claim(scope["scope_id"], "destination_account_owner", item.get("into"), item)
            if self._ref(self.quantities, item.get("amount"), sid) is not None:
                value, basis, amount_evidence = self.quantity(item["amount"])
                self.claim(scope["scope_id"], "amount_lovelace", value, amount_evidence, basis)
                current = balances.get(item.get("into"), 0)
                balances[item.get("into")] = (None if value is None or current is None
                                              else current + value)
            deadline_kind = "deposit_deadline_ms"
        elif kind == "choice":
            self.party_claim(scope["scope_id"], "choice_owner", item.get("by"), item)
            bounds = item.get("bounds") or {}
            scope["choice_bounds"] = {"from": bounds.get("from"), "to": bounds.get("to"),
                                      "source_evidence": evidence}
            for index, branch in enumerate(item.get("branches") or [], 1):
                guard = branch.get("guard") or {}
                branch_scope = {"scope_id": f"b_{sid}_{index}", "scope_type": "branch",
                                "decision_id": scope["scope_id"], "branch_id": f"{sid}_{index}",
                                "choice_guard": {"operator": guard.get("op"),
                                                 "value": guard.get("value"),
                                                 "source_evidence": evidence}}
                self.scopes.append(branch_scope)
                self.chain(branch_scope, branch.get("then"), dict(balances), sid)
            deadline_kind = "choice_deadline_ms"
        else:
            self.problems.append((sid, f"step kind {kind!r} is outside the spike"))
            return scope["scope_id"]
        deadline_id = self.deadline_claim(scope["scope_id"], deadline_kind,
                                          item.get("deadline"), sid)
        timeout = {"scope_id": f"to_{sid}", "scope_type": "timeout", "timeout_id": f"to_{sid}",
                   "decision_id": scope["scope_id"]}
        if deadline_id:
            timeout["deadline_claim_id"] = deadline_id
        self.scopes.append(timeout)
        self.chain(timeout, item.get("on_timeout"), before, sid)
        if kind == "deposit":
            self.chain(scope, item.get("then"), balances, sid)
        return scope["scope_id"]

    def build(self) -> dict[str, Any]:
        asset = self.draft.get("asset") or {}
        if asset.get("ada") is not True:
            self.problems.append(("asset", "only ADA is inside the spike"))
        else:
            self.claim("global", "asset", "ADA", self._evidence("asset", asset.get("evidence")))
        referenced = {ref for step in self.steps.values()
                      for ref in _step_refs(step)}
        roots = [sid for sid in self.steps if sid not in referenced]
        if len(roots) != 1:
            self.problems.append(("steps", f"expected one first step, found {roots}"))
        else:
            self.step(roots[0], {})
        for table in (self.parties, self.quantities, self.instants, self.steps, self.outcomes):
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
        unresolved = any(claim["status"] == "unresolved" for claim in self.claims)
        # Resolution follows from the facts; the model's resolution_hint is advisory only.
        resolution = "clarification_required" if unresolved else "accepted_interpretation"
        questions = [question["question"] for question in self.questions] if unresolved else []
        return {"schema_version": CORE_SCHEMA_VERSION_V4,
                "requirement_history": self.history,
                "behavior_scopes": self.scopes, "claims": self.claims,
                "required_clarifications": questions, "unscored_observations": [],
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


def build_core(draft: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a v4-tagged core or raise DraftError listing atomic-item defects."""
    if draft.get("schema_version") != FACT_DRAFT_VERSION:
        raise DraftError([("schema_version", f"expected {FACT_DRAFT_VERSION}")])
    return _Builder(draft, history).build()
