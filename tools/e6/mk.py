"""Shortcut for the common one-deposit, one-choice shape; writes scenarios through `auto.py scen`.

  python tools/e6/mk.py N DEPOSITOR AMOUNT DEPOSIT_BY CHOOSER CHOICE_BY "1=Payee" "2=Payee" \
      [--timeout PAYEE] [--token CS NAME]

AMOUNT is ADA, or token units with --token. Instants are ISO 8601 with offset. Each "V=Payee"
gives a scenario where CHOOSER picks V and the whole deposit goes to Payee. --timeout adds the
scenario where nobody chooses (whole deposit to PAYEE). A no-deposit scenario is always added.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

parser = argparse.ArgumentParser()
parser.add_argument("case", type=int)
parser.add_argument("depositor")
parser.add_argument("amount")
parser.add_argument("deposit_by")
parser.add_argument("chooser")
parser.add_argument("choice_by")
parser.add_argument("choices", nargs="*")
parser.add_argument("--timeout")
parser.add_argument("--token", nargs=2)
args = parser.parse_args()
token = [args.token[0], args.token[1], int(args.amount)] if args.token else None


def money(source: str, payee: str) -> list:
    return [source, payee, 0, token] if token else [source, payee, float(args.amount)]


deposit = ["deposit", args.depositor, args.depositor, 0 if token else float(args.amount)]
if token:
    deposit.append(token)
scenarios = {}
for item in args.choices:
    value, payee = item.split("=", 1)
    scenarios[f"choose_{value}"] = {
        "tx": [[args.deposit_by, [deposit]], [args.choice_by, [["choice", args.chooser, int(value)]]]],
        "pay": [money(args.depositor, payee)]}
if args.timeout:
    scenarios["timeout"] = {"tx": [[args.deposit_by, [deposit]], [args.choice_by, []]],
                            "pay": [money(args.depositor, args.timeout)]}
scenarios["no_deposit"] = {"tx": [[args.deposit_by, []]], "pay": []}
sys.exit(subprocess.call([sys.executable, str(ROOT / "tools" / "e6" / "auto.py"), "scen",
                          str(args.case), json.dumps(scenarios, ensure_ascii=False)]))
