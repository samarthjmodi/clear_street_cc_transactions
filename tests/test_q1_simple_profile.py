import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from q1_simple_profile import chance_gap, day_one_segment, lowest_and_highest  # noqa: E402


def test_day_one_segment_splits_credit_at_10k_band():
    product = pd.Series(["Credit", "Credit", "Credit", "Debit", "Prepaid"])
    band = pd.Series(["$10–15k", "$5–10k", "$25k+", "No credit card on day one", "No credit card on day one"])
    assert list(day_one_segment(product, band)) == [
        "Credit, limit $10k+", "Credit, limit under $10k", "Credit, limit $10k+", "Debit", "Prepaid"]


def test_lowest_and_highest_skips_small_and_non_groups():
    d = pd.DataFrame({
        "region": ["A"] * 3 + ["B"] * 3 + ["C"] + ["No signup record"] * 3,
        "value_with_data": [100, 100, 100, 400, 400, 400, 9_999, 0, 0, 0],
    })
    r = lowest_and_highest(d, "region", min_group=3)
    assert r["groups_compared"] == 2
    assert (r["lowest_group"], r["highest_group"]) == ("A", "B")
    assert r["gap"] == 300


def test_chance_gap_is_zero_when_everyone_earns_the_same_and_positive_otherwise():
    flat = pd.DataFrame({"g": ["A"] * 5 + ["B"] * 5, "value_with_data": [50.0] * 10})
    assert chance_gap(flat, "g", min_group=5, n=50) == 0
    mixed = pd.DataFrame({"g": ["A"] * 5 + ["B"] * 5, "value_with_data": [0.0] * 5 + [100.0] * 5})
    assert 0 < chance_gap(mixed, "g", min_group=5, n=200) < 100
