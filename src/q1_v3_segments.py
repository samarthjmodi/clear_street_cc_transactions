"""Q1 v3: four acquisition segments, valued on customers with transaction data.

Segments (product held and credit limit, known on day one / before the window):
  Premium credit  a credit card with limit >= $10k
  Core credit     credit card(s), highest limit < $10k
  Debit           debit card, no credit card
  Prepaid         prepaid only

The cut and the highest-limit rule match Q1 Part 2 and Q2. New-customer values price
prepaid at the debit rate, as Q1 Part 2 does.

Customers with no transactions anywhere in 2010-2019 are "no transaction data":
excluded from value averages and reported separately, plus a missing-as-$0 variant
for the new-customer cohort.

Run from repo root after build_card_month.py, build_q1_v2_customer_metrics.py and
q1_v3_cohorts.py:
  .venv/bin/python src/q1_v3_segments.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_revenue import WINDOW_END_MONTH, interchange, load_cards, money, month_index  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V2 = HANDOUT / "analysis" / "q1_scratch" / "v2"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
PLOTS = V3 / "plots"
WINDOW_START_M = 2018 * 12 + 11
FIRST_M = 2010 * 12 + 1
LIMIT_CUT = 10_000
VALUE = "value_prepaid_debit"
SEGMENTS = ["Premium credit", "Core credit", "Debit", "Prepaid"]
COLORS = {"Premium credit": "#1f4e79", "Core credit": "#5b8fad", "Debit": "#9fbfd6", "Prepaid": "#c9ccd1"}
RNG = np.random.default_rng(11)


def segment_of(has_credit: pd.Series, credit_limit: pd.Series, has_debit: pd.Series) -> pd.Series:
    return pd.Series(
        np.select(
            [has_credit & (credit_limit >= LIMIT_CUT), has_credit, has_debit],
            ["Premium credit", "Core credit", "Debit"],
            default="Prepaid",
        ),
        index=has_credit.index,
    )


def holdings(cards: pd.DataFrame) -> pd.DataFrame:
    g = cards.groupby("client_id")
    out = pd.DataFrame(
        {
            "has_credit": g.card_type.apply(lambda s: s.eq("Credit").any()),
            "has_debit": g.card_type.apply(lambda s: s.eq("Debit").any()),
            "n_cards": g.size(),
        }
    )
    out["credit_limit"] = cards[cards.card_type.eq("Credit")].groupby("client_id").credit_limit.max()
    out["credit_limit"] = out.credit_limit.fillna(0)
    out["segment"] = segment_of(out.has_credit, out.credit_limit, out.has_debit)
    return out


def boot_ci(v: np.ndarray, n: int = 2000) -> tuple[float, float]:
    if len(v) < 2:
        return (np.nan, np.nan)
    means = v[RNG.integers(0, len(v), size=(n, len(v)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def load_card_month(cards: pd.DataFrame) -> pd.DataFrame:
    cm = pd.read_csv(V3 / "card_month.csv")
    cm["m"] = month_index(cm.month)
    ct = cm.card_id.map(cards.set_index("card_id").card_type)
    cm["rev"] = interchange(cm, ct)
    cm["rev_no_mt"] = interchange(cm, ct, exclude_money_transfer=True)
    cm["rev_prepaid_debit"] = interchange(cm, ct, prepaid_as_debit=True)
    return cm


def base_segments(cards, users, cm, observed) -> tuple[pd.DataFrame, dict]:
    m = pd.read_csv(V2 / "customer_metrics.csv")
    pre = cards[cards.open_m < WINDOW_START_M]
    h = holdings(pre)
    w = cm[(cm.m >= WINDOW_START_M) & (cm.m <= WINDOW_END_MONTH)]
    ic = w.groupby("client_id")[["rev", "rev_no_mt", "rev_prepaid_debit", "purchase_volume"]].sum()
    df = m[["client_id", "amex_fees", "interchange", "estimated_revenue", "product_role", "credit_share"]].merge(
        h, left_on="client_id", right_index=True, how="left"
    )
    df = df.merge(ic, left_on="client_id", right_index=True, how="left").fillna(
        {"rev": 0, "rev_no_mt": 0, "rev_prepaid_debit": 0, "purchase_volume": 0}
    )
    recon = {"v2_interchange": float(m.interchange.sum()), "v3_interchange": float(df.rev.sum())}
    assert abs(recon["v2_interchange"] - recon["v3_interchange"]) < 1.0, recon
    df["value"] = df.rev + df.amex_fees
    df["value_no_mt"] = df.rev_no_mt + df.amex_fees
    df["value_prepaid_debit"] = df.rev_prepaid_debit + df.amex_fees
    df["observed"] = df.client_id.isin(observed)
    df = df.merge(users[["client_id", "current_age", "yearly_income", "credit_score", "total_debt"]], on="client_id")
    obs = df[df.observed]
    df["top_decile"] = df.observed & (df.value >= obs.value.quantile(0.9))
    return df, recon


def segment_table(df: pd.DataFrame) -> pd.DataFrame:
    obs = df[df.observed]
    total = obs.value.sum()
    rows = []
    for s in SEGMENTS:
        a, o = df[df.segment.eq(s)], obs[obs.segment.eq(s)]
        lo, hi = boot_ci(o.value.to_numpy())
        rows.append(
            {
                "segment": s,
                "customers_all": len(a),
                "no_txn_data": int((~a.observed).sum()),
                "pct_no_txn_data": (~a.observed).mean() if len(a) else np.nan,
                "customers_observed": len(o),
                "pct_of_observed": len(o) / len(obs),
                "mean_value": o.value.mean(),
                "ci_low": lo,
                "ci_high": hi,
                "median_value": o.value.median(),
                "p10": o.value.quantile(0.1),
                "p90": o.value.quantile(0.9),
                "pct_value": o.value.sum() / total,
                "mean_value_no_money_transfer": o.value_no_mt.mean(),
                "mean_value_prepaid_as_debit": o.value_prepaid_debit.mean(),
                "mean_purchase_volume": o.purchase_volume.mean(),
                "lapsed_no_window_spend": int((o.purchase_volume == 0).sum()),
                "pct_credit_primary": o.product_role.eq("Credit-primary").mean(),
                "pct_top_decile": o.top_decile.sum() / obs.top_decile.sum(),
                "median_income": o.yearly_income.median(),
                "median_age": o.current_age.median(),
                "median_credit_score": o.credit_score.median(),
                "median_credit_limit": o.credit_limit.median(),
                "median_age_no_txn_data": a[~a.observed].current_age.median(),
            }
        )
    return pd.DataFrame(rows)


def new_customer_cohort(observed) -> pd.DataFrame:
    c = pd.read_csv(V3 / "new_customer_value.csv")
    c["segment"] = segment_of(c.acq_has_credit.astype(bool), c.acq_credit_limit, c.acq_has_debit.astype(bool))
    c["observed"] = c.client_id.isin(observed)
    c["cum3"] = c[f"y1_{VALUE}"] + c[f"y2_{VALUE}"] + c[f"y3_{VALUE}"]
    return c


def new_customer_value_ci(cohort: pd.DataFrame) -> pd.DataFrame:
    """Mean value per segment and year among customers with data, plus the mean when
    customers without transaction data count as $0 over the same observable horizon."""
    rows = []
    for s in SEGMENTS:
        a = cohort[cohort.segment.eq(s)]
        for col in ["y1", "y2", "y3", "cum3"]:
            key = "cum3" if col == "cum3" else f"{col}_{VALUE}"
            horizon = a[a[key].notna()]
            v = horizon.loc[horizon.observed, key].to_numpy()
            lo, hi = boot_ci(v)
            rows.append({"segment": s, "year": col, "n": len(v), "mean": v.mean() if len(v) else np.nan,
                         "ci_low": lo, "ci_high": hi, "n_all": len(horizon),
                         "mean_missing_as_zero": horizon[key].where(horizon.observed, 0).mean()})
    return pd.DataFrame(rows)


def cannibalisation(cards, cm, observed) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Customer revenue 12 months after vs before an additional card, net of a control trend."""
    obs_cm = cm[cm.client_id.isin(observed)]
    months = np.arange(FIRST_M, WINDOW_END_MONTH + 1)
    R = obs_cm.pivot_table(index="client_id", columns="m", values="rev", aggfunc="sum").reindex(columns=months).fillna(0)
    clients = R.index.to_numpy()
    cum = np.concatenate([np.zeros((len(R), 1)), R.to_numpy().cumsum(axis=1)], axis=1)

    def window_sum(t0: int, t1: int) -> np.ndarray:  # months [t0, t1)
        return cum[:, t1 - FIRST_M] - cum[:, t0 - FIRST_M]

    first_m = cards.groupby("client_id").open_m.min()
    ev = cards[
        cards.client_id.isin(observed)
        & (cards.open_m > cards.client_id.map(first_m))
        & (cards.open_m >= FIRST_M + 12)
        & (cards.open_m + 11 <= WINDOW_END_MONTH)
    ].copy()
    opens = cards[cards.client_id.isin(observed)].groupby("client_id").open_m.apply(np.array).reindex(clients)
    pos = {c: i for i, c in enumerate(clients)}
    own = cm.merge(ev[["card_id", "open_m"]], on="card_id")
    own = own[(own.m >= own.open_m) & (own.m < own.open_m + 12)].groupby("card_id").rev.sum()

    rows = []
    for t, grp in ev.groupby("open_m"):
        before, after = window_sum(t - 12, t), window_sum(t, t + 12)
        quiet = np.array([not np.any((o >= t - 12) & (o < t + 12)) for o in opens])
        control = float((after - before)[quiet].mean())
        for _, r in grp.iterrows():
            i = pos[r.client_id]
            rows.append(
                {
                    "card_id": r.card_id,
                    "client_id": r.client_id,
                    "card_type": r.card_type,
                    "credit_limit": r.credit_limit,
                    "open_m": t,
                    "before": before[i],
                    "after": after[i],
                    "control_change": control,
                    "own_card_y1": own.get(r.card_id, 0.0),
                }
            )
    e = pd.DataFrame(rows)
    e["incremental"] = e.after - e.before - e.control_change
    summary = (
        e.groupby("card_type")
        .agg(
            events=("card_id", "size"),
            own_card_y1=("own_card_y1", "mean"),
            customer_before=("before", "mean"),
            customer_after=("after", "mean"),
            control_change=("control_change", "mean"),
            incremental=("incremental", "mean"),
        )
        .assign(incremental_share_of_own=lambda x: x.incremental / x.own_card_y1.replace(0, np.nan))
    )
    ci = e.groupby("card_type").incremental.apply(lambda s: boot_ci(s.to_numpy()))
    summary["incr_ci_low"] = ci.map(lambda t: t[0])
    summary["incr_ci_high"] = ci.map(lambda t: t[1])
    return e, summary


