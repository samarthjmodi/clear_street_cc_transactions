"""Q1 in plain terms: who the value segments are, and which groups earn the most.

Uses only customers with transaction records; customers without them are left out rather
than counted as $0. Every comparison is a plain average by group, with group sizes. No
variance ratios, p-values or correlations.

  1. Profile of each day-one segment: size, first-year revenue, share of revenue, and
     the typical customer (income, age at first card, credit score, 2019 spend)
  2. For every cut, the lowest- and highest-earning group (groups of 10+ customers),
     tagged by when the cut is known, next to the gap you'd typically see between random
     groups of the same sizes
  3. Within each day-one product, the lowest- and highest-earning income fifth
  4. Early signal: revenue in months 4-12 by fifth of first-90-day spend
  5. Chart: first-year revenue by day-one segment and by day-one credit limit

Run from repo root after q1_part2_value.py:
  .venv/bin/python src/q1_simple_profile.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
Q1 = REPO / "active_ds_takehome_handout" / "analysis" / "q1_value"
PLOTS = REPO / "plots"
MIN_GROUP = 10
SEGMENTS = ["Credit, limit $10k+", "Credit, limit under $10k", "Debit", "Prepaid"]
HIGH_LIMIT_BANDS = {"$10–15k", "$15–25k", "$25k+"}
LIMIT_ORDER = ["No credit card on day one", "under $5k", "$5–10k", "$10–15k", "$15–25k", "$25k+"]
FIFTHS = ["Bottom", "2nd", "3rd", "4th", "Top"]
NOT_A_GROUP = {"No signup record", "Not active Nov 2018 – Oct 2019"}

# column -> (label, when it's known)
CUTS = {
    "day_one_segment": ("Product and credit limit on day one", "Day one"),
    "day_one_brand": ("Card brand on day one", "Day one"),
    "age_at_first_card": ("Age at first card", "Day one"),
    "year_joined": ("Year joined", "Day one"),
    "income_fifth": ("Income fifth", "Feb 2020 snapshot"),
    "area_income_fifth": ("Area income fifth", "Feb 2020 snapshot"),
    "credit_score": ("Credit score band", "Feb 2020 snapshot"),
    "debt_to_income": ("Debt-to-income band", "Feb 2020 snapshot"),
    "region": ("Region", "Feb 2020 snapshot"),
    "gender": ("Gender", "Feb 2020 snapshot"),
    "self_reported_source": ("Self-reported source", "At signup"),
    "signup_landing_page": ("Landing page", "At signup"),
    "channel_last_touch": ("Last ad channel before signup", "At signup"),
    "persona": ("Persona", "Measured later (2019)"),
    "spend_fifth_2019": ("Spend fifth, 2019", "Measured later (2019)"),
    "products_held_feb_2020": ("Products held, Feb 2020", "Measured later (Feb 2020)"),
}


def day_one_segment(product: pd.Series, limit_band: pd.Series) -> pd.Series:
    credit = product.eq("Credit")
    out = product.where(~credit, "Credit, limit under $10k")
    return out.where(~(credit & limit_band.isin(HIGH_LIMIT_BANDS)), "Credit, limit $10k+")


def group_means(d: pd.DataFrame, by: str, value: str = "value_with_data") -> pd.DataFrame:
    g = d[~d[by].isin(NOT_A_GROUP)].groupby(by)[value]
    return pd.DataFrame({"customers": g.size(), "mean_revenue": g.mean()})


def lowest_and_highest(d: pd.DataFrame, by: str, min_group: int = MIN_GROUP,
                       value: str = "value_with_data") -> dict:
    """Lowest- and highest-earning groups among groups with at least `min_group` customers."""
    t = group_means(d, by, value)
    t = t[t.customers >= min_group].sort_values("mean_revenue")
    if len(t) < 2:
        return {"groups_compared": len(t)}
    lo, hi = t.iloc[0], t.iloc[-1]
    return {"groups_compared": len(t),
            "lowest_group": t.index[0], "lowest_customers": int(lo.customers), "lowest_revenue": lo.mean_revenue,
            "highest_group": t.index[-1], "highest_customers": int(hi.customers), "highest_revenue": hi.mean_revenue,
            "gap": hi.mean_revenue - lo.mean_revenue}


def chance_gap(d: pd.DataFrame, by: str, min_group: int = MIN_GROUP, n: int = 1000, seed: int = 0,
               value: str = "value_with_data") -> float:
    """Typical highest-minus-lowest gap when the same customers are dealt into random groups
    of the same sizes as the real groups compared."""
    t = group_means(d, by, value)
    keep = t.index[t.customers >= min_group]
    if len(keep) < 2:
        return float("nan")
    values = d.loc[d[by].isin(keep), value].to_numpy()
    cuts = np.cumsum(t.loc[keep, "customers"].to_numpy())[:-1]
    rng = np.random.default_rng(seed)
    gaps = []
    for _ in range(n):
        means = [g.mean() for g in np.split(rng.permutation(values), cuts)]
        gaps.append(max(means) - min(means))
    return float(np.median(gaps))


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    p2 = pd.read_csv(Q1 / "part2_customers.csv")
    p1 = pd.read_csv(Q1 / "part1_customers.csv",
                     usecols=["client_id", "yearly_income", "age_at_first_card", "credit_score", "spend"]
                     ).add_prefix("p1_").rename(columns={"p1_client_id": "client_id"})
    p2["day_one_segment"] = day_one_segment(p2.day_one_product, p2.day_one_credit_limit)
    d = p2[p2.has_data].merge(p1, on="client_id", how="left")
    out: dict = {"customers_in_cohort": len(p2), "customers_with_data": len(d),
                 "customers_left_out_no_data": int((~p2.has_data).sum())}

    # 1. Segment profile
    g = d.groupby("day_one_segment")
    prof = pd.DataFrame({
        "customers": g.size(),
        "mean_first_year_revenue": g.value_with_data.mean(),
        "median_income": g.p1_yearly_income.median(),
        "median_age_at_first_card": g.p1_age_at_first_card.median(),
        "median_credit_score": g.p1_credit_score.median(),
        "median_spend_2019": g.p1_spend.median(),
    }).reindex(SEGMENTS)
    prof.insert(1, "share_of_customers", prof.customers / prof.customers.sum())
    prof.insert(3, "share_of_revenue", g.value_with_data.sum().reindex(SEGMENTS) / d.value_with_data.sum())
    prof.to_csv(Q1 / "simple_segment_profile.csv")

    # 2. Lowest vs highest group, every cut
    # Revenue relative to others who opened the same day-one segment
    d["vs_own_segment"] = d.value_with_data - d.groupby("day_one_segment").value_with_data.transform("mean")
    rows = []
    for col, (label, when) in CUTS.items():
        same = lowest_and_highest(d, col, value="vs_own_segment")
        rows.append({"cut": label, "when_known": when, **lowest_and_highest(d, col),
                     "typical_chance_gap": chance_gap(d, col),
                     "gap_same_segment": same.get("gap", float("nan")),
                     "lowest_group_same_segment": same.get("lowest_group"),
                     "highest_group_same_segment": same.get("highest_group"),
                     "typical_chance_gap_same_segment": chance_gap(d, col, value="vs_own_segment")})
    spread = pd.DataFrame(rows)
    spread.to_csv(Q1 / "simple_cut_spread.csv", index=False)

    # 3. Income within each day-one product
    d["product_group"] = d.day_one_product.where(d.day_one_product.eq("Credit"), "Debit or prepaid")
    within = {}
    for prod, sub in d.groupby("product_group"):
        t = group_means(sub, "income_fifth").reindex(FIFTHS)
        within[prod] = t.round(1).to_dict(orient="index")
    out["income_fifth_within_product"] = within

    # 4. Early signal
    d["early_fifth"] = pd.qcut(d.first_90_days_spend.rank(method="first"), 5, labels=FIFTHS)
    early = d.groupby("early_fifth", observed=True).agg(
        customers=("client_id", "size"), median_first_90_days_spend=("first_90_days_spend", "median"),
        mean_months_4_12_revenue=("months_4_12_revenue", "mean"))
    early.to_csv(Q1 / "simple_early_signal.csv")
    halves = {}
    for prod, sub in d.groupby("product_group"):
        top = sub.first_90_days_spend >= sub.first_90_days_spend.median()
        halves[prod] = {"customers": len(sub),
                        "months_4_12_revenue_top_half": float(sub[top].months_4_12_revenue.mean()),
                        "months_4_12_revenue_bottom_half": float(sub[~top].months_4_12_revenue.mean())}
    out["early_signal_halves_within_product"] = halves
    (Q1 / "simple_summary.json").write_text(json.dumps(out, indent=2, default=str))

    # 5. Chart
    limits = group_means(d, "day_one_credit_limit").reindex(LIMIT_ORDER)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    seg_colors = ["#1f4e79", "#5b8fad", "#9fbfd6", "#c9ccd1"]
    axes[0].barh(SEGMENTS[::-1], prof.mean_first_year_revenue[::-1], color=seg_colors[::-1])
    for i, s in enumerate(SEGMENTS[::-1]):
        axes[0].text(prof.loc[s, "mean_first_year_revenue"] + 15, i,
                     f"${prof.loc[s, 'mean_first_year_revenue']:,.0f}  ({int(prof.loc[s, 'customers'])} customers)",
                     va="center", fontsize=9)
    axes[0].set_xlim(0, prof.mean_first_year_revenue.max() * 1.5)
    axes[0].set_title("By what they opened on day one")
    colors = ["#c9ccd1" if n < MIN_GROUP else "#1f4e79" for n in limits.customers]
    axes[1].barh(LIMIT_ORDER, limits.mean_revenue, color=colors)
    for i, band in enumerate(LIMIT_ORDER):
        axes[1].text(limits.loc[band, "mean_revenue"] + 30, i,
                     f"${limits.loc[band, 'mean_revenue']:,.0f}  ({int(limits.loc[band, 'customers'])})",
                     va="center", fontsize=9)
    axes[1].set_xlim(0, limits.mean_revenue.max() * 1.35)
    axes[1].set_title(f"By highest credit limit on day one\n(grey: fewer than {MIN_GROUP} customers)")
    for ax in axes:
        ax.set_xlabel("Average first-year revenue per customer ($)")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("First-year revenue, customers with transaction records (joined 2010–2018)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_first_year_value.png", dpi=150)
    plt.close(fig)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 20)
    print(prof.round(2).to_string(), "\n")
    print(spread.round(0).to_string(index=False), "\n")
    print(early.round(0).to_string(), "\n")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
