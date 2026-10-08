"""Q1 Part 1: a descriptive profile of our customers.

Who they are (demographics and finances), what they hold (cards), how they behave (the latest
12 months of transactions, Nov 2018 - Oct 2019), how they came to us (signups and touches), how
these attributes relate, and data-driven personas. Descriptive only: no revenue.

Attributes cover all 2,000 customers; holdings are as of the Feb 2020 customer snapshot;
behaviour covers customers with at least one settled purchase in the window.

Run from repo root:  .venv/bin/python src/q1_part1_profile.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_customer_value import (HANDOUT, MCC_CATEGORY, OUT, PLOTS, STATE_NAMES, WINDOW, age_at, age_band,  # noqa: E402
                               brand_label, dollars, join_period, money, plain, prepare, products_label,
                               score_band)

SNAPSHOT_IDX = 2020 * 12 + 2
WINDOW_END = pd.Timestamp("2019-10-31")
METHODS = {"Online Transaction": "online", "Chip Transaction": "chip", "Swipe Transaction": "swipe"}
HOUR_BANDS = ([0, 6, 12, 18, 24], ["night (0–6)", "morning (6–12)", "afternoon (12–18)", "evening (18–24)"])
CREDENTIAL_ERRORS = "Bad PIN|Bad CVV|Bad Card Number|Bad Expiration|Bad Zipcode"
FIRST_CARD_AGE_BANDS = ([0, 18, 25, 30, 40, 50, 60, 200],
                        ["Under 18", "18–24", "25–29", "30–39", "40–49", "50–59", "60+"])
TENURE_BANDS = ([0, 5, 10, 15, 20, 100], ["Under 5 years", "5–9 years", "10–14 years", "15–19 years", "20+ years"])
CLUSTER_FEATURES = {
    # profile
    "current_age": "age", "log_yearly_income": "income (log)", "debt_to_income": "debt to income",
    "credit_score": "credit score", "tenure_years": "tenure",
    # holdings
    "cards_open": "cards open", "log_total_credit_limit": "credit limit (log)",
    "credit_share_of_spend": "credit share of spend",
    # behaviour
    "log_purchases": "purchases (log)", "log_avg_ticket": "average ticket (log)", "online_share": "online share",
    "log_distinct_merchants": "distinct merchants (log)", "in_person_out_of_state_share": "out-of-state share",
    "error_rate": "decline/error rate",
    "share_Grocery, wholesale and pharmacy": "grocery share", "share_Gas and auto": "gas & auto share",
    "share_Restaurants and bars": "restaurant share", "share_Money transfer": "money-transfer share",
    "share_Bills, utilities and professional services": "bills share",
}
PROFILE_FEATURES = ["current_age", "log_yearly_income", "debt_to_income", "credit_score", "tenure_years",
                    "cards_open", "log_total_credit_limit", "credit_share_of_spend"]
K_RANGE = range(2, 9)


# ---------- loading ----------

def load_window() -> pd.DataFrame:
    """Every transaction row in the window, including declines and refunds."""
    cols = ["date", "client_id", "card_id", "amount", "use_chip", "merchant_id", "merchant_state", "mcc", "errors"]
    parts = []
    for ch in pd.read_csv(HANDOUT / "transactions_data.csv", usecols=cols, chunksize=1_000_000,
                          dtype={"date": "string", "amount": "string", "use_chip": "string",
                                 "merchant_state": "string", "errors": "string"}):
        m = ch.date.str[:7]
        parts.append(ch[(m >= WINDOW[0]) & (m <= WINDOW[1])])
    w = pd.concat(parts, ignore_index=True)
    w["amt"] = money(w.pop("amount"))
    w["ts"] = pd.to_datetime(w.pop("date"), format="%Y-%m-%d %H:%M:%S")
    return w


def load_touches() -> pd.DataFrame:
    cols = ["client_id", "touch_ts", "channel", "device"]
    parts = [ch[ch.client_id.notna()] for ch in pd.read_csv(HANDOUT / "marketing_touchpoints.csv", usecols=cols,
                                                            parse_dates=["touch_ts"], chunksize=300_000)]
    t = pd.concat(parts, ignore_index=True)
    t["client_id"] = t.client_id.astype(int)
    return t


# ---------- features ----------

def describe(x: pd.Series) -> dict:
    x = x.dropna()
    q = x.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    return {"n": int(len(x)), "mean": float(x.mean()), "p10": float(q[0.1]), "p25": float(q[0.25]),
            "median": float(q[0.5]), "p75": float(q[0.75]), "p90": float(q[0.9]),
            "min": float(x.min()), "max": float(x.max())}


def attributes(c: pd.DataFrame, users: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    """Demographics, finances, tenure and holdings for every customer (holdings at Feb 2020)."""
    u = users.set_index("id").reindex(c.index)
    a = pd.DataFrame(index=c.index)
    a["current_age"] = c.current_age
    a["age_at_first_card"] = age_at(c.first_card_month, c.birth_year, c.birth_month)
    a["years_to_retirement"] = u.retirement_age - c.current_age
    a["birth_decade"] = (c.birth_year // 10 * 10).astype(int).astype(str) + "s"
    a["gender"] = c.gender
    a["state"], a["region"] = c.state, c.region
    a["per_capita_income"], a["yearly_income"] = c.per_capita_income, c.yearly_income
    a["income_to_area_income"] = (c.yearly_income / c.per_capita_income).where(c.per_capita_income > 0)
    a["total_debt"] = c.total_debt
    a["debt_to_income"] = c.total_debt / c.yearly_income
    a["credit_score"] = c.credit_score
    a["num_credit_cards_field"] = c.num_credit_cards
    a["first_card_year"] = (c.first_card_month - 1) // 12
    a["tenure_years"] = (SNAPSHOT_IDX - c.first_card_month) / 12
    a["join_period"] = join_period(c.first_card_month)

    cards = cards.assign(open_now=(cards.open_idx <= SNAPSHOT_IDX) & (cards.expires_idx >= SNAPSHOT_IDX),
                         card_age_years=(SNAPSHOT_IDX - cards.open_idx) / 12,
                         years_since_pin_change=2020 - cards.year_pin_last_changed,
                         chip=cards.has_chip.eq("YES"), dark_web=cards.card_on_dark_web.eq("Yes"))
    now = cards[cards.open_now]
    g_all, g_now = cards.groupby("client_id"), now.groupby("client_id")
    a["cards_ever"] = g_all.size().reindex(a.index, fill_value=0)
    a["cards_open"] = g_now.size().reindex(a.index, fill_value=0)
    a["cards_expired"] = a.cards_ever - a.cards_open - cards[cards.open_idx > SNAPSHOT_IDX].groupby(
        "client_id").size().reindex(a.index, fill_value=0)
    for t, name in [("Credit", "credit"), ("Debit", "debit"), ("Debit (Prepaid)", "prepaid")]:
        a[f"{name}_cards_open"] = now[now.card_type == t].groupby("client_id").size().reindex(a.index, fill_value=0)
    types = g_now.card_type.agg(set).reindex(a.index)
    a["products_held"] = types.apply(lambda v: products_label(v if isinstance(v, set) else set())).str.replace(
        "No open card in window", "No open card")
    brands = g_now.card_brand.agg(set).reindex(a.index)
    a["brands_held"] = brands.apply(lambda v: brand_label(v if isinstance(v, set) else set())).str.replace(
        "No open card in window", "No open card")
    credit_now = now[now.card_type == "Credit"].groupby("client_id").credit_limit
    a["total_credit_limit"] = credit_now.sum().reindex(a.index)
    a["max_credit_limit"] = credit_now.max().reindex(a.index)
    a["credit_limit_to_income"] = a.total_credit_limit / a.yearly_income
    a["avg_card_age_years"] = g_now.card_age_years.mean().reindex(a.index)
    a["chip_share_of_cards"] = g_now.chip.mean().reindex(a.index)
    a["avg_cards_issued"] = g_now.num_cards_issued.mean().reindex(a.index)
    a["avg_years_since_pin_change"] = g_now.years_since_pin_change.mean().reindex(a.index)
    a["any_card_on_dark_web"] = g_all.dark_web.any().reindex(a.index, fill_value=False)
    a["has_transactions"] = c.ever_transacted
    a["active_in_window"] = c.active
    return a


def behaviour_features(w: pd.DataFrame, home_state: pd.Series, card_type: pd.Series,
                       total_credit_limit: pd.Series, cards_held: pd.Series,
                       end: pd.Timestamp = WINDOW_END) -> pd.DataFrame:
    """Per customer with at least one settled purchase (amount > 0, no error) in the window."""
    ok = w.errors.isna()
    p = w[ok & (w.amt > 0)].copy()
    p["day"] = p.ts.dt.normalize()
    g = p.groupby("client_id")
    f = pd.DataFrame({"purchases": g.size(), "spend": g.amt.sum(), "median_ticket": g.amt.median()})
    f["avg_ticket"] = f.spend / f.purchases
    f["active_months"] = (p.ts.dt.year * 12 + p.ts.dt.month).groupby(p.client_id).nunique()

    d = p[["client_id", "day"]].drop_duplicates().sort_values(["client_id", "day"])
    d["gap"] = d.groupby("client_id").day.diff().dt.days
    f["active_days"] = d.groupby("client_id").size()
    f["median_days_between_purchase_days"] = d.groupby("client_id").gap.median()
    f["recency_days"] = (end - g.day.max()).dt.days

    for method, name in METHODS.items():
        f[f"{name}_share"] = p.amt.where(p.use_chip.eq(method), 0.0).groupby(p.client_id).sum() / f.spend

    shares = p.assign(cat=p.mcc.astype(str).map(MCC_CATEGORY)).pivot_table(
        index="client_id", columns="cat", values="amt", aggfunc="sum", fill_value=0.0).div(f.spend, axis=0)
    f = f.join(shares.add_prefix("share_"))
    f["main_category"] = shares.idxmax(axis=1)

    ms = p.groupby(["client_id", "merchant_id"]).amt.sum()
    f["distinct_merchants"] = ms.groupby(level=0).size()
    f["top_merchant_share"] = ms.groupby(level=0).max() / f.spend
    f["top5_merchant_share"] = ms.sort_values(ascending=False).groupby(level=0).head(5).groupby(level=0).sum() / f.spend

    inp = p[~p.use_chip.eq("Online Transaction")]
    name = inp.merchant_state.map(STATE_NAMES)
    home = inp.client_id.map(home_state)
    away = name.notna() & home.notna() & (name != home)
    abroad = inp.merchant_state.notna() & name.isna()
    inp_spend = inp.groupby("client_id").amt.sum()
    f["in_person_out_of_state_share"] = inp.amt.where(away, 0.0).groupby(inp.client_id).sum() / inp_spend
    f["in_person_abroad_share"] = inp.amt.where(abroad, 0.0).groupby(inp.client_id).sum() / inp_spend
    f["merchant_states"] = inp[name.notna()].groupby("client_id").merchant_state.nunique()

    f["weekend_share"] = p.ts.dt.dayofweek.ge(5).groupby(p.client_id).mean()
    bands = pd.cut(p.ts.dt.hour, HOUR_BANDS[0], right=False, labels=HOUR_BANDS[1])
    f = f.join(pd.crosstab(p.client_id, bands, normalize="index").add_prefix("hour_"))
    f["nov_dec_share"] = p.amt.where(p.ts.dt.month.isin([11, 12]), 0.0).groupby(p.client_id).sum() / f.spend

    err = w.errors.notna()
    f["attempts"] = w.groupby("client_id").size()
    f["error_rate"] = err.groupby(w.client_id).mean()
    f["insufficient_balance_rate"] = w.errors.str.contains("Insufficient Balance", na=False).groupby(w.client_id).mean()
    f["credential_error_rate"] = w.errors.str.contains(CREDENTIAL_ERRORS, na=False).groupby(w.client_id).mean()
    f["technical_glitch_rate"] = w.errors.str.contains("Technical Glitch", na=False).groupby(w.client_id).mean()
    f["refund_share"] = -w.amt.where(ok & (w.amt < 0), 0.0).groupby(w.client_id).sum() / f.spend

    is_credit = p.card_id.map(card_type).eq("Credit")
    credit_spend = p.amt.where(is_credit, 0.0).groupby(p.client_id).sum()
    f["credit_share_of_spend"] = credit_spend / f.spend
    lim = total_credit_limit.reindex(f.index)
    f["monthly_credit_spend_to_limit"] = (credit_spend.reindex(f.index) / 12 / lim).where(lim > 0)
    cs = p.groupby(["client_id", "card_id"]).amt.sum()
    f["cards_used"] = cs.groupby(level=0).size()
    f["share_of_held_cards_used"] = f.cards_used / cards_held.reindex(f.index)
    f["top_card_share"] = cs.groupby(level=0).max() / f.spend
    return f.reindex(f.index[f.purchases > 0])


def acquisition(c: pd.DataFrame, signups: pd.DataFrame, touches: pd.DataFrame) -> pd.DataFrame:
    """For customers with a signup record: their first signup and the touches before it."""
    has = c.first_signup_ts.notna()
    q = c.loc[has, ["first_signup_ts", "first_signup_kind", "self_reported_source", "signup_landing_page",
                    "channel_last_touch", "channel_first_touch"]].copy()
    q["signup_year"] = q.first_signup_ts.dt.year
    q["signups"] = signups.groupby("client_id").size().reindex(q.index)
    t = touches[touches.client_id.isin(q.index)]
    t = t[t.touch_ts <= t.client_id.map(q.first_signup_ts)].sort_values(["client_id", "touch_ts"])
    g = t.groupby("client_id")
    q["journey_touches"] = g.size().reindex(q.index, fill_value=0)
    q["journey_channels"] = g.channel.nunique().reindex(q.index, fill_value=0)
    q["journey_days"] = (q.first_signup_ts - g.touch_ts.min().reindex(q.index)).dt.total_seconds() / 86400
    q["device_last_touch"] = g.device.last().reindex(q.index)
    q["device_first_touch"] = g.device.first().reindex(q.index)
    return q


# ---------- tables ----------

def distribution(s: pd.Series, name: str, order: list | None = None) -> pd.DataFrame:
    counts = s.fillna("Missing").value_counts()
    if order:
        counts = counts.reindex([o for o in order if o in counts.index] + [k for k in counts.index if k not in order])
    return pd.DataFrame({"attribute": name, "group": counts.index.astype(str), "customers": counts.to_numpy(),
                         "share": (counts / counts.sum()).to_numpy()})


def crosstab(rows: pd.Series, cols: pd.Series, name: str) -> pd.DataFrame:
    t = pd.crosstab(rows, cols, normalize="index")
    t.insert(0, "customers", rows.value_counts().reindex(t.index))
    return t.reset_index().rename(columns={t.index.name or "row_0": "group"}).assign(table=name)


# ---------- personas ----------

def cluster_matrix(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    x["current_age"] = df.current_age
    x["log_yearly_income"] = np.log(df.yearly_income.clip(lower=1))
    x["debt_to_income"] = df.debt_to_income.clip(upper=df.debt_to_income.quantile(0.99))
    x["credit_score"] = df.credit_score
    x["tenure_years"] = df.tenure_years
    x["cards_open"] = df.cards_open
    x["log_total_credit_limit"] = np.log1p(df.total_credit_limit.fillna(0))
    x["credit_share_of_spend"] = df.credit_share_of_spend
    x["log_purchases"] = np.log(df.purchases)
    x["log_avg_ticket"] = np.log(df.avg_ticket)
    x["online_share"] = df.online_share
    x["log_distinct_merchants"] = np.log(df.distinct_merchants)
    x["in_person_out_of_state_share"] = df.in_person_out_of_state_share.fillna(0)
    x["error_rate"] = df.error_rate
    for k in [k for k in CLUSTER_FEATURES if k.startswith("share_")]:
        x[k] = df.get(k, 0.0)
    return x[list(CLUSTER_FEATURES)].fillna(0.0)


def choose_k(z: np.ndarray, seeds: int = 20) -> pd.DataFrame:
    """Fit k-means for each k; score by silhouette and by stability (adjusted Rand index between
    the full-data solution and solutions fitted on bootstrap resamples)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    rng = np.random.default_rng(0)
    rows = []
    for k in K_RANGE:
        ref = KMeans(k, n_init=20, random_state=0).fit(z)
        aris = []
        for s in range(seeds):
            idx = rng.integers(0, len(z), len(z))
            m = KMeans(k, n_init=10, random_state=s + 1).fit(z[idx])
            aris.append(adjusted_rand_score(ref.labels_, m.predict(z)))
        sizes = np.bincount(ref.labels_)
        rows.append({"k": k, "silhouette": float(silhouette_score(z, ref.labels_)),
                     "stability_ari": float(np.mean(aris)), "smallest_cluster": int(sizes.min()),
                     "inertia": float(ref.inertia_)})
    return pd.DataFrame(rows)


