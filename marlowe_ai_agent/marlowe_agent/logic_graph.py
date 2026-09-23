from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .marlowe_ast import is_close, walk_contract
from .marlowe_validator import validate_contract
from .models import ContractDraft, LogicGraphResult
from .utils import canonical_json, unique_strings


MAX_PATHS = 10_000


@dataclass
class PathState:
    balances: dict[tuple[str, str], int | None] = field(default_factory=dict)
    bound_values: dict[str, int | None] = field(default_factory=dict)
    chosen_ids: set[str] = field(default_factory=set)
    deadline_stack: list[int] = field(default_factory=list)

    def copy(self) -> PathState:
        return PathState(self.balances.copy(), self.bound_values.copy(),
                         self.chosen_ids.copy(), self.deadline_stack.copy())


def _key(account: Any, token: Any) -> tuple[str, str]:
    return canonical_json(account), canonical_json(token)


def _evaluate(value: Any, state: PathState) -> int | None:
    if type(value) is int:
        return value
    if not isinstance(value, dict):
        return None
    if "use_value" in value:
        return state.bound_values.get(value["use_value"])
    if "negate" in value:
        inner = _evaluate(value["negate"], state)
        return -inner if inner is not None else None
    for left, right, operation in [("add", "and", 1), ("value", "minus", -1)]:
        if left in value and right in value:
            a, b = _evaluate(value[left], state), _evaluate(value[right], state)
            return a + operation * b if a is not None and b is not None else None
    return None


def _inspect_refs(expr: Any, state: PathState, path: str,
                  errors: list[str], warnings: list[str]) -> None:
    if isinstance(expr, list):
        for index, item in enumerate(expr):
            _inspect_refs(item, state, f"{path}[{index}]", errors, warnings)
    elif isinstance(expr, dict):
        if "use_value" in expr and expr["use_value"] not in state.bound_values:
            errors.append(f"{path}.use_value: biến '{expr['use_value']}' chưa được Let định nghĩa.")
        for key in ("value_of_choice", "chose_something_for"):
            if key in expr and canonical_json(expr[key]) not in state.chosen_ids:
                warnings.append(f"{path}.{key}: Choice chưa được chọn trên đường đi này.")
        for key, value in expr.items():
            _inspect_refs(value, state, f"{path}.{key}", errors, warnings)


