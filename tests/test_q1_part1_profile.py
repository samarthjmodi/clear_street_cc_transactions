"""Tests for the Q1 Part 1 behaviour features and persona choice. A silent error here (a decline
counted as a purchase, online spend counted as out of state, a refund counted as spend, the
wrong cluster count) would misdescribe who our customers are."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q1_part1_profile import behaviour_features, describe_cluster, distribution, pick_k  # noqa: E402


@pytest.fixture(scope="module")
def features() -> pd.DataFrame:
    w = pd.DataFrame({
        "client_id": [1, 1, 1, 1, 1, 1, 2],
        "card_id": [10, 11, 10, 10, 10, 10, 20],
        "ts": pd.to_datetime(["2019-01-05 10:00", "2019-01-05 20:00", "2019-01-08 09:00", "2019-03-08 12:00",
                              "2019-03-09 13:00", "2019-03-10 03:00", "2019-03-10 03:00"]),
        "amt": [100.0, 50.0, 50.0, -20.0, 30.0, 200.0, 40.0],
        "use_chip": ["Chip Transaction", "Online Transaction", "Swipe Transaction", "Chip Transaction",
                     "Chip Transaction", "Chip Transaction", "Chip Transaction"],
        "merchant_id": [1, 2, 1, 1, 3, 3, 9],
        "merchant_state": ["CA", None, "NV", "CA", "Mexico", "Mexico", "CA"],
        "mcc": [5411, 5812, 5541, 5411, 5812, 4829, 5411],
        "errors": [None, None, None, None, "Insufficient Balance", None, "Bad PIN"],
    })
    return behaviour_features(
        w, home_state=pd.Series({1: "California", 2: "California"}),
        card_type=pd.Series({10: "Credit", 11: "Debit", 20: "Debit"}),
        total_credit_limit=pd.Series({1: 10_000.0}), cards_held=pd.Series({1: 3, 2: 1}),
        end=pd.Timestamp("2019-10-31"))


def test_only_settled_purchases_count_and_customers_without_any_are_dropped(features):
    assert features.index.tolist() == [1]
    f = features.loc[1]
    assert (f.purchases, f.spend, f.avg_ticket, f.median_ticket) == (4, 400.0, 100.0, 75.0)


def test_activity_timing(features):
    f = features.loc[1]
    assert (f.active_months, f.active_days, f.median_days_between_purchase_days, f.recency_days) == (2, 3, 32.0, 235)
    assert f.weekend_share == pytest.approx(0.75)
    assert (f["hour_morning (6–12)"], f["hour_evening (18–24)"], f["hour_night (0–6)"]) == (0.5, 0.25, 0.25)


def test_payment_method_and_category_shares_are_of_purchase_dollars(features):
    f = features.loc[1]
    assert (f.online_share, f.chip_share, f.swipe_share) == pytest.approx((0.125, 0.75, 0.125))
    assert f["share_Money transfer"] == pytest.approx(0.5)
    assert f.main_category == "Money transfer"


def test_merchant_concentration(features):
    f = features.loc[1]
    assert (f.distinct_merchants, f.top_merchant_share, f.top5_merchant_share) == (3, 0.5, 1.0)


def test_geography_uses_in_person_spend_only(features):
    f = features.loc[1]
    assert f.in_person_out_of_state_share == pytest.approx(50 / 350)
    assert f.in_person_abroad_share == pytest.approx(200 / 350)
    assert f.merchant_states == 2


def test_declines_and_refunds(features):
    f = features.loc[1]
    assert f.attempts == 6
    assert (f.error_rate, f.insufficient_balance_rate, f.credential_error_rate) == pytest.approx((1 / 6, 1 / 6, 0))
    assert f.refund_share == pytest.approx(20 / 400)


def test_credit_use(features):
    f = features.loc[1]
    assert f.credit_share_of_spend == pytest.approx(350 / 400)
    assert f.monthly_credit_spend_to_limit == pytest.approx(350 / 12 / 10_000)
    assert (f.cards_used, f.share_of_held_cards_used, f.top_card_share) == pytest.approx((2, 2 / 3, 350 / 400))


def test_pick_k_takes_the_most_detailed_stable_solution():
    scores = pd.DataFrame({"k": [2, 3, 4, 5, 6], "silhouette": [0.12, 0.12, 0.10, 0.11, 0.10],
                           "stability_ari": [0.97, 0.88, 0.80, 0.69, 0.67], "smallest_cluster": [440, 98, 86, 65, 9]})
    assert pick_k(scores) == 4


def test_describe_cluster_names_the_largest_deviations():
    z = pd.Series({"online_share": 2.4, "current_age": -0.2, "log_purchases": 1.0})
    assert describe_cluster(z, 2) == "high online share (+2.4 sd); high purchases (log) (+1.0 sd)"


def test_distribution_counts_missing_and_keeps_order():
    d = distribution(pd.Series(["b", "a", None, "a"]), "x", order=["b", "a"])
    assert d.group.tolist() == ["b", "a", "Missing"]
    assert d.customers.tolist() == [1, 2, 1]
    assert d.share.sum() == pytest.approx(1.0)
