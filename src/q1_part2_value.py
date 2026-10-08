"""Q1 Part 2: rate each customer cut on revenue in the customer's first year.

Unit: customers whose first card opened Jan 2010 - Nov 2018, so their first 12 months are
observed by Oct 2019. First-year revenue covers months 1-12 from the first-card month, on every
card the customer holds, under the step 2 revenue model (interchange net of refunds, prepaid at
the debit rate, Amex fee pro-rated by months open; no revolving interest, no costs).

Headline: customers with no transaction data count as $0. Every group also shows the mean among
customers with data only.

Cuts known on day one come from the cards opened in the first-card month; owner attributes are
the Feb 2020 snapshot; behaviour cuts and personas come from Part 1 (measured Nov 2018 - Oct
2019, years after the first year) and are rated as consequences, among customers with data.

Run from repo root after q1_part1_profile.py:  .venv/bin/python src/q1_part2_value.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_customer_value import (OUT, PLOTS, age_at, adjusted_eta_squared, bootstrap_ci, customer_years,  # noqa: E402
                               eta_squared, months_overlap, monthly_card_revenue, permutation_p, plain, prepare,
                               rank_stability, score_band)
from q1_part1_profile import FIRST_CARD_AGE_BANDS  # noqa: E402

FIRST_YEAR_COHORT = (2010 * 12 + 1, 2018 * 12 + 11)
MIN_GROUP = 10
LIMIT_BANDS = ([0, 5000, 10000, 15000, 25000, 1e9], ["under $5k", "$5–10k", "$10–15k", "$15–25k", "$25k+"])
YEAR_GROUPS = {2010: "2010", 2011: "2011", 2012: "2012–2013", 2013: "2012–2013", 2014: "2014–2015",
               2015: "2014–2015", 2016: "2016–2018", 2017: "2016–2018", 2018: "2016–2018"}
FIFTHS = ["Bottom", "2nd", "3rd", "4th", "Top"]
NO_DATA = "Not active Nov 2018 – Oct 2019"
NO_SIGNUP = "No signup record"
PERSONA_NAMES = {"P1": "Younger credit users", "P2": "Debit-only everyday spenders",
                 "P3": "Established multi-card households", "P4": "Toll-road drivers"}
MIN_PLOT_GROUP = 5

# dimension -> (when it's known, labels left out of the ratings)
DIMENSIONS = {
    "day_one_product": ("Day one", []),
    "day_one_credit_limit": ("Day one", []),
    "day_one_brand": ("Day one", []),
    "cards_in_first_month": ("Day one", []),
    "year_joined": ("Day one", []),
    "age_at_first_card": ("Day one", []),
    "income_fifth": ("Snapshot (Feb 2020)", []),
    "area_income_fifth": ("Snapshot (Feb 2020)", []),
    "debt_to_income": ("Snapshot (Feb 2020)", []),
    "credit_score": ("Snapshot (Feb 2020)", []),
    "region": ("Snapshot (Feb 2020)", ["Unresolved"]),
    "gender": ("Snapshot (Feb 2020)", []),
    "self_reported_source": ("At signup", [NO_SIGNUP]),
    "signup_landing_page": ("At signup", [NO_SIGNUP]),
    "channel_last_touch": ("At signup", [NO_SIGNUP, "No linked touches"]),
    "persona": ("Consequence (Nov 2018 – Oct 2019)", [NO_DATA]),
    "products_held_feb_2020": ("Consequence (Feb 2020)", []),
    "main_spend_category": ("Consequence (Nov 2018 – Oct 2019)", [NO_DATA]),
    "spend_fifth_2019": ("Consequence (Nov 2018 – Oct 2019)", [NO_DATA]),
    "online_share_fifth_2019": ("Consequence (Nov 2018 – Oct 2019)", [NO_DATA]),
}
WITHIN_PRODUCT = ["age_at_first_card", "income_fifth", "area_income_fifth", "debt_to_income", "credit_score",
                  "region", "gender", "year_joined", "day_one_brand"]


# ---------- building blocks ----------

def first_year_value(years: pd.DataFrame) -> pd.DataFrame:
    """Customers whose first year is fully observed. Headline value counts customers with no
    transaction data as $0; value_with_data leaves them out."""
    y = years[years.years_observed >= 1].copy()
    y["value_with_data"] = y.year1.where(y.has_data)
    y["value"] = y.value_with_data.fillna(0.0)
    return y[["first_card_month", "cohort_year", "has_data", "value", "value_with_data"]]


def day_one_cards(cards: pd.DataFrame, first: pd.Series) -> pd.DataFrame:
    """Product, brand, highest credit limit and card count of the cards opened in the first-card month."""
    d = cards[cards.client_id.isin(first.index)]
    d = d[d.open_idx == d.client_id.map(first)]
    g = d.groupby("client_id")
    types, brands = g.card_type.agg(set), g.card_brand.agg(set)
    out = pd.DataFrame({
        "day_one_product": types.map(lambda s: "Credit" if "Credit" in s else "Debit" if "Debit" in s else "Prepaid"),
        "day_one_brand": brands.map(lambda s: next(iter(s)) if len(s) == 1 else "Several brands"),
        "day_one_max_limit": d[d.card_type == "Credit"].groupby("client_id").credit_limit.max(),
        "cards_in_first_month": g.size().map(lambda n: "1" if n == 1 else "2+"),
    })
    return out.reindex(first.index)


def band(x: pd.Series, edges: list, labels: list, missing: str) -> pd.Series:
    return pd.cut(x, edges, right=False, labels=labels).astype(object).where(x.notna(), missing)


def dti_band(dti: pd.Series) -> pd.Series:
    return pd.Series(np.select([dti.eq(0), dti < 1, dti < 2], ["No debt", "Under 1×", "1–2×"], "2× or more"),
                     index=dti.index).where(dti.notna(), "Missing")


def early_split(txn: dict, cards: pd.DataFrame, rates: dict, first: pd.Series) -> pd.DataFrame:
    """Spend and revenue in months 1-3 against revenue in months 4-12 of the first year."""
    rev = monthly_card_revenue(txn, cards, rates)
    rev = rev[rev.client_id.isin(first.index)]
    t = rev.month - rev.client_id.map(first)
    early, rest = rev[t.between(0, 2)], rev[t.between(3, 11)]
    a = cards[(cards.card_brand == "Amex") & (cards.card_type == "Credit") & cards.client_id.isin(first.index)]
    f = a.client_id.map(first)
    fee = lambda lo, hi: (months_overlap(a.open_idx, a.expires_idx, f + lo, f + hi) * rates["amex_fee"] / 12
                          ).groupby(a.client_id).sum()
    out = pd.DataFrame(index=first.index)
    out["first_90_days_spend"] = early.groupby("client_id").spend.sum()
    out["first_90_days_revenue"] = early.groupby("client_id").interchange.sum().add(fee(0, 2), fill_value=0)
    out["months_4_12_revenue"] = rest.groupby("client_id").interchange.sum().add(fee(3, 11), fill_value=0)
    return out.reindex(first.index)


def build_cuts(c: pd.DataFrame, cards: pd.DataFrame, fy: pd.DataFrame, part1: pd.DataFrame) -> pd.DataFrame:
    first = fy.first_card_month
    d1 = day_one_cards(cards, first)
    x = pd.DataFrame(index=fy.index)
    x["day_one_product"] = d1.day_one_product
    x["day_one_credit_limit"] = band(d1.day_one_max_limit, *LIMIT_BANDS, "No credit card on day one")
    x["day_one_brand"] = d1.day_one_brand
    x["cards_in_first_month"] = d1.cards_in_first_month
    x["year_joined"] = fy.cohort_year.map(YEAR_GROUPS)
    age = pd.Series(age_at(first, c.birth_year.reindex(fy.index), c.birth_month.reindex(fy.index)), index=fy.index)
    x["age_at_first_card"] = band(age, *FIRST_CARD_AGE_BANDS, "Missing")
    x["income_fifth"] = pd.qcut(c.yearly_income, 5, labels=FIFTHS).astype(str).reindex(fy.index)
    x["area_income_fifth"] = pd.qcut(c.per_capita_income.rank(method="first"), 5, labels=FIFTHS).astype(str).reindex(
        fy.index)
    x["debt_to_income"] = dti_band((c.total_debt / c.yearly_income).reindex(fy.index))
    x["credit_score"] = score_band(c.credit_score).reindex(fy.index).astype(object)
    x["region"] = c.region.reindex(fy.index).fillna("Unresolved")
    x["gender"] = c.gender.reindex(fy.index)
    has_signup = c.first_signup_ts.reindex(fy.index).notna()
    for col in ["self_reported_source", "signup_landing_page"]:
        x[col] = c[col].reindex(fy.index).where(has_signup, NO_SIGNUP)
    x["channel_last_touch"] = c.channel_last_touch.reindex(fy.index).where(has_signup, NO_SIGNUP).fillna(
        "No linked touches")

    p = part1.reindex(fy.index)
    active = p.purchases.notna()
    x["persona"] = p.persona.map(PERSONA_NAMES).where(active, NO_DATA)
    x["products_held_feb_2020"] = p.products_held
    x["main_spend_category"] = p.main_category.where(active, NO_DATA)
    for col, name in [("spend", "spend_fifth_2019"), ("online_share", "online_share_fifth_2019")]:
        q = pd.qcut(p[col].where(active), 5, labels=FIFTHS)
        x[name] = q.astype(object).where(active, NO_DATA)
    return x


# ---------- ratings ----------

def group_table(v: pd.Series, v_data: pd.Series, has_data: pd.Series, g: pd.Series, dim: str) -> pd.DataFrame:
    rows, overall, total = [], v.mean(), v.sum()
    for grp, idx in g.groupby(g).groups.items():
        a, b = v[idx], v_data[idx].dropna()
        lo, hi = bootstrap_ci(a) if len(a) > 1 else (np.nan, np.nan)
        blo, bhi = bootstrap_ci(b) if len(b) > 1 else (np.nan, np.nan)
        rows.append({"dimension": dim, "group": grp, "customers": len(a), "with_data": int(has_data[idx].sum()),
                     "first_year_revenue": a.mean(), "low_95": lo, "high_95": hi, "median": a.median(),
                     "index_vs_all": a.mean() / overall, "share_of_first_year_revenue": a.sum() / total,
                     "with_data_revenue": b.mean() if len(b) else np.nan, "with_data_low_95": blo,
                     "with_data_high_95": bhi})
    return pd.DataFrame(rows).sort_values("first_year_revenue", ascending=False)


def rate_dimension(v: pd.Series, g: pd.Series, excluded: list) -> dict:
    use = ~g.isin(excluded) & v.notna()
    v, g = v[use], g[use]
    sizes = g.value_counts()
    big = sizes.index[sizes >= MIN_GROUP]
    vb, gb = v[g.isin(big)], g[g.isin(big)]
    e = eta_squared(v, g) if len(sizes) > 1 else np.nan
    return {"customers": int(len(v)), "groups": int(len(sizes)), "groups_with_10_plus": int(len(big)),
            "eta_squared_adjusted": adjusted_eta_squared(e, len(v), len(sizes)) if len(sizes) > 1 else np.nan,
            "permutation_p": permutation_p(v, g) if len(sizes) > 1 else np.nan,
            "rank_stability_10_plus": rank_stability(vb, gb) if len(big) > 1 else np.nan}


def rate_all(fy: pd.DataFrame, cuts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    groups, ranks = [], []
    for dim, (known, excluded) in DIMENSIONS.items():
        consequence = known.startswith("Consequence") and dim != "products_held_feb_2020"
        v = fy.value_with_data if consequence else fy.value
        groups.append(group_table(fy.value, fy.value_with_data, fy.has_data, cuts[dim], dim).assign(known=known))
        head = rate_dimension(v, cuts[dim], excluded)
        data_only = rate_dimension(fy.value_with_data, cuts[dim], excluded)
        ranks.append({"dimension": dim, "known": known,
                      "headline_basis": "customers with data" if consequence else "all, no data as $0",
                      **head, "with_data_eta_squared_adjusted": data_only["eta_squared_adjusted"],
                      "with_data_permutation_p": data_only["permutation_p"],
                      "with_data_customers": data_only["customers"]})
    return pd.concat(groups, ignore_index=True), pd.DataFrame(ranks).sort_values("eta_squared_adjusted",
                                                                                   ascending=False)


def within_product(fy: pd.DataFrame, cuts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    product = cuts.day_one_product.map(lambda p: "Credit" if p == "Credit" else "Debit or prepaid")
    for prod in ["Credit", "Debit or prepaid"]:
        m = product.eq(prod)
        for dim in WITHIN_PRODUCT:
            g = cuts.loc[m, dim]
            r = rate_dimension(fy.value[m], g, DIMENSIONS[dim][1])
            t = group_table(fy.value[m], fy.value_with_data[m], fy.has_data[m], g, dim)
            rows.append(t.assign(product=prod, dimension_eta_squared_adjusted=r["eta_squared_adjusted"],
                                 dimension_permutation_p=r["permutation_p"]))
    return pd.concat(rows, ignore_index=True)


def early_signal(fy: pd.DataFrame, early: pd.DataFrame, cuts: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    e = early[fy.has_data].fillna(0.0)
    e = e.assign(product=cuts.day_one_product.reindex(e.index).map(
        lambda p: "Credit" if p == "Credit" else "Debit or prepaid"),
                 spend_fifth=pd.qcut(e.first_90_days_spend.rank(method="first"), 5, labels=FIFTHS).astype(str))
    t = e.groupby("spend_fifth").agg(customers=("months_4_12_revenue", "size"),
                                     first_90_days_spend=("first_90_days_spend", "median"),
                                     months_4_12_revenue=("months_4_12_revenue", "mean")).reindex(FIFTHS)
    rho = {"all": float(e.first_90_days_spend.corr(e.months_4_12_revenue, method="spearman")),
           "revenue_all": float(e.first_90_days_revenue.corr(e.months_4_12_revenue, method="spearman"))}
    for prod, g in e.groupby("product"):
        rho[f"spend_{prod}"] = float(g.first_90_days_spend.corr(g.months_4_12_revenue, method="spearman"))
        rho[f"revenue_{prod}"] = float(g.first_90_days_revenue.corr(g.months_4_12_revenue, method="spearman"))
    rho["customers"] = int(len(e))
    return t.reset_index(), rho


# ---------- plots ----------

def plots(groups: pd.DataFrame, ranks: pd.DataFrame, within: pd.DataFrame, early_t: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    colours = {"Day one": "tab:blue", "Snapshot (Feb 2020)": "tab:orange", "At signup": "tab:green"}
    r = ranks.sort_values("eta_squared_adjusted")
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.barh(r.dimension.str.replace("_", " ") + "  (n=" + r.customers.astype(str) + ")",
            r.eta_squared_adjusted.clip(lower=0) * 100,
            color=[colours.get(k, "lightgrey") for k in r.known])
    ax.set_xlabel("Share of first-year revenue variance explained by the groups, net of chance (%)")
    ax.set_title("Which cuts separate first-year revenue\n(customers who joined 2010 – Nov 2018)")
    ax.legend(handles=[Patch(color=v, label=k) for k, v in colours.items()]
              + [Patch(color="lightgrey", label="Consequence (measured later)")], fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p2_separation.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, dim, title in [(axes[0], "day_one_product", "Product on day one"),
                           (axes[1], "day_one_credit_limit", "Highest credit limit on day one")]:
        s = groups[groups.dimension == dim].sort_values("first_year_revenue")
        y = np.arange(len(s))
        ax.barh(y, s.first_year_revenue, xerr=[s.first_year_revenue - s.low_95, s.high_95 - s.first_year_revenue],
                color="tab:blue", alpha=0.8, capsize=3, label="all customers (no data = $0)")
        ax.scatter(s.with_data_revenue, y, color="black", zorder=3, s=18, label="customers with data only")
        ax.set_yticks(y, [f"{g}  (n={n}, {d} with data)" for g, n, d in zip(s.group, s.customers, s.with_data)],
                      fontsize=8)
        ax.set_xlabel("First-year revenue per customer ($, 95% CI)")
        ax.set_title(title, fontsize=10)
    axes[0].legend(fontsize=8, loc="lower right")
    fig.suptitle("First-year revenue by what customers opened on day one")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p2_day_one.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    for ax, dim, title in [(axes[0], "income_fifth", "Income fifth"), (axes[1], "age_at_first_card", "Age at first card"),
                           (axes[2], "year_joined", "Year joined")]:
        for prod, col in [("Credit", "tab:blue"), ("Debit or prepaid", "tab:orange")]:
            s = within[(within.dimension == dim) & (within["product"] == prod) & (within.customers >= MIN_PLOT_GROUP)]
            order = {"income_fifth": FIFTHS, "age_at_first_card": FIRST_CARD_AGE_BANDS[1]}.get(dim, sorted(s.group))
            s = s.set_index("group").reindex([o for o in order if o in set(s.group)])
            ax.plot(s.index, s.first_year_revenue, marker="o", color=col, label=f"{prod} on day one")
        ax.set_title(title, fontsize=10)
        ax.tick_params(axis="x", rotation=30)
    axes[0].set_ylabel("First-year revenue per customer (no data counted as zero)")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Owner cuts within each day-one product (groups with {MIN_PLOT_GROUP}+ customers)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p2_within_product.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    s = groups[(groups.dimension == "persona") & groups.group.ne(NO_DATA)].sort_values("with_data_revenue")
    y = np.arange(len(s))
    axes[0].barh(y, s.with_data_revenue, xerr=[s.with_data_revenue - s.with_data_low_95,
                                               s.with_data_high_95 - s.with_data_revenue],
                 color="lightgrey", edgecolor="grey", capsize=3)
    axes[0].set_yticks(y, [f"{g}  (n={d})" for g, d in zip(s.group, s.with_data)])
    axes[0].set_xlabel("First-year revenue per customer ($, customers with data, 95% CI)")
    axes[0].set_title("By Part 1 persona (measured years later: a consequence)", fontsize=10)
    axes[1].bar(early_t.spend_fifth, early_t.months_4_12_revenue, color="tab:blue")
    axes[1].set_xlabel("Fifth of spend in the first 90 days")
    axes[1].set_ylabel("Revenue in months 4–12 ($)")
    axes[1].set_title("Early signal: first 90 days against the rest of year one", fontsize=10)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p2_consequences_and_early_signal.png", dpi=150)
    plt.close(fig)


# ---------- main ----------

def main() -> dict:
    p = prepare()
    c, cards, txn, rates = p["c"], p["cards"], p["txn"], p["rates"]
    years = customer_years(c, cards, txn, rates)
    fy = first_year_value(years)
    fy = fy[fy.first_card_month.between(*FIRST_YEAR_COHORT)]
    part1 = pd.read_csv(OUT / "part1_customers.csv", index_col=0)
    cuts = build_cuts(c, cards, fy, part1)
    groups, ranks = rate_all(fy, cuts)
    within = within_product(fy, cuts)
    early = early_split(txn, cards, rates, fy.first_card_month)
    early_t, rho = early_signal(fy, early, cuts)

    fy.join(cuts).join(early).to_csv(OUT / "part2_customers.csv")
    groups.to_csv(OUT / "part2_segment_value.csv", index=False)
    ranks.to_csv(OUT / "part2_dimension_ranking.csv", index=False)
    within.to_csv(OUT / "part2_within_product.csv", index=False)
    early_t.to_csv(OUT / "part2_early_signal.csv", index=False)
    summary = {
        "cohort": {"customers": int(len(fy)), "with_data": int(fy.has_data.sum()),
                   "by_year": pd.crosstab(fy.cohort_year, fy.has_data).to_dict()},
        "first_year_revenue": {"all_no_data_as_zero": float(fy.value.mean()),
                               "with_data_only": float(fy.value_with_data.mean()),
                               "all_ci": bootstrap_ci(fy.value), "with_data_ci": bootstrap_ci(fy.value_with_data.dropna())},
        "early_signal_spearman": rho,
    }
    (OUT / "part2_summary.json").write_text(json.dumps(plain(summary), indent=2, default=str))
    plots(groups, ranks, within, early_t)
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, default=str))
