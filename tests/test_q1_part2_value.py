"""Tests for Q1 Part 2: first-year value per customer and how cuts are rated. A silent error here
(a customer without data dropped instead of counted as $0, a half-observed first year included,
the wrong cards treated as day-one, an excluded group left in a rating) would change which
segments look worth having."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q1_part2_value import day_one_cards, dti_band, early_split, first_year_value, rate_dimension  # noqa: E402

RATES = {"credit": 0.018, "debit": 0.0005, "debit_fixed": 0.21, "amex_fee": 120.0}


def test_first_year_value_counts_no_data_as_zero_and_drops_unobserved_years():
    years = pd.DataFrame({"first_card_month": [1, 2, 3], "cohort_year": [2015, 2015, 2018],
                          "years_observed": [3, 3, 0], "has_data": [True, False, False],
                          "year1": [500.0, np.nan, np.nan]}, index=[10, 11, 12])
    fy = first_year_value(years)
    assert fy.index.tolist() == [10, 11]
    assert fy.value.tolist() == [500.0, 0.0]
    assert fy.value_with_data.isna().tolist() == [False, True]


def test_day_one_cards_use_only_the_first_card_month():
    first = pd.Series({1: 100, 2: 200})
    cards = pd.DataFrame({"client_id": [1, 1, 1, 2, 2],
                          "card_type": ["Debit", "Credit", "Credit", "Debit (Prepaid)", "Debit"],
                          "card_brand": ["Visa", "Amex", "Visa", "Mastercard", "Mastercard"],
                          "credit_limit": [3000.0, 15000.0, 40000.0, 50.0, 9000.0],
                          "open_idx": [100, 100, 130, 200, 200]})
    d = day_one_cards(cards, first)
    assert d.loc[1].tolist()[:2] == ["Credit", "Several brands"]
    assert d.loc[1, "day_one_max_limit"] == 15000.0  # the $40k card opened later doesn't count
    assert d.loc[1, "cards_in_first_month"] == "2+"
    assert (d.loc[2, "day_one_product"], d.loc[2, "day_one_brand"]) == ("Debit", "Mastercard")
    assert np.isnan(d.loc[2, "day_one_max_limit"])


def test_debt_to_income_bands():
    assert dti_band(pd.Series([0.0, 0.5, 1.0, 1.99, 2.0, np.nan])).tolist() == [
        "No debt", "Under 1×", "1–2×", "1–2×", "2× or more", "Missing"]


def test_rate_dimension_leaves_out_excluded_groups():
    v = pd.Series([100.0] * 10 + [300.0] * 10 + [999.0] * 5)
    g = pd.Series(["a"] * 10 + ["b"] * 10 + ["No signup record"] * 5)
    r = rate_dimension(v, g, ["No signup record"])
    assert (r["customers"], r["groups"], r["groups_with_10_plus"]) == (20, 2, 2)
    assert r["eta_squared_adjusted"] == pytest.approx(1.0)


def test_early_split_separates_months_1_to_3_from_4_to_12_and_adds_amex_fees():
    first = pd.Series({7: 1000})
    monthly = pd.DataFrame({
        "purchases": [10, 10, 10, 10], "spend": [100.0, 200.0, 300.0, 400.0], "refunds": [0] * 4,
        "refund_amount": [0.0] * 4, "mt_purchases": [0] * 4, "mt_spend": [0.0] * 4, "mt_refunds": [0] * 4,
        "mt_refund_amount": [0.0] * 4},
        index=pd.MultiIndex.from_tuples([(7, 1, 1000), (7, 1, 1002), (7, 1, 1003), (7, 1, 1012)],
                                        names=["client_id", "card_id", "month"]))
    cards = pd.DataFrame({"id": [1], "client_id": [7], "card_type": ["Credit"], "card_brand": ["Amex"],
                          "open_idx": [1000], "expires_idx": [2000]})
    e = early_split({"monthly": monthly}, cards, RATES, first)
    assert e.loc[7, "first_90_days_spend"] == pytest.approx(300.0)
    assert e.loc[7, "first_90_days_revenue"] == pytest.approx(300 * 0.018 + 3 * 10.0)
    # month 1012 is month 13, outside the first year
    assert e.loc[7, "months_4_12_revenue"] == pytest.approx(300 * 0.018 + 9 * 10.0)
