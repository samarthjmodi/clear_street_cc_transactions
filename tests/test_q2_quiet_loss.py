"""Tests for Q2 quiet-loss definitions. A silent error here (wrong gap, counting
terminal silence as a return, or mis-assigning the $10k day-one cut) would change
the early-warning rule."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q2_quiet_loss import (day_one_segment, gap_features, silence_episodes,  # noqa: E402
                           silence_summary, structural_exit)


def test_day_one_segment_splits_credit_at_10k():
    product = pd.Series({1: "Credit", 2: "Credit", 3: "Credit", 4: "Debit", 5: "Prepaid"})
    limit = pd.Series({1: 10_000.0, 2: 9_999.0, 3: np.nan, 4: np.nan, 5: 50.0})
    s = day_one_segment(product, limit)
    assert s.tolist() == [
        "Credit, limit $10k+",
        "Credit, limit under $10k",
        "Credit, limit under $10k",
        "Debit",
        "Prepaid",
    ]


def test_gap_features_median_max_and_terminal_silence():
    days = pd.DataFrame({
        "client_id": [1, 1, 1, 2, 2],
        "day": pd.to_datetime(["2019-01-01", "2019-01-02", "2019-01-10", "2019-10-01", "2019-10-20"]),
    })
    end = pd.Timestamp("2019-10-31")
    g = gap_features(days, end=end)
    assert g.loc[1, "median_gap_days"] == 4.5  # gaps 1 and 8
    assert g.loc[1, "max_gap_days"] == 8.0
    assert g.loc[1, "terminal_silence_days"] == (end - pd.Timestamp("2019-01-10")).days
    assert g.loc[2, "max_gap_days"] == 19.0
    assert g.loc[2, "terminal_silence_days"] == 11


def test_silence_episodes_return_rule_and_terminal_excluded_from_return():
    # gaps: 10 (returns within 7+30), 50 (does not); terminal silence excluded from return
    days = pd.DataFrame({
        "client_id": [9, 9, 9],
        "day": pd.to_datetime(["2019-01-01", "2019-01-11", "2019-03-02"]),
    })
    end = pd.Timestamp("2019-10-31")
    ep = silence_episodes(days, n=7, end=end, return_days=30)
    inter = ep[~ep.terminal].sort_values("gap_days")
    assert inter.gap_days.tolist() == [10, 50]
    assert inter.returned_within_return_window.tolist() == [True, False]
    term = ep[ep.terminal]
    assert len(term) == 1
    assert pd.isna(term.iloc[0].returned_within_return_window)


def test_silence_summary_hit_rate_by_segment():
    customers = pd.DataFrame({
        "day_one_segment": ["Debit", "Debit", "Credit, limit $10k+"],
    }, index=[1, 2, 3])
    episodes = pd.DataFrame({
        "client_id": [1, 1, 3],
        "n": [14, 14, 14],
        "gap_days": [20, 40, 15],
        "terminal": [False, True, False],
        "returned_within_return_window": [True, pd.NA, True],
    })
    s = silence_summary(customers, episodes, n=14)
    debit = s[s.day_one_segment.eq("Debit")].iloc[0]
    assert debit.customers == 2
    assert debit.hit_customers == 1
    assert debit.hit_rate == pytest.approx(0.5)
    assert debit.inter_purchase_episodes == 1
    assert debit.terminal_silence_customers == 1
    assert debit.return_rate_given_inter_purchase_silence == pytest.approx(1.0)


def test_silence_summary_does_not_count_terminal_as_inter_purchase():
    """Object-dtype True must not be flipped by ~ into an inter-purchase episode."""
    customers = pd.DataFrame({"day_one_segment": ["Debit", "Debit"]}, index=[375, 711])
    episodes = pd.DataFrame({
        "client_id": [375, 711],
        "n": [30, 30],
        "gap_days": [31, 31],
        "terminal": [True, True],  # object-friendly construction
        "returned_within_return_window": [pd.NA, pd.NA],
    }).astype({"terminal": object})
    s = silence_summary(customers, episodes, n=30)
    all_row = s[s.day_one_segment.eq("All active")].iloc[0]
    assert all_row.inter_purchase_episodes == 0
    assert all_row.terminal_silence_customers == 2
    assert all_row.hit_customers == 2


def test_structural_exit_no_open_card_at_snapshot():
    cards = pd.DataFrame({
        "client_id": [1, 1, 2, 3],
        "open_idx": [2010 * 12 + 1, 2015 * 12 + 1, 2010 * 12 + 1, 2019 * 12 + 6],
        "expires_idx": [2018 * 12 + 1, 2025 * 12 + 1, 2019 * 12 + 1, 2025 * 12 + 1],
    })
    # snapshot Feb 2020 = 2020*12+2
    out = structural_exit(cards, pd.Index([1, 2, 3]), snapshot_idx=2020 * 12 + 2)
    assert out.tolist() == [False, True, False]  # 1 has open card; 2 expired; 3 still open
