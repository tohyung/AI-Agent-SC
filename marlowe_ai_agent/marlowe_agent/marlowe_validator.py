from __future__ import annotations

from typing import Any

from .marlowe_ast import is_close


class MarloweValidationError(ValueError):
    """A Marlowe JSON contract does not match the supported Core V1 grammar."""


PARTY_SHAPES = ({"role_token"}, {"address"})
PAYEE_SHAPES = ({"party"}, {"account"})
TOKEN_FIELDS = {"currency_symbol", "token_name"}
CHOICE_ID_FIELDS = {"choice_name", "choice_owner"}
BOUND_FIELDS = {"from", "to"}
CASE_FIELDS = {"case", "then"}
VALUE_LITERALS = ("time_interval_start", "time_interval_end")
OBSERVATION_LITERALS = (True, False)
VALUE_SHAPES = (
    {"in_account", "amount_of_token"}, {"negate"}, {"add", "and"},
    {"value", "minus"}, {"multiply", "times"}, {"divide", "by"},
    {"value_of_choice"}, {"use_value"}, {"if", "then", "else"},
)
OBSERVATION_SHAPES = (
    {"both", "and"}, {"either", "or"}, {"not"}, {"chose_something_for"},
    {"value", "ge_than"}, {"value", "gt"}, {"value", "lt"},
    {"value", "le_than"}, {"value", "equal_to"},
)
ACTION_SHAPES = (
    {"party", "deposits", "of_token", "into_account"},
    {"for_choice", "choose_between"}, {"notify_if"},
)
CONTRACT_SHAPES = (
    {"pay", "from_account", "to", "token", "then"},
    {"if", "then", "else"}, {"when", "timeout", "timeout_continuation"},
    {"let", "be", "then"}, {"assert", "then"},
)


def describe_marlowe_grammar() -> str:
    def shapes(items: tuple[set[str], ...]) -> str:
        return " | ".join("{" + ", ".join(sorted(item)) + "}" for item in items)

    return "\n".join((
        'Marlowe Core V1 JSON; Close = "close".',
        "Contract: " + shapes(CONTRACT_SHAPES),
        "Action: " + shapes(ACTION_SHAPES),
        "Value: integer | " + " | ".join(VALUE_LITERALS) + " | " + shapes(VALUE_SHAPES),
        "Observation: " + " | ".join(str(value).lower() for value in OBSERVATION_LITERALS)
        + " | " + shapes(OBSERVATION_SHAPES),
        "Party: " + shapes(PARTY_SHAPES),
        "Payee: " + shapes(PAYEE_SHAPES),
        "Token: {" + ", ".join(sorted(TOKEN_FIELDS)) + "}",
        "ChoiceId: {" + ", ".join(sorted(CHOICE_ID_FIELDS)) + "}",
        "Bound: {" + ", ".join(sorted(BOUND_FIELDS)) + "}",
        "Case: {" + ", ".join(sorted(CASE_FIELDS)) + "}",
        "Every object must have exactly one listed field set; no extra fields. "
        "When timeout is a positive POSIX millisecond timestamp; choose_between is a nonempty Bound list. "
        "ADA amounts are integer lovelace (1 ADA = 1000000 lovelace).",
    ))


def _integer(value: Any) -> bool:
    return type(value) is int


