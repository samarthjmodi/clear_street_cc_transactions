"""Slim customer rollup for Q1 from the v2 grains.

Run from repo root after build_q1_v2_tables.py:
  .venv/bin/python src/build_q1_v2_customer_metrics.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
V2 = ROOT / "analysis" / "q1_scratch" / "v2"
START = pd.Timestamp("2018-11-01")
END = pd.Timestamp("2019-11-01")
WINDOW_MONTHS = 12

SETTLED = "(errors IS NULL OR errors = '')"


def role(credit_share: float, has_purchase: bool) -> str:
    if not has_purchase:
        return "Dormant"
    if credit_share >= 0.5:
        return "Credit-primary"
    if credit_share > 0:
        return "Mixed"
    return "Debit/prepaid only"


def main() -> None:
    rates = (
        pd.read_csv(ROOT / "revenue_assumptions.csv")
        .set_index("assumption_key")
        .assumption_value
    )
    credit_rate = rates["interchange_credit_bps"] / 10_000
    debit_rate = rates["interchange_debit_bps"] / 10_000
    debit_fixed = rates["interchange_debit_fixed_cents"] / 100
    amex_fee = rates["annual_fee_amex_usd"]

    con = sqlite3.connect(V2 / "q1_v2.sqlite")
    customers = pd.read_csv(V2 / "dim_customers.csv")
    cards = pd.read_csv(V2 / "dim_cards.csv", parse_dates=["opened"])

    activity = pd.read_sql_query(
        f"""
        SELECT client_id,
               SUM(CASE WHEN amount_usd > 0 THEN 1 ELSE 0 END) AS purchase_count,
               SUM(CASE WHEN amount_usd > 0 THEN amount_usd ELSE 0 END) AS purchase_volume,
               SUM(CASE WHEN amount_usd < 0 THEN -amount_usd ELSE 0 END) AS refund_volume,
               SUM(CASE WHEN amount_usd > 0 AND card_type = 'Credit' THEN amount_usd ELSE 0 END) AS credit_purchase_volume,
               SUM(CASE WHEN amount_usd < 0 AND card_type = 'Credit' THEN -amount_usd ELSE 0 END) AS credit_refund_volume,
               SUM(CASE WHEN amount_usd > 0 AND card_type = 'Debit' THEN amount_usd ELSE 0 END) AS debit_purchase_volume,
               SUM(CASE WHEN amount_usd < 0 AND card_type = 'Debit' THEN -amount_usd ELSE 0 END) AS debit_refund_volume,
               SUM(CASE WHEN amount_usd > 0 AND card_type = 'Debit' THEN 1 ELSE 0 END) AS debit_purchase_count,
               SUM(CASE WHEN amount_usd > 0 AND card_type = 'Debit (Prepaid)' THEN amount_usd ELSE 0 END) AS prepaid_purchase_volume,
               COUNT(DISTINCT CASE WHEN amount_usd > 0 THEN substr(date, 1, 7) END) AS active_months
        FROM fact_transactions
        WHERE {SETTLED}
        GROUP BY client_id
        """,
        con,
    )
    con.close()

    pre = cards[cards.opened < START]
    ownership = pre.groupby("client_id").agg(
        n_cards_pre_window=("card_id", "size"),
        n_credit_pre_window=("card_type", lambda s: int(s.eq("Credit").sum())),
        n_debit_pre_window=("card_type", lambda s: int(s.eq("Debit").sum())),
        n_prepaid_pre_window=("card_type", lambda s: int(s.eq("Debit (Prepaid)").sum())),
    )

    amex = cards[
        cards.card_brand.eq("Amex") & cards.card_type.eq("Credit") & cards.opened.lt(END)
    ].copy()
    fee_start = amex.opened.clip(lower=START)
    months = (END.year - fee_start.dt.year) * 12 + (END.month - fee_start.dt.month)
    amex["amex_fee"] = amex_fee * months.clip(0, WINDOW_MONTHS) / WINDOW_MONTHS
    fees = amex.groupby("client_id").amex_fee.sum().rename("amex_fees")

    m = (
        customers[
            ["client_id", "current_age", "gender", "yearly_income", "total_debt", "credit_score"]
        ]
        .merge(ownership, on="client_id", how="left")
        .merge(activity, on="client_id", how="left")
        .merge(fees, on="client_id", how="left")
    )
    numeric = [c for c in activity.columns if c != "client_id"] + ["amex_fees"]
    m[numeric] = m[numeric].fillna(0)

    m["has_window_purchase"] = m.purchase_count.gt(0)
    m["credit_share"] = np.where(
        m.purchase_volume > 0, m.credit_purchase_volume / m.purchase_volume, np.nan
    )
    m["product_role"] = [
        role(cs, hp) for cs, hp in zip(m.credit_share.fillna(0), m.has_window_purchase)
    ]
    m["owned_credit_pre_window"] = m.n_credit_pre_window.gt(0)

    m["interchange"] = (
        (m.credit_purchase_volume - m.credit_refund_volume) * credit_rate
        + (m.debit_purchase_volume - m.debit_refund_volume) * debit_rate
        + m.debit_purchase_count * debit_fixed
    )
    m["estimated_revenue"] = m.interchange + m.amex_fees

    keep = [
        "client_id", "current_age", "gender", "yearly_income", "total_debt", "credit_score",
        "n_cards_pre_window", "n_credit_pre_window", "n_debit_pre_window", "n_prepaid_pre_window",
        "owned_credit_pre_window", "has_window_purchase", "active_months", "purchase_count",
        "purchase_volume", "refund_volume", "credit_purchase_volume", "debit_purchase_volume",
        "prepaid_purchase_volume", "credit_share", "product_role", "interchange", "amex_fees",
        "estimated_revenue",
    ]
    m = m[keep]
    assert m.client_id.is_unique and len(m) == 1603
    assert int(m.has_window_purchase.sum()) == 1206
    m.to_csv(V2 / "customer_metrics.csv", index=False)

    order = ["Credit-primary", "Mixed", "Debit/prepaid only", "Dormant"]
    total = m.estimated_revenue.sum()
    by_role = (
        m.groupby("product_role")
        .agg(
            customers=("client_id", "size"),
            mean_revenue=("estimated_revenue", "mean"),
            median_revenue=("estimated_revenue", "median"),
            total_revenue=("estimated_revenue", "sum"),
            mean_purchase_volume=("purchase_volume", "mean"),
            mean_credit_share=("credit_share", "mean"),
            pct_owned_credit_pre_window=("owned_credit_pre_window", "mean"),
            median_age=("current_age", "median"),
            median_income=("yearly_income", "median"),
            median_credit_score=("credit_score", "median"),
        )
        .reindex(order)
    )
    by_role["pct_customers"] = by_role.customers / len(m)
    by_role["pct_revenue"] = by_role.total_revenue / total
    by_role.to_csv(V2 / "product_role_summary.csv")

    by_ownership = (
        m.groupby("owned_credit_pre_window")
        .agg(
            customers=("client_id", "size"),
            pct_dormant=("has_window_purchase", lambda s: float((~s).mean())),
            pct_credit_primary=("product_role", lambda s: float(s.eq("Credit-primary").mean())),
            mean_revenue=("estimated_revenue", "mean"),
        )
    )
    by_ownership.to_csv(V2 / "pre_window_credit_ownership_summary.csv")

    audit = {
        "customers": int(len(m)),
        "transactors": int(m.has_window_purchase.sum()),
        "total_estimated_revenue": float(total),
        "total_interchange": float(m.interchange.sum()),
        "total_amex_fees": float(m.amex_fees.sum()),
        "role_counts": m.product_role.value_counts().to_dict(),
    }
    (V2 / "customer_metrics_audit.json").write_text(json.dumps(audit, indent=2))

    print(by_role.to_string())
    print()
    print(by_ownership.to_string())
    print()
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
