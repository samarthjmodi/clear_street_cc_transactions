"""Q1: first-year revenue of each card, profiled by who opened it.

Cards opened 2010-01..2018-11 (a full first year of transactions is visible), held by
customers with transaction data. Revenue is the card's own first 12 months of
interchange plus pro-rated Amex fees (from q1_v3_cohorts.py).

Profiles: age at card opening, state (from latitude/longitude), per-capita income,
yearly income and num_credit_cards buckets.

Run from repo root after build_card_month.py and q1_v3_cohorts.py:
  .venv/bin/python src/q1_card_first_year_profile.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_revenue import money  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
OUT = HANDOUT / "analysis" / "q1_scratch" / "card_profile"
GEOJSON = HANDOUT / "analysis" / "reference" / "us_states.geojson"
PLOTS = REPO / "plots"
SNAPSHOT_YEAR = 2020 + 1 / 12  # users_data ages are as of Feb 2020
RNG = np.random.default_rng(7)
TYPES = ["Credit", "Debit", "Debit (Prepaid)"]
TYPE_LABEL = {"Credit": "Credit", "Debit": "Debit", "Debit (Prepaid)": "Prepaid"}
TYPE_COLOR = {"Credit": "#1f4e79", "Debit": "#9fbfd6", "Debit (Prepaid)": "#c9ccd1"}

REGION = {
    "Northeast": ["Connecticut", "Maine", "Massachusetts", "New Hampshire", "Rhode Island", "Vermont",
                  "New Jersey", "New York", "Pennsylvania"],
    "Midwest": ["Illinois", "Indiana", "Michigan", "Ohio", "Wisconsin", "Iowa", "Kansas", "Minnesota",
                "Missouri", "Nebraska", "North Dakota", "South Dakota"],
    "South": ["Delaware", "District of Columbia", "Florida", "Georgia", "Maryland", "North Carolina",
              "South Carolina", "Virginia", "West Virginia", "Alabama", "Kentucky", "Mississippi",
              "Tennessee", "Arkansas", "Louisiana", "Oklahoma", "Texas"],
    "West": ["Arizona", "Colorado", "Idaho", "Montana", "Nevada", "New Mexico", "Utah", "Wyoming",
             "Alaska", "California", "Hawaii", "Oregon", "Washington"],
}
STATE_REGION = {s: r for r, ss in REGION.items() for s in ss}
STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY", "Puerto Rico": "PR",
}


def load_state_polygons(path: Path = GEOJSON) -> list[tuple[str, MplPath]]:
    polys = []
    for f in json.loads(path.read_text())["features"]:
        g = f["geometry"]
        rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        polys += [(f["properties"]["name"], MplPath(np.asarray(r)[:, :2])) for r in rings]
    return polys


def state_of(lat: np.ndarray, lon: np.ndarray, polys: list[tuple[str, MplPath]]) -> tuple[np.ndarray, np.ndarray]:
    """State containing each point; points outside every outline get the state with the nearest boundary vertex."""
    pts = np.column_stack([lon, lat])
    state = np.full(len(pts), None, dtype=object)
    for name, p in polys:
        hit = (state == None) & p.contains_points(pts)  # noqa: E711
        state[hit] = name
    inside = state != None  # noqa: E711
    if (~inside).any():
        verts = np.vstack([p.vertices for _, p in polys])
        names = np.concatenate([[n] * len(p.vertices) for n, p in polys])
        for i in np.where(~inside)[0]:
            state[i] = names[np.argmin(((verts - pts[i]) ** 2).sum(axis=1))]
    return state, inside


def in_person_home_state(clients: set[int]) -> pd.Series:
    """Each customer's most common merchant_state across in-person (non-online) purchases."""
    counts = []
    for ch in pd.read_csv(HANDOUT / "transactions_data.csv", usecols=["client_id", "merchant_state", "use_chip"],
                          chunksize=1_000_000):
        ch = ch[ch.client_id.isin(clients) & ch.use_chip.ne("Online Transaction") & ch.merchant_state.notna()]
        counts.append(ch.groupby(["client_id", "merchant_state"]).size())
    c = pd.concat(counts).groupby(level=[0, 1]).sum().reset_index(name="n")
    return c.sort_values("n", ascending=False).drop_duplicates("client_id").set_index("client_id").merchant_state


