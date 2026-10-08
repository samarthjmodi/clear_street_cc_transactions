"""Q1 worth-having table and plots from v2 customer_metrics.

Run from repo root after build_q1_v2_customer_metrics.py:
  .venv/bin/python src/q1_v2_worth_having.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
V2 = REPO / "active_ds_takehome_handout" / "analysis" / "q1_scratch" / "v2"
PLOTS = REPO / "plots"

ORDER = ["Credit-primary", "Mixed", "Debit/prepaid only", "Dormant"]
COLORS = ["#1f4e79", "#5b8fad", "#9fbfd6", "#c9ccd1"]
VERDICT = {
    "Credit-primary": "Worth having. Prioritize in acquisition and retention.",
    "Mixed": "Worth having. Second priority; move more of their spend onto credit.",
    "Debit/prepaid only": "Keep, but cap what we pay to acquire them.",
    "Dormant": "Not a growth segment. Reactivation question for Q2.",
}


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    m = pd.read_csv(V2 / "customer_metrics.csv")
    total = m.estimated_revenue.sum()

    t = (
        m.groupby("product_role")
        .agg(
            customers=("client_id", "size"),
            mean_revenue=("estimated_revenue", "mean"),
            median_revenue=("estimated_revenue", "median"),
            total_revenue=("estimated_revenue", "sum"),
            mean_purchase_volume=("purchase_volume", "mean"),
            purchase_volume=("purchase_volume", "sum"),
        )
        .reindex(ORDER)
    )
    t["pct_customers"] = t.customers / len(m)
    t["pct_revenue"] = t.total_revenue / total
    t["revenue_per_100_purchase"] = np.where(
        t.purchase_volume > 0, t.total_revenue / t.purchase_volume * 100, np.nan
    )
    t["verdict"] = t.index.map(VERDICT)
    t.drop(columns="purchase_volume").to_csv(V2 / "worth_having.csv")

    unused_credit = m[m.product_role.eq("Debit/prepaid only") & m.owned_credit_pre_window]
    notes = {
        "unused_credit_card_holders": int(len(unused_credit)),
        "unused_credit_holders_mean_revenue": float(unused_credit.estimated_revenue.mean()),
        "credit_primary_vs_debit_only_mean_revenue_ratio": float(
            t.loc["Credit-primary", "mean_revenue"] / t.loc["Debit/prepaid only", "mean_revenue"]
        ),
    }
    (V2 / "worth_having_notes.json").write_text(json.dumps(notes, indent=2))

    plt.style.use("seaborn-v0_8-whitegrid")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(t))
    ax.bar(x, t.mean_revenue, color=COLORS)
    for i, (v, n) in enumerate(zip(t.mean_revenue, t.customers)):
        ax.text(i, v + 12, f"${v:,.0f}\nn={n}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(ORDER)
    ax.set_ylabel("Mean estimated revenue per customer ($)")
    ax.set_ylim(0, t.mean_revenue.max() * 1.25)
    ax.set_title("Mean customer value by product role, Nov 2018 to Oct 2019")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_mean_revenue_by_role.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.6))
    left = 0.0
    for role, color in zip(ORDER, COLORS):
        share = t.loc[role, "pct_revenue"] * 100
        ax.barh(["Revenue"], [share], left=left, color=color, label=role)
        left += share
    left = 0.0
    for role, color in zip(ORDER, COLORS):
        share = t.loc[role, "pct_customers"] * 100
        ax.barh(["Customers"], [share], left=left, color=color)
        if share > 6:
            ax.text(left + share / 2, 1, f"{share:.0f}%", ha="center", va="center", color="white", fontsize=9)
        left += share
    left = 0.0
    for role in ORDER:
        share = t.loc[role, "pct_revenue"] * 100
        if share > 6:
            ax.text(left + share / 2, 0, f"{share:.0f}%", ha="center", va="center", color="white", fontsize=9)
        left += share
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of eligible customers / estimated revenue (%)")
    ax.set_title("Credit-primary customers are a third of the base and two-thirds of revenue")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.3), frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_customer_vs_revenue_share.png", dpi=150)
    plt.close(fig)

    own = m.groupby("owned_credit_pre_window").agg(
        customers=("client_id", "size"),
        pct_credit_primary=("product_role", lambda s: s.eq("Credit-primary").mean()),
        pct_mixed=("product_role", lambda s: s.eq("Mixed").mean()),
        pct_debit_only=("product_role", lambda s: s.eq("Debit/prepaid only").mean()),
        pct_dormant=("product_role", lambda s: s.eq("Dormant").mean()),
    )
    own.index = ["No credit card before window", "Owned credit card before window"]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    left = np.zeros(len(own))
    for col, role, color in zip(
        ["pct_credit_primary", "pct_mixed", "pct_debit_only", "pct_dormant"], ORDER, COLORS
    ):
        vals = own[col].values * 100
        ax.barh(own.index, vals, left=left, color=color, label=role)
        for j, v in enumerate(vals):
            if v > 6:
                ax.text(left[j] + v / 2, j, f"{v:.0f}%", ha="center", va="center", color="white", fontsize=9)
        left += vals
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of customers (%)")
    ax.set_title("Owning a credit card before the window predicts the product role")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.3), frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_role_by_pre_window_credit.png", dpi=150)
    plt.close(fig)

    print(t.to_string())
    print(json.dumps(notes, indent=2))


if __name__ == "__main__":
    main()
