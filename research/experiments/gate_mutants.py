"""E5 candidate variants: deterministic edits of a reference Core V1 contract.

An operator only proposes an edit; whether the result is wrong is decided by the label
oracle (`gate_labels`), never by the operator's name (docs/archive/E5-Evidence-Gates.md, section 3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
ADA = {"currency_symbol": "", "token_name": ""}
MAX_SITES = 2
COMPARISONS = ("ge_than", "gt", "lt", "le_than", "equal_to")

Path = tuple[Any, ...]


@dataclass(frozen=True)
class Variant:
    operator: str
    site: int
    intent: str  # "wrong" or "equivalent": what the operator aims for, not the label
    contract: Any


def _nodes(value: Any, path: Path = ()) -> Iterator[tuple[Path, Any]]:
    """Every dict/list node in a fixed pre-order."""
    yield path, value
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _nodes(value[key], (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _nodes(item, (*path, index))


def _contracts(value: Any, path: Path = ()) -> Iterator[tuple[Path, Any]]:
    """Contract nodes only (not actions, values or observations), in pre-order."""
    yield path, value
    if not isinstance(value, dict):
        return
    if "when" in value:
        for index, branch in enumerate(value["when"]):
            yield from _contracts(branch["then"], (*path, "when", index, "then"))
        yield from _contracts(value["timeout_continuation"], (*path, "timeout_continuation"))
    elif "if" in value:
        yield from _contracts(value["then"], (*path, "then"))
        yield from _contracts(value["else"], (*path, "else"))
    elif "then" in value:
        yield from _contracts(value["then"], (*path, "then"))


def _get(root: Any, path: Path) -> Any:
    for key in path:
        root = root[key]
    return root


def _set(root: Any, path: Path, value: Any) -> Any:
    if not path:
        return value
    _get(root, path[:-1])[path[-1]] = value
    return root


def roles(contract: Any) -> list[str]:
    return sorted({node["role_token"] for _, node in _nodes(contract)
                   if isinstance(node, dict) and isinstance(node.get("role_token"), str)})


def _other_role(contract: Any, current: Any) -> dict[str, str] | None:
    name = current.get("role_token") if isinstance(current, dict) else None
    others = [role for role in roles(contract) if role != name]
    return {"role_token": others[0]} if others else None


def _edit_sites(contract: Any, select: Callable[[Path, Any], bool],
                edit: Callable[[Any, Path, Any], Any | None]) -> list[Any]:
    """Apply `edit` at the first MAX_SITES nodes where it changes the contract."""
    results = []
    for path, node in list(_contracts(contract)):
        if len(results) >= MAX_SITES:
            break
        if not select(path, node):
            continue
        copy = deepcopy(contract)
        edited = edit(copy, path, deepcopy(node))
        if edited is not None and edited != contract:
            results.append(edited)
    return results


def _is_pay(_: Path, node: Any) -> bool:
    return isinstance(node, dict) and "pay" in node


def _is_when(_: Path, node: Any) -> bool:
    return isinstance(node, dict) and "when" in node


def _is_if(_: Path, node: Any) -> bool:
    return isinstance(node, dict) and "if" in node


def _payee(root: Any, path: Path, node: Any) -> Any | None:
    target = node["to"].get("party")
    other = _other_role(root, target)
    if target is None or other is None:
        return None
    node["to"] = {"party": other}
    return _set(root, path, node)


def _scale(factor_num: int, factor_den: int) -> Callable[[Any, Path, Any], Any | None]:
    def edit(root: Any, path: Path, node: Any) -> Any | None:
        if type(node["pay"]) is not int:
            return None
        scaled = node["pay"] * factor_num // factor_den
        if scaled <= 0 or scaled == node["pay"]:
            return None
        node["pay"] = scaled
        return _set(root, path, node)
    return edit


def _deposit_sites(contract: Any) -> list[tuple[Path, Any]]:
    return [(path, node) for path, node in _nodes(contract)
            if isinstance(node, dict) and "deposits" in node][:MAX_SITES]


def _depositor(contract: Any) -> list[Any]:
    results = []
    for path, action in _deposit_sites(contract):
        other = _other_role(contract, action["party"])
        if other is None:
            continue
        copy = deepcopy(contract)
        _get(copy, path)["party"] = other
        results.append(copy)
    return results


def _shift(delta: int) -> Callable[[Any, Path, Any], Any | None]:
    def edit(root: Any, path: Path, node: Any) -> Any | None:
        if type(node["timeout"]) is not int:
            return None
        node["timeout"] = node["timeout"] + delta
        return _set(root, path, node)
    return edit


def _swap_if(root: Any, path: Path, node: Any) -> Any | None:
    node["then"], node["else"] = node["else"], node["then"]
    return _set(root, path, node)


def _swap_timeout(root: Any, path: Path, node: Any) -> Any | None:
    if not node["when"]:
        return None
    first = node["when"][0]
    first["then"], node["timeout_continuation"] = node["timeout_continuation"], first["then"]
    return _set(root, path, node)


def _drop_pay(root: Any, path: Path, node: Any) -> Any | None:
    return _set(root, path, node["then"])


def _thresholds(contract: Any) -> list[Any]:
    results = []
    for path, node in _nodes(contract):
        if len(results) >= MAX_SITES:
            break
        if not isinstance(node, dict):
            continue
        for key in COMPARISONS:
            if key in node and type(node[key]) is int:
                copy = deepcopy(contract)
                value = node[key]
                _get(copy, path)[key] = value + max(1, abs(value) // 5)
                results.append(copy)
                break
    return results


def _ada_named(contract: Any) -> list[Any]:
    copy = deepcopy(contract)
    changed = False
    for path, node in list(_nodes(copy)):
        if node == ADA and path:
            _set(copy, path, {"currency_symbol": "", "token_name": "ADA"})
            changed = True
    return [copy] if changed else []


def _narrow_bounds(contract: Any) -> list[Any]:
    results = []
    for path, node in _nodes(contract):
        if len(results) >= MAX_SITES:
            break
        if isinstance(node, dict) and "choose_between" in node and node["choose_between"]:
            bound = node["choose_between"][0]
            low, high = bound.get("from"), bound.get("to")
            if type(low) is int and type(high) is int and high > low:
                copy = deepcopy(contract)
                _get(copy, path)["choose_between"][0] = {"from": low, "to": (low + high) // 2}
                results.append(copy)
    return results


def _reverse_cases(root: Any, path: Path, node: Any) -> Any | None:
    if len(node["when"]) < 2:
        return None
    node["when"] = list(reversed(node["when"]))
    return _set(root, path, node)


def _split_pay(root: Any, path: Path, node: Any) -> Any | None:
    if type(node["pay"]) is not int or node["pay"] < 2:
        return None
    first = node["pay"] // 2
    second = {**node, "pay": node["pay"] - first}
    return _set(root, path, {**node, "pay": first, "then": second})


def _wrap_if_true(contract: Any) -> list[Any]:
    return [{"if": True, "then": deepcopy(contract), "else": "close"}]


def _shift_all(delta: int) -> Callable[[Any], list[Any]]:
    def edit(contract: Any) -> list[Any]:
        copy = deepcopy(contract)
        changed = False
        for path, node in list(_contracts(copy)):
            if isinstance(node, dict) and "when" in node and type(node["timeout"]) is int:
                node["timeout"] += delta
                changed = True
        return [copy] if changed else []
    return edit


def _site_operator(select: Callable[[Path, Any], bool],
                   edit: Callable[[Any, Path, Any], Any | None]) -> Callable[[Any], list[Any]]:
    return lambda contract: _edit_sites(contract, select, edit)


OPERATORS: tuple[tuple[str, str, Callable[[Any], list[Any]]], ...] = (
    ("payee", "wrong", _site_operator(_is_pay, _payee)),
    ("pay_half", "wrong", _site_operator(_is_pay, _scale(1, 2))),
    ("pay_double", "wrong", _site_operator(_is_pay, _scale(2, 1))),
    ("pay_unit_error", "wrong", _site_operator(_is_pay, _scale(1_000_000, 1))),
    ("depositor", "wrong", _depositor),
    ("deadline_earlier", "wrong", _site_operator(_is_when, _shift(-3 * DAY_MS))),
    ("deadline_later", "wrong", _site_operator(_is_when, _shift(3 * DAY_MS))),
    ("swap_if", "wrong", _site_operator(_is_if, _swap_if)),
    ("swap_timeout", "wrong", _site_operator(_is_when, _swap_timeout)),
    ("drop_pay", "wrong", _site_operator(_is_pay, _drop_pay)),
    ("threshold", "wrong", _thresholds),
    ("ada_token_name", "wrong", _ada_named),
    ("narrow_bounds", "wrong", _narrow_bounds),
    ("reverse_cases", "equivalent", _site_operator(_is_when, _reverse_cases)),
    ("split_pay", "equivalent", _site_operator(_is_pay, _split_pay)),
    ("if_true", "equivalent", _wrap_if_true),
    ("hours_later", "equivalent", _shift_all(3 * HOUR_MS)),
)


def variants(reference: Any) -> list[Variant]:
    """The reference itself, then every operator output that differs from it, deduplicated."""
    found = [Variant("reference", 0, "equivalent", deepcopy(reference))]
    seen = [reference]
    for name, intent, operator in OPERATORS:
        for site, contract in enumerate(operator(reference), start=1):
            if contract in seen:
                continue
            seen.append(contract)
            found.append(Variant(name, site, intent, contract))
    return found
