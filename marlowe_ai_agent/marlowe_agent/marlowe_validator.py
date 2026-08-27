from __future__ import annotations

from typing import Any


CONTRACT_KEYS = {"close", "pay", "if", "when", "let", "assert"}


class MarloweValidationError(ValueError):
    pass


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _validate_contract(contract, "root", errors)
    return errors


def _validate_contract(contract: Any, path: str, errors: list[str]) -> None:
    if not isinstance(contract, dict):
        errors.append(f"{path}: contract phai la object.")
        return

    present = [key for key in CONTRACT_KEYS if key in contract]
    if len(present) != 1:
        errors.append(f"{path}: contract phai co dung 1 constructor trong {sorted(CONTRACT_KEYS)}.")
        return

    kind = present[0]
    if kind == "close":
        return

    if kind == "pay":
        _require(contract, ["pay", "from_account", "to", "token", "then"], path, errors)
        _validate_value(contract.get("pay"), f"{path}.pay", errors)
        _validate_contract(contract.get("then"), f"{path}.then", errors)
        return

    if kind == "if":
        _require(contract, ["if", "then", "else"], path, errors)
        _validate_observation(contract.get("if"), f"{path}.if", errors)
        _validate_contract(contract.get("then"), f"{path}.then", errors)
        _validate_contract(contract.get("else"), f"{path}.else", errors)
        return

    if kind == "when":
        _require(contract, ["when", "timeout", "timeout_continuation"], path, errors)
        cases = contract.get("when")
        if not isinstance(cases, list):
            errors.append(f"{path}.when: phai la list Case.")
        else:
            for index, case in enumerate(cases):
                _validate_case(case, f"{path}.when[{index}]", errors)
        if not isinstance(contract.get("timeout"), int):
            errors.append(f"{path}.timeout: phai la integer POSIX timeout.")
        _validate_contract(contract.get("timeout_continuation"), f"{path}.timeout_continuation", errors)
        return

    if kind == "let":
        _require(contract, ["let", "be", "then"], path, errors)
        _validate_value(contract.get("be"), f"{path}.be", errors)
        _validate_contract(contract.get("then"), f"{path}.then", errors)
        return

    if kind == "assert":
        _require(contract, ["assert", "then"], path, errors)
        _validate_observation(contract.get("assert"), f"{path}.assert", errors)
        _validate_contract(contract.get("then"), f"{path}.then", errors)


def _validate_case(case: Any, path: str, errors: list[str]) -> None:
    if not isinstance(case, dict):
        errors.append(f"{path}: Case phai la object.")
        return
    _require(case, ["case", "then"], path, errors)
    _validate_action(case.get("case"), f"{path}.case", errors)
    _validate_contract(case.get("then"), f"{path}.then", errors)


def _validate_action(action: Any, path: str, errors: list[str]) -> None:
    if not isinstance(action, dict):
        errors.append(f"{path}: action phai la object.")
        return
    if "deposits" in action:
        _require(action, ["deposits", "into_account", "of_token", "party"], path, errors)
        _validate_value(action.get("deposits"), f"{path}.deposits", errors)
        return
    if "choice" in action:
        _require(action, ["choice", "bounds"], path, errors)
        if not isinstance(action.get("bounds"), list) or not action["bounds"]:
            errors.append(f"{path}.bounds: choice can it nhat 1 bound.")
        return
    if "notify_if" in action:
        _validate_observation(action.get("notify_if"), f"{path}.notify_if", errors)
        return
    errors.append(f"{path}: action phai la Deposit, Choice hoac Notify.")


def _validate_value(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path}: value phai la object.")
        return
    if not value:
        errors.append(f"{path}: value rong.")


def _validate_observation(observation: Any, path: str, errors: list[str]) -> None:
    if not isinstance(observation, dict):
        errors.append(f"{path}: observation phai la object.")
        return
    if not observation:
        errors.append(f"{path}: observation rong.")


def _require(data: dict[str, Any], keys: list[str], path: str, errors: list[str]) -> None:
    for key in keys:
        if key not in data:
            errors.append(f"{path}: thieu field '{key}'.")