def cluster_boot_ci(df: pd.DataFrame, col: str = "y1_value", n: int = 2000) -> tuple[float, float]:
    """95% CI for the mean card value, resampling customers (cards of one customer move together)."""
    g = df.groupby("client_id")[col].agg(["sum", "count"])
    if len(g) < 2:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(g), size=(n, len(g)))
    means = g["sum"].to_numpy()[idx].sum(axis=1) / g["count"].to_numpy()[idx].sum(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def money_bins(s: pd.Series, q: int = 5) -> pd.Series:
    edges = np.unique(np.quantile(s, np.linspace(0, 1, q + 1)))
    labels = [f"${edges[i] / 1000:,.0f}k–${edges[i + 1] / 1000:,.0f}k" for i in range(len(edges) - 1)]
    return pd.cut(s, edges, labels=labels, include_lowest=True)


def add_buckets(c: pd.DataFrame) -> pd.DataFrame:
    c["age_at_open"] = (c.current_age - (SNAPSHOT_YEAR - (c.opened.dt.year + (c.opened.dt.month - 0.5) / 12))).round()
    c["age_bucket"] = pd.cut(c.age_at_open, [0, 29, 39, 49, 59, 69, 120],
                             labels=["Under 30", "30–39", "40–49", "50–59", "60–69", "70+"])
    c["per_capita_income_bucket"] = money_bins(c.per_capita_income)
    c["yearly_income_bucket"] = money_bins(c.yearly_income)
    c["num_cards_bucket"] = pd.cut(c.num_credit_cards, [0, 1, 2, 3, 4, 5, 20],
                                   labels=["1", "2", "3", "4", "5", "6+"])
    c["card_type_label"] = pd.Categorical(c.card_type.map(TYPE_LABEL), ["Credit", "Debit", "Prepaid"])
    c["brand_type"] = c.card_brand + " " + c.card_type_label.astype(str).str.lower()
    c["open_year"] = c.opened.dt.year
    c["card_role"] = np.where(c.new_customer_card, "Customer's first card", "Extra card")
    credit = c.card_type.eq("Credit")
    c.loc[credit, "credit_limit_bucket"] = money_bins(c.loc[credit, "credit_limit"]).astype(str)
    debit = c.card_type.eq("Debit")
    c.loc[debit, "debit_limit_bucket"] = money_bins(c.loc[debit, "credit_limit"]).astype(str)
    return c


def profile(c: pd.DataFrame, by: str, min_cards: int = 0) -> pd.DataFrame:
    rows = []
    for key, g in c.groupby(by, observed=True):
        if len(g) < min_cards:
            continue
        lo, hi = cluster_boot_ci(g)
        r = {
            by: key,
            "cards": len(g),
            "customers": g.client_id.nunique(),
            "pct_of_cards": len(g) / len(c),
            "mean_y1_value": g.y1_value.mean(),
            "ci_low": lo,
            "ci_high": hi,
            "median_y1_value": g.y1_value.median(),
            "pct_of_y1_value": g.y1_value.sum() / c.y1_value.sum(),
            "pct_credit": g.card_type.eq("Credit").mean(),
            "mean_purchase_volume": g.y1_purchase_volume.mean(),
            "mean_y1_interchange": g.y1_interchange.mean(),
            "mean_y1_amex_fee": (g.y1_value - g.y1_interchange).mean(),
            "mean_active_months": g.y1_active_months.mean(),
            "pct_first_card": g.new_customer_card.mean(),
        }
        for t in TYPES:
            gt = g[g.card_type.eq(t)]
            r[f"n_{TYPE_LABEL[t].lower()}"] = len(gt)
            r[f"mean_{TYPE_LABEL[t].lower()}"] = gt.y1_value.mean() if len(gt) else np.nan
        r["median_credit_limit_credit"] = g[g.card_type.eq("Credit")].credit_limit.median()
        rows.append(r)
    return pd.DataFrame(rows)


def mix_adjusted(c: pd.DataFrame, by: str) -> pd.Series:
    """Mean value if every bucket had the overall card-type mix: shows how much of the gap is product mix."""
    overall_mix = c.card_type.value_counts(normalize=True)
    by_type = c.groupby([by, "card_type"], observed=True).y1_value.mean().unstack()
    return (by_type.fillna(by_type.mean()) * overall_mix).sum(axis=1)


def plot_profiles(tables: dict[str, pd.DataFrame], titles: dict[str, str]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, (by, t) in zip(axes.flat, tables.items()):
        x = np.arange(len(t))
        w = 0.38
        ax.bar(x - w / 2, t.mean_credit, w, color=TYPE_COLOR["Credit"], label="Credit cards")
        ax.bar(x + w / 2, t.mean_debit, w, color=TYPE_COLOR["Debit"], label="Debit cards")
        ax.plot(x, t.mean_y1_value, "o-", color="#d62728", lw=1.8, label="All cards (incl. prepaid)")
        for i, r in t.reset_index(drop=True).iterrows():
            ax.text(i, max(r.mean_credit if np.isfinite(r.mean_credit) else 0, r.mean_y1_value) + 15,
                    f"n={r.cards}\n{r.pct_credit:.0%} credit", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(x)
        ax.set_xticklabels(t[by].astype(str).str.replace("$", r"\$", regex=False), fontsize=8.5)
        ax.set_title(titles[by], fontsize=11)
        ax.set_ylabel("First-year revenue per card ($)")
        ax.set_ylim(0, np.nanmax(t[["mean_credit", "mean_y1_value"]].to_numpy()) * 1.35)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9, frameon=False)
    fig.suptitle("First-year revenue per card by who opened it (cards opened 2010–2018, customers with data)",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(PLOTS / "q1_card_y1_by_user_attributes.png", dpi=150)
    plt.close(fig)


def _ci_bars(ax, t: pd.DataFrame, key: str, color, label_fmt) -> None:
    x = np.arange(len(t))
    ax.bar(x, t.mean_y1_value, color=color)
    ax.errorbar(x, t.mean_y1_value, yerr=[t.mean_y1_value - t.ci_low, t.ci_high - t.mean_y1_value],
                fmt="none", ecolor="black", capsize=3, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([label_fmt(r) for _, r in t.iterrows()], fontsize=8)
    ax.set_ylabel("First-year revenue per card ($), 95% CI")


def plot_card_attributes(brand: pd.DataFrame, role: pd.DataFrame, limit: pd.DataFrame, cohort: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    ax = axes[0, 0]
    colors = [TYPE_COLOR[{"credit": "Credit", "debit": "Debit", "prepaid": "Debit (Prepaid)"}[b.split()[-1]]]
              for b in brand.brand_type]
    _ci_bars(ax, brand, "brand_type", colors, lambda r: f"{r.brand_type.replace(' ', chr(10))}\nn={r.cards}")
    for i, r in enumerate(brand.itertuples()):
        if r.mean_y1_amex_fee > 0:
            ax.bar(i, r.mean_y1_amex_fee, bottom=r.mean_y1_interchange, color="#e6a23c", width=0.8,
                   label="Amex annual fee")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("By brand and card type")

    ax = axes[0, 1]
    x = np.arange(3)
    w = 0.38
    counts = {}
    for j, (rl, col) in enumerate([("Customer's first card", "#1f4e79"), ("Extra card", "#9fbfd6")]):
        t = role[role.card_role.eq(rl)].set_index("card_type_label").reindex(["Credit", "Debit", "Prepaid"])
        xs = x + (j - 0.5) * w
        ax.bar(xs, t.mean_y1_value, w, color=col, label=rl)
        ax.errorbar(xs, t.mean_y1_value, yerr=[t.mean_y1_value - t.ci_low, t.ci_high - t.mean_y1_value],
                    fmt="none", ecolor="black", capsize=3, lw=0.8)
        counts[rl] = t.cards.fillna(0).astype(int)
    ax.set_xticks(x)
    first, extra = counts["Customer's first card"], counts["Extra card"]
    ax.set_xticklabels([f"{k}\nfirst n={first[k]}, extra n={extra[k]}" for k in ["Credit", "Debit", "Prepaid"]],
                       fontsize=8.5)
    ax.set_ylim(0, None)
    ax.set_ylabel("First-year revenue per card ($), 95% CI")
    ax.legend(fontsize=8)
    ax.set_title("By card type: a customer's first card versus an extra card")

    ax = axes[1, 0]
    _ci_bars(ax, limit, "credit_limit_bucket", TYPE_COLOR["Credit"],
             lambda r: f"{r.credit_limit_bucket.replace('$', chr(92) + '$')}\nn={r.cards}")
    ax.set_title("Credit cards by credit limit (quintiles)")

    ax = axes[1, 1]
    for t, col, lab in [("Credit", TYPE_COLOR["Credit"], "Credit cards"),
                        ("Debit", "#5b8fad", "Debit cards"), ("all", "#d62728", "All cards")]:
        y = cohort["mean_y1_value"] if t == "all" else cohort[f"mean_{t.lower()}"]
        ax.plot(cohort.open_year, y, "o-", color=col, lw=1.8, label=lab)
    for r in cohort.itertuples():
        ax.text(r.open_year, 8, f"n={r.cards}\n{r.pct_credit:.0%} cr", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(cohort.open_year)
    ax.set_ylim(0, cohort.mean_credit.max() * 1.3)
    ax.set_ylabel("First-year revenue per card ($)")
    ax.legend(fontsize=8, loc="upper left", ncol=3)
    ax.set_title("By year the card was opened")

    fig.suptitle("First-year revenue per card by card attributes (cards opened 2010–2018, customers with data)",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_card_y1_by_card_attributes.png", dpi=150)
    plt.close(fig)


def plot_geography(region: pd.DataFrame, states: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), gridspec_kw={"width_ratios": [1, 2.4]})
    for ax, t, key, title in [(axes[0], region, "region", "By census region"),
                              (axes[1], states, "state_abbr", "By state (states with 30+ cards)")]:
        x = np.arange(len(t))
        ax.bar(x, t.mean_y1_value, color="#5b8fad")
        ax.errorbar(x, t.mean_y1_value, yerr=[t.mean_y1_value - t.ci_low, t.ci_high - t.mean_y1_value],
                    fmt="none", ecolor="black", capsize=3, lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{k}\nn={n}" for k, n in zip(t[key], t.cards)], fontsize=8)
        ax.set_title(title)
        ax.set_ylabel("First-year revenue per card ($), 95% CI")
    fig.suptitle("First-year revenue per card by customer location", fontsize=12)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_card_y1_by_geography.png", dpi=150)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cards = pd.read_csv(V3 / "card_first_year_value.csv", parse_dates=["opened"])
    observed = set(pd.read_csv(V3 / "card_month.csv", usecols=["client_id"]).client_id)
    users = pd.read_csv(HANDOUT / "users_data.csv").rename(columns={"id": "client_id"})
    for col in ["per_capita_income", "yearly_income"]:
        users[col] = money(users[col])

    polys = load_state_polygons()
    users["state"], users["inside_outline"] = state_of(users.latitude.to_numpy(), users.longitude.to_numpy(), polys)
    users["state_abbr"] = users.state.map(STATE_ABBR)
    users["region"] = users.state.map(STATE_REGION).fillna("Other")

    c = cards[cards.client_id.isin(observed)].drop(columns=["yearly_income", "credit_score", "current_age", "total_debt"])
    c = c.merge(users[["client_id", "current_age", "latitude", "longitude", "per_capita_income", "yearly_income",
                       "num_credit_cards", "state", "state_abbr", "region", "inside_outline"]], on="client_id")
    c = add_buckets(c)

    home = in_person_home_state(set(c.client_id))
    cust = c.drop_duplicates("client_id").set_index("client_id")
    agree = cust.state_abbr.eq(home.reindex(cust.index))
    validation = {
        "customers": len(cust),
        "inside_an_outline": int(cust.inside_outline.sum()),
        "nearest_state_fallback": int((~cust.inside_outline).sum()),
        "with_in_person_home_state": int(home.reindex(cust.index).notna().sum()),
        "derived_state_matches_in_person_home_state": float(agree[home.reindex(cust.index).notna()].mean()),
    }

    dims = {
        "age_bucket": "Age when the card was opened",
        "per_capita_income_bucket": "Area per-capita income (quintiles)",
        "yearly_income_bucket": "Yearly income (quintiles)",
        "num_cards_bucket": "num_credit_cards (all cards held, Feb 2020)",
    }
    tables = {}
    for by in dims:
        t = profile(c, by)
        t["mix_adjusted_mean"] = t[by].map(mix_adjusted(c, by))
        t.to_csv(OUT / f"profile_{by}.csv", index=False)
        tables[by] = t
    region = profile(c, "region").sort_values("mean_y1_value", ascending=False)
    region["mix_adjusted_mean"] = region.region.map(mix_adjusted(c, "region"))
    states_all = profile(c, "state_abbr").sort_values("cards", ascending=False)
    states = states_all[states_all.cards >= 30].sort_values("mean_y1_value", ascending=False)
    region.to_csv(OUT / "profile_region.csv", index=False)
    states_all.to_csv(OUT / "profile_state.csv", index=False)

    card_tables = {
        "card_brand": profile(c, "card_brand"),
        "brand_type": profile(c, "brand_type").sort_values("mean_y1_value", ascending=False),
        "card_type_label": profile(c, "card_type_label"),
        "card_role_type": profile(c.assign(card_role_type=c.card_role + " | " + c.card_type_label.astype(str)),
                                  "card_role_type"),
        "credit_limit_bucket": profile(c[c.card_type.eq("Credit")], "credit_limit_bucket"),
        "debit_limit_bucket": profile(c[c.card_type.eq("Debit")], "debit_limit_bucket"),
        "open_year": profile(c, "open_year"),
    }
    for t in ["credit_limit_bucket", "debit_limit_bucket"]:
        tb = card_tables[t]
        tb["_lo"] = tb[t].str.extract(r"\$([\d,]+)k")[0].str.replace(",", "").astype(float)
        card_tables[t] = tb.sort_values("_lo").drop(columns="_lo")
    card_tables["open_year"]["mix_adjusted_mean"] = card_tables["open_year"].open_year.map(mix_adjusted(c, "open_year"))
    for name, tb in card_tables.items():
        tb.to_csv(OUT / f"profile_{name}.csv", index=False)
    role = card_tables["card_role_type"].copy()
    role[["card_role", "card_type_label"]] = role.card_role_type.str.split(" \\| ", expand=True)
    credit_c, debit_c = c[c.card_type.eq("Credit")], c[c.card_type.eq("Debit")]
    limit_corr = {
        "credit_limit_vs_y1_value": float(credit_c.credit_limit.rank().corr(credit_c.y1_value.rank())),
        "credit_limit_vs_yearly_income": float(credit_c.credit_limit.rank().corr(credit_c.yearly_income.rank())),
        "debit_limit_vs_y1_value": float(debit_c.credit_limit.rank().corr(debit_c.y1_value.rank())),
        "debit_limit_vs_yearly_income": float(debit_c.credit_limit.rank().corr(debit_c.yearly_income.rank())),
        "credit_cards_with_zero_limit": int(credit_c.credit_limit.eq(0).sum()),
        "prepaid_limit_median": float(c[c.card_type.eq("Debit (Prepaid)")].credit_limit.median()),
    }
    plot_card_attributes(card_tables["brand_type"], role, card_tables["credit_limit_bucket"], card_tables["open_year"])

    by_type = c.groupby("card_type").agg(cards=("card_id", "size"), customers=("client_id", "nunique"),
                                         mean_y1_value=("y1_value", "mean"), median=("y1_value", "median"))
    corr_rows = {}
    for t in ["Credit", "Debit"]:
        ct = c[c.card_type.eq(t)]
        corr_rows[t] = {a: float(ct[a].rank().corr(ct.y1_value.rank()))
                        for a in ["age_at_open", "per_capita_income", "yearly_income", "num_credit_cards"]}
    notes = {
        "cards": len(c),
        "customers": int(c.client_id.nunique()),
        "cards_in_source_file": len(cards),
        "cards_dropped_no_transaction_data": int((~cards.client_id.isin(observed)).sum()),
        "open_period": [str(c.opened.min().date()), str(c.opened.max().date())],
        "mean_y1_value_all_cards": float(c.y1_value.mean()),
        "by_card_type": by_type.round(2).reset_index().to_dict(orient="records"),
        "rank_correlation_with_y1_value_within_type": corr_rows,
        "state_validation": validation,
        "states_with_30plus_cards": int(len(states)),
        "states_represented": int(c.state.nunique()),
        "limit_checks": limit_corr,
    }
    (OUT / "card_profile_notes.json").write_text(json.dumps(notes, indent=2, default=str))
    c.to_csv(OUT / "card_first_year_profiled.csv", index=False)

    PLOTS.mkdir(exist_ok=True)
    plot_profiles(tables, dims)
    plot_geography(region, states)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    cols = ["cards", "customers", "mean_y1_value", "ci_low", "ci_high", "median_y1_value", "pct_credit",
            "mean_credit", "mean_debit", "mean_prepaid", "mix_adjusted_mean", "median_credit_limit_credit"]
    for by, t in {**tables, "region": region}.items():
        print(t[[by] + cols].round(2).to_string(index=False), "\n")
    print(states[["state_abbr", "cards", "customers", "mean_y1_value", "ci_low", "ci_high", "pct_credit",
                  "mean_credit", "mean_debit"]].round(2).to_string(index=False))
    card_cols = ["cards", "customers", "mean_y1_value", "ci_low", "ci_high", "median_y1_value", "mean_y1_interchange",
                 "mean_y1_amex_fee", "pct_credit", "mean_credit", "mean_debit", "mean_purchase_volume",
                 "mean_active_months", "pct_first_card"]
    for by, t in card_tables.items():
        extra = ["mix_adjusted_mean"] if "mix_adjusted_mean" in t else []
        print(t[[by] + card_cols + extra].round(2).to_string(index=False), "\n")
    print(json.dumps(notes, indent=2, default=str))


if __name__ == "__main__":
    main()
