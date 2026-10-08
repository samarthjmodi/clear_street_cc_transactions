import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from q1_v3_robustness import auc, limit_drift, net_of_cost, spend_vs_revenue  # noqa: E402


def test_auc_perfect_random_and_ties():
    label = pd.Series([False, False, True, True])
    assert auc(pd.Series([1, 2, 3, 4]), label) == 1.0
    assert auc(pd.Series([4, 3, 2, 1]), label) == 0.0
    assert auc(pd.Series([1, 1, 1, 1]), label) == 0.5


def test_spend_vs_revenue_ratios_bands_and_missing_revenue():
    active = pd.DataFrame({"client_id": [1, 2, 3, 4], "persona": ["P1", "P1", "P2", "P2"],
                           "spend": [100.0, 300.0, 200.0, 200.0],
                           "credit_share_of_spend": [1.0, 0.5, 0.0, 0.0]})
    revenue = pd.Series({1: 2.0, 2: 3.0, 3: 1.0})
    by_persona, by_credit, _ = spend_vs_revenue(active, revenue)
    assert by_persona.loc["Younger credit users", "revenue_per_100_spend"] == pytest.approx(5.0 / 400 * 100)
    assert by_persona.loc["Debit-only everyday spenders", "median_revenue"] == 0.5
    assert by_credit.loc["Everything on credit", "customers"] == 1
    assert by_credit.loc["Some on credit", "customers"] == 1
    assert by_credit.loc["Nothing on credit", "customers"] == 2


def test_limit_drift_compares_earliest_and_latest_credit_card():
    cards = pd.DataFrame({
        "card_id": [1, 2, 3, 4, 5, 6],
        "client_id": [1, 1, 2, 2, 3, 3],
        "card_type": ["Credit", "Credit", "Credit", "Credit", "Credit", "Debit"],
        "open_m": [24_000, 24_100, 24_000, 24_100, 24_000, 24_100],
        "credit_limit": [5_000, 3_000, 2_000, 4_000, 6_000, 50_000],
    })
    income = pd.Series({1: 20_000, 2: 20_000, 3: 30_000})
    _, stats = limit_drift(cards, income)
    assert stats["customers_with_credit_cards_opened_apart"] == 2
    assert stats["share_earliest_card_higher_limit"] == 0.5
    assert stats["share_equal_limits"] == 0.0


def test_net_of_cost_scales_with_credit_spend():
    # $180 credit interchange = $10k credit spend; 1% cost = $100
    value = pd.Series([200.0, 50.0])
    credit_ic = pd.Series([180.0, 0.0])
    out = net_of_cost(value, credit_ic, 0.01)
    assert out.tolist() == pytest.approx([100.0, 50.0])
    assert net_of_cost(value, credit_ic, 0.0).tolist() == value.tolist()
