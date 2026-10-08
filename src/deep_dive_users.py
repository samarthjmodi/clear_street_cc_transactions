"""Deep dive on users_data.csv: quality, consistency, distributions, geography,
links to other tables, and relationship to customer value.

Run from repo root (after build_card_month.py and q1_v3_segments.py):
  .venv/bin/python src/deep_dive_users.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_revenue import load_cards, money  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
OUT = HANDOUT / "analysis" / "deep_dives" / "users"
PLOTS = OUT / "plots"
MONEY_COLS = ["per_capita_income", "yearly_income", "total_debt"]
NUM_COLS = ["current_age", "retirement_age", "birth_year", "birth_month", "latitude", "longitude",
            "per_capita_income", "yearly_income", "total_debt", "credit_score", "num_credit_cards"]


def load_users() -> tuple[pd.DataFrame, dict]:
    raw = pd.read_csv(HANDOUT / "users_data.csv", dtype=str)
    u = raw.copy()
    parse_fail = {}
    for c in MONEY_COLS:
        u[c] = money(raw[c])
        parse_fail[c] = int(u[c].isna().sum())
    for c in ["id", "current_age", "retirement_age", "birth_year", "birth_month", "credit_score", "num_credit_cards"]:
        u[c] = pd.to_numeric(raw[c], errors="coerce")
    for c in ["latitude", "longitude"]:
        u[c] = pd.to_numeric(raw[c], errors="coerce")
    return u.rename(columns={"id": "client_id"}), parse_fail


def rank_corr(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[cols].rank().corr()


def quality(u: pd.DataFrame, parse_fail: dict) -> dict:
    q = {
        "rows": len(u),
        "columns": u.shape[1],
        "nulls": u.isna().sum()[lambda s: s > 0].to_dict(),
        "money_parse_failures": parse_fail,
        "duplicate_ids": int(u.client_id.duplicated().sum()),
        "id_range": [int(u.client_id.min()), int(u.client_id.max())],
        "duplicate_addresses": u[u.address.duplicated(keep=False)][["client_id", "address", "latitude", "longitude"]].to_dict(orient="records"),
        "duplicate_full_rows_excl_id": int(u.drop(columns="client_id").duplicated().sum()),
        "ranges": {c: [float(u[c].min()), float(u[c].median()), float(u[c].max())] for c in NUM_COLS},
        "zero_counts": {c: int((u[c] == 0).sum()) for c in ["per_capita_income", "yearly_income", "total_debt", "num_credit_cards"]},
        "credit_score_outside_300_850": int(((u.credit_score < 300) | (u.credit_score > 850)).sum()),
        "gender": u.gender.value_counts().to_dict(),
    }
    as_of = u.birth_year + u.current_age
    q["implied_as_of_year"] = as_of.value_counts().sort_index().to_dict()
    q["retired_share"] = float((u.current_age >= u.retirement_age).mean())
    q["age_over_retirement_by_band"] = (
        u.assign(over=u.current_age >= u.retirement_age)
        .groupby(pd.cut(u.current_age, [0, 59, 64, 69, 120]), observed=True).over.mean().round(3).astype(float)
        .rename(index=str).to_dict()
    )
    q["yearly_lt_per_capita"] = int((u.yearly_income < u.per_capita_income).sum())
    ratio = u.yearly_income / u.per_capita_income
    q["income_to_per_capita_ratio"] = ratio.describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).round(3).to_dict()
    q["coord_precision_decimals"] = int(u.latitude.astype(str).str.split(".").str[1].str.len().max())
    coords = u.groupby(["latitude", "longitude"]).size()
    q["unique_coordinates"] = int(len(coords))
    q["users_sharing_coordinates"] = int(coords[coords > 1].sum())
    pc = u.groupby(["latitude", "longitude"]).per_capita_income.nunique()
    q["coords_with_multiple_per_capita_values"] = int((pc > 1).sum())
    q["outside_contiguous_us"] = int(((u.latitude > 49.5) | (u.latitude < 24.5) | (u.longitude < -125)).sum())
    return q


def links(u: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    cards = load_cards(HANDOUT / "cards_data.csv")
    cm = pd.read_csv(V3 / "card_month.csv", usecols=["client_id"])
    signups = pd.read_csv(HANDOUT / "account_signups.csv", usecols=["client_id"])
    tp_clients = set()
    for chunk in pd.read_csv(HANDOUT / "marketing_touchpoints.csv", usecols=["client_id"], chunksize=500_000):
        tp_clients.update(chunk.client_id.dropna().astype(int).unique())

    n_cards = cards.groupby("client_id").size()
    n_credit = cards[cards.card_type.eq("Credit")].groupby("client_id").size()
    n_credit_pre2020 = cards[cards.card_type.eq("Credit") & (cards.opened < "2020-01-01")].groupby("client_id").size()
    u = u.assign(
        cards_in_table=u.client_id.map(n_cards).fillna(0).astype(int),
        credit_cards_in_table=u.client_id.map(n_credit).fillna(0).astype(int),
        credit_cards_pre2020=u.client_id.map(n_credit_pre2020).fillna(0).astype(int),
        has_transactions=u.client_id.isin(set(cm.client_id)),
        has_signup=u.client_id.isin(set(signups.client_id)),
        has_touchpoints=u.client_id.isin(tp_clients),
    )
    out = {
        "users_with_cards": int((u.cards_in_table > 0).sum()),
        "card_client_ids_not_in_users": int((~cards.client_id.isin(u.client_id)).sum()),
        "users_with_transactions": int(u.has_transactions.sum()),
        "users_with_signup": int(u.has_signup.sum()),
        "users_with_touchpoints": int(u.has_touchpoints.sum()),
        "num_credit_cards_eq_credit_cards_in_table": float((u.num_credit_cards == u.credit_cards_in_table).mean()),
        "num_credit_cards_eq_all_cards_in_table": float((u.num_credit_cards == u.cards_in_table).mean()),
        "num_credit_cards_minus_credit_in_table": (u.num_credit_cards - u.credit_cards_in_table).describe().round(2).to_dict(),
        "num_credit_cards_minus_all_in_table": (u.num_credit_cards - u.cards_in_table).describe().round(2).to_dict(),
        "rank_corr_num_credit_cards_vs_credit_in_table": float(u.num_credit_cards.rank().corr(u.credit_cards_in_table.rank())),
        "rank_corr_num_credit_cards_vs_all_in_table": float(u.num_credit_cards.rank().corr(u.cards_in_table.rank())),
    }
    prof = []
    for flag in ["has_transactions", "has_signup", "has_touchpoints"]:
        for val, g in u.groupby(flag):
            prof.append({
                "flag": flag, "value": bool(val), "n": len(g),
                "median_age": g.current_age.median(), "median_income": g.yearly_income.median(),
                "median_debt": g.total_debt.median(), "median_score": g.credit_score.median(),
                "mean_cards_in_table": g.cards_in_table.mean(), "pct_female": g.gender.eq("Female").mean(),
            })
    return out, pd.DataFrame(prof), u


def value_relationships(u: pd.DataFrame) -> dict:
    base = pd.read_csv(V3 / "base_customers_segmented.csv")
    b = base[base.observed][["client_id", "value", "segment", "day_one", "purchase_volume"]].merge(
        u[["client_id", "current_age", "yearly_income", "per_capita_income", "total_debt", "credit_score",
           "num_credit_cards", "gender", "retirement_age", "latitude", "longitude"]], on="client_id")
    b["dti"] = b.total_debt / b.yearly_income
    b["income_vs_area"] = b.yearly_income / b.per_capita_income
    b["retired"] = b.current_age >= b.retirement_age
    bands = {
        "age": pd.cut(b.current_age, [17, 29, 39, 49, 59, 69, 120], labels=["18-29", "30-39", "40-49", "50-59", "60-69", "70+"]),
        "income_quintile": pd.qcut(b.yearly_income, 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]),
        "credit_score": pd.cut(b.credit_score, [0, 649, 699, 749, 900], labels=["<650", "650-699", "700-749", "750+"]),
        "debt_to_income": pd.cut(b.dti, [-0.01, 0.0001, 0.5, 1.5, 3, 100], labels=["0", "0-0.5", "0.5-1.5", "1.5-3", "3+"]),
        "num_credit_cards": b.num_credit_cards.clip(upper=7).astype(int).astype(str).replace("7", "7+"),
        "gender": b.gender,
        "retired": b.retired.map({True: "retired", False: "working age"}),
    }
    res = {}
    for name, band in bands.items():
        g = b.groupby(band, observed=True)
        t = pd.DataFrame({
            "n": g.size(),
            "mean_value": g.value.mean().round(0),
            "median_value": g.value.median().round(0),
            "mean_purchase_volume": g.purchase_volume.mean().round(0),
            "pct_credit_today": g.segment.apply(lambda s: s.isin(["Premium credit", "Core credit"]).mean()).round(3),
            "pct_premium_day_one": g.day_one.apply(lambda s: s.eq("Premium credit").mean()).round(3),
        })
        res[name] = t.reset_index().rename(columns={t.index.name or "index": "band"}).astype({"band": str}).to_dict(orient="records")
    cols = ["value", "purchase_volume", "current_age", "yearly_income", "per_capita_income", "total_debt", "dti",
            "credit_score", "num_credit_cards", "income_vs_area"]
    res["rank_corr_with_value"] = rank_corr(b, cols)["value"].drop("value").round(3).to_dict()
    res["rank_corr_with_purchase_volume"] = rank_corr(b, cols)["purchase_volume"].drop(["value", "purchase_volume"]).round(3).to_dict()
    res["n"] = len(b)
    return res, b


def plots(u: pd.DataFrame, b: pd.DataFrame, prof: pd.DataFrame) -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    specs = [
        ("current_age", "Current age", None),
        ("yearly_income", "Yearly income ($, log)", "log"),
        ("total_debt", "Total debt ($, log1p)", "log1p"),
        ("credit_score", "Credit score", None),
        ("num_credit_cards", "num_credit_cards (users table)", "int"),
        ("retirement_age", "Retirement age", None),
    ]
    for ax, (col, title, kind) in zip(axes.flat, specs):
        v = u[col].dropna()
        if kind == "log":
            ax.hist(np.log10(v[v > 0]), bins=40, color="#5b8fad")
            ax.set_xticks([4, 4.5, 5, 5.5])
            ax.set_xticklabels(["$10k", "$32k", "$100k", "$316k"])
        elif kind == "log1p":
            ax.hist(np.log10(v + 1), bins=40, color="#5b8fad")
            ax.set_xticks([0, 2, 4, 5, 6])
            ax.set_xticklabels(["$0", "$100", "$10k", "$100k", "$1M"])
        elif kind == "int":
            vc = v.value_counts().sort_index()
            ax.bar(vc.index, vc.values, color="#5b8fad")
        else:
            ax.hist(v, bins=40, color="#5b8fad")
        ax.set_title(title, fontsize=10)
    fig.suptitle("users_data.csv: distributions (2,000 customers)")
    fig.tight_layout()
    fig.savefig(PLOTS / "users_distributions.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    m = u.has_transactions
    ax.scatter(u.longitude[m], u.latitude[m], s=6, alpha=0.5, color="#1f4e79", label=f"Has transactions ({m.sum()})")
    ax.scatter(u.longitude[~m], u.latitude[~m], s=6, alpha=0.5, color="#d9822b", label=f"No transactions ({(~m).sum()})")
    ax.set_xlim(-127, -65)
    ax.set_ylim(23, 50)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Customer locations (contiguous US view)")
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOTS / "users_geography.png", dpi=140)
    plt.close(fig)

    cols = ["current_age", "retirement_age", "yearly_income", "per_capita_income", "total_debt", "credit_score",
            "num_credit_cards", "cards_in_table", "credit_cards_in_table"]
    corr = rank_corr(u, cols)
    fig, ax = plt.subplots(figsize=(8.5, 7))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8.5)
    ax.set_yticklabels(cols, fontsize=8.5)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=7.5,
                    color="white" if abs(corr.iloc[i, j]) > 0.5 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Rank correlations between user attributes (all 2,000)")
    fig.tight_layout()
    fig.savefig(PLOTS / "users_correlations.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    panels = [
        (pd.cut(b.current_age, [17, 29, 39, 49, 59, 69, 120], labels=["18-29", "30-39", "40-49", "50-59", "60-69", "70+"]), "Age"),
        (pd.qcut(b.yearly_income, 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]), "Income quintile"),
        (pd.cut(b.credit_score, [0, 649, 699, 749, 900], labels=["<650", "650-699", "700-749", "750+"]), "Credit score"),
        (pd.cut(b.dti, [-0.01, 0.0001, 0.5, 1.5, 3, 100], labels=["0", "0-0.5", "0.5-1.5", "1.5-3", "3+"]), "Debt-to-income"),
    ]
    for ax, (band, title) in zip(axes.flat, panels):
        g = b.groupby(band, observed=True).value
        mean, n = g.mean(), g.size()
        se = g.std() / np.sqrt(n)
        ax.bar(mean.index.astype(str), mean.values, yerr=1.96 * se.values, color="#5b8fad", capsize=3)
        for i, (v, k) in enumerate(zip(mean.values, n.values)):
            ax.text(i, v * 0.5, f"n={k}", ha="center", color="white", fontsize=8)
        ax.set_title(f"Annual value by {title.lower()}", fontsize=10)
        ax.set_ylabel("$ per customer")
    fig.suptitle("Established customers with transaction data (n=1,219), Nov 2018 to Oct 2019, mean ± 95% CI")
    fig.tight_layout()
    fig.savefig(PLOTS / "users_value_by_attribute.png", dpi=140)
    plt.close(fig)

    p = prof[prof.flag.eq("has_transactions")].set_index("value")
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6))
    for ax, (col, title, fmt) in zip(axes, [
        ("median_age", "Median age", "{:.0f}"),
        ("median_income", "Median income", "${:,.0f}"),
        ("median_score", "Median credit score", "{:.0f}"),
        ("mean_cards_in_table", "Cards per customer", "{:.1f}"),
    ]):
        vals = [p.loc[True, col], p.loc[False, col]]
        ax.bar(["Has txns", "No txns"], vals, color=["#1f4e79", "#d9822b"])
        for i, v in enumerate(vals):
            ax.text(i, v * 1.01, fmt.format(v), ha="center", va="bottom", fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, max(vals) * 1.2)
    fig.suptitle("Customers with vs without any transactions")
    fig.tight_layout()
    fig.savefig(PLOTS / "users_with_vs_without_transactions.png", dpi=140)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    u, parse_fail = load_users()
    q = quality(u, parse_fail)
    lk, prof, u = links(u)
    val, b = value_relationships(u)
    prof.to_csv(OUT / "coverage_profiles.csv", index=False)
    u.to_csv(OUT / "users_enriched.csv", index=False)
    desc = u[NUM_COLS + ["cards_in_table", "credit_cards_in_table"]].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).T
    desc.to_csv(OUT / "users_describe.csv")
    result = {"quality": q, "links": lk, "value": val}
    (OUT / "users_deep_dive.json").write_text(json.dumps(result, indent=2, default=str))
    plots(u, b, prof)
    pd.set_option("display.width", 250)
    print(desc.round(1).to_string())
    print(prof.round(2).to_string(index=False))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
