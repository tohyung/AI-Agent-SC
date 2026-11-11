"""Write one E6 expectation scenario from a compact description the simulated user writes.

  python tools/e6/expect.py OUT.json '<compact JSON>'

Compact form:
  {"tx": [["2027-03-20T23:59+07:00", [["deposit", "Minh", "Minh", 45]],
                                      ["choice", "Minh", 1], ["notify"]]], ...],
   "pay": [["Minh", "Thảo", 45]],          # from account, to party, ADA (or [.., amount, token])
   "end": "close"}                          # optional, default close
Amounts are ADA unless a token is given as [currency_symbol, token_name, units].
Each transaction is placed 1 ms before the given instant, so a deadline instant means "just in time".
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

ADA = {"currency_symbol": "", "token_name": ""}


def _ms(text: str) -> int:
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def _amount(value: object, token: list | None) -> tuple[dict, int]:
    if token:
        return {"currency_symbol": token[0], "token_name": token[1]}, int(token[2])
    return ADA, round(float(value) * 1_000_000)


def build(compact: dict) -> dict:
    transactions = []
    for instant, inputs in compact["tx"]:
        moment = _ms(instant) - 1
        items = []
        for item in inputs:
            if item[0] == "deposit":
                token, amount = _amount(item[3], item[4] if len(item) > 4 else None)
                items.append({"type": "Deposit", "party": {"role_token": item[1]},
                              "account": {"role_token": item[2]}, "token": token, "amount": amount})
            elif item[0] == "choice":
                items.append({"type": "Choice", "choice_owner": {"role_token": item[1]},
                              "chosen": int(item[2])})
            elif item[0] == "notify":
                items.append({"type": "Notify"})
            else:
                raise ValueError(f"unknown input {item[0]}")
        transactions.append({"interval": {"from": moment, "to": moment}, "inputs": items})
    payments = []
    for row in compact.get("pay", []):
        token, amount = _amount(row[2], row[3] if len(row) > 3 else None)
        payments.append({"source_account": {"role_token": row[0]},
                         "payee": {"party": {"role_token": row[1]}}, "token": token, "amount": amount})
    return {"request": {"state": {"accounts": [], "choices": [], "boundValues": [], "minTime": 0},
                        "transactions": transactions},
            "expected_status": "Success", "expected_final_contract": compact.get("end", "close"),
            "expected_warnings": [], "expected_payments": payments}


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(json.loads(sys.argv[2])), ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
