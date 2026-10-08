"""Tests for the Q4 counting rules. A silent error in the new/existing split, the cohort
boundaries or the settled-purchase filter changes every incremental count."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q4_brand_campaign import (  # noqa: E402
    acquisition_cohort, classify_signups, customer_first_card, daily_signups, daily_transactions, date_runs,
)

HANDOUT = ROOT / "active_ds_takehome_handout"


@pytest.fixture
def cards_and_signups():
    # client 1: first card 2015 (no signup row), adds a card in 2018
    # client 2: two cards in first month, signups out of order
    # client 3: one card in first month, another two months later
    cards = pd.DataFrame({
        "card_id": [10, 11, 20, 21, 30, 31],
        "client_id": [1, 1, 2, 2, 3, 3],
        "open_m": pd.PeriodIndex(["2015-06", "2018-03", "2019-03", "2019-03", "2019-03", "2019-05"], freq="M"),
    })
    signups = pd.DataFrame({
        "signup_id": ["s1", "s2", "s3", "s4", "s5"],
        "client_id": [1, 2, 2, 3, 3],
        "card_id": [11, 20, 21, 30, 31],
        "signup_ts": pd.to_datetime(["2018-03-20 10:00", "2019-03-10 09:00", "2019-03-05 09:00",
                                     "2019-03-02 12:00", "2019-05-07 08:00"]),
    })
    return cards, signups


def test_first_card_is_earliest_signup_in_first_month_or_month_start(cards_and_signups):
    first = customer_first_card(*cards_and_signups)
    assert first[1] == pd.Timestamp("2015-06-01")
    assert first[2] == pd.Timestamp("2019-03-05 09:00")
    assert first[3] == pd.Timestamp("2019-03-02 12:00")


def test_classify_signups_uses_full_card_history(cards_and_signups):
    cards, signups = cards_and_signups
    kind = classify_signups(signups, cards).set_index("signup_id").kind
    assert kind["s1"] == "existing_customer"
    assert kind["s3"] == "new_customer"
    assert kind["s2"] == "new_customer_extra_card"
    assert kind["s4"] == "new_customer"
    assert kind["s5"] == "existing_customer"


@pytest.mark.parametrize("ts, cohort", [
    ("2019-03-03 23:59", "existing"),
    ("2019-03-04 00:00", "campaign"),
    ("2019-03-17 23:59", "campaign"),
    ("2019-03-18 00:00", "post"),
    ("2019-03-31 23:59", "post"),
    ("2019-04-01 00:00", "later"),
])
def test_acquisition_cohort_boundaries(ts, cohort):
    assert acquisition_cohort(pd.Series([pd.Timestamp(ts)])).iloc[0] == cohort


def _txns(rows):
    df = pd.DataFrame(rows, columns=["date", "client_id", "amount", "errors"])
    return df.astype({"date": "string", "amount": "string", "errors": "string"})


def test_daily_transactions_counts_only_settled_purchases():
    chunk = _txns([
        ("2019-03-04 10:00:00", 1, "$10.00", None),
        ("2019-03-04 11:00:00", 1, "$-5.00", None),
        ("2019-03-04 12:00:00", 1, "$20.00", "Insufficient Balance"),
        ("2019-03-04 13:00:00", 2, "$1,000.50", None),
        ("2019-03-05 09:00:00", 1, "$0.00", None),
    ])
    out = daily_transactions(chunk, pd.Series({1: "existing", 2: "campaign"})).set_index(["date", "cohort"])
    e = out.loc[("2019-03-04", "existing")]
    assert (e.rows, e.purchases, e.purchase_volume, e.refunds, e.refund_volume, e.failed) == (3, 1, 10.0, 1, 5.0, 1)
    c = out.loc[("2019-03-04", "campaign")]
    assert (c.purchases, c.purchase_volume) == (1, 1000.5)
    z = out.loc[("2019-03-05", "existing")]
    assert (z.rows, z.purchases, z.refunds, z.failed) == (1, 0, 0, 0)
    assert out.rows.sum() == len(chunk)


def test_daily_transactions_rejects_customer_without_a_card():
    chunk = _txns([("2019-03-04 10:00:00", 99, "$10.00", None)])
    with pytest.raises(ValueError):
        daily_transactions(chunk, pd.Series({1: "existing"}))


def test_daily_signups_splits_new_and_existing_and_fills_empty_days():
    classified = pd.DataFrame({
        "signup_ts": pd.to_datetime(["2019-03-04 09:00", "2019-03-04 15:00", "2019-03-06 10:00"]),
        "kind": ["new_customer", "existing_customer", "new_customer_extra_card"],
    })
    d = daily_signups(classified, "2019-03-04", "2019-03-06")
    assert d.loc["2019-03-04"].tolist() == [2, 1, 1, 1]
    assert d.loc["2019-03-05"].tolist() == [0, 0, 0, 0]
    assert d.loc["2019-03-06"].tolist() == [1, 1, 0, 0]


def test_date_runs_collapses_consecutive_days():
    days = pd.to_datetime(["2019-06-03", "2019-06-04", "2019-06-05", "2019-06-09"])
    assert date_runs(days) == [["2019-06-03", "2019-06-05"], ["2019-06-09", "2019-06-09"]]


@pytest.mark.skipif(not (HANDOUT / "account_signups.csv").exists(), reason="handout data not present")
def test_new_customers_per_year_match_first_card_year_in_cards_data():
    from q4_brand_campaign import load_cards

    cards = load_cards()
    signups = pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"])
    classified = classify_signups(signups, cards)
    from_signups = classified[classified.kind == "new_customer"].signup_ts.dt.year.value_counts()
    from_cards = cards.groupby("client_id").open_m.min().dt.year.value_counts()
    for year in range(2016, 2021):
        assert from_signups.get(year, 0) == from_cards.get(year, 0)
