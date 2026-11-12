"""A plain-language summary of an accepted-intent candidate, for the user to review (E7, Q-NHÁNH 3).

The text is computed from the semantic core only (scopes and claims), never by a model, so what the
user reads is exactly what the contract will be generated from. Times are shown in the zone the
request uses (UTC+7 when it says Vietnam time, else the single offset it states, else UTC).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from research.formalization.fact_builder import _zones, request_language

WORDS = {
    "vi": {
        "intro": "Tôi hiểu hợp đồng như sau:",
        "deposit": "{party} nạp {amount} vào hợp đồng trước {time}.",
        "deposit_for": "{party} nạp {amount} vào hợp đồng (giữ cho {owner}) trước {time}.",
        "choice": "{owner} chọn một giá trị từ {low} đến {high} trước {time}.",
        "choice_one": "{owner} bấm xác nhận trước {time}.",
        "notify": "Bất kỳ ai cũng có thể bấm xác nhận trước {time}.",
        "wait": "Chờ đến {time}.",
        "branch": "Nếu {owner} chọn {guard}:",
        "on_success": "Khi việc đó xảy ra:",
        "timeout": "Nếu đến {time} mà việc đó chưa xảy ra:",
        "pay": "hợp đồng chuyển {amount} (tiền {source} đã nạp) cho {recipient}.",
        "pay_rest": "hợp đồng chuyển phần còn lại của tiền {source} đã nạp cho {recipient}.",
        "end": "hợp đồng kết thúc; tiền còn giữ trong hợp đồng thì trả lại cho người đã nạp.",
        "question": "Như vậy có đúng ý bạn không? Nếu sai chỗ nào, xin nói rõ chỗ đó.",
        "ops": {"eq": "{v}", "ge": "từ {v} trở lên", "gt": "lớn hơn {v}", "le": "từ {v} trở xuống",
                "lt": "nhỏ hơn {v}"},
        "time": "{hm} ngày {dmy} ({zone})",
    },
    "en": {
        "intro": "This is how I understand the contract:",
        "deposit": "{party} deposits {amount} into the contract by {time}.",
        "deposit_for": "{party} deposits {amount} into the contract (held for {owner}) by {time}.",
        "choice": "{owner} chooses a value from {low} to {high} by {time}.",
        "choice_one": "{owner} presses confirm by {time}.",
        "notify": "Anyone can press confirm by {time}.",
        "wait": "Wait until {time}.",
        "branch": "If {owner} chooses {guard}:",
        "on_success": "When that happens:",
        "timeout": "If that has not happened by {time}:",
        "pay": "the contract sends {amount} (from what {source} deposited) to {recipient}.",
        "pay_rest": "the contract sends what is left of {source}'s deposit to {recipient}.",
        "end": "the contract ends; money it still holds goes back to whoever deposited it.",
        "question": "Is this what you want? If something is wrong, please say exactly what.",
        "ops": {"eq": "{v}", "ge": "{v} or more", "gt": "more than {v}", "le": "{v} or less",
                "lt": "less than {v}"},
        # ISO dates in English: "05/08/2027" reads as May 8 to many English readers.
        "time": "{hm} on {iso} ({zone})",
    },
}


class _Summary:
    def __init__(self, core: dict[str, Any], language: str):
        self.words = WORDS[language]
        self.scopes = {scope["scope_id"]: scope for scope in core.get("behavior_scopes", [])}
        self.claims: dict[tuple[str, str], Any] = {}
        for claim in core.get("claims", []):
            self.claims.setdefault((claim["scope_id"], claim["kind"]), claim.get("value"))
        messages = [message for version in core.get("requirement_history", [])
                    for message in version.get("messages", [])]
        zones = set().union(*(_zones(message) for message in messages)) if messages else set()
        hours = 7 if 7 in zones else (next(iter(zones)) if len(zones) == 1 else 0)
        self.zone = timezone(timedelta(hours=hours))
        self.zone_name = "UTC" if hours == 0 else f"UTC{hours:+d}"
        self.asset = self.claims.get(("global", "asset"))
        self.lines: list[str] = []
        self.seen: set[str] = set()

    def claim(self, scope_id: str, kind: str) -> Any:
        return self.claims.get((scope_id, kind))

    def time(self, ms: Any) -> str:
        if type(ms) is not int:
            return "?"
        moment = datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(self.zone)
        return self.words["time"].format(hm=f"{moment:%H:%M}", dmy=f"{moment:%d/%m/%Y}",
                                         iso=f"{moment:%Y-%m-%d}", zone=self.zone_name)

    def amount(self, scope_id: str) -> str:
        lovelace = self.claim(scope_id, "amount_lovelace")
        if type(lovelace) is int:
            ada = Decimal(lovelace) / Decimal(1_000_000)
            return f"{ada.normalize():f} ADA"
        units = self.claim(scope_id, "amount_token_units")
        if units is not None:
            asset = self.claim(scope_id, "asset") or "token"
            name = str(asset).rsplit("/", 1)[-1]
            try:
                name = bytes.fromhex(name).decode("utf-8")
            except ValueError:
                pass
            return f"{units} {name}"
        return "?"

    def children(self, scope_id: str) -> str | None:
        """The scope that follows `scope_id` on its path."""
        scope = self.scopes.get(scope_id, {})
        if scope.get("continuation_scope_id"):
            return scope["continuation_scope_id"]
        continued = {item.get("continuation_scope_id") for item in self.scopes.values()}
        return next((sid for sid, item in self.scopes.items()
                     if item.get("parent_scope_id") == scope_id and sid not in continued), None)

    def say(self, depth: int, text: str) -> None:
        self.lines.append("  " * depth + "- " + text)

    def follow(self, scope_id: str | None, depth: int) -> None:
        if scope_id is None:
            self.say(depth, self.words["end"])
            return
        if scope_id in self.seen:
            return
        self.seen.add(scope_id)
        scope = self.scopes.get(scope_id, {})
        kind = scope.get("scope_type")
        if kind == "terminal_outcome":
            self.outcome(scope_id, depth)
            self.follow(self.children(scope_id), depth)
        elif kind == "transition":
            self.transition(scope_id, scope, depth)
        else:
            self.follow(self.children(scope_id), depth)

    def outcome(self, scope_id: str, depth: int) -> None:
        source = self.claim(scope_id, "payment_source_account_owner")
        recipient = next((self.claim(scope_id, kind) for kind in
                          ("payment_recipient", "refund_recipient", "release_recipient")
                          if self.claim(scope_id, kind) is not None), "?")
        amount = self.amount(scope_id)
        if amount == "?" and self.claim(scope_id, "amount_lovelace") is None:
            self.say(depth, self.words["pay_rest"].format(source=source, recipient=recipient))
        else:
            self.say(depth, self.words["pay"].format(source=source, amount=amount,
                                                     recipient=recipient))

    def transition(self, scope_id: str, scope: dict[str, Any], depth: int) -> None:
        action = scope.get("transition_kind")
        words = self.words
        if action == "deposit":
            deadline = self.claim(scope_id, "deposit_deadline_ms")
            party = self.claim(scope_id, "depositing_party")
            owner = self.claim(scope_id, "destination_account_owner")
            # The account is shown only when it is not the depositor's own (no Marlowe jargon).
            key = "deposit" if owner in {None, party} else "deposit_for"
            self.say(depth, words[key].format(party=party, amount=self.amount(scope_id),
                                              owner=owner, time=self.time(deadline)))
        elif action == "choice":
            deadline = self.claim(scope_id, "choice_deadline_ms")
            owner = self.claim(scope_id, "choice_owner")
            bounds = scope.get("choice_bounds") or {}
            low, high = bounds.get("from"), bounds.get("to")
            key = "choice_one" if low == high else "choice"
            self.say(depth, words[key].format(owner=owner, low=low, high=high,
                                              time=self.time(deadline)))
        elif action == "notify":
            deadline = self.claim(scope_id, "timeout_ms")
            self.say(depth, words["notify"].format(time=self.time(deadline)))
        else:
            deadline = self.claim(scope_id, "payment_release_time_ms")
            self.say(depth, words["wait"].format(time=self.time(deadline)))
        branches = [(sid, item) for sid, item in self.scopes.items()
                    if item.get("scope_type") == "branch" and item.get("decision_id") == scope_id]
        if branches and action == "choice":
            owner = self.claim(scope_id, "choice_owner")
            for sid, item in branches:
                guard = item.get("choice_guard") or {}
                text = words["ops"].get(guard.get("operator"), "{v}").format(v=guard.get("value"))
                self.say(depth, words["branch"].format(owner=owner, guard=text))
                self.follow(item.get("continuation_scope_id") or self.children(sid), depth + 1)
        elif scope.get("continuation_scope_id") and action == "payment":
            self.follow(scope["continuation_scope_id"], depth)
        elif scope.get("continuation_scope_id"):
            self.say(depth, words["on_success"])
            self.follow(scope["continuation_scope_id"], depth + 1)
        else:
            self.say(depth, words["on_success"])
            self.say(depth + 1, words["end"])
        for sid, item in self.scopes.items():
            if item.get("scope_type") == "timeout" and item.get("decision_id") == scope_id:
                self.say(depth, words["timeout"].format(time=self.time(deadline)))
                self.follow(self.children(sid), depth + 1)


def summarize(core: dict[str, Any]) -> str:
    """The summary text, in the language of the request, ending with the review question."""
    messages = [message for version in core.get("requirement_history", [])
                for message in version.get("messages", [])]
    language = request_language(messages)
    summary = _Summary(core, language)
    continued = {item.get("continuation_scope_id") for item in summary.scopes.values()}
    roots = [sid for sid, item in summary.scopes.items()
             if item.get("scope_type") == "transition" and sid not in continued
             and not item.get("parent_scope_id")]
    # A transition reached only through an outcome chain is not a root either.
    reached = {item.get("continuation_scope_id") for item in summary.scopes.values()
               if item.get("scope_type") in {"terminal_outcome", "branch"}}
    roots = [sid for sid in roots if sid not in reached] or roots[:1]
    for root in roots[:1]:
        summary.follow(root, 0)
    return "\n".join([WORDS[language]["intro"], *summary.lines, WORDS[language]["question"]])
