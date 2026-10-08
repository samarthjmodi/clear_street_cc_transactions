"""Q1 robustness and gap checks behind the segment verdicts.

  1. Segment counts for the whole customer base (all 2,000), by data status
  2. Cost sensitivity: value net of costs that scale with credit spend (rewards, losses),
     and the maximum affordable acquisition cost per segment
  3. Robustness of the ranking: bootstrap rank stability, card-level support, and
     survivorship scenarios for unobserved customer churn
  4. Prepaid and Debit as on-ramps: how often and how fast starters add credit
  5. How well day-one-visible attributes predict landing in Premium credit
  6. Spend vs revenue: active customers' twelve-month spend against rate-card revenue
  7. Whether recorded credit limits look set at opening (the file holds no limit history)

Run from repo root after q1_part1_profile.py, build_q1_v2_customer_metrics.py,
build_card_month.py, q1_v3_cohorts.py and q1_v3_segments.py:
  .venv/bin/python src/q1_v3_robustness.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_card_first_year_profile import STATE_REGION, load_state_polygons, state_of  # noqa: E402
from q1_part2_value import PERSONA_NAMES  # noqa: E402
from q1_revenue import (CREDIT_BPS, WINDOW_END_MONTH, interchange, load_cards, money,  # noqa: E402
                        month_index, revolving_interest)
from q1_v3_segments import LIMIT_CUT, SEGMENTS, VALUE, holdings, segment_of  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
Q1_VALUE = HANDOUT / "analysis" / "q1_value"
V2 = HANDOUT / "analysis" / "q1_scratch" / "v2"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
CREDIT_BANDS = ["Nothing on credit", "Some on credit", "Everything on credit"]
WINDOW_START_M = 2018 * 12 + 11
SNAPSHOT_M = 2020 * 12 + 2
COST_RATES = [0.0, 0.005, 0.010, 0.015]
CHURN_RATES = [0.0, 0.05, 0.10, 0.15]
RNG = np.random.default_rng(31)


def net_of_cost(value: pd.Series, credit_interchange: pd.Series, rate: float,
                with_interest: bool = False) -> pd.Series:
    """Value minus a cost of `rate` x net credit spend; credit interchange is 1.8% of that spend.
    `with_interest` adds revolving interest on the same credit spend."""
    extra = revolving_interest(credit_interchange) if with_interest else 0
    return value + extra - credit_interchange * rate / (CREDIT_BPS / 10_000)


def auc(score: pd.Series, label: pd.Series) -> float:
    """Probability a random positive outranks a random negative (Mann-Whitney), ties count half."""
    r = score.rank()
    n1, n0 = int(label.sum()), int((~label).sum())
    return float((r[label].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def base_counts(cards: pd.DataFrame, users: pd.DataFrame, observed: set) -> pd.DataFrame:
    first_m = cards.groupby("client_id").open_m.min()
    d1 = holdings(cards[cards.open_m.eq(cards.client_id.map(first_m))])
    u = users[["client_id"]].assign(day_one=users.client_id.map(d1.segment), first_m=users.client_id.map(first_m))
    u["status"] = np.select(
        [u.client_id.isin(observed), u.first_m >= WINDOW_END_MONTH + 1],
        ["With transaction data", "Joined Nov 2019 or later (no spend yet)"],
        default="Joined earlier, no transaction data",
    )
    t = pd.crosstab(u.day_one, u.status, margins=True, margins_name="Total").reindex(SEGMENTS + ["Total"])
    t["share_of_all"] = t["Total"] / len(u)
    earlier = t["Joined earlier, no transaction data"] + t["With transaction data"]
    t["pct_missing_of_joined_earlier"] = t["Joined earlier, no transaction data"] / earlier
    return t


def spend_vs_revenue(active: pd.DataFrame, revenue: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Twelve-month spend against rate-card revenue, by persona and by share of spend on credit.
    Returns both summaries and the rank correlation between spend and revenue."""
    d = active.assign(revenue=active.client_id.map(revenue).fillna(0))
    d["credit_band"] = np.select([d.credit_share_of_spend.eq(0), d.credit_share_of_spend.eq(1)],
                                 [CREDIT_BANDS[0], CREDIT_BANDS[2]], CREDIT_BANDS[1])

    def summary(by) -> pd.DataFrame:
        g = d.groupby(by)
        return pd.DataFrame({"customers": g.size(), "median_spend": g.spend.median(),
                             "median_revenue": g.revenue.median(),
                             "revenue_per_100_spend": g.revenue.sum() / g.spend.sum() * 100,
                             "median_credit_share": g.credit_share_of_spend.median()})

    by_persona = summary(d.persona.map(PERSONA_NAMES).rename("persona")).sort_values(
        "revenue_per_100_spend", ascending=False)
    by_credit = summary("credit_band").reindex(CREDIT_BANDS)
    return by_persona, by_credit, float(d.spend.corr(d.revenue, method="spearman"))


