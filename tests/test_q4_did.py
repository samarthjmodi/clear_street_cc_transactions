"""Tests for the Q4 difference-in-differences estimators and the interchange model. A silent
error here (wrong reference period, misaligned weekdays, placebo windows overlapping the
campaign, wrong rate applied) would change the incremental estimates."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q4_brand_campaign import daily_purchases, interchange  # noqa: E402
from q4_did import YEAR, gap_did, placebo_starts, placebo_summary, shift, upper_90, yoy_did  # noqa: E402

PERIODS = {"pre": ("2019-02-18", "2019-03-03"), "campaign": ("2019-03-04", "2019-03-17"),
           "post": ("2019-03-18", "2019-03-31")}
DAYS = pd.date_range("2019-02-18", "2019-03-31")


def _panel(seed=0, effect=0.0):
    rng = np.random.default_rng(seed)
    base = {"brand": 100, "a": 50, "b": 80, "c": 30}
    day_effect = rng.normal(0, 0.1, len(DAYS))
    p = pd.DataFrame({ch: np.exp(np.log(v) + day_effect + rng.normal(0, 0.05, len(DAYS))) for ch, v in base.items()},
                     index=DAYS)
    p.loc["2019-03-04":"2019-03-17", "brand"] *= np.exp(effect)
    return p


def test_gap_did_recovers_a_known_effect_net_of_common_shocks():
    clean = pd.DataFrame({"brand": 100.0, "a": 50.0, "b": 80.0, "c": 30.0}, index=DAYS)
    clean = clean.mul(np.linspace(1, 1.5, len(DAYS)), axis=0)  # common trend hits every channel
    clean.loc["2019-03-04":"2019-03-17", "brand"] *= 2
    est = gap_did(clean, "brand", ["a", "b", "c"], PERIODS)
    assert np.expm1(est["campaign"]) == pytest.approx(1.0)
    assert est["post"] == pytest.approx(0.0, abs=1e-12)


def test_gap_did_equals_two_way_fixed_effects_regression():
    p = _panel(seed=3, effect=0.3)
    y = np.log(p).stack().rename("y").reset_index()
    y.columns = ["date", "channel", "y"]
    period = pd.Series("pre", index=DAYS)
    period.loc["2019-03-04":"2019-03-17"], period.loc["2019-03-18":"2019-03-31"] = "campaign", "post"
    y["campaign"] = ((y.channel == "brand") & y.date.map(period).eq("campaign")).astype(float)
    y["post"] = ((y.channel == "brand") & y.date.map(period).eq("post")).astype(float)
    X = pd.concat([pd.get_dummies(y.channel, drop_first=True), pd.get_dummies(y.date.astype(str)),
                   y[["campaign", "post"]]], axis=1).astype(float)
    beta = np.linalg.lstsq(X.to_numpy(), y.y.to_numpy(), rcond=None)[0]
    coef = pd.Series(beta, index=X.columns)
    est = gap_did(p, "brand", ["a", "b", "c"], PERIODS)
    assert est["campaign"] == pytest.approx(coef["campaign"])
    assert est["post"] == pytest.approx(coef["post"])


def test_yoy_did_compares_same_weekdays_a_year_earlier():
    days = pd.date_range("2018-01-01", "2019-12-31")
    s = pd.Series(np.where(days.dayofweek == 5, 30.0, 10.0), index=days)  # Saturdays busier
    s.loc["2019-01-01":] += 2.0  # a level shift between years must not count as an effect
    s.loc["2019-03-04":"2019-03-17"] += 5.0
    out = yoy_did(s, PERIODS)
    assert out.did["campaign"] == pytest.approx(5.0)
    assert out.did["post"] == pytest.approx(0.0)
    last = shift(PERIODS, -YEAR)
    assert pd.Timestamp(last["campaign"][0]).dayofweek == pd.Timestamp(PERIODS["campaign"][0]).dayofweek


def test_yoy_did_accepts_explicit_last_year_periods():
    days = pd.date_range("2018-01-01", "2019-12-31")
    s = pd.Series(1.0, index=days)
    s.loc["2019-03-01":"2019-03-31"] = 3.0
    this = {"pre": ("2019-01-01", "2019-02-28"), "campaign": ("2019-03-01", "2019-03-31")}
    last = {"pre": ("2018-01-01", "2018-02-28"), "campaign": ("2018-03-01", "2018-03-31")}
    assert yoy_did(s, this, last).did["campaign"] == pytest.approx(2.0)


def test_placebo_windows_keep_weekdays_and_avoid_the_real_window_and_exclusions():
    starts = placebo_starts(PERIODS, "2018-01-01", "2019-12-31", exclude=[("2019-06-03", "2019-06-23")])
    real_start, real_end = pd.Timestamp("2019-02-18"), pd.Timestamp("2019-03-31")
    length = real_end - real_start
    assert starts and all(s.dayofweek == real_start.dayofweek for s in starts)
    for s in starts:
        assert s + length < real_start or s > real_end
        assert s + length < pd.Timestamp("2019-06-03") or s > pd.Timestamp("2019-06-23")
        assert s + length <= pd.Timestamp("2019-12-31")


def test_placebo_summary_p_value_counts_placebos_at_least_as_large():
    s = placebo_summary(0.5, pd.Series([0.1, -0.6, 0.2, 0.0]))
    assert s["p_value"] == pytest.approx(2 / 5)


def test_upper_90_converts_the_placebo_sd_at_the_no_campaign_level():
    # 1,100 observed with an estimated +100 means 1,000 without the campaign; 1 SD = 1% of that
    assert upper_90(100, 1_100, 0.01) == pytest.approx(100 + 1.645 * 10)


def test_interchange_applies_the_rate_card_by_card_type():
    rates = {"credit": 0.018, "debit": 0.0005, "debit_fixed": 0.21}
    out = interchange(np.array([100.0, 100.0, 100.0]), np.array(["Credit", "Debit", "Debit (Prepaid)"]), rates)
    assert out.tolist() == pytest.approx([1.8, 0.26, 0.0])


def test_daily_purchases_keeps_settled_purchases_and_flags_new_cards():
    chunk = pd.DataFrame({
        "date": ["2019-03-05 10:00:00", "2019-03-05 11:00:00", "2019-03-05 12:00:00", "2019-03-06 09:00:00"],
        "card_id": [1, 1, 2, 2],
        "amount": ["$100.00", "$-20.00", "$50.00", "$10.00"],
        "errors": [None, None, "Bad PIN", None],
    }).astype({"date": "string", "amount": "string", "errors": "string"})
    info = pd.DataFrame({"card_type": ["Credit", "Debit"], "open_idx": [2019 * 12 + 2, 2018 * 12 + 1]},
                        index=pd.Index([1, 2], name="card_id"))
    rates = {"credit": 0.018, "debit": 0.0005, "debit_fixed": 0.21}
    out = daily_purchases(chunk, info, rates).set_index(["date", "card_type"])
    credit = out.loc[("2019-03-05", "Credit")]
    assert (credit.purchases, credit.purchase_volume, bool(credit.new_card)) == (1, 100.0, True)
    assert credit.interchange == pytest.approx(1.8)
    debit = out.loc[("2019-03-06", "Debit")]
    assert (debit.purchases, bool(debit.new_card)) == (1, False)
    assert ("2019-03-05", "Debit") not in out.index