def check_draft_consistency(draft: ContractDraft) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    roles: set[str] = set()
    amounts: set[int] = set()
    timeouts: set[int] = set()

    def visit(value: Any, path: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            if "role_token" in value:
                role_name = value["role_token"]
                roles.add(role_name)
                allowed = {item for party in draft.parties for item in (party.name, party.role)}
                if role_name not in allowed:
                    errors.append(f"{path}.role_token: vai trò '{role_name}' không có trong draft.parties.")
            if "timeout" in value:
                timeouts.add(value["timeout"])
            for key in ("pay", "deposits"):
                if key in value and type(value[key]) is int:
                    amounts.add(value[key])
            for key, item in value.items():
                visit(item, f"{path}.{key}")

    visit(draft.marlowe_contract, "root")
    for party in draft.parties:
        if party.name not in roles and party.role not in roles:
            warnings.append(f"root: bên '{party.name}' trong draft không xuất hiện trong AST.")
    if draft.amount is not None and draft.amount not in amounts:
        warnings.append(f"root: không thấy số tiền {draft.amount} trong Deposit/Pay; kiểm tra đơn vị lovelace.")
    for name in ("deposit_timeout", "decision_timeout"):
        timeout = getattr(draft, name)
        if timeout is not None and timeout not in timeouts:
            warnings.append(f"root: {name}={timeout} không xuất hiện trong AST.")
    return unique_strings(errors), unique_strings(warnings)


class LogicGraphVerifier:
    def verify(self, contract: Any, draft: ContractDraft | None = None) -> LogicGraphResult:
        validation_errors = validate_contract(contract)
        if validation_errors:
            return LogicGraphResult(False, validation_errors, {"nodes": [], "edges": []},
                                    errors=validation_errors)

        graph = self._build_graph(contract)
        errors: list[str] = []
        warnings: list[str] = []
        paths_explored = 0
        truncated = False
        unknown = False

        def visit(node: Any, path: str, state: PathState) -> None:
            nonlocal paths_explored, truncated, unknown
            if paths_explored >= MAX_PATHS:
                truncated = True
                return
            if is_close(node):
                paths_explored += 1
                for balance in state.balances.values():
                    if balance is not None and balance > 0:
                        warnings.append(f"{path}: Close còn dư {balance}; Marlowe sẽ hoàn về chủ account.")
                return
            if "when" in node:
                timeout = node["timeout"]
                if state.deadline_stack and timeout <= state.deadline_stack[-1]:
                    errors.append(f"{path}.timeout: timeout lồng nhau không tăng ({timeout} <= {state.deadline_stack[-1]}).")
                if not node["when"]:
                    warnings.append(f"{path}.when: When rỗng, chỉ chờ timeout.")
                self._check_case_overlap(node["when"], path, errors)
                for index, item in enumerate(node["when"]):
                    action = item["case"]
                    action_path = f"{path}.when[{index}].case"
                    branch = state.copy()
                    branch.deadline_stack.append(timeout)
                    _inspect_refs(action, branch, action_path, errors, warnings)
                    if "deposits" in action:
                        amount = _evaluate(action["deposits"], branch)
                        if amount is not None and amount <= 0:
                            errors.append(f"{action_path}.deposits: số tiền Deposit phải > 0.")
                        # TODO(spec): Minimum ADA is protocol-parameter dependent; query it before warning.
                        account_key = _key(action["into_account"], action["of_token"])
                        balance = branch.balances.get(account_key, 0)
                        branch.balances[account_key] = balance + amount if balance is not None and amount is not None else None
                        unknown |= amount is None
                    elif "for_choice" in action:
                        branch.chosen_ids.add(canonical_json(action["for_choice"]))
                    visit(item["then"], f"{path}.when[{index}].then", branch)
                timeout_branch = state.copy()
                timeout_branch.deadline_stack.append(timeout)
                visit(node["timeout_continuation"], f"{path}.timeout_continuation", timeout_branch)
            elif "pay" in node:
                _inspect_refs(node["pay"], state, f"{path}.pay", errors, warnings)
                amount = _evaluate(node["pay"], state)
                if amount is not None and amount <= 0:
                    errors.append(f"{path}.pay: số tiền Pay phải > 0.")
                account_key = _key(node["from_account"], node["token"])
                balance = state.balances.get(account_key, 0)
                if amount is not None and balance is not None:
                    if amount > balance:
                        errors.append(f"{path}.pay: Pay {amount} vượt số dư {balance}; sẽ chỉ trả một phần.")
                    transferred = min(max(amount, 0), balance)
                    state.balances[account_key] = balance - transferred
                    if "account" in node["to"]:
                        payee_key = _key(node["to"]["account"], node["token"])
                        payee_balance = state.balances.get(payee_key, 0)
                        state.balances[payee_key] = payee_balance + transferred if payee_balance is not None else None
                else:
                    state.balances[account_key] = None
                    unknown = True
                visit(node["then"], f"{path}.then", state)
            elif "let" in node:
                _inspect_refs(node["be"], state, f"{path}.be", errors, warnings)
                state.bound_values[node["let"]] = _evaluate(node["be"], state)
                unknown |= state.bound_values[node["let"]] is None
                visit(node["then"], f"{path}.then", state)
            elif "if" in node:
                _inspect_refs(node["if"], state, f"{path}.if", errors, warnings)
                if type(node["if"]) is bool:
                    dead = "else" if node["if"] else "then"
                    live = "then" if node["if"] else "else"
                    warnings.append(f"{path}.{dead}: nhánh chết vì điều kiện hằng.")
                    visit(node[live], f"{path}.{live}", state)
                else:
                    visit(node["then"], f"{path}.then", state.copy())
                    visit(node["else"], f"{path}.else", state.copy())
            else:
                _inspect_refs(node["assert"], state, f"{path}.assert", errors, warnings)
                visit(node["then"], f"{path}.then", state)

        visit(contract, "root", PathState())
        if truncated:
            warnings.append("root: đã cắt bớt phân tích vì vượt MAX_PATHS.")
        if unknown:
            warnings.append("root: không thể kiểm tĩnh đầy đủ với giá trị không xác định.")
        if draft:
            draft_errors, draft_warnings = check_draft_consistency(draft)
            errors.extend(draft_errors)
            warnings.extend(draft_warnings)
        errors = unique_strings(errors)
        warnings = unique_strings(warnings)
        findings = errors + warnings or ["Logic graph pass."]
        return LogicGraphResult(not errors, findings, graph, errors, warnings, paths_explored)

    def _check_case_overlap(self, cases: list[dict[str, Any]], path: str, errors: list[str]) -> None:
        seen: set[str] = set()
        choices: dict[str, list[tuple[int, int]]] = {}
        for index, item in enumerate(cases):
            action = item["case"]
            action_path = f"{path}.when[{index}].case"
            encoded = canonical_json(action)
            if encoded in seen:
                errors.append(f"{action_path}: action trùng hệt case khác trong cùng When.")
            seen.add(encoded)
            if "for_choice" not in action:
                continue
            key = canonical_json(action["for_choice"])
            previous = choices.setdefault(key, [])
            for bound in action["choose_between"]:
                low, high = bound["from"], bound["to"]
                if any(max(low, old_low) <= min(high, old_high) for old_low, old_high in previous):
                    errors.append(f"{action_path}.choose_between: các khoảng Choice cùng ID chồng lấn.")
            previous.extend((bound["from"], bound["to"]) for bound in action["choose_between"])

    def _build_graph(self, contract: Any) -> dict[str, Any]:
        nodes: list[dict[str, str]] = []
        edges: list[dict[str, str]] = []
        for path, node in walk_contract(contract):
            kind = "Close" if is_close(node) else next((name for name in ("when", "pay", "if", "let", "assert") if name in node), "Unknown")
            nodes.append({"id": path, "type": kind.title()})
            if is_close(node):
                continue
            if "when" in node:
                for index, item in enumerate(node["when"]):
                    label = canonical_json(item["case"])
                    edges.append({"from": path, "to": f"{path}.when[{index}].then",
                                  "label": label[:80] + ("..." if len(label) > 80 else "")})
                edges.append({"from": path, "to": f"{path}.timeout_continuation",
                              "label": f"timeout@{node['timeout']}"})
            elif "if" in node:
                for branch in ("then", "else"):
                    edges.append({"from": path, "to": f"{path}.{branch}", "label": branch})
            else:
                edges.append({"from": path, "to": f"{path}.then", "label": "then"})
        return {"nodes": nodes, "edges": edges}