def _shape(value: Any, required: set[str], path: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{path}: phải là object.")
        return False
    missing = required - value.keys()
    extra = value.keys() - required
    for key in sorted(missing):
        errors.append(f"{path}: thiếu field '{key}'.")
    for key in sorted(extra):
        errors.append(f"{path}: field không được hỗ trợ '{key}'.")
    return not missing and not extra


def _one_shape(value: Any, shapes: tuple[set[str], ...], path: str, errors: list[str]) -> set[str] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: phải là object.")
        return None
    for shape in shapes:
        if set(value) == shape:
            return shape
    errors.append(f"{path}: tổ hợp field không hợp lệ: {sorted(value)}.")
    return None


def _text(value: Any, path: str, errors: list[str], allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value):
        errors.append(f"{path}: phải là chuỗi{' (có thể rỗng)' if allow_empty else ' không rỗng'}.")


def validate_party(party: Any, path: str, errors: list[str]) -> None:
    shape = _one_shape(party, PARTY_SHAPES, path, errors)
    if shape:
        key = next(iter(shape))
        _text(party[key], f"{path}.{key}", errors)


def validate_token(token: Any, path: str, errors: list[str]) -> None:
    if _shape(token, TOKEN_FIELDS, path, errors):
        _text(token["currency_symbol"], f"{path}.currency_symbol", errors, True)
        _text(token["token_name"], f"{path}.token_name", errors, True)


def validate_choice_id(choice: Any, path: str, errors: list[str]) -> None:
    if _shape(choice, CHOICE_ID_FIELDS, path, errors):
        _text(choice["choice_name"], f"{path}.choice_name", errors)
        validate_party(choice["choice_owner"], f"{path}.choice_owner", errors)


def validate_value(value: Any, path: str, errors: list[str]) -> None:
    if _integer(value) or value in VALUE_LITERALS:
        return
    if isinstance(value, bool) or not isinstance(value, dict):
        errors.append(f"{path}: Value phải là số nguyên, thời gian hoặc object hợp lệ.")
        return
    shape = _one_shape(value, VALUE_SHAPES, path, errors)
    if shape is None:
        return
    if "in_account" in shape:
        validate_party(value["in_account"], f"{path}.in_account", errors)
        validate_token(value["amount_of_token"], f"{path}.amount_of_token", errors)
    elif "negate" in shape:
        validate_value(value["negate"], f"{path}.negate", errors)
    elif "value_of_choice" in shape:
        validate_choice_id(value["value_of_choice"], f"{path}.value_of_choice", errors)
    elif "use_value" in shape:
        _text(value["use_value"], f"{path}.use_value", errors)
    elif "if" in shape:
        validate_observation(value["if"], f"{path}.if", errors)
        validate_value(value["then"], f"{path}.then", errors)
        validate_value(value["else"], f"{path}.else", errors)
    else:
        for key in sorted(shape):
            validate_value(value[key], f"{path}.{key}", errors)


def validate_observation(observation: Any, path: str, errors: list[str]) -> None:
    if type(observation) is bool and observation in OBSERVATION_LITERALS:
        return
    shape = _one_shape(observation, OBSERVATION_SHAPES, path, errors)
    if shape is None:
        return
    if "chose_something_for" in shape:
        validate_choice_id(observation["chose_something_for"], f"{path}.chose_something_for", errors)
    elif "not" in shape:
        validate_observation(observation["not"], f"{path}.not", errors)
    elif "both" in shape or "either" in shape:
        for key in sorted(shape):
            validate_observation(observation[key], f"{path}.{key}", errors)
    else:
        for key in sorted(shape):
            validate_value(observation[key], f"{path}.{key}", errors)


def validate_action(action: Any, path: str, errors: list[str]) -> None:
    shape = _one_shape(action, ACTION_SHAPES, path, errors)
    if shape is None:
        return
    if "deposits" in shape:
        validate_party(action["party"], f"{path}.party", errors)
        validate_party(action["into_account"], f"{path}.into_account", errors)
        validate_token(action["of_token"], f"{path}.of_token", errors)
        validate_value(action["deposits"], f"{path}.deposits", errors)
    elif "for_choice" in shape:
        validate_choice_id(action["for_choice"], f"{path}.for_choice", errors)
        bounds = action["choose_between"]
        if not isinstance(bounds, list) or not bounds:
            errors.append(f"{path}.choose_between: phải là danh sách Bound không rỗng.")
        else:
            for index, bound in enumerate(bounds):
                bound_path = f"{path}.choose_between[{index}]"
                if _shape(bound, BOUND_FIELDS, bound_path, errors):
                    if not _integer(bound["from"]) or not _integer(bound["to"]):
                        errors.append(f"{bound_path}: from/to phải là số nguyên.")
                    elif bound["from"] > bound["to"]:
                        errors.append(f"{bound_path}: from phải <= to.")
    else:
        validate_observation(action["notify_if"], f"{path}.notify_if", errors)


def _validate_contract(contract: Any, path: str, errors: list[str]) -> None:
    if is_close(contract):
        return
    shape = _one_shape(contract, CONTRACT_SHAPES, path, errors)
    if shape is None:
        return
    if "pay" in shape:
        validate_value(contract["pay"], f"{path}.pay", errors)
        validate_party(contract["from_account"], f"{path}.from_account", errors)
        payee = contract["to"]
        payee_shape = _one_shape(payee, PAYEE_SHAPES, f"{path}.to", errors)
        if payee_shape:
            key = next(iter(payee_shape))
            validate_party(payee[key], f"{path}.to.{key}", errors)
        validate_token(contract["token"], f"{path}.token", errors)
        _validate_contract(contract["then"], f"{path}.then", errors)
    elif "when" in shape:
        cases = contract["when"]
        if not isinstance(cases, list):
            errors.append(f"{path}.when: phải là danh sách Case.")
        else:
            for index, item in enumerate(cases):
                case_path = f"{path}.when[{index}]"
                if _shape(item, CASE_FIELDS, case_path, errors):
                    validate_action(item["case"], f"{case_path}.case", errors)
                    _validate_contract(item["then"], f"{case_path}.then", errors)
        timeout = contract["timeout"]
        if not _integer(timeout) or timeout <= 0:
            errors.append(f"{path}.timeout: phải là số nguyên POSIX ms > 0.")
        elif timeout < 10**11:
            errors.append(f"{path}.timeout: có vẻ đang dùng giây; Marlowe dùng POSIX ms.")
        _validate_contract(contract["timeout_continuation"], f"{path}.timeout_continuation", errors)
    elif "if" in shape:
        validate_observation(contract["if"], f"{path}.if", errors)
        _validate_contract(contract["then"], f"{path}.then", errors)
        _validate_contract(contract["else"], f"{path}.else", errors)
    elif "let" in shape:
        _text(contract["let"], f"{path}.let", errors)
        validate_value(contract["be"], f"{path}.be", errors)
        _validate_contract(contract["then"], f"{path}.then", errors)
    else:
        validate_observation(contract["assert"], f"{path}.assert", errors)
        _validate_contract(contract["then"], f"{path}.then", errors)


def validate_contract(contract: Any) -> list[str]:
    errors: list[str] = []
    _validate_contract(contract, "root", errors)
    return errors


def assert_valid(contract: Any) -> None:
    errors = validate_contract(contract)
    if errors:
        raise MarloweValidationError("\n".join(errors))
