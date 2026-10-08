"""Tests for the Q1 step 1 building blocks. A silent error here (wrong rate, fee charged for a
whole year on a card opened mid-window, a band boundary off by one, an unmapped merchant code or
state) would move a segment's revenue or put customers in the wrong group."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q1_customer_value import (CENSUS_REGION, MCC_CATEGORY, adjusted_eta_squared, amex_fee,  # noqa: E402
                               age_at, amex_fee_by_tenure_year, as_of_month_share, auc, best_split, brand_label,
                               chargeable, customer_revenue, day_one_and_today, eta_squared, full_years_observed,
                               interchange, join_period, money, permutation_p, products_label, quintiles,
                               rank_stability, scheme_labels, score_band, tenure_year)

RATES = {"credit": 0.018, "debit": 0.0005, "debit_fixed": 0.21, "amex_fee": 95.0}
WINDOW = (2018 * 12 + 11, 2019 * 12 + 10)


def test_money_parses_dollar_strings_including_negatives():
    assert money(pd.Series(["$1,234.50", "$-77.00", "$0"])).tolist() == [1234.5, -77.0, 0.0]


def test_interchange_applies_the_rate_card_with_prepaid_at_debit_rate_or_zero():
    args = ([1000.0, 1000.0, 1000.0], [10, 10, 10], ["Credit", "Debit", "Debit (Prepaid)"], RATES)
    assert interchange(*args).tolist() == pytest.approx([18.0, 2.6, 2.6])
    assert interchange(*args, prepaid="zero").tolist() == pytest.approx([18.0, 2.6, 0.0])


FLOWS = pd.DataFrame({"purchases": [10], "spend": [500.0], "refunds": [2], "refund_amount": [-50.0],
                      "mt_purchases": [1], "mt_spend": [100.0], "mt_refunds": [0], "mt_refund_amount": [0.0]})


@pytest.mark.parametrize("model, volume, count", [
    ({"net_refunds": True, "money_transfer": "full"}, 450.0, 8),
    ({"net_refunds": False, "money_transfer": "full"}, 500.0, 10),
    ({"net_refunds": True, "money_transfer": "zero"}, 350.0, 7),
])
def test_chargeable_nets_refunds_and_can_drop_money_transfers(model, volume, count):
    v, n = chargeable(FLOWS, model)
    assert (v.iloc[0], n.iloc[0]) == (pytest.approx(volume), count)


def test_customer_revenue_end_to_end():
    cards = pd.DataFrame({"id": [1, 2, 3, 4], "client_id": [7, 7, 8, 9],
                          "card_type": ["Credit", "Debit", "Debit (Prepaid)", "Credit"],
                          "card_brand": ["Amex", "Visa", "Visa", "Amex"],
                          "open_idx": [2015 * 12 + 1] * 4, "expires_idx": [2024 * 12 + 1] * 4})
    by_card = pd.DataFrame({"purchases": [10, 10, 5], "spend": [1000.0, 500.0, 100.0], "refunds": [1, 2, 0],
                            "refund_amount": [-100.0, -50.0, 0.0], "mt_purchases": [0, 0, 0],
                            "mt_spend": [0.0, 0.0, 0.0], "mt_refunds": [0, 0, 0], "mt_refund_amount": [0.0] * 3},
                           index=pd.MultiIndex.from_tuples([(7, 1), (7, 2), (8, 3)], names=["client_id", "card_id"]))
    active = pd.Series({7: True, 8: True, 9: False})
    model = {"net_refunds": True, "prepaid": "debit", "money_transfer": "full", "amex_fee": True}
    r = customer_revenue(by_card, cards, RATES, model, active)
    # client 7: credit 900 x 1.8% + debit (450 x 0.05% + 8 x 21c) + a full year of Amex fee
    assert r.loc[7, "revenue"] == pytest.approx(16.2 + 0.225 + 1.68 + 95.0)
    assert r.loc[8, "revenue"] == pytest.approx(0.05 + 1.05)
    assert r.loc[9, "revenue"] == 0.0  # holds an Amex but isn't active, so no fee


def test_amex_fee_is_prorated_by_months_open_in_the_window():
    # opened before, mid-window, last month, after; expired mid-window; expired before; not Amex
    open_idx = [2015 * 12 + 1, 2019 * 12 + 5, 2019 * 12 + 10, 2019 * 12 + 11, 2015 * 12 + 1, 2010 * 12 + 1,
                2015 * 12 + 1]
    expires = [2024 * 12 + 1] * 4 + [2019 * 12 + 1, 2018 * 12 + 10, 2024 * 12 + 1]
    brands = ["Amex"] * 6 + ["Visa"]
    fee = amex_fee(brands, ["Credit"] * 7, open_idx, expires, 95.0, WINDOW)
    assert fee.tolist() == pytest.approx([95.0, 95 * 6 / 12, 95 / 12, 0.0, 95 * 3 / 12, 0.0, 0.0])


def test_as_of_month_share_finds_the_month_ages_were_taken():
    birth_year, birth_month = pd.Series([1960, 1975, 1990]), pd.Series([3, 11, 6])
    age = pd.Series([59, 44, 29])  # all right in Jan 2020, wrong by Jul 2020 for the 1990 June birth
    share = as_of_month_share(birth_year, birth_month, age, range(2019 * 12 + 1, 2021 * 12 + 1))
    assert share[2020 * 12 + 1] == 1.0
    assert share[2020 * 12 + 7] < 1.0


def test_score_bands_put_boundaries_in_the_upper_band():
    assert score_band(pd.Series([579, 580, 669, 670, 739, 740, 799, 800])).tolist() == [
        "Under 580", "580–669", "580–669", "670–739", "670–739", "740–799", "740–799", "800+"]


def test_quintiles_make_five_equal_groups_labelled_by_their_ranges():
    q = quintiles(pd.Series(np.arange(1, 101, dtype=float)))
    assert q.value_counts().tolist() == [20] * 5
    assert q.iloc[0] == "Q1 (1–20)" and q.iloc[-1] == "Q5 (81–100)"


def test_products_and_brand_labels():
    assert products_label({"Debit"}) == "Debit only"
    assert products_label({"Credit", "Debit", "Debit (Prepaid)"}) == "Credit + debit + prepaid"
    assert products_label(set()) == "No open card in window"
    assert brand_label({"Visa", "Amex"}) == "Any Amex"
    assert brand_label({"Visa", "Mastercard"}) == "Multi-brand, no Amex"
    assert brand_label({"Visa"}) == "Visa only"


def test_eta_squared_is_one_when_groups_explain_everything_and_zero_when_nothing():
    v = pd.Series([1.0, 1.0, 5.0, 5.0])
    assert eta_squared(v, pd.Series(["a", "a", "b", "b"])) == pytest.approx(1.0)
    assert eta_squared(v, pd.Series(["a", "b", "a", "b"])) == pytest.approx(0.0)


def test_adjusted_eta_squared_removes_what_many_groups_explain_by_chance():
    rng = np.random.default_rng(1)
    v = pd.Series(rng.normal(size=1200))
    g = pd.Series(rng.integers(0, 50, size=1200))
    raw = eta_squared(v, g)
    assert raw > 0.02
    assert abs(adjusted_eta_squared(raw, 1200, 50)) < 0.02
    assert permutation_p(v, g, n_perm=199) > 0.05
    assert permutation_p(v, pd.Series(np.where(v > 0, "hi", "lo")), n_perm=199) < 0.01


def test_tenure_years_start_in_the_first_card_month_and_stop_after_three():
    first = 2015 * 12 + 3
    months = [first - 1, first, first + 11, first + 12, first + 35, first + 36]
    assert tenure_year(months, first).tolist() == [0, 1, 1, 2, 3, 0]


def test_full_years_observed_counts_only_complete_years_by_oct_2019():
    oct_2017, nov_2016, jan_2010 = 2017 * 12 + 10, 2016 * 12 + 11, 2010 * 12 + 1
    assert full_years_observed([oct_2017, nov_2016, jan_2010]).tolist() == [2, 3, 3]


def test_amex_fee_accrues_by_month_within_each_tenure_year():
    first = pd.Series({1: 2015 * 12 + 1})
    cards = pd.DataFrame({"client_id": [1, 1], "card_brand": ["Amex", "Visa"], "card_type": ["Credit", "Credit"],
                          "open_idx": [2015 * 12 + 7, 2015 * 12 + 1], "expires_idx": [2016 * 12 + 6, 2030 * 12]})
    fees = amex_fee_by_tenure_year(cards, first, 120.0)
    # Amex open Jul 2015 - Jun 2016: 6 months in year 1, 6 in year 2, none in year 3
    assert fees.loc[1].tolist() == pytest.approx([60.0, 60.0, 0.0])


def test_best_split_finds_the_break_in_revenue():
    x = pd.Series(np.arange(1000, 30001, 250, dtype=float))
    y = pd.Series(np.where(x >= 12000, 600.0, 300.0)) + np.sin(x) * 10
    cut, _ = best_split(x, y)
    assert cut == 12000.0


def test_day_one_uses_only_first_month_cards_and_today_only_cards_open_in_oct_2019():
    first = pd.Series({1: 2012 * 12 + 5})
    cards = pd.DataFrame({"client_id": [1, 1, 1], "card_type": ["Debit", "Credit", "Credit"],
                          "credit_limit": [5000.0, 9000.0, 20000.0],
                          "open_idx": [2012 * 12 + 5, 2013 * 12 + 1, 2014 * 12 + 1],
                          "expires_idx": [2022 * 12, 2018 * 12, 2023 * 12]})
    day1, today = day_one_and_today(cards, first)
    assert (day1.loc[1, "product"], day1.loc[1, "product_raw"]) == ("Debit or prepaid", "Debit")
    assert (today.loc[1, "product"], today.loc[1, "max_credit_limit"]) == ("Credit", 20000.0)


def test_scheme_labels_split_credit_by_limit_and_the_rest_by_income():
    h = pd.DataFrame({"product": ["Credit", "Credit", "Debit or prepaid", None],
                      "max_credit_limit": [15000.0, 5000.0, np.nan, np.nan]})
    income = pd.Series([30000.0, 60000.0, 60000.0, 40000.0])
    s = scheme_labels(h, income, 12000.0, 45000.0)
    assert s.product_limit_income.tolist() == ["Credit, limit $12.0k+", "Credit, limit under $12.0k",
                                               "Debit or prepaid, income $45.0k+", "No open card"]
    assert s.product_income.tolist()[0] == "Credit, income under $45.0k"


def test_rank_stability_is_high_for_well_separated_groups_and_low_for_ties():
    rng = np.random.default_rng(3)
    g = pd.Series(["a"] * 50 + ["b"] * 50)
    apart = pd.Series(np.r_[rng.normal(10, 1, 50), rng.normal(0, 1, 50)])
    tied = pd.Series(rng.normal(0, 1, 100))
    assert rank_stability(apart, g, n=200) > 0.99
    assert rank_stability(tied, g, n=200) < 0.9


def test_age_at_first_card_counts_completed_years():
    birth_year, birth_month = pd.Series([1980, 1980]), pd.Series([6, 6])
    assert age_at([2010 * 12 + 5, 2010 * 12 + 6], birth_year, birth_month).tolist() == [29, 30]


def test_auc_is_one_for_perfect_separation_and_half_for_none():
    score = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert auc(score, pd.Series([False, False, True, True])) == pytest.approx(1.0)
    assert auc(score, pd.Series([True, False, False, True])) == pytest.approx(0.5)
    assert auc(pd.Series([1.0, 1.0]), pd.Series([True, False])) == pytest.approx(0.5)


def test_join_periods_split_at_2010_2018_and_the_end_of_the_data():
    idx = pd.Series([2009 * 12 + 12, 2010 * 12 + 1, 2017 * 12 + 12, 2018 * 12 + 1, 2019 * 12 + 10, 2019 * 12 + 11])
    assert join_period(idx).tolist() == ["Joined before 2010", "Joined 2010–2017", "Joined 2010–2017",
                                         "Joined 2018 – Oct 2019", "Joined 2018 – Oct 2019",
                                         "Joined Nov 2019 – Feb 2020"]


def test_every_merchant_code_has_a_category():
    codes = json.loads((ROOT / "active_ds_takehome_handout" / "mcc_codes.json").read_text())
    assert set(codes) <= set(MCC_CATEGORY)


def test_census_regions_cover_50_states_and_dc():
    assert len(CENSUS_REGION) == 51
    assert pd.Series(CENSUS_REGION).value_counts().to_dict() == {"South": 17, "West": 13, "Midwest": 12,
                                                                 "Northeast": 9}