def pick_k(scores: pd.DataFrame, min_stability: float = 0.8, min_size: int = 50) -> int:
    """The most detailed solution that stays stable across resamples and has no tiny cluster.
    Silhouettes are low for every k here (no crisp natural clusters), so separation alone
    doesn't discriminate between solutions; stability does."""
    ok = scores[(scores.stability_ari >= min_stability) & (scores.smallest_cluster >= min_size)]
    pool = ok if len(ok) else scores
    return int(pool.k.max() if len(ok) else pool.sort_values("stability_ari", ascending=False).k.iloc[0])


def describe_cluster(zmeans: pd.Series, n: int = 4) -> str:
    top = zmeans.reindex(zmeans.abs().sort_values(ascending=False).index).head(n)
    return "; ".join(f"{'high' if v > 0 else 'low'} {CLUSTER_FEATURES[k]} ({v:+.1f} sd)" for k, v in top.items())


# ---------- plots ----------

def plots(df: pd.DataFrame, beh: pd.DataFrame, acq: pd.DataFrame, corr: pd.DataFrame, zprof: pd.DataFrame,
          cat_mix: pd.Series, monthly: pd.Series, hourly: pd.Series) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PLOTS.mkdir(exist_ok=True)

    # 1. where customers live
    fig, ax = plt.subplots(figsize=(10, 5.5))
    lower = df[(df.longitude > -130) & (df.latitude < 50)]
    fifth = pd.qcut(df.yearly_income, 5, labels=["bottom", "2nd", "3rd", "4th", "top"]).reindex(lower.index)
    for f, col in zip(["bottom", "2nd", "3rd", "4th", "top"], plt.cm.viridis(np.linspace(0, 1, 5))):
        s = lower[fifth == f]
        ax.scatter(s.longitude, s.latitude, s=6, color=col, label=f"{f} income fifth", alpha=0.7)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title(f"Where customers live (lower 48 states; {len(df) - len(lower)} in Alaska/Hawaii not shown)")
    ax.legend(fontsize=8, markerscale=2, loc="lower left")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_map.png", dpi=150)
    plt.close(fig)

    # 2. demographics
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    axes[0, 0].hist(df.current_age, bins=range(15, 105, 5), color="tab:blue", alpha=0.7, label="age today")
    axes[0, 0].hist(df.age_at_first_card, bins=range(15, 105, 5), color="tab:orange", alpha=0.6, label="age at first card")
    axes[0, 0].set_title("Age")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].hist(df.yearly_income / 1000, bins=np.arange(0, 160, 5), color="tab:blue")
    axes[0, 1].set_title(f"Yearly income, thousands ({(df.yearly_income > 155000).sum()} above 155k not shown)")
    axes[1, 0].hist(df.credit_score, bins=range(480, 860, 10), color="tab:blue")
    axes[1, 0].set_title("Credit score")
    axes[1, 1].hist(df.debt_to_income.clip(upper=5), bins=np.arange(0, 5.1, 0.1), color="tab:blue")
    axes[1, 1].set_title("Total debt / yearly income (capped at 5)")
    fig.suptitle("Who our customers are (all 2,000; Feb 2020 snapshot)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_demographics.png", dpi=150)
    plt.close(fig)

    # 3. holdings and tenure
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    pm = df.products_held.value_counts().sort_values()
    axes[0, 0].barh(pm.index, pm.to_numpy(), color="tab:blue")
    axes[0, 0].set_title("Products held (cards open, Feb 2020)")
    co = df.cards_open.value_counts().sort_index()
    axes[0, 1].bar(co.index.astype(str), co.to_numpy(), color="tab:blue")
    axes[0, 1].set_title("Cards open per customer")
    yr = pd.crosstab(df.first_card_year, df.has_transactions)
    axes[1, 0].bar(yr.index, yr.get(True, 0), color="tab:blue", label="has transactions")
    axes[1, 0].bar(yr.index, yr.get(False, 0), bottom=yr.get(True, 0), color="lightgrey", label="no transactions")
    axes[1, 0].set_title("Customers by year of first card")
    axes[1, 0].legend(fontsize=8)
    lim = df.max_credit_limit.dropna()
    axes[1, 1].hist(lim.clip(upper=50000) / 1000, bins=np.arange(0, 51, 2), color="tab:blue")
    axes[1, 1].set_title("Highest credit limit held ($k, capped at 50)")
    fig.suptitle("What they hold")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_holdings.png", dpi=150)
    plt.close(fig)

    # 4. behaviour
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes[0, 0].hist(beh.purchases, bins=40, color="tab:blue")
    axes[0, 0].set_title("Purchases in 12 months")
    axes[0, 1].hist(beh.spend / 1000, bins=40, color="tab:blue")
    axes[0, 1].set_title("Spend in 12 months ($k)")
    axes[0, 2].hist(beh.avg_ticket.clip(upper=200), bins=40, color="tab:blue")
    axes[0, 2].set_title("Average purchase ($, capped at 200)")
    cm = cat_mix.sort_values()
    axes[1, 0].barh(cm.index, cm.to_numpy() * 100, color="tab:blue")
    axes[1, 0].set_title("Share of all purchase dollars by category (%)")
    axes[1, 1].plot(monthly.index, monthly.to_numpy() / 1e6, marker="o")
    axes[1, 1].set_title("Purchase dollars by month ($M)")
    axes[1, 1].tick_params(axis="x", rotation=45)
    axes[1, 2].bar(hourly.index, hourly.to_numpy() * 100, color="tab:blue")
    axes[1, 2].set_title("Share of purchases by hour of day (%)")
    fig.suptitle(f"How they behave ({len(beh):,} customers with purchases, Nov 2018 – Oct 2019)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_behaviour.png", dpi=150)
    plt.close(fig)

    # 5. correlations
    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(corr)), corr.index, fontsize=7)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.iat[i, j]
            if abs(v) >= 0.3 and i != j:
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=5)
    fig.colorbar(im, ax=ax, shrink=0.7, label="Spearman correlation")
    ax.set_title("How attributes move together (customers with purchases)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_correlations.png", dpi=150)
    plt.close(fig)

    # 6. personas
    fig, ax = plt.subplots(figsize=(11, 0.6 * len(zprof) + 3))
    im = ax.imshow(zprof.to_numpy(), cmap="RdBu_r", vmin=-1.5, vmax=1.5, aspect="auto")
    ax.set_xticks(range(zprof.shape[1]), [CLUSTER_FEATURES[k] for k in zprof.columns], rotation=60, ha="right",
                  fontsize=8)
    ax.set_yticks(range(len(zprof)), zprof.index, fontsize=9)
    for i in range(zprof.shape[0]):
        for j in range(zprof.shape[1]):
            ax.text(j, i, f"{zprof.iat[i, j]:+.1f}", ha="center", va="center", fontsize=6)
    fig.colorbar(im, ax=ax, shrink=0.8, label="cluster mean, standard deviations from all customers")
    ax.set_title("Personas: how each cluster differs from the average customer")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_personas.png", dpi=150)
    plt.close(fig)

    # 7. acquisition
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    for ax, col, title in [(axes[0, 0], "self_reported_source", "Self-reported source"),
                           (axes[0, 1], "signup_landing_page", "Landing page"),
                           (axes[1, 0], "channel_last_touch", "Last-touch channel"),
                           (axes[1, 1], "device_last_touch", "Last-touch device")]:
        v = acq[col].fillna("No linked touches").value_counts().sort_values()
        ax.barh(v.index, v.to_numpy(), color="tab:blue")
        ax.set_title(title)
    fig.suptitle(f"How they came to us (first signup of the {len(acq):,} customers with a signup record)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_p1_acquisition.png", dpi=150)
    plt.close(fig)


