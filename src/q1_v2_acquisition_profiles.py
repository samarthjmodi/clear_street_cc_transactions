"""Q1 acquisition profiles: segments Growth can see at signup.

Profile = credit-card holding and total credit limit band x income band, all
known before the observation window (Q1 population) or at signup (2020 signups).

Run from repo root after build_q1_v2_customer_metrics.py:
  .venv/bin/python src/q1_v2_acquisition_profiles.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V2 = HANDOUT / "analysis" / "q1_scratch" / "v2"
PLOTS = REPO / "plots"
START = pd.Timestamp("2018-11-01")
LIMIT_CUT = 12_000
ROLE_ORDER = ["Credit-primary", "Mixed", "Debit/prepaid only", "Dormant"]
PROFILE_ORDER = [
    "Credit $12k+ / higher income",
    "Credit $12k+ / lower income",
    "Credit <$12k / higher income",
    "Credit <$12k / lower income",
    "No credit card / higher income",
    "No credit card / lower income",
]
N_BOOT = 2000
RNG = np.random.default_rng(7)


def money(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")


def profile_label(has_credit: bool, credit_limit: float, income: float, income_cut: float) -> str:
    inc = "higher income" if income >= income_cut else "lower income"
    if not has_credit:
        return f"No credit card / {inc}"
    band = "Credit $12k+" if credit_limit >= LIMIT_CUT else "Credit <$12k"
    return f"{band} / {inc}"


def credit_holdings(cards: pd.DataFrame, as_of: pd.Series) -> pd.DataFrame:
    """Credit cards held and total credit limit per key, using cards opened on or before as_of."""
    c = cards.merge(as_of.rename("as_of"), left_on="key", right_index=True)
    c = c[(c.opened <= c.as_of) & c.card_type.eq("Credit")]
    g = c.groupby("key")
    return pd.DataFrame({"n_credit": g.size(), "credit_limit_total": g.credit_limit.sum()})


def boot_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) == 0:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(values), size=(N_BOOT, len(values)))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


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
    f["labelled_amt"] = np.where(f.id.isin(labelled_ids), f.amount_usd, 0.0)
    f["fraud_amt"] = np.where(f.id.isin(fraud_ids), f.amount_usd, 0.0)
    g = f.groupby("client_id")
    return pd.DataFrame({"labelled_volume": g.labelled_amt.sum(), "fraud_dollars": g.fraud_amt.sum()})


def segment_table(df: pd.DataFrame, by: str, order: list[str]) -> pd.DataFrame:
    rows = []
    for name in order:
        s = df[df[by].eq(name)]
        lo, hi = boot_ci(s.estimated_revenue.to_numpy())
        nlo, nhi = boot_ci(s.net_of_fraud.to_numpy())
        labelled = s.labelled_volume.sum()
        rows.append(
            {
                by: name,
                "customers": len(s),
                "pct_customers": len(s) / len(df),
                "mean_revenue": s.estimated_revenue.mean(),
                "ci_low": lo,
                "ci_high": hi,
                "median_revenue": s.estimated_revenue.median(),
                "p10_revenue": s.estimated_revenue.quantile(0.1),
                "p90_revenue": s.estimated_revenue.quantile(0.9),
                "pct_revenue": s.estimated_revenue.sum() / df.estimated_revenue.sum(),
                "fraud_rate_labelled": s.fraud_dollars.sum() / labelled if labelled else np.nan,
                "mean_fraud_dollars": s.fraud_dollars.mean(),
                "mean_net_of_fraud": s.net_of_fraud.mean(),
                "net_ci_low": nlo,
                "net_ci_high": nhi,
                "pct_dormant": s.product_role.eq("Dormant").mean(),
                "pct_credit_primary": s.product_role.eq("Credit-primary").mean(),
                "pct_top_decile": s.top_decile.mean(),
            }
        )
    return pd.DataFrame(rows)


def build_population() -> tuple[pd.DataFrame, float]:
    m = pd.read_csv(V2 / "customer_metrics.csv")
    cards = pd.read_csv(V2 / "dim_cards.csv")
    cards["opened"] = pd.to_datetime(cards["opened"])
    cards["credit_limit"] = money(cards["credit_limit"])
    cards["key"] = cards["client_id"]
    as_of = pd.Series(START - pd.Timedelta(days=1), index=m.client_id.unique())
    hold = credit_holdings(cards, as_of)
    df = m.merge(hold, left_on="client_id", right_index=True, how="left")
    df[["n_credit", "credit_limit_total"]] = df[["n_credit", "credit_limit_total"]].fillna(0)
    df = df.merge(fraud_by_customer(), left_on="client_id", right_index=True, how="left")
    df[["labelled_volume", "fraud_dollars"]] = df[["labelled_volume", "fraud_dollars"]].fillna(0)
    df["net_of_fraud"] = df.estimated_revenue - df.fraud_dollars
    df["top_decile"] = df.estimated_revenue >= df.estimated_revenue.quantile(0.9)
    income_cut = float(df.yearly_income.median())
    df["profile"] = [
        profile_label(h, l, i, income_cut)
        for h, l, i in zip(df.n_credit > 0, df.credit_limit_total, df.yearly_income)
    ]
    return df, income_cut


def profile_2020_signups(income_cut: float) -> pd.DataFrame:
    s = pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"])
    s = s[s.signup_ts.dt.year.eq(2020)].reset_index(drop=True)
    users = pd.read_csv(HANDOUT / "users_data.csv")
    cards = pd.read_csv(HANDOUT / "cards_data.csv")
    cards["opened"] = pd.to_datetime(cards["acct_open_date"], format="%m/%Y")
    cards["credit_limit"] = money(cards["credit_limit"])
    signup_card = cards.set_index("id")[["card_type", "credit_limit"]]
    s = s.join(signup_card, on="card_id")
    s["key"] = s.index
    cards_by_signup = cards.merge(s[["client_id", "key"]], on="client_id")
    hold = credit_holdings(cards_by_signup, s.set_index("key").signup_ts)
    s = s.join(hold, on="key")
    s[["n_credit", "credit_limit_total"]] = s[["n_credit", "credit_limit_total"]].fillna(0)
    s["yearly_income"] = s.client_id.map(users.set_index("id").yearly_income.pipe(money))
    s["profile"] = [
        profile_label(h, l, i, income_cut)
        for h, l, i in zip(s.n_credit > 0, s.credit_limit_total, s.yearly_income)
    ]
    return s


def plot_profiles(prof: pd.DataFrame, mix: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    p = prof.set_index("profile").reindex(PROFILE_ORDER)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    y = np.arange(len(p))[::-1]
    ax.barh(y, p.mean_revenue, color="#1f4e79", alpha=0.85, label="Mean revenue")
    ax.errorbar(
        p.mean_revenue, y,
        xerr=[p.mean_revenue - p.ci_low, p.ci_high - p.mean_revenue],
        fmt="none", ecolor="black", capsize=3, lw=1,
    )
    ax.scatter(p.mean_net_of_fraud, y, color="#d9822b", zorder=3, label="Net of labelled fraud (worst case)")
    for yi, (v, n, d) in zip(y, zip(p.mean_revenue, p.customers, p.pct_dormant)):
        ax.text(p.ci_high.max() * 1.03, yi, f"n={n}, {d:.0%} dormant", va="center", fontsize=8.5)
    ax.set_yticks(y)
    ax.set_yticklabels(p.index)
    ax.set_xlim(min(0, p.mean_net_of_fraud.min() * 1.1), p.ci_high.max() * 1.45)
    ax.set_xlabel("Estimated revenue per customer, Nov 2018 to Oct 2019 ($), 95% bootstrap CI")
    ax.set_title("Customer value by acquisition profile (known before the year)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_value_by_acquisition_profile.png", dpi=150)
    plt.close(fig)

    mx = mix.set_index("profile").reindex(PROFILE_ORDER)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = np.arange(len(mx))[::-1]
    ax.barh(y + 0.2, mx.pct_q1_population * 100, height=0.4, color="#9fbfd6", label="Existing base (Q1 population)")
    ax.barh(y - 0.2, mx.pct_2020_signups * 100, height=0.4, color="#1f4e79", label="2020 signups")
    ax.set_yticks(y)
    ax.set_yticklabels(mx.index)
    ax.set_xlabel("Share (%)")
    ax.set_title("Profile mix: 2020 signups versus the existing base")
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_profile_mix_2020_signups.png", dpi=150)
    plt.close(fig)


def plot_tail(df: pd.DataFrame) -> None:
    rev = np.sort(df.estimated_revenue.to_numpy())[::-1]
    cum = np.cumsum(rev) / rev.sum()
    x = np.arange(1, len(rev) + 1) / len(rev)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(x * 100, cum * 100, color="#1f4e79")
    axes[0].plot([0, 100], [0, 100], ls="--", color="grey", lw=0.8)
    for q in (0.1, 0.2):
        v = cum[int(len(rev) * q) - 1] * 100
        axes[0].scatter(q * 100, v, color="#d9822b", zorder=3)
        axes[0].annotate(f"Top {q:.0%}: {v:.0f}% of revenue", (q * 100, v), xytext=(8, -12), textcoords="offset points", fontsize=9)
    axes[0].set_xlabel("Customers ranked by revenue (%)")
    axes[0].set_ylabel("Cumulative share of revenue (%)")
    axes[0].set_title("Revenue concentration")
    active = [df.loc[df.product_role.eq(r), "estimated_revenue"].to_numpy() for r in ROLE_ORDER[:3]]
    axes[1].boxplot(active, showfliers=False, whis=(10, 90))
    axes[1].set_xticks([1, 2, 3])
    axes[1].set_xticklabels(ROLE_ORDER[:3])
    axes[1].set_ylabel("Estimated revenue per customer ($)")
    axes[1].set_title("Spread within each role (whiskers = 10th to 90th pct)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_revenue_concentration.png", dpi=150)
    plt.close(fig)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    df, income_cut = build_population()

    roles = segment_table(df, "product_role", ROLE_ORDER)
    profiles = segment_table(df, "profile", PROFILE_ORDER)
    roles.to_csv(V2 / "role_value_with_ci.csv", index=False)
    profiles.to_csv(V2 / "acquisition_profiles.csv", index=False)

    role_x_profile = pd.crosstab(df.profile, df.product_role, normalize="index").reindex(PROFILE_ORDER)[ROLE_ORDER]
    role_x_profile.to_csv(V2 / "profile_role_mix.csv")

    s20 = profile_2020_signups(income_cut)
    mix = pd.DataFrame(
        {
            "pct_q1_population": df.profile.value_counts(normalize=True),
            "pct_2020_signups": s20.profile.value_counts(normalize=True),
            "n_2020_signups": s20.profile.value_counts(),
        }
    ).reindex(PROFILE_ORDER).fillna(0).reset_index(names="profile")
    value = profiles.set_index("profile").mean_revenue
    mix["profile_mean_revenue"] = mix.profile.map(value)
    mix.to_csv(V2 / "profile_mix_2020_signups.csv", index=False)
    s20.drop(columns="key").to_csv(V2 / "signups_2020_profiled.csv", index=False)

    rev = df.estimated_revenue.sort_values(ascending=False)
    notes = {
        "income_cut_median": income_cut,
        "credit_limit_cut": LIMIT_CUT,
        "top_10pct_revenue_share": float(rev.head(int(len(rev) * 0.1)).sum() / rev.sum()),
        "top_20pct_revenue_share": float(rev.head(int(len(rev) * 0.2)).sum() / rev.sum()),
        "top_decile_threshold": float(df.estimated_revenue.quantile(0.9)),
        "fraud_label_coverage_of_purchase_volume": float(df.labelled_volume.sum() / df.purchase_volume.sum()),
        "expected_value_2020_mix": float((mix.pct_2020_signups * mix.profile_mean_revenue).sum()),
        "expected_value_base_mix": float((mix.pct_q1_population * mix.profile_mean_revenue).sum()),
        "signups_2020": int(len(s20)),
        "signups_2020_clients": int(s20.client_id.nunique()),
        "signups_2020_card_type": s20.card_type.value_counts(normalize=True).round(3).to_dict(),
        "mixed_p90_vs_credit_primary_median": [
            float(df.loc[df.product_role.eq("Mixed"), "estimated_revenue"].quantile(0.9)),
            float(df.loc[df.product_role.eq("Credit-primary"), "estimated_revenue"].median()),
        ],
    }
    (V2 / "acquisition_profiles_notes.json").write_text(json.dumps(notes, indent=2))

    plot_profiles(profiles, mix)
    plot_tail(df)

    pd.set_option("display.width", 250)
    print(roles.round(3).to_string(index=False))
    print(profiles.round(3).to_string(index=False))
    print(role_x_profile.round(3).to_string())
    print(mix.round(3).to_string(index=False))
    print(json.dumps(notes, indent=2))


if __name__ == "__main__":
    main()
