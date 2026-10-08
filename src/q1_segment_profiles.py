"""Q1: who is in each day-one segment.

Established customers with transaction data (the population behind the established values in
Q1_FINDINGS.md), grouped by the segment of the cards opened in their first month.
Attributes come from users_data (Feb 2020 snapshot) and cards_data.

Run from repo root after q1_v3_segments.py:
  .venv/bin/python src/q1_segment_profiles.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_card_first_year_profile import STATE_ABBR, STATE_REGION, load_state_polygons, state_of  # noqa: E402
from q1_revenue import load_cards, money  # noqa: E402
from q1_v3_segments import SEGMENTS, holdings  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
SNAPSHOT_YEAR = 2020 + 1 / 12


def main() -> None:
    base = pd.read_csv(V3 / "base_customers_segmented.csv")
    base = base[base.observed]
    users = pd.read_csv(HANDOUT / "users_data.csv").rename(columns={"id": "client_id"})
    for col in ["per_capita_income", "yearly_income", "total_debt"]:
        users[col] = money(users[col])
    users["state"], _ = state_of(users.latitude.to_numpy(), users.longitude.to_numpy(), load_state_polygons())
    users["region"] = users.state.map(STATE_REGION).fillna("Other")
    users["state_abbr"] = users.state.map(STATE_ABBR)
    income_fifth = pd.qcut(users.yearly_income, 5, labels=False)
    users["top_income_fifth"] = income_fifth.eq(4)
    users["bottom_income_fifth"] = income_fifth.eq(0)

    cards = load_cards(HANDOUT / "cards_data.csv")
    first_m = cards.groupby("client_id").open_m.transform("min")
    day_one_cards = cards[cards.open_m.eq(first_m)]
    d1 = holdings(day_one_cards)
    d1["day_one_cards"] = day_one_cards.groupby("client_id").size()
    first_open = cards.groupby("client_id").opened.min()

    df = base[["client_id", "day_one", "segment", "value", "n_cards", "purchase_volume"]].merge(
        users[["client_id", "current_age", "gender", "yearly_income", "per_capita_income", "total_debt",
               "credit_score", "region", "state_abbr", "top_income_fifth", "bottom_income_fifth"]], on="client_id")
    df["day_one_limit"] = df.client_id.map(d1.credit_limit)
    df["day_one_cards"] = df.client_id.map(d1.day_one_cards)
    fo = df.client_id.map(first_open)
    df["first_card_year"] = fo.dt.year
    df["age_at_first_card"] = df.current_age - (SNAPSHOT_YEAR - (fo.dt.year + (fo.dt.month - 0.5) / 12))
    df["holds_credit_now"] = df.segment.isin(["Premium credit", "Core credit"])
    df["premium_now"] = df.segment.eq("Premium credit")

    rows = []
    for s in SEGMENTS:
        g = df[df.day_one.eq(s)]
        reg = g.region.value_counts(normalize=True)
        top_states = g.state_abbr.value_counts().head(3)
        rows.append({
            "segment": s,
            "customers": len(g),
            "share_of_customers": len(g) / len(df),
            "annual_value": g.value.mean(),
            "median_age_at_first_card": g.age_at_first_card.median(),
            "median_age_now": g.current_age.median(),
            "pct_under_40_at_first_card": g.age_at_first_card.lt(40).mean(),
            "pct_female": g.gender.eq("Female").mean(),
            "median_yearly_income": g.yearly_income.median(),
            "pct_top_income_fifth": g.top_income_fifth.mean(),
            "pct_bottom_income_fifth": g.bottom_income_fifth.mean(),
            "median_total_debt": g.total_debt.median(),
            "median_credit_score": g.credit_score.median(),
            "median_day_one_credit_limit": g.loc[g.day_one_limit > 0, "day_one_limit"].median(),
            "median_first_card_year": g.first_card_year.median(),
            "median_cards_held": g.n_cards.median(),
            "pct_hold_credit_now": g.holds_credit_now.mean(),
            "pct_premium_now": g.premium_now.mean(),
            "mean_purchase_volume": g.purchase_volume.mean(),
            "pct_northeast": reg.get("Northeast", 0.0),
            "pct_midwest": reg.get("Midwest", 0.0),
            "pct_south": reg.get("South", 0.0),
            "pct_west": reg.get("West", 0.0),
            "top_states": ", ".join(f"{k} {v / len(g):.0%}" for k, v in top_states.items()),
        })
    prof = pd.DataFrame(rows)
    allrow = {
        "segment": "All established",
        "customers": len(df),
        "share_of_customers": 1.0,
        "annual_value": df.value.mean(),
        "median_age_at_first_card": df.age_at_first_card.median(),
        "median_age_now": df.current_age.median(),
        "pct_under_40_at_first_card": df.age_at_first_card.lt(40).mean(),
        "pct_female": df.gender.eq("Female").mean(),
        "median_yearly_income": df.yearly_income.median(),
        "pct_top_income_fifth": df.top_income_fifth.mean(),
        "pct_bottom_income_fifth": df.bottom_income_fifth.mean(),
        "median_total_debt": df.total_debt.median(),
        "median_credit_score": df.credit_score.median(),
        "median_day_one_credit_limit": df.loc[df.day_one_limit > 0, "day_one_limit"].median(),
        "median_first_card_year": df.first_card_year.median(),
        "median_cards_held": df.n_cards.median(),
        "pct_hold_credit_now": df.holds_credit_now.mean(),
        "pct_premium_now": df.premium_now.mean(),
        "mean_purchase_volume": df.purchase_volume.mean(),
        **{f"pct_{r.lower()}": df.region.eq(r).mean() for r in ["Northeast", "Midwest", "South", "West"]},
        "top_states": ", ".join(f"{k} {v / len(df):.0%}" for k, v in df.state_abbr.value_counts().head(3).items()),
    }
    prof = pd.concat([prof, pd.DataFrame([allrow])], ignore_index=True)
    prof.to_csv(V3 / "segment_profiles.csv", index=False)

    rank_age = df.age_at_first_card.rank()
    checks = {
        "age_at_first_card_vs_value_rank_corr": float(rank_age.corr(df.value.rank())),
        "income_vs_value_rank_corr": float(df.yearly_income.rank().corr(df.value.rank())),
    }
    pd.set_option("display.width", 250)
    print(prof.set_index("segment").T.to_string())
    print(checks)


if __name__ == "__main__":
    main()
