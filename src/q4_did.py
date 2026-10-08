"""Difference-in-differences estimators for Q4.

Two designs, both comparing each period's change from the pre period:
- channel: brand search against control channels on the same days (gap_did)
- year over year: 2019 against the same weekdays 364 days earlier (yoy_did)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

YEAR = pd.Timedelta(days=364)


def shift(periods: dict, delta: pd.Timedelta) -> dict:
    return {k: (str((pd.Timestamp(a) + delta).date()), str((pd.Timestamp(z) + delta).date()))
            for k, (a, z) in periods.items()}


def span(periods: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    return (min(pd.Timestamp(a) for a, _ in periods.values()),
            max(pd.Timestamp(z) for _, z in periods.values()))


def period_means(s: pd.Series, periods: dict) -> pd.Series:
    return pd.Series({k: s.loc[a:z].mean() for k, (a, z) in periods.items()})


def gap_did(panel: pd.DataFrame, treated: str, controls: list[str], periods: dict,
            ref: str = "pre", log: bool = True) -> pd.Series:
    """Treated-minus-controls gap in each period, less the gap in the reference period.

    panel: one row per day, one column per channel. With log=True the gap is
    log(treated) - mean log(controls), so exp(estimate) - 1 is the proportional effect.
    On a balanced panel this equals the two-way fixed-effects (channel + day) estimate."""
    y = panel[[treated, *controls]].astype(float)
    if log:
        y = np.log(y)
    gap = y[treated] - y[controls].mean(axis=1)
    m = period_means(gap, periods)
    return (m - m[ref]).drop(ref)


def yoy_did(s: pd.Series, periods: dict, last_periods: dict | None = None,
            ref: str = "pre", log: bool = False) -> pd.DataFrame:
    """Each period's change from ref this year, less the same change last year.

    s: daily series. last_periods defaults to the same weekdays 364 days earlier.
    log=False gives the effect in units per day; log=True a log-point effect."""
    last_periods = last_periods or shift(periods, -YEAR)
    this, last = period_means(s, periods), period_means(s, last_periods)
    if log:
        did = (np.log(this) - np.log(this[ref])) - (np.log(last) - np.log(last[ref]))
    else:
        did = (this - this[ref]) - (last - last[ref])
    return pd.DataFrame({"this_year": this, "last_year": last, "did": did}).drop(ref)


def placebo_starts(periods: dict, first: str, last_end: str, exclude: list[tuple[str, str]] = ()) -> list:
    """Start dates for placebo windows with the same layout as `periods`, moved in whole
    weeks so weekdays line up, ending by last_end, and overlapping none of `exclude`
    (the real window is always excluded)."""
    start, end = span(periods)
    length = end - start
    blocked = [(start, end)] + [(pd.Timestamp(a), pd.Timestamp(z)) for a, z in exclude]
    first_ts = pd.Timestamp(first)
    offset = (start - first_ts).days % 7
    candidates = pd.date_range(first_ts + pd.Timedelta(days=offset), pd.Timestamp(last_end) - length, freq="7D")
    return [s for s in candidates if all(s > z or s + length < a for a, z in blocked)]


def placebo_summary(estimate: float, placebos: pd.Series) -> dict:
    """Where the real estimate sits among placebo estimates. p_value is the two-sided
    permutation share: (1 + placebos at least as large in absolute value) / (n + 1)."""
    p = pd.Series(placebos, dtype=float).dropna()
    return {
        "estimate": float(estimate),
        "placebo_n": int(len(p)),
        "placebo_mean": float(p.mean()),
        "placebo_sd": float(p.std()),
        "placebo_p05": float(p.quantile(0.05)),
        "placebo_p95": float(p.quantile(0.95)),
        "p_value": float((1 + (p.abs() >= abs(estimate)).sum()) / (len(p) + 1)),
        "min_detectable_effect": float(2.8 * p.std()),
    }


def upper_90(total: float, actual: float, pct_sd: float) -> float:
    """Top of a 90% range in level terms: the level estimate plus 1.645 placebo SDs, with the
    placebo SD (a % effect) converted to levels at the no-campaign level, actual - total."""
    return total + 1.645 * pct_sd * (actual - total)
