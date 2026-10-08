import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from q1_v3_segments import holdings, new_customer_value_ci, segment_of  # noqa: E402


def test_segment_rules_and_limit_boundary():
    has_credit = pd.Series([True, True, True, False, False])
    limit = pd.Series([10_000, 9_999, 0, 0, 0])
    has_debit = pd.Series([False, True, False, True, False])
    assert list(segment_of(has_credit, limit, has_debit)) == [
        "Premium credit", "Core credit", "Core credit", "Debit", "Prepaid",
    ]


def test_holdings_uses_highest_credit_limit_like_q1_part2():
    cards = pd.DataFrame({
        "client_id": [1, 1, 1, 2, 3, 4],
        "card_type": ["Credit", "Credit", "Debit", "Debit", "Debit (Prepaid)", "Credit"],
        "credit_limit": [7_000, 6_000, 50_000, 30_000, 500, 10_000],
    })
    h = holdings(cards)
    assert h.loc[1, "credit_limit"] == 7_000
    assert h.loc[1, "segment"] == "Core credit"
    assert h.loc[2, "segment"] == "Debit"
    assert h.loc[3, "segment"] == "Prepaid"
    assert h.loc[4, "segment"] == "Premium credit"


def test_new_customer_value_ci_missing_as_zero_and_horizon():
    nan = float("nan")
    cohort = pd.DataFrame({
        "segment": ["Debit"] * 4,
        "observed": [True, True, False, False],
        "y1_value_prepaid_debit": [100.0, 300.0, 0.0, 95.0],
        "y2_value_prepaid_debit": [100.0, 300.0, 0.0, nan],
        "y3_value_prepaid_debit": [100.0, 300.0, 0.0, nan],
    })
    cohort["cum3"] = cohort[[f"y{k}_value_prepaid_debit" for k in (1, 2, 3)]].sum(axis=1, min_count=3)
    t = new_customer_value_ci(cohort).set_index(["segment", "year"])
    assert t.loc[("Debit", "y1"), "mean"] == 200.0
    assert t.loc[("Debit", "y1"), "n_all"] == 4
    assert t.loc[("Debit", "y1"), "mean_missing_as_zero"] == 100.0
    assert t.loc[("Debit", "cum3"), "mean"] == 600.0
    assert t.loc[("Debit", "cum3"), "n_all"] == 3
    assert t.loc[("Debit", "cum3"), "mean_missing_as_zero"] == 400.0
