from research.experiments.e7_score import (
    bind_step,
    deadline_problems,
    machine_verdict,
    received_by_party,
    run_scenario,
)

ADA = {"currency_symbol": "", "token_name": ""}
CONTRACT = {"timeout": 1_000_000, "timeout_continuation": "close", "when": [
    {"case": {"party": {"role_token": "Công ty"}, "deposits": 5, "of_token": ADA,
              "into_account": {"role_token": "Công ty"}}, "then": {
        "timeout": 2_000_000, "timeout_continuation": "close", "when": [
            {"case": {"notify_if": True}, "then": "close"},
            {"case": {"for_choice": {"choice_name": "ok", "choice_owner": {"role_token": "Vy"}},
                      "choose_between": [{"from": 0, "to": 1}]}, "then": "close"}]}}]}


def test_a_deposit_binds_to_the_enabled_case_with_a_folded_party_name():
    bound = bind_step({"kind": "deposit", "party": "CongTy", "amount": 5, "token": ""}, CONTRACT)
    assert bound == {"type": "Deposit", "party": {"role_token": "Công ty"},
                     "account": {"role_token": "Công ty"}, "token": ADA, "amount": 5}
    assert bind_step({"kind": "deposit", "party": "CongTy", "amount": 6, "token": ""}, CONTRACT) is None


def test_choice_binds_by_owner_and_value_with_any_choice_name():
    inner = CONTRACT["when"][0]["then"]
    bound = bind_step({"kind": "choice", "party": "vy", "name": "dong_y", "value": 1}, inner)
    assert bound["choice_id"]["choice_name"] == "ok" and bound["chosen"] == 1
    assert bind_step({"kind": "choice", "party": "vy", "name": "x", "value": 2}, inner) is None
    assert bind_step({"kind": "notify"}, inner) == {"type": "Notify"}
    assert bind_step({"kind": "advance"}, inner) == {}


def test_received_counts_party_payments_only_by_folded_name():
    payments = [{"payee": {"party": {"role_token": "Hà"}}, "token": ADA, "amount": 3},
                {"payee": {"party": {"role_token": "ha"}}, "token": ADA, "amount": 2},
                {"payee": {"account": {"role_token": "Vy"}}, "token": ADA, "amount": 9}]
    assert received_by_party(payments) == {"ha": {"": 5}}


class FakeReference:
    def __init__(self, results):
        self.results = list(results)

    def execute(self, request):
        return self.results.pop(0)


def test_a_scenario_passes_when_steps_run_and_receipts_match():
    scenario = {"name": "s", "steps": [{"kind": "deposit", "party": "CongTy", "amount": 5,
                                        "token": "", "time": 10}],
                "received": {"Cong Ty": {"": 5}}, "closed": True}
    paid = {"status": "Success", "final_contract": "close", "steps": [
        {"status": "Success", "payments": [
            {"payee": {"party": {"role_token": "Công ty"}}, "token": ADA, "amount": 5}]}]}
    assert run_scenario(CONTRACT, scenario, FakeReference([paid])) == []
    unpaid = {**paid, "steps": [{"status": "Success", "payments": []}]}
    assert run_scenario(CONTRACT, scenario, FakeReference([unpaid]))


def test_deadlines_must_match_the_spec_within_a_minute():
    contract = {"timeout": 1_801_486_800_000 + 30_000, "when": [], "timeout_continuation": "close"}
    assert deadline_problems(contract, {"by": "2027-02-01T20:00+07:00"}) == []
    late = {**contract, "timeout": 1_801_486_800_000 + 3_600_000}
    assert len(deadline_problems(late, {"by": "2027-02-01T20:00+07:00"})) == 2


def test_no_contract_is_none():
    assert machine_verdict(None, {"checks": {"scenarios": []}}, None)["verdict"] == "NONE"
