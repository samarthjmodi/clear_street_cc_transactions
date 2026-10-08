"""Value of acquired customers and cards in the years after acquisition.

Two lenses, both using full transaction history (2010-01 to 2019-10):
  * card level: every card opened 2010-01..2018-10, its own first-12-month revenue
  * customer level: customers whose first card opened 2010-01..2018-10, value in
    years 1-3 after acquisition across all their cards

Run from repo root after build_card_month.py:
  .venv/bin/python src/q1_v3_cohorts.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from q1_revenue import AMEX_FEE, WINDOW_END_MONTH, amex_fee_months, interchange, load_cards, money, month_index

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
FIRST_M = 2010 * 12 + 1
LAST_ACQ_M = WINDOW_END_MONTH - 11  # need a full first year


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cards = load_cards(HANDOUT / "cards_data.csv")
    users = pd.read_csv(HANDOUT / "users_data.csv").rename(columns={"id": "client_id"})
    users["yearly_income"] = money(users["yearly_income"])
    users["total_debt"] = money(users["total_debt"])
    cm = pd.read_csv(V3 / "card_month.csv")
    cm["m"] = month_index(cm.month)
    types = cards.set_index("card_id").card_type
    variants = {
        "rev": {},
        "rev_no_mt": {"exclude_money_transfer": True},
        "rev_prepaid_debit": {"prepaid_as_debit": True},
    }
    ct = cm.card_id.map(types)
    for col, kw in variants.items():
        cm[col] = interchange(cm, ct, **kw)
    return cards, users, cm


def card_year_value(cards: pd.DataFrame, cm: pd.DataFrame) -> pd.DataFrame:
    c = cards[(cards.open_m >= FIRST_M) & (cards.open_m <= LAST_ACQ_M)].copy()
    x = cm.merge(c[["card_id", "open_m"]], on="card_id")
    x = x[(x.m >= x.open_m) & (x.m < x.open_m + 12)]
    agg = x.groupby("card_id").agg(
        y1_interchange=("rev", "sum"),
        y1_interchange_no_mt=("rev_no_mt", "sum"),
        y1_interchange_prepaid_debit=("rev_prepaid_debit", "sum"),
        y1_purchase_volume=("purchase_volume", "sum"),
        y1_active_months=("purchase_count", lambda s: int((s > 0).sum())),
    )
    c = c.merge(agg, left_on="card_id", right_index=True, how="left")
    fill = ["y1_interchange", "y1_interchange_no_mt", "y1_interchange_prepaid_debit", "y1_purchase_volume", "y1_active_months"]
    c[fill] = c[fill].fillna(0)
    amex = (c.card_brand.eq("Amex") & c.card_type.eq("Credit")) * AMEX_FEE
    for base in ["", "_no_mt", "_prepaid_debit"]:
        c[f"y1_value{base}"] = c[f"y1_interchange{base}"] + amex
    first_m = cards.groupby("client_id").open_m.min()
    c["new_customer_card"] = c.open_m.eq(c.client_id.map(first_m))
    return c


def customer_year_values(cards: pd.DataFrame, cm: pd.DataFrame) -> pd.DataFrame:
    first_m = cards.groupby("client_id").open_m.min().rename("acq_m")
    acq = first_m[(first_m >= FIRST_M) & (first_m <= LAST_ACQ_M)].reset_index()
    cm2 = cm.merge(acq, on="client_id")
    cm2["year"] = (cm2.m - cm2.acq_m) // 12 + 1
    rows = acq.copy()
    amex = cards[cards.card_brand.eq("Amex") & cards.card_type.eq("Credit")].merge(acq, on="client_id")
    for k in (1, 2, 3):
        start = rows.acq_m + 12 * (k - 1)
        observable = start + 12 - 1 <= WINDOW_END_MONTH
        for col, src in [("value", "rev"), ("value_no_mt", "rev_no_mt"), ("value_prepaid_debit", "rev_prepaid_debit")]:
            ic = cm2[cm2.year.eq(k)].groupby("client_id")[src].sum()
            rows[f"y{k}_{col}"] = rows.client_id.map(ic).fillna(0)
        a_start = amex.acq_m + 12 * (k - 1)
        fee = (amex_fee_months(amex.open_m, a_start, a_start + 12) / 12 * AMEX_FEE).groupby(amex.client_id).sum()
        for col in ["value", "value_no_mt", "value_prepaid_debit"]:
            rows[f"y{k}_{col}"] = (rows[f"y{k}_{col}"] + rows.client_id.map(fee).fillna(0)).where(observable)
        pc = cm2[cm2.year.eq(k)].groupby("client_id").purchase_count.sum()
        rows[f"y{k}_purchases"] = rows.client_id.map(pc).fillna(0).where(observable)

    at_acq = cards.merge(acq, on="client_id")
    at_acq = at_acq[at_acq.open_m.eq(at_acq.acq_m)]
    g = at_acq.groupby("client_id")
    prod = pd.DataFrame(
        {
            "acq_has_credit": g.card_type.apply(lambda s: s.eq("Credit").any()),
            "acq_has_debit": g.card_type.apply(lambda s: s.eq("Debit").any()),
            "acq_credit_limit": at_acq[at_acq.card_type.eq("Credit")].groupby("client_id").credit_limit.max(),
            "acq_n_cards": g.size(),
        }
    )
    prod["acq_credit_limit"] = prod.acq_credit_limit.fillna(0)
    prod["acq_product"] = np.select(
        [prod.acq_has_credit, prod.acq_has_debit], ["Credit", "Debit"], default="Prepaid only"
    )
    rows = rows.merge(prod, left_on="client_id", right_index=True)
    later = cards.merge(acq, on="client_id")
    later = later[(later.open_m > later.acq_m) & (later.open_m < later.acq_m + 12) & later.card_type.eq("Credit")]
    rows["added_credit_in_y1"] = rows.client_id.isin(later.client_id)
    return rows


def main() -> None:
    cards, users, cm = load()
    demo = users[["client_id", "yearly_income", "credit_score", "current_age", "total_debt"]]

    cv = card_year_value(cards, cm).merge(demo, on="client_id", how="left")
    cust = customer_year_values(cards, cm).merge(demo, on="client_id", how="left")
    cv.to_csv(V3 / "card_first_year_value.csv", index=False)
    cust.to_csv(V3 / "new_customer_value.csv", index=False)

    out: dict = {"n_cards": len(cv), "n_new_customers": len(cust)}
    cv_obs = cv[cv.client_id.isin(set(cm.client_id))]
    out["n_cards_customers_with_data"] = len(cv_obs)
    out["card_by_type"] = (
        cv_obs.groupby(["card_type", "new_customer_card"])
        .agg(n=("card_id", "size"), mean_y1=("y1_value", "mean"), median_y1=("y1_value", "median"),
             pct_active=("y1_active_months", lambda s: (s > 0).mean()))
        .round(2).reset_index().to_dict(orient="records")
    )
    cr = cv_obs[cv_obs.card_type.eq("Credit")].copy()
    out["credit_card_underwriting"] = {
        "rank_corr_limit_income": round(cr.credit_limit.rank().corr(cr.yearly_income.rank()), 3),
        "rank_corr_limit_score": round(cr.credit_limit.rank().corr(cr.credit_score.rank()), 3),
        "rank_corr_y1_limit": round(cr.y1_value.rank().corr(cr.credit_limit.rank()), 3),
        "rank_corr_y1_income": round(cr.y1_value.rank().corr(cr.yearly_income.rank()), 3),
        "rank_corr_y1_score": round(cr.y1_value.rank().corr(cr.credit_score.rank()), 3),
        "limit_to_income_median": round((cr.credit_limit / cr.yearly_income).median(), 3),
    }

    def r2(X: np.ndarray, y: np.ndarray) -> float:
        X = np.column_stack([np.ones(len(X)), X])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        return float(1 - resid.var() / y.var())

    y = np.log1p(cr.y1_value.to_numpy())
    li, ls, ll = np.log(cr.yearly_income), cr.credit_score / 100, np.log1p(cr.credit_limit)
    out["credit_card_underwriting"]["r2_income_score"] = round(r2(np.column_stack([li, ls]), y), 3)
    out["credit_card_underwriting"]["r2_income_score_limit"] = round(r2(np.column_stack([li, ls, ll]), y), 3)
    out["credit_card_underwriting"]["r2_limit_only"] = round(r2(np.column_stack([ll]), y), 3)
    out["credit_card_underwriting"]["r2_income_only"] = round(r2(np.column_stack([li]), y), 3)

    cr["inc_t"] = pd.qcut(cr.yearly_income, 3, labels=["low", "mid", "high"])
    cr["lim_t"] = cr.groupby("inc_t", observed=True).credit_limit.transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["low", "mid", "high"]))
    out["credit_y1_by_income_x_limit"] = cr.pivot_table(
        index="inc_t", columns="lim_t", values="y1_value", aggfunc="mean", observed=True).round(0).to_dict()
    cr["lim_q"] = pd.qcut(cr.credit_limit, 4)
    out["credit_y1_by_limit_quartile"] = (
        cr.groupby("lim_q", observed=True).agg(n=("card_id", "size"), mean_y1=("y1_value", "mean"),
                                               mean_income=("yearly_income", "median"))
        .round(0).reset_index().astype({"lim_q": str}).to_dict(orient="records"))
    cr["inc_q"] = pd.qcut(cr.yearly_income, 4)
    out["credit_y1_by_income_quartile"] = (
        cr.groupby("inc_q", observed=True).agg(n=("card_id", "size"), mean_y1=("y1_value", "mean"),
                                               median_limit=("credit_limit", "median"))
        .round(0).reset_index().astype({"inc_q": str}).to_dict(orient="records"))
    db = cv_obs[cv_obs.card_type.eq("Debit")].copy()
    db["inc_q"] = pd.qcut(db.yearly_income, 4)
    out["debit_y1_by_income_quartile"] = (
        db.groupby("inc_q", observed=True).agg(n=("card_id", "size"), mean_y1=("y1_value", "mean"))
        .round(0).reset_index().astype({"inc_q": str}).to_dict(orient="records"))

    out["new_customers_by_product"] = (
        cust.groupby("acq_product")
        .agg(n=("client_id", "size"), y1=("y1_value", "mean"), y1_med=("y1_value", "median"),
             y2=("y2_value", "mean"), y3=("y3_value", "mean"), n_y3=("y3_value", "count"),
             pct_inactive_y1=("y1_purchases", lambda s: (s == 0).mean()),
             pct_added_credit=("added_credit_in_y1", "mean"),
             med_income=("yearly_income", "median"), med_limit=("acq_credit_limit", "median"))
        .round(2).reset_index().to_dict(orient="records")
    )
    (V3 / "cohort_notes.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
