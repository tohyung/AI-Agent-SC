#!/usr/bin/env bash
# Loan scenarios: bash tools/e6/loan.sh N LENDER PRINCIPAL FUND_BY BORROWER REPAY REPAY_BY
# (ADA; funding is paid straight to the borrower; no repayment closes the contract).
N=$1; A=$2; P=$3; D1=$4; B=$5; R=$6; D2=$7
PYTHONIOENCODING=utf-8 python tools/e6/auto.py scen "$N" "{\"repaid\":{\"tx\":[[\"$D1\",[[\"deposit\",\"$A\",\"$A\",$P]]],[\"$D2\",[[\"deposit\",\"$B\",\"$B\",$R]]]],\"pay\":[[\"$A\",\"$B\",$P],[\"$B\",\"$A\",$R]]},\"default\":{\"tx\":[[\"$D1\",[[\"deposit\",\"$A\",\"$A\",$P]]],[\"$D2\",[]]],\"pay\":[[\"$A\",\"$B\",$P]]},\"no_deposit\":{\"tx\":[[\"$D1\",[]]],\"pay\":[]}}"