# ---------- main ----------

def main() -> dict:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    OUT.mkdir(parents=True, exist_ok=True)
    p = prepare()
    c, users, cards = p["c"], p["users"], p["cards"]
    attrs = attributes(c, users, cards)
    w = load_window()
    beh = behaviour_features(w, c.state, cards.set_index("id").card_type, c.total_credit_limit, c.cards_held)
    signups = pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"])
    acq = acquisition(c, signups, load_touches())
    df = attrs.join(beh).join(c[["latitude", "longitude"]])

    # A. base and coverage
    base = {
        "customers": len(df),
        "join_period": df.join_period.value_counts().to_dict(),
        "has_transactions": int(df.has_transactions.sum()),
        "active_in_window": int(df.active_in_window.sum()),
        "tenure_years": describe(df.tenure_years),
        "first_card_year": describe(df.first_card_year),
    }
    bands = pd.DataFrame({
        "age band": age_band(df.current_age),
        "age at first card": pd.cut(df.age_at_first_card, FIRST_CARD_AGE_BANDS[0], right=False,
                                    labels=FIRST_CARD_AGE_BANDS[1]).astype(str),
        "join period": df.join_period,
        "tenure": pd.cut(df.tenure_years, TENURE_BANDS[0], right=False, labels=TENURE_BANDS[1]).astype(str),
        "region": df.region.fillna("Unresolved"),
        "income fifth": pd.qcut(df.yearly_income, 5, labels=["Bottom", "2nd", "3rd", "4th", "Top"]).astype(str),
        "credit score": score_band(df.credit_score),
        "products held": df.products_held,
        "gender": df.gender,
    }, index=df.index)
    coverage = pd.concat([
        df.groupby(bands[col]).agg(customers=("has_transactions", "size"), has_transactions=("has_transactions", "mean"),
                                   active_in_window=("active_in_window", "mean")).reset_index().rename(
            columns={col: "group"}).assign(attribute=col) for col in bands.columns], ignore_index=True)

    # B/C. attribute distributions and summary statistics
    numeric_attrs = ["current_age", "age_at_first_card", "years_to_retirement", "tenure_years", "per_capita_income",
                     "yearly_income", "income_to_area_income", "total_debt", "debt_to_income", "credit_score",
                     "num_credit_cards_field", "cards_ever", "cards_open", "cards_expired", "credit_cards_open",
                     "debit_cards_open", "prepaid_cards_open", "total_credit_limit", "max_credit_limit",
                     "credit_limit_to_income", "avg_card_age_years", "chip_share_of_cards", "avg_cards_issued",
                     "avg_years_since_pin_change"]
    attr_stats = pd.DataFrame({k: describe(df[k]) for k in numeric_attrs}).T
    dists = pd.concat([distribution(bands[col], col) for col in bands.columns]
                      + [distribution(df.birth_decade, "birth decade"),
                         distribution(df.state, "state"),
                         distribution(df.brands_held, "brands held"),
                         distribution(df.cards_open.clip(upper=6).astype(str).replace("6", "6+"), "cards open"),
                         distribution(pd.Series(np.where(df.any_card_on_dark_web, "Yes", "No"), index=df.index),
                                      "any card flagged on dark web")], ignore_index=True)
    card_level = cards.assign(open_now=(cards.open_idx <= SNAPSHOT_IDX) & (cards.expires_idx >= SNAPSHOT_IDX))
    card_tables = {
        "type_by_brand": pd.crosstab(card_level.card_type, card_level.card_brand, margins=True).to_dict(),
        "status": {"open_feb_2020": int(card_level.open_now.sum()),
                   "expired": int((card_level.expires_idx < SNAPSHOT_IDX).sum()),
                   "opened_after_snapshot": int((card_level.open_idx > SNAPSHOT_IDX).sum())},
        "credit_limit_by_type": {t: describe(g.credit_limit) for t, g in card_level.groupby("card_type")},
        "chip_share": float(card_level.has_chip.eq("YES").mean()),
        "dark_web_share": float(card_level.card_on_dark_web.eq("Yes").mean()),
        "num_cards_issued": card_level.num_cards_issued.value_counts().sort_index().to_dict(),
        "cards_opened_by_year": ((card_level.open_idx - 1) // 12).value_counts().sort_index().to_dict(),
    }

    # D. behaviour
    act = df[df.purchases.notna()]
    beh_numeric = [k for k in beh.columns if k != "main_category"]
    beh_stats = pd.DataFrame({k: describe(act[k]) for k in beh_numeric}).T
    ok_p = w[w.errors.isna() & (w.amt > 0)]
    cat_mix = ok_p.groupby(ok_p.mcc.astype(str).map(MCC_CATEGORY)).amt.sum() / ok_p.amt.sum()
    method_mix = ok_p.groupby("use_chip").amt.sum() / ok_p.amt.sum()
    method_count_mix = ok_p.use_chip.value_counts(normalize=True)
    monthly = ok_p.groupby(ok_p.ts.dt.strftime("%Y-%m")).amt.sum()
    hourly = ok_p.ts.dt.hour.value_counts(normalize=True).sort_index()
    weekday = ok_p.ts.dt.day_name().value_counts(normalize=True)
    errors_mix = w.errors.dropna().str.split(",").explode().value_counts()
    beh_dists = pd.concat([
        distribution(act.main_category, "main spend category"),
        distribution(pd.cut(act.active_months, [0, 3, 6, 9, 11, 12], labels=["1–3", "4–6", "7–9", "10–11", "12"]
                            ).astype(str), "active months"),
        distribution(pd.cut(act.error_rate, [-0.001, 0, 0.01, 0.02, 0.05, 1], labels=[
            "none", "under 1%", "1–2%", "2–5%", "5%+"]).astype(str), "decline/error rate"),
        distribution(pd.cut(act.in_person_out_of_state_share.fillna(0), [-0.001, 0, 0.05, 0.2, 0.5, 1], labels=[
            "none", "under 5%", "5–20%", "20–50%", "50%+"]).astype(str), "in-person spend out of home state"),
        distribution(pd.Series(np.where(act.in_person_abroad_share > 0, "Yes", "No"), index=act.index),
                     "any in-person spend abroad"),
        distribution(pd.Series(np.where(act.insufficient_balance_rate > 0, "Yes", "No"), index=act.index),
                     "any insufficient-balance decline"),
    ], ignore_index=True)
    overall = {
        "purchase_rows": int(len(ok_p)), "purchase_dollars": float(ok_p.amt.sum()),
        "refund_dollars": float(-w.amt.where(w.errors.isna() & (w.amt < 0), 0).sum()),
        "attempts": int(len(w)), "error_rows": int(w.errors.notna().sum()),
        "category_dollar_mix": cat_mix.sort_values(ascending=False).round(4).to_dict(),
        "method_dollar_mix": method_mix.round(4).to_dict(), "method_count_mix": method_count_mix.round(4).to_dict(),
        "monthly_purchase_dollars": monthly.round(0).to_dict(), "weekday_count_mix": weekday.round(4).to_dict(),
        "error_types": errors_mix.to_dict(),
        "abroad_dollars_share_of_in_person": float(
            ok_p.amt.where(ok_p.merchant_state.notna() & ok_p.merchant_state.map(STATE_NAMES).isna(), 0).sum()
            / ok_p.amt.where(~ok_p.use_chip.eq("Online Transaction"), 0).sum()),
        "top_abroad_countries": ok_p[ok_p.merchant_state.notna() & ok_p.merchant_state.map(STATE_NAMES).isna()
                                     ].merchant_state.value_counts().head(8).to_dict(),
    }

    # E. acquisition
    acq_dists = pd.concat([distribution(acq[col], col) for col in [
        "self_reported_source", "signup_landing_page", "channel_last_touch", "channel_first_touch",
        "device_last_touch", "signup_year", "first_signup_kind"]]
        + [distribution(acq.signups.clip(upper=4).astype(int).astype(str).replace("4", "4+"), "signups per customer")],
        ignore_index=True)
    acq_stats = pd.DataFrame({k: describe(acq[k]) for k in ["journey_touches", "journey_channels", "journey_days"]}).T
    acq_x = acq.join(bands[["age band", "income fifth"]]).join(df[["products_held"]])

    # F. relationships
    corr_cols = ["current_age", "age_at_first_card", "tenure_years", "yearly_income", "per_capita_income",
                 "total_debt", "debt_to_income", "credit_score", "cards_open", "credit_cards_open", "total_credit_limit",
                 "max_credit_limit", "purchases", "spend", "avg_ticket", "active_days", "distinct_merchants",
                 "online_share", "in_person_out_of_state_share", "weekend_share", "error_rate",
                 "insufficient_balance_rate", "refund_share", "credit_share_of_spend", "monthly_credit_spend_to_limit",
                 "share_Grocery, wholesale and pharmacy", "share_Money transfer", "share_Gas and auto"]
    corr = act[corr_cols].corr(method="spearman")
    pairs = corr.where(np.triu(np.ones(corr.shape, bool), 1)).stack().rename("rho").reset_index()
    pairs = pairs.reindex(pairs.rho.abs().sort_values(ascending=False).index)
    crosstabs = pd.concat([
        crosstab(bands["income fifth"], df.products_held, "income fifth x products held"),
        crosstab(bands["income fifth"], pd.cut(df.max_credit_limit, [0, 5000, 10000, 15000, 25000, 1e9], right=False,
                                               labels=["under $5k", "$5–10k", "$10–15k", "$15–25k", "$25k+"]
                                               ).cat.add_categories("no credit card").fillna("no credit card"),
                 "income fifth x highest credit limit"),
        crosstab(bands["age band"], df.products_held, "age band x products held"),
        crosstab(bands["region"], bands["income fifth"], "region x income fifth"),
        crosstab(bands["tenure"], df.cards_open.clip(upper=5).astype(str).replace("5", "5+"), "tenure x cards open"),
        crosstab(bands["credit score"], df.products_held, "credit score x products held"),
        crosstab(acq_x.self_reported_source, acq_x["age band"], "source x age band"),
        crosstab(acq_x.self_reported_source, acq_x["income fifth"], "source x income fifth"),
        crosstab(acq_x.channel_last_touch.fillna("No linked touches"), acq_x.first_signup_kind,
                 "last-touch channel x new or existing customer"),
    ], ignore_index=True)

    # G. personas (customers with purchases)
    x = cluster_matrix(act)
    z = StandardScaler().fit_transform(x)
    k_scores = choose_k(z)
    k = pick_k(k_scores)
    behaviour_only = [f for f in CLUSTER_FEATURES if f not in PROFILE_FEATURES]
    k_scores_behaviour = choose_k(StandardScaler().fit_transform(x[behaviour_only]))
    labels = KMeans(k, n_init=50, random_state=0).fit_predict(z)
    zdf = pd.DataFrame(z, index=x.index, columns=x.columns)
    order = pd.Series(labels, index=x.index).value_counts().index
    names = {old: f"P{i + 1}" for i, old in enumerate(order)}
    persona = pd.Series(labels, index=x.index).map(names)
    zprof = zdf.groupby(persona).mean()
    zprof.index = [f"{i} (n={int((persona == i).sum())})" for i in zprof.index]
    profile_cols = ["current_age", "age_at_first_card", "tenure_years", "yearly_income", "total_debt", "debt_to_income",
                    "credit_score", "cards_open", "total_credit_limit", "purchases", "spend", "avg_ticket",
                    "active_days", "distinct_merchants", "online_share", "in_person_out_of_state_share",
                    "error_rate", "insufficient_balance_rate", "credit_share_of_spend",
                    "share_Grocery, wholesale and pharmacy", "share_Gas and auto", "share_Restaurants and bars",
                    "share_Money transfer", "share_Bills, utilities and professional services"]
    pa = act.assign(persona=persona)
    persona_profile = pa.groupby("persona")[profile_cols].median().T
    persona_profile.loc["customers"] = pa.persona.value_counts()
    persona_mix = pd.concat([
        crosstab(pa.persona, pa.products_held, "persona x products held"),
        crosstab(pa.persona, bands.loc[pa.index, "income fifth"], "persona x income fifth"),
        crosstab(pa.persona, bands.loc[pa.index, "age band"], "persona x age band"),
        crosstab(pa.persona, bands.loc[pa.index, "region"], "persona x region"),
        crosstab(pa.persona, pa.gender, "persona x gender"),
        crosstab(pa.persona, pa.main_category, "persona x main spend category"),
    ], ignore_index=True)
    persona_desc = {f"P{i + 1}": describe_cluster(zdf[persona == f"P{i + 1}"].mean()) for i in range(k)}

    # write
    df.assign(persona=persona).to_csv(OUT / "part1_customers.csv")
    coverage.to_csv(OUT / "part1_coverage.csv", index=False)
    attr_stats.to_csv(OUT / "part1_attribute_stats.csv")
    dists.to_csv(OUT / "part1_attribute_distributions.csv", index=False)
    beh_stats.to_csv(OUT / "part1_behaviour_stats.csv")
    beh_dists.to_csv(OUT / "part1_behaviour_distributions.csv", index=False)
    acq_dists.to_csv(OUT / "part1_acquisition_distributions.csv", index=False)
    acq_stats.to_csv(OUT / "part1_acquisition_journey_stats.csv")
    corr.to_csv(OUT / "part1_correlations.csv")
    pairs.head(40).to_csv(OUT / "part1_strongest_correlations.csv", index=False)
    crosstabs.to_csv(OUT / "part1_crosstabs.csv", index=False)
    k_scores.to_csv(OUT / "part1_persona_k_selection.csv", index=False)
    k_scores_behaviour.to_csv(OUT / "part1_persona_k_selection_behaviour_only.csv", index=False)
    persona_profile.to_csv(OUT / "part1_persona_profiles.csv")
    zprof.to_csv(OUT / "part1_persona_zscores.csv")
    persona_mix.to_csv(OUT / "part1_persona_mix.csv", index=False)
    summary = {"base": base, "cards": card_tables, "behaviour_overall": overall, "personas": {
        "k": k, "features": list(CLUSTER_FEATURES), "description": persona_desc,
        "sizes": pa.persona.value_counts().sort_index().to_dict()}}
    (OUT / "part1_summary.json").write_text(json.dumps(plain(summary), indent=2, default=str))
    plots(df, act, acq, corr, zprof, cat_mix, monthly, hourly)
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, default=str))
