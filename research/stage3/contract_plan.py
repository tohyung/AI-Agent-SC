"""Deterministic Marlowe constructors for compiler plugins, never model output.

This lowers a typed, source-linked plan to Core V1 JSON. It does not establish
funding conservation, business intent, or compiler authority; plugins and the
reference comparison retain those responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marlowe_ai_agent.marlowe_agent.marlowe_validator import validate_contract
from research.stage2b.intent_spec import parse_native_asset_id


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class ClaimValue:
    value: Any
    claim_id: str


@dataclass(frozen=True)
class Close:
    scope_id: str


@dataclass(frozen=True)
class Pay:
    scope_id: str
    account: ClaimValue
    recipient: ClaimValue
    asset: ClaimValue
    amount: ClaimValue
    then: ContractNode


@dataclass(frozen=True)
class Deposit:
    scope_id: str
    party: ClaimValue
    account: ClaimValue
    asset: ClaimValue
    amount: ClaimValue


@dataclass(frozen=True)
class Choice:
    scope_id: str
    owner: ClaimValue
    lower: int
    upper: int


@dataclass(frozen=True)
class Notify:
    scope_id: str
    observation: bool


Action = Deposit | Choice | Notify


@dataclass(frozen=True)
class Case:
    action: Action
    then: ContractNode


@dataclass(frozen=True)
class When:
    scope_id: str
    cases: tuple[Case, ...]
    deadline: ClaimValue
    timeout: ContractNode


@dataclass(frozen=True)
class ChoiceGuard:
    choice_scope_id: str
    owner: ClaimValue
    operator: str
    threshold: int


@dataclass(frozen=True)
class IfChoice:
    scope_id: str
    guard: ChoiceGuard
    then: ContractNode
    otherwise: ContractNode


ContractNode = Close | Pay | When | IfChoice


@dataclass(frozen=True)
class LoweredPlan:
    contract: Any
    mapping_evidence: tuple[dict[str, str], ...]


def _role(value: ClaimValue) -> dict[str, str]:
    if not isinstance(value.value, str) or not value.value or not value.claim_id:
        raise PlanError("role requires a nonempty source-linked name")
    return {"role_token": value.value}


def _asset(value: ClaimValue) -> dict[str, str]:
    if not value.claim_id:
        raise PlanError("asset requires a source claim")
    if value.value == "ADA":
        return {"currency_symbol": "", "token_name": ""}
    parsed = parse_native_asset_id(value.value) if isinstance(value.value, str) else None
    if parsed is None:
        raise PlanError("asset requires ADA or a canonical native identifier")
    policy, name_hex = parsed
    try:
        name = bytes.fromhex(name_hex).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanError("native token name must be UTF-8 for Core V1 JSON") from exc
    return {"currency_symbol": policy, "token_name": name}


def _positive(value: ClaimValue, label: str) -> int:
    if not value.claim_id or type(value.value) is not int or value.value <= 0:
        raise PlanError(f"{label} requires a positive source-linked integer")
    return value.value


def lower_contract_plan(root: ContractNode) -> LoweredPlan:
    mapping: list[dict[str, str]] = []
    active: set[int] = set()
    node_count = 0

    def record(kind: str, source_id: str, path: str) -> None:
        if not isinstance(source_id, str) or not source_id:
            raise PlanError("mapping source ID must be nonempty")
        mapping.append({"source_kind": kind, "source_id": source_id,
                        "ast_path": path})

    def claim(item: ClaimValue, path: str) -> None:
        record("claim", item.claim_id, path)

    def descend(node: ContractNode, path: str,
                available_choices: frozenset[tuple[str, str]]) -> Any:
        nonlocal node_count
        node_count += 1
        if node_count > 512 or id(node) in active:
            raise PlanError("contract plan cycle or node budget exceeded")
        active.add(id(node))
        try:
            if isinstance(node, Close):
                record("scope", node.scope_id, path)
                return "close"
            if isinstance(node, Pay):
                record("scope", node.scope_id, path)
                amount = _positive(node.amount, "payment amount")
                account = _role(node.account)
                recipient = _role(node.recipient)
                asset = _asset(node.asset)
                for item, suffix in ((node.account, ".from_account"),
                                     (node.recipient, ".to.party"),
                                     (node.asset, ".token"), (node.amount, ".pay")):
                    claim(item, path + suffix)
                return {"pay": amount, "from_account": account,
                        "to": {"party": recipient}, "token": asset,
                        "then": descend(node.then, path + ".then", available_choices)}
            if isinstance(node, When):
                record("scope", node.scope_id, path)
                deadline = _positive(node.deadline, "timeout")
                claim(node.deadline, path + ".timeout")
                cases = []
                for index, case in enumerate(node.cases):
                    base = f"{path}.when[{index}]"
                    action = case.action
                    record("scope", action.scope_id, base + ".case")
                    case_choices = available_choices
                    if isinstance(action, Deposit):
                        body = {"party": _role(action.party),
                                "into_account": _role(action.account),
                                "of_token": _asset(action.asset),
                                "deposits": _positive(action.amount, "deposit amount")}
                        for item, suffix in ((action.party, ".party"),
                                             (action.account, ".into_account"),
                                             (action.asset, ".of_token"),
                                             (action.amount, ".deposits")):
                            claim(item, base + ".case" + suffix)
                    elif isinstance(action, Choice):
                        if (type(action.lower) is not int or type(action.upper) is not int
                                or action.lower > action.upper):
                            raise PlanError("choice bounds must be ordered integers")
                        body = {"for_choice": {
                            "choice_name": action.scope_id,
                            "choice_owner": _role(action.owner)},
                            "choose_between": [{"from": action.lower,
                                                "to": action.upper}]}
                        claim(action.owner, base + ".case.for_choice.choice_owner")
                        case_choices = available_choices | {(action.scope_id, action.owner.value)}
                    elif isinstance(action, Notify):
                        if type(action.observation) is not bool:
                            raise PlanError("notify needs a typed observation")
                        body = {"notify_if": action.observation}
                    else:
                        raise PlanError("unsupported case action")
                    cases.append({"case": body, "then": descend(
                        case.then, base + ".then", case_choices)})
                return {"when": cases, "timeout": deadline,
                        "timeout_continuation": descend(
                            node.timeout, path + ".timeout_continuation", available_choices)}
            if isinstance(node, IfChoice):
                record("scope", node.scope_id, path)
                guard = node.guard
                operator = {"ge": "ge_than", "gt": "gt", "le": "le_than",
                            "lt": "lt", "eq": "equal_to"}.get(guard.operator)
                if operator is None or type(guard.threshold) is not int:
                    raise PlanError("choice guard requires a supported integer comparison")
                if (guard.choice_scope_id, guard.owner.value) not in available_choices:
                    raise PlanError("choice guard refers to a Choice absent from this path")
                choice_id = {"choice_name": guard.choice_scope_id,
                             "choice_owner": _role(guard.owner)}
                claim(guard.owner, path + ".if.value.value_of_choice.choice_owner")
                return {"if": {"value": {"value_of_choice": choice_id},
                               operator: guard.threshold},
                        "then": descend(node.then, path + ".then", available_choices),
                        "else": descend(node.otherwise, path + ".else", available_choices)}
            raise PlanError("unsupported contract-plan node")
        finally:
            active.remove(id(node))

    contract = descend(root, "$", frozenset())
    errors = validate_contract(contract)
    if errors:
        raise PlanError(f"lowered Core V1 AST is structurally invalid: {errors}")
    return LoweredPlan(contract, tuple(mapping))
