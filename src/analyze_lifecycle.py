"""Activation and quiet-loss definitions from existing Q1 customer metrics.

Run from repo root:
  .venv/bin/python src/analyze_lifecycle.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
OUT = ROOT / "analysis" / "lifecycle"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cm = pd.read_csv(
        ROOT / "analysis/q1/customer_metrics.csv",
        parse_dates=["last_purchase", "first_observed_purchase"],
    )
    cards = pd.read_csv(ROOT / "cards_data.csv")
    cards["opened"] = pd.to_datetime(cards.acct_open_date, format="%m/%Y")
    first_card = cards.groupby("client_id").opened.min().rename("first_card_open")
    life = cm.merge(first_card, left_on="client_id", right_index=True, how="left")
    life["eligible_before_window"] = life.first_card_open.lt("2018-11-01")
    life["opened_in_2020"] = life.first_card_open.ge("2020-01-01")
    life["transactor"] = life.purchase_count.gt(0)
    life["lifecycle_status"] = np.select(
        [
            life.opened_in_2020,
            ~life.transactor & life.eligible_before_window,
            ~life.transactor,
            life.active_months.ge(9) & life.credit_share.ge(0.5),
            life.active_months.ge(9),
            life.transactor,
        ],
        [
            "Too-new / post-window open (no txn history in data)",
            "Dormant eligible (quiet loss candidate)",
            "No window purchases (opened near/during window)",
            "Established credit-led",
            "Established debit/prepaid-led",
            "Active but not established",
        ],
        default="Unknown",
    )
    summary = life.groupby("lifecycle_status").agg(
        customers=("client_id", "size"),
        median_age=("current_age", "median"),
        median_income=("yearly_income", "median"),
        median_credit_score=("credit_score", "median"),
        total_interchange=("interchange", "sum"),
        mean_interchange=("interchange", "mean"),
        median_active_months=("active_months", "median"),
    )
    summary.to_csv(OUT / "lifecycle_summary.csv")
    life[
        [
            "client_id",
            "segment",
            "lifecycle_status",
            "first_card_open",
            "first_observed_purchase",
            "last_purchase",
            "active_months",
            "purchase_count",
            "interchange",
            "credit_share",
            "days_since_purchase",
            "eligible_before_window",
        ]
    ].to_csv(OUT / "customer_lifecycle.csv", index=False)

    cmm = pd.read_csv(ROOT / "analysis/q1/card_month_metrics.csv")
    cust_month = (
        cmm[cmm.purchase_count > 0]
        .groupby(["client_id", "month"])
        .purchase_count.sum()
        .reset_index()
    )
    months = sorted(cust_month.month.unique())
    rows = []
    for a, b in zip(months[:-1], months[1:]):
        A = set(cust_month.loc[cust_month.month.eq(a), "client_id"])
        B = set(cust_month.loc[cust_month.month.eq(b), "client_id"])
        rows.append(
            {
                "from_month": a,
                "to_month": b,
                "active": len(A),
                "retained": len(A & B),
                "retention_rate": len(A & B) / len(A) if A else np.nan,
            }
        )
    ret = pd.DataFrame(rows)
    ret.to_csv(OUT / "month_to_month_retention.csv", index=False)
    audit = {
        "transactors": int(life.transactor.sum()),
        "dormant_eligible": int((~life.transactor & life.eligible_before_window).sum()),
        "opened_2020": int(life.opened_in_2020.sum()),
        "median_m2m_retention": float(ret.retention_rate.median()),
        "min_m2m_retention": float(ret.retention_rate.min()),
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2))
    print(summary[["customers", "mean_interchange"]].to_string())
    print("AUDIT", audit)


if __name__ == "__main__":
    main()