def card_openings_view(cards, observed) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every card opening, flagged as a new customer's first-month card or an extra card for an existing one."""
    o = cards[["card_id", "client_id", "open_m", "opened", "card_type", "credit_limit"]].copy()
    first_m = o.groupby("client_id").open_m.transform("min")
    o["existing_customer"] = o.open_m > first_m
    o["year"] = o.opened.dt.year
    o["day_one_segment"] = o.client_id.map(holdings(o[o.open_m.eq(first_m)]).segment)
    o["observed_customer"] = o.client_id.isin(observed)
    by_year = (
        o.groupby("year")
        .agg(
            cards_opened=("card_id", "size"),
            existing_customer=("existing_customer", "sum"),
            customers=("client_id", "nunique"),
            observed=("observed_customer", "mean"),
        )
        .assign(
            new_customer=lambda x: x.cards_opened - x.existing_customer,
            pct_existing=lambda x: x.existing_customer / x.cards_opened,
        )
    )
    return o, by_year


def plots(seg: pd.DataFrame, seg_d1: pd.DataFrame, coh_ci: pd.DataFrame, cov: pd.DataFrame, age: pd.Series) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    t = seg.set_index("segment").reindex(SEGMENTS)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = np.arange(len(t))
    ax.bar(x, t.mean_value, color=[COLORS[s] for s in SEGMENTS])
    ax.errorbar(x, t.mean_value, yerr=[t.mean_value - t.ci_low, t.ci_high - t.mean_value],
                fmt="none", ecolor="black", capsize=4, lw=1)
    for i, s in enumerate(SEGMENTS):
        ax.text(i, (t.ci_high.iloc[i] if np.isfinite(t.ci_high.iloc[i]) else t.mean_value.iloc[i]) + 20,
                f"${t.mean_value.iloc[i]:,.0f}\n{t.customers_observed.iloc[i]} customers\n"
                f"{t.pct_value.iloc[i]:.0%} of revenue",
                ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(SEGMENTS)
    ax.set_ylim(0, t.ci_high.max() * 1.45)
    ax.set_ylabel("Revenue per customer, Nov 2018 to Oct 2019 ($)")
    ax.set_title("Annual value by product held today (established customers with data, 95% CI)")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_segment_value.png", dpi=150)
    plt.close(fig)

    traj = seg_d1.set_index("segment").reindex(SEGMENTS)
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    offsets = dict(zip(SEGMENTS, [-0.15, -0.05, 0.05, 0.15]))
    for s in SEGMENTS:
        c = coh_ci[coh_ci.segment.eq(s)].set_index("year").reindex(["y1", "y2", "y3"])
        xs = np.array([1, 2, 3, 4.2]) + offsets[s]
        ys = list(c["mean"]) + [traj.loc[s, "mean_value"]]
        lo = list(c.ci_low) + [traj.loc[s, "ci_low"]]
        hi = list(c.ci_high) + [traj.loc[s, "ci_high"]]
        n_new = int(c.n.iloc[0])
        ax.plot(xs[:3], ys[:3], marker="o", color=COLORS[s], lw=2, label=f"{s} (new n={n_new}, established n={int(traj.loc[s, 'customers_observed'])})")
        ax.plot(xs[2:], ys[2:], ls=":", color=COLORS[s], lw=1.5)
        ax.scatter(xs[3], ys[3], marker="s", color=COLORS[s], s=50, zorder=3)
        ax.errorbar(xs, ys, yerr=[np.array(ys) - np.array(lo), np.array(hi) - np.array(ys)],
                    fmt="none", ecolor=COLORS[s], capsize=3, lw=1)
    ax.set_xticks([1, 2, 3, 4.2])
    ax.set_xticklabels(["Year 1", "Year 2", "Year 3", "Established\n(~14 yrs tenure)"])
    ax.set_ylim(0, None)
    ax.set_ylabel("Revenue per customer per year ($), 95% CI")
    ax.set_title("Annual value by day-one segment: new customers' first three years and established customers")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_value_by_day_one_segment.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    cov = cov[cov.index.astype(str) != "2020"]
    axes[0].bar(cov.index.astype(str), cov.pct_no_txn * 100, color="#9fbfd6")
    axes[0].set_ylabel("Customers with no transactions at all (%)")
    axes[0].set_xlabel("Year of first card")
    axes[0].set_title("Missing transaction data rises for recent customers")
    for lab in axes[0].get_xticklabels():
        lab.set_rotation(30)
    axes[1].bar(age.index.astype(str), age.values * 100, color="#5b8fad")
    axes[1].set_xlabel("Current age")
    axes[1].set_title("...and for younger customers")
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_missing_transaction_data.png", dpi=150)
    plt.close(fig)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    cards = load_cards(HANDOUT / "cards_data.csv")
    users = pd.read_csv(HANDOUT / "users_data.csv").rename(columns={"id": "client_id"})
    for col in ["yearly_income", "total_debt"]:
        users[col] = money(users[col])
    cm = load_card_month(cards)
    observed = set(cm.client_id)

    base, recon = base_segments(cards, users, cm, observed)
    first_m = cards.groupby("client_id").open_m.transform("min")
    base["day_one"] = base.client_id.map(holdings(cards[cards.open_m.eq(first_m)]).segment)
    first_year = cards.groupby("client_id").opened.min().dt.year
    base["first_card_year"] = base.client_id.map(first_year)
    seg = segment_table(base)
    seg.to_csv(V3 / "segment_value.csv", index=False)
    seg_d1 = segment_table(base.assign(segment=base.day_one))
    seg_d1.to_csv(V3 / "segment_value_day_one.csv", index=False)
    migration = pd.crosstab(base[base.observed].day_one, base[base.observed].segment, normalize="index").reindex(SEGMENTS)[SEGMENTS]
    migration.to_csv(V3 / "day_one_to_held_today.csv")
    base.to_csv(V3 / "base_customers_segmented.csv", index=False)

    cohort = new_customer_cohort(observed)
    coh = (
        cohort.groupby(["segment", "observed"])
        .agg(n=("client_id", "size"), y1=(f"y1_{VALUE}", "mean"), y2=(f"y2_{VALUE}", "mean"),
             y3=(f"y3_{VALUE}", "mean"), cum3=("cum3", "mean"), n_cum3=("cum3", "count"))
        .reset_index()
    )
    coh.to_csv(V3 / "new_customer_cohort_by_segment.csv", index=False)
    coh_ci = new_customer_value_ci(cohort)
    coh_ci.to_csv(V3 / "new_customer_value_ci.csv", index=False)

    events, cann = cannibalisation(cards, cm, observed)
    events.to_csv(V3 / "additional_card_events.csv", index=False)
    cann.to_csv(V3 / "additional_card_incrementality.csv")

    s, by_year = card_openings_view(cards, observed)
    by_year.to_csv(V3 / "card_openings_new_vs_existing.csv")
    s.to_csv(V3 / "card_openings_classified.csv", index=False)
    for stale in ["signups_new_vs_existing.csv", "signups_classified.csv", "paid_spend_per_signup.csv"]:
        (V3 / stale).unlink(missing_ok=True)

    s20 = s[s.year.eq(2020)]
    y1 = coh_ci[coh_ci.year.eq("y1")].set_index("segment")["mean"]
    c3 = coh_ci[coh_ci.year.eq("cum3")].set_index("segment")["mean"]
    incr = cann.incremental.clip(lower=0)
    s20_new = s20[~s20.existing_customer].drop_duplicates("client_id")
    s20_ex = s20[s20.existing_customer]
    hist_mix = cohort.segment.value_counts(normalize=True).reindex(SEGMENTS).fillna(0)
    new_mix = s20_new.day_one_segment.value_counts(normalize=True).reindex(SEGMENTS).fillna(0)
    mix = pd.DataFrame({"new_customers_2010_2018": hist_mix, "new_customers_jan_feb_2020": new_mix,
                        "y1_value": y1, "cum3_value": c3})
    mix.to_csv(V3 / "new_customer_mix_over_time.csv")
    openings_2020 = {
        "cards_opened": len(s20),
        "new_customers": int(s20_new.client_id.nunique()),
        "new_customer_cards": int((~s20.existing_customer).sum()),
        "existing_customer_cards": len(s20_ex),
        "new_customer_day_one_mix": new_mix.round(3).to_dict(),
        "historical_new_customer_day_one_mix_2010_2018": hist_mix.round(3).to_dict(),
        "expected_y1_value_new_customer_2020_mix": float((new_mix * y1).sum()),
        "expected_y1_value_new_customer_historical_mix": float((hist_mix * y1).sum()),
        "expected_cum3_value_new_customer_2020_mix": float((new_mix * c3).sum()),
        "expected_cum3_value_new_customer_historical_mix": float((hist_mix * c3).sum()),
        "existing_customer_added_card_type": s20_ex.card_type.value_counts(normalize=True).round(3).to_dict(),
        "expected_y1_incremental_value_existing_customer_card": float(s20_ex.card_type.map(incr).fillna(0).mean()),
        "monthly_cards_opened_2019_avg": float(s[s.year.eq(2019)].shape[0] / 12),
        "monthly_cards_opened_2020_avg": float(len(s20) / 2),
    }
    obs_base = base[base.observed]
    pocket = obs_base[obs_base.segment.isin(["Premium credit", "Core credit"]) & (obs_base.purchase_volume > 0)]
    users_credit = pocket[pocket.credit_share > 0].value.mean()
    idle = pocket[pocket.credit_share.eq(0)]
    activation_pocket = {
        "customers": len(idle),
        "mean_value": float(idle.value.mean()),
        "mean_value_credit_users": float(users_credit),
        "annual_uplift_if_like_credit_users": float(len(idle) * (users_credit - idle.value.mean())),
    }

    users_first = cards.groupby("client_id").opened.min().dt.year
    u = users.assign(first_year=users.client_id.map(users_first), has_txn=users.client_id.isin(observed))
    cov = u.groupby(pd.cut(u.first_year, [1900, 1999, 2004, 2009, 2014, 2019, 2020],
                           labels=["pre-2000", "2000-04", "2005-09", "2010-14", "2015-19", "2020"])
                    , observed=True).has_txn.agg(["size", "mean"])
    cov["pct_no_txn"] = 1 - cov["mean"]
    age_missing = 1 - u.groupby(pd.cut(u.current_age, [17, 29, 39, 49, 59, 69, 120],
                                            labels=["18-29", "30-39", "40-49", "50-59", "60-69", "70+"]),
                                     observed=True).has_txn.mean()
    lapsed = base[base.observed & base.purchase_volume.eq(0)]
    last_purchase = cm[cm.client_id.isin(lapsed.client_id) & (cm.purchase_count > 0)].groupby("client_id").month.max()

    notes = {
        "reconciliation": recon,
        "observed_customers_total": len(observed),
        "users_total": len(users),
        "q1_population": len(base),
        "q1_population_observed": int(base.observed.sum()),
        "coverage_by_first_card_year": cov[["size", "pct_no_txn"]].round(3).reset_index().astype(str).to_dict(orient="records"),
        "coverage_by_age": age_missing.round(3).astype(float).to_dict(),
        "observed_cards_unused_in_first_year_2010_2018": "0 (every card opened 2010-2018 by an observed customer transacted in year 1)",
        "lapsed": {
            "n": len(lapsed),
            "segments": lapsed.segment.value_counts().to_dict(),
            "last_purchase_month": last_purchase.to_dict(),
        },
        "top_decile_threshold_observed": float(base[base.observed].value.quantile(0.9)),
        "top10_share_observed": float(base[base.observed].value.nlargest(int(base.observed.sum() * 0.1)).sum()
                                      / base[base.observed].value.sum()),
        "card_openings_2020": openings_2020,
        "activation_pocket": activation_pocket,
        "established_median_first_card_year": float(obs_base.first_card_year.median()),
        "established_median_age": float(obs_base.current_age.median()),
        "established_pct_under_30": float(obs_base.current_age.lt(30).mean()),
        "all_users_pct_under_30": float(users.current_age.lt(30).mean()),
    }
    (V3 / "segments_notes.json").write_text(json.dumps(notes, indent=2, default=str))
    plots(seg, seg_d1, coh_ci, cov, age_missing)
    old_plot = PLOTS / "q1_payback_vs_cac.png"
    if old_plot.exists():
        old_plot.unlink()

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(seg.round(2).T.to_string())
    print(seg_d1.round(2).T.to_string())
    print(migration.round(2).to_string())
    print(coh_ci.round(0).to_string(index=False))
    print(mix.round(3).to_string())
    print(cann.round(2).to_string())
    print(by_year.round(3).to_string())
    print(json.dumps(notes, indent=2, default=str))


if __name__ == "__main__":
    main()