def limit_drift(cards: pd.DataFrame, income: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Limit-to-income by card age, and how often a customer's earliest credit card carries a
    higher limit than their latest. Flat ratios and ~50% suggest limits are set at opening."""
    cr = cards[cards.card_type.eq("Credit")].copy()
    cr["age_years"] = (SNAPSHOT_M - cr.open_m) / 12
    cr["limit_to_income"] = cr.credit_limit / cr.client_id.map(income)
    bands = pd.cut(cr.age_years, [-1, 2, 5, 10, 15, 100], labels=["Under 2", "2–5", "5–10", "10–15", "15+"])
    by_age = cr.groupby(bands.rename("card_age_years"), observed=True).agg(
        cards=("card_id", "size"), median_limit=("credit_limit", "median"),
        median_limit_to_income=("limit_to_income", "median"))
    multi = cr[cr.groupby("client_id").open_m.transform("nunique") >= 2].sort_values(
        ["client_id", "open_m", "card_id"])
    g = multi.groupby("client_id").credit_limit
    earliest, latest = g.first(), g.last()
    stats = {
        "rank_corr_card_age_vs_limit_to_income": float(cr.age_years.corr(cr.limit_to_income, method="spearman")),
        "customers_with_credit_cards_opened_apart": int(len(earliest)),
        "share_earliest_card_higher_limit": float((earliest > latest).mean()),
        "share_equal_limits": float((earliest == latest).mean()),
    }
    return by_age, stats


def credit_interchange_by_year(cards, cm, cohort) -> pd.DataFrame:
    credit_ids = set(cards.loc[cards.card_type.eq("Credit"), "card_id"])
    x = cm[cm.card_id.isin(credit_ids)].merge(cohort[["client_id", "acq_m"]], on="client_id")
    x["year"] = (x.m - x.acq_m) // 12 + 1
    out = cohort[["client_id"]].copy()
    for k in (1, 2, 3):
        out[f"y{k}_credit_ic"] = out.client_id.map(x[x.year.eq(k)].groupby("client_id").rev.sum()).fillna(0)
    return out


def main() -> None:
    cards = load_cards(HANDOUT / "cards_data.csv")
    users = pd.read_csv(HANDOUT / "users_data.csv").rename(columns={"id": "client_id"})
    for col in ["yearly_income", "per_capita_income", "total_debt"]:
        users[col] = money(users[col])
    cm = pd.read_csv(V3 / "card_month.csv")
    cm["m"] = month_index(cm.month)
    cm["rev"] = interchange(cm, cm.card_id.map(cards.set_index("card_id").card_type))
    observed = set(cm.client_id)
    out: dict = {}

    # 1. Whole-base counts
    counts = base_counts(cards, users, observed)
    counts.to_csv(V3 / "segment_counts_all_customers.csv")

    # 2. Cost sensitivity on the new-customer cohort and established customers
    coh = pd.read_csv(V3 / "new_customer_value.csv")
    coh["segment"] = segment_of(coh.acq_has_credit.astype(bool), coh.acq_credit_limit, coh.acq_has_debit.astype(bool))
    coh = coh[coh.client_id.isin(observed)].merge(credit_interchange_by_year(cards, cm, coh), on="client_id")
    base = pd.read_csv(V3 / "base_customers_segmented.csv")
    base = base[base.observed].copy()
    credit_ids = set(cards.loc[cards.card_type.eq("Credit"), "card_id"])
    w = cm[(cm.m >= WINDOW_START_M) & (cm.m <= WINDOW_END_MONTH) & cm.card_id.isin(credit_ids)]
    base["credit_ic"] = base.client_id.map(w.groupby("client_id").rev.sum()).fillna(0)

    cost_rows = []
    for s in SEGMENTS:
        c = coh[coh.segment.eq(s)]
        c3 = c.dropna(subset=[f"y3_{VALUE}"])
        b = base[base.day_one.eq(s)]
        for interest in (False, True):
            for r in COST_RATES:
                three = sum(net_of_cost(c3[f"y{k}_{VALUE}"], c3[f"y{k}_credit_ic"], r, interest) for k in (1, 2, 3))
                cost_rows.append({
                    "segment": s, "with_revolving_interest": interest, "cost_pct_of_credit_spend": r * 100,
                    "y1_net": net_of_cost(c[f"y1_{VALUE}"], c.y1_credit_ic, r, interest).mean(),
                    "three_year_net": three.mean(), "n_three_year": len(c3),
                    "established_annual_net": net_of_cost(b.value, b.credit_ic, r, interest).mean(),
                    "credit_share_of_revenue_3y": (c3[["y1_credit_ic", "y2_credit_ic", "y3_credit_ic"]].sum().sum()
                                                   / c3[[f"y{k}_{VALUE}" for k in (1, 2, 3)]].sum().sum()),
                })
    costs = pd.DataFrame(cost_rows)
    costs.to_csv(V3 / "segment_value_net_of_costs.csv", index=False)
    piv = costs.pivot_table(index=["with_revolving_interest", "cost_pct_of_credit_spend"], columns="segment",
                            values="three_year_net")[SEGMENTS]
    grid = np.linspace(0, 0.03, 301)
    s3 = {s: coh[coh.segment.eq(s)].dropna(subset=[f"y3_{VALUE}"]) for s in SEGMENTS}

    def three_net(s, r, interest):
        c = s3[s]
        return float(sum(net_of_cost(c[f"y{k}_{VALUE}"], c[f"y{k}_credit_ic"], r, interest)
                         for k in (1, 2, 3)).mean())

    def crossover(a, b, interest):
        for r in grid:
            if three_net(a, r, interest) <= three_net(b, r, interest):
                return float(r * 100)
        return None

    out["cost_crossover_pct"] = {
        label: {
            "premium_falls_to_debit": crossover("Premium credit", "Debit", interest),
            "core_falls_to_debit": crossover("Core credit", "Debit", interest),
            "premium_falls_to_core": crossover("Premium credit", "Core credit", interest),
        }
        for label, interest in [("interchange_only", False), ("with_revolving_interest", True)]
    }

    # 3. Robustness
    boot = {s: s3[s][[f"y{k}_{VALUE}" for k in (1, 2, 3)]].sum(axis=1).to_numpy() for s in SEGMENTS}
    estab = {s: base[base.day_one.eq(s)].value.to_numpy() for s in SEGMENTS}

    def p_order(d, a, b, n=4000):
        ma = d[a][RNG.integers(0, len(d[a]), (n, len(d[a])))].mean(axis=1)
        mb = d[b][RNG.integers(0, len(d[b]), (n, len(d[b])))].mean(axis=1)
        return float((ma > mb).mean())

    pairs = [("Premium credit", "Core credit"), ("Core credit", "Debit"), ("Debit", "Prepaid"),
             ("Premium credit", "Debit")]
    out["p_ranking_holds"] = {
        "three_year_new_customers": {f"{a} > {b}": p_order(boot, a, b) for a, b in pairs},
        "established_annual": {f"{a} > {b}": p_order(estab, a, b) for a, b in pairs},
    }
    card = pd.read_csv(V3 / "card_first_year_value.csv")
    card = card[card.client_id.isin(observed) & card.card_type.eq("Credit")]
    out["card_level_support_all_credit_cards"] = {
        "limit_cut": LIMIT_CUT,
        "cards_at_or_above_cut": int(card.credit_limit.ge(LIMIT_CUT).sum()),
        "y1_at_or_above_cut": float(card[card.credit_limit.ge(LIMIT_CUT)].y1_value.mean()),
        "cards_below_cut": int(card.credit_limit.lt(LIMIT_CUT).sum()),
        "y1_below_cut": float(card[card.credit_limit.lt(LIMIT_CUT)].y1_value.mean()),
    }
    surv = []
    for s in SEGMENTS:
        c = s3[s]
        means = [c[f"y{k}_{VALUE}"].mean() for k in (1, 2, 3)]
        for ch in CHURN_RATES:
            surv.append({"segment": s, "annual_churn_pct": ch * 100,
                         "three_year_value": sum(m * (1 - ch) ** (k) for k, m in enumerate(means))})
    surv = pd.DataFrame(surv)
    surv.to_csv(V3 / "segment_value_churn_scenarios.csv", index=False)
    out["value_per_account_if_missing_is_zero"] = {
        s: {"pct_missing": float(counts.loc[s, "pct_missing_of_joined_earlier"]),
            "established_with_data": float(base[base.day_one.eq(s)].value.mean())}
        for s in SEGMENTS
    }
    est_all = pd.read_csv(V3 / "base_customers_segmented.csv")
    for s in SEGMENTS:
        e = est_all[est_all.day_one.eq(s)]
        out["value_per_account_if_missing_is_zero"][s].update({
            "established_pct_missing": float((~e.observed).mean()),
            "established_value_per_account_missing_as_zero": float(e.value.where(e.observed, 0).mean()),
        })

    # 4. On-ramps: time from first card to first credit card, for Debit and Prepaid starters
    first_m = cards.groupby("client_id").open_m.min()
    day1 = holdings(cards[cards.open_m.eq(cards.client_id.map(first_m))]).segment
    fc = cards[cards.card_type.eq("Credit")].groupby("client_id").open_m.min()
    fd = cards[cards.card_type.eq("Debit")].groupby("client_id").open_m.min()
    ramp_rows = []
    for s in ["Debit", "Prepaid"]:
        ids = day1[day1.eq(s)].index
        f0 = first_m.reindex(ids)
        to_credit = (fc.reindex(ids) - f0) / 12
        to_debit = (fd.reindex(ids) - f0) / 12
        tenure = (SNAPSHOT_M - f0) / 12
        row = {"segment": s, "customers": len(ids),
               "pct_ever_added_credit": float(to_credit.notna().mean()),
               "median_years_to_credit_if_added": float(to_credit.median())}
        for yrs in (1, 3, 5, 10):
            elig = tenure >= yrs
            row[f"pct_credit_within_{yrs}y"] = float((to_credit[elig] <= yrs).mean())
            row[f"n_eligible_{yrs}y"] = int(elig.sum())
        if s == "Prepaid":
            row["pct_ever_added_debit"] = float(to_debit.notna().mean())
            row["pct_ever_added_debit_or_credit"] = float((to_debit.notna() | to_credit.notna()).mean())
        ramp_rows.append(row)
    ramps = pd.DataFrame(ramp_rows)
    ramps.to_csv(V3 / "on_ramp_debit_prepaid.csv", index=False)
    pre = base[base.day_one.eq("Prepaid")]
    out["prepaid_starters_established_value"] = {
        "added_credit": {"n": int(pre.has_credit.sum()), "value": float(pre[pre.has_credit].value.mean())},
        "no_credit": {"n": int((~pre.has_credit).sum()), "value": float(pre[~pre.has_credit].value.mean())},
    }
    deb = base[base.day_one.eq("Debit")]
    out["debit_starters_established_value"] = {
        "added_credit": {"n": int(deb.has_credit.sum()), "value": float(deb[deb.has_credit].value.mean())},
        "no_credit": {"n": int((~deb.has_credit).sum()), "value": float(deb[~deb.has_credit].value.mean())},
    }
    pc = coh[coh.segment.eq("Prepaid")]
    out["prepaid_new_cohort"] = (pc[["client_id"] + [f"y{k}_{VALUE}" for k in (1, 2, 3)]]
                                 .round(0).to_dict(orient="records"))

    # 5. Predicting Premium from attributes visible around approval
    users["state"], _ = state_of(users.latitude.to_numpy(), users.longitude.to_numpy(), load_state_polygons())
    users["region"] = users.state.map(STATE_REGION).fillna("Other")
    fo = users.client_id.map(first_m)
    users["age_at_first_card"] = users.current_age - (SNAPSHOT_M - fo) / 12
    users["day_one"] = users.client_id.map(day1)
    users["is_premium"] = users.day_one.eq("Premium credit")
    users["income_fifth"] = pd.qcut(users.yearly_income, 5, labels=["Bottom", "2nd", "3rd", "4th", "Top"])
    users["age_band"] = pd.cut(users.age_at_first_card, [0, 29, 39, 49, 120], labels=["Under 30", "30–39", "40–49", "50+"])
    pred = {}
    for by in ["income_fifth", "age_band", "region"]:
        g = users.groupby(by, observed=True)
        pred[by] = pd.DataFrame({
            "customers": g.size(),
            "pct_premium_day_one": g.is_premium.mean(),
            "pct_credit_day_one": g.day_one.apply(lambda s: s.isin(["Premium credit", "Core credit"]).mean()),
            "pct_premium_among_credit": g.apply(lambda d: d[d.day_one.isin(["Premium credit", "Core credit"])]
                                                .is_premium.mean(), include_groups=False),
        })
        pred[by].to_csv(V3 / f"premium_rate_by_{by}.csv")
    credit_start = users[users.day_one.isin(["Premium credit", "Core credit"])]
    out["premium_predictability"] = {
        "base_rate_premium_all": float(users.is_premium.mean()),
        "base_rate_premium_among_credit_starters": float(credit_start.is_premium.mean()),
        "auc_premium_vs_core": {
            a: auc(credit_start[a], credit_start.is_premium)
            for a in ["yearly_income", "per_capita_income", "age_at_first_card", "credit_score", "total_debt"]
        },
        "auc_premium_vs_all_others": {
            a: auc(users[a], users.is_premium) for a in ["yearly_income", "per_capita_income", "age_at_first_card"]
        },
    }

    # 6. Spend vs revenue, priced like the three-year values (prepaid at the debit rate, Amex fee)
    active = pd.read_csv(Q1_VALUE / "part1_customers.csv",
                         usecols=["client_id", "persona", "spend", "credit_share_of_spend"]).dropna(subset=["persona"])
    w_all = cm[(cm.m >= WINDOW_START_M) & (cm.m <= WINDOW_END_MONTH)]
    window_rev = interchange(w_all, w_all.card_id.map(cards.set_index("card_id").card_type),
                             prepaid_as_debit=True).groupby(w_all.client_id).sum()
    fees = pd.read_csv(V2 / "customer_metrics.csv").set_index("client_id").amex_fees
    by_persona, by_credit, rho = spend_vs_revenue(active, window_rev.add(fees, fill_value=0))
    by_persona.to_csv(V3 / "spend_vs_revenue_by_persona.csv")
    by_credit.to_csv(V3 / "spend_vs_revenue_by_credit_share.csv")
    out["spend_vs_revenue"] = {"customers": len(active), "rank_correlation": rho}

    # 7. Credit limits: set at opening, or raised later?
    limits_by_age, out["limit_drift"] = limit_drift(cards, users.set_index("client_id").yearly_income)
    limits_by_age.to_csv(V3 / "credit_limit_by_card_age.csv")

    (V3 / "robustness_notes.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(counts.to_string(), "\n")
    print(costs.round(1).to_string(index=False), "\n")
    print(piv.round(0).to_string(), "\n")
    print(surv.pivot(index="annual_churn_pct", columns="segment", values="three_year_value")[SEGMENTS].round(0), "\n")
    print(ramps.round(3).T.to_string(), "\n")
    for by, t in pred.items():
        print(t.round(3).to_string(), "\n")
    print(by_persona.round(2).to_string(), "\n")
    print(by_credit.round(2).to_string(), "\n")
    print(limits_by_age.round(3).to_string(), "\n")
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
