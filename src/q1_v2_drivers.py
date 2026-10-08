"""Q1 stress test: which pre-window attributes relate to customer value?

Run from repo root:
  .venv/bin/python src/q1_v2_drivers.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V2 = HANDOUT / "analysis" / "q1_scratch" / "v2"
START = pd.Timestamp("2018-11-01")


def money(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")


def rank_corr(a: pd.Series, b: pd.Series) -> float:
    ok = a.notna() & b.notna()
    return round(a[ok].rank().corr(b[ok].rank()), 3)


def card_features(cards: pd.DataFrame) -> pd.DataFrame:
    c = cards.copy()
    c["opened"] = pd.to_datetime(c["opened"])
    c["credit_limit"] = money(c["credit_limit"])
    c = c[c.opened < START]
    credit = c[c.card_type.eq("Credit")]
    g = c.groupby("client_id")
    out = pd.DataFrame(
        {
            "total_limit_all_cards": g.credit_limit.sum(),
            "oldest_card_years": g.opened.min().map(lambda d: (START - d).days / 365.25),
            "any_dark_web": g.card_on_dark_web.apply(lambda s: s.eq("Yes").any()),
        }
    )
    cg = credit.groupby("client_id")
    out["credit_limit_total"] = cg.credit_limit.sum()
    out["credit_limit_max"] = cg.credit_limit.max()
    out["owns_amex_credit"] = cg.card_brand.apply(lambda s: s.eq("Amex").any())
    out[["credit_limit_total", "credit_limit_max"]] = out[["credit_limit_total", "credit_limit_max"]].fillna(0)
    out["owns_amex_credit"] = out["owns_amex_credit"].fillna(False).astype(bool)
    return out


def fraud_by_customer() -> pd.DataFrame:
    labels = json.loads((HANDOUT / "train_fraud_labels.json").read_text())["target"]
    fraud_ids = {int(k) for k, v in labels.items() if v == "Yes"}
    labelled_ids = {int(k) for k in labels}
    con = sqlite3.connect(V2 / "q1_v2.sqlite")
    f = pd.read_sql(
        "SELECT id, client_id, amount_usd FROM fact_transactions "
        "WHERE amount_usd > 0 AND (errors IS NULL OR errors = '')",
        con,
    )
    f["labelled"] = f.id.isin(labelled_ids)
    f["fraud"] = f.id.isin(fraud_ids)
    g = f.groupby("client_id")
    return pd.DataFrame(
        {
            "labelled_share": g.labelled.mean(),
            "fraud_txns": g.fraud.sum(),
            "fraud_dollars": f[f.fraud].groupby("client_id").amount_usd.sum(),
        }
    ).fillna({"fraud_dollars": 0})


def main() -> None:
    m = pd.read_csv(V2 / "customer_metrics.csv")
    users = pd.read_csv(V2 / "dim_customers.csv")[["client_id", "num_credit_cards", "per_capita_income"]]
    users["per_capita_income"] = money(users["per_capita_income"])
    cards = pd.read_csv(V2 / "dim_cards.csv")
    df = (
        m.merge(users, on="client_id", how="left")
        .merge(card_features(cards), left_on="client_id", right_index=True, how="left")
        .merge(fraud_by_customer(), left_on="client_id", right_index=True, how="left")
    )
    for col in ["yearly_income", "total_debt"]:
        df[col] = money(df[col])
    df["debt_to_income"] = df.total_debt / df.yearly_income
    df["credit_utilisation"] = np.where(
        df.credit_limit_total > 0, df.credit_purchase_volume / 12 / df.credit_limit_total, np.nan
    )

    pre = [
        "credit_limit_total", "credit_limit_max", "total_limit_all_cards", "n_cards_pre_window",
        "n_credit_pre_window", "num_credit_cards", "yearly_income", "per_capita_income",
        "total_debt", "debt_to_income", "credit_score", "current_age", "oldest_card_years",
    ]
    out: dict = {}

    def spearman(frame: pd.DataFrame, target: str) -> dict:
        return {c: rank_corr(frame[c], frame[target]) for c in pre}

    owners = df[df.owned_credit_pre_window]
    active_owners = owners[owners.has_window_purchase]
    out["spearman_revenue_all"] = spearman(df, "estimated_revenue")
    out["spearman_revenue_credit_owners"] = spearman(owners, "estimated_revenue")
    out["spearman_credit_volume_active_credit_owners"] = {
        c: rank_corr(active_owners[c], active_owners.credit_purchase_volume) for c in pre
    }
    out["spearman_purchase_volume_active"] = {
        c: rank_corr(df[df.has_window_purchase][c], df[df.has_window_purchase].purchase_volume)
        for c in pre
    }

    owners = owners.assign(limit_q=pd.qcut(owners.credit_limit_total, 5, labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"]))
    out["by_credit_limit_quintile_owners"] = (
        owners.groupby("limit_q", observed=True)
        .agg(
            n=("client_id", "size"),
            limit_min=("credit_limit_total", "min"),
            limit_max=("credit_limit_total", "max"),
            mean_revenue=("estimated_revenue", "mean"),
            median_revenue=("estimated_revenue", "median"),
            pct_credit_primary=("product_role", lambda s: round(s.eq("Credit-primary").mean(), 3)),
            pct_dormant=("product_role", lambda s: round(s.eq("Dormant").mean(), 3)),
            median_util=("credit_utilisation", "median"),
        )
        .round(2)
        .reset_index()
        .to_dict(orient="records")
    )

    df = df.assign(score_band=pd.cut(df.credit_score, [0, 650, 700, 750, 900], labels=["<650", "650-699", "700-749", "750+"]))
    out["by_credit_score_band"] = (
        df.groupby("score_band", observed=True)
        .agg(
            n=("client_id", "size"),
            mean_revenue=("estimated_revenue", "mean"),
            pct_owned_credit=("owned_credit_pre_window", "mean"),
            pct_credit_primary=("product_role", lambda s: s.eq("Credit-primary").mean()),
            pct_dormant=("product_role", lambda s: s.eq("Dormant").mean()),
            median_dti=("debt_to_income", "median"),
        )
        .round(3)
        .reset_index()
        .to_dict(orient="records")
    )

    rev = df.estimated_revenue.sort_values(ascending=False)
    out["concentration"] = {
        "top_10pct_share": round(rev.head(int(len(rev) * 0.1)).sum() / rev.sum(), 3),
        "top_20pct_share": round(rev.head(int(len(rev) * 0.2)).sum() / rev.sum(), 3),
    }
    out["within_role_spread"] = (
        df[df.has_window_purchase]
        .groupby("product_role")
        .estimated_revenue.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
        .round(0)
        .reset_index()
        .to_dict(orient="records")
    )
    top = df.estimated_revenue >= df.estimated_revenue.quantile(0.9)
    out["top_decile_role_mix"] = df[top].product_role.value_counts(normalize=True).round(3).to_dict()

    out["fraud"] = {
        "labelled_share_of_window_purchases": round(df.labelled_share.mean(), 3),
        "by_role": df[df.has_window_purchase]
        .groupby("product_role")
        .agg(fraud_txns=("fraud_txns", "sum"), fraud_dollars=("fraud_dollars", "sum"), revenue=("estimated_revenue", "sum"))
        .assign(fraud_dollars_per_rev_dollar=lambda x: (x.fraud_dollars / x.revenue).round(3))
        .round({"fraud_dollars": 0, "revenue": 0})
        .reset_index()
        .to_dict(orient="records"),
    }

    (V2 / "drivers_stress_test.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
