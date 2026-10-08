"""Tests for the channel x day spend table. A silent error here changes every CAC and the
March 2019 incremental-spend figure."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clean_channel_spend import clean_channel_spend  # noqa: E402

RAW_PATH = ROOT / "active_ds_takehome_handout" / "channel_spend.csv"


def _rows(channel, campaign, spend, conv, date="2019-03-04", impressions=1000, clicks=50):
    return pd.DataFrame({
        "spend_date": pd.to_datetime([date] * len(conv)),
        "channel": channel, "campaign": campaign,
        "spend": spend, "impressions": impressions, "clicks": clicks,
        "platform_reported_conversions": conv,
    })


@pytest.mark.parametrize("conv", [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
def test_triplicate_counts_spend_once_and_keeps_the_conversion(conv):
    raw = _rows("apple_search_ads", "asa_exact", 12.0, conv)
    out = clean_channel_spend(raw)
    assert len(out) == 1
    assert out.spend.iloc[0] == 12.0
    assert out.platform_reported_conversions.iloc[0] == 1.0
    assert out.raw_rows.iloc[0] == 3


def test_duplicates_that_disagree_on_spend_raise():
    raw = pd.concat([_rows("apple_search_ads", "asa_exact", 12.0, [0.0]),
                     _rows("apple_search_ads", "asa_exact", 13.0, [0.0])])
    with pytest.raises(ValueError, match="disagree"):
        clean_channel_spend(raw)


def test_duplicates_with_conflicting_conversions_raise():
    raw = _rows("apple_search_ads", "asa_exact", 12.0, [1.0, 2.0])
    with pytest.raises(ValueError, match="conflicting"):
        clean_channel_spend(raw)


def test_campaigns_sum_to_channel_and_split_rounding_is_undone():
    raw = pd.concat([
        _rows("paid_search_nonbrand", c, 100.0, [0.33]) for c in ["generic_cards", "compare_cards", "rewards_terms"]
    ] + [
        _rows("paid_social_meta", c, 50.0, [0.4]) for c in ["prospecting_lal", "retargeting_site", "spring_launch"]
    ] + [
        _rows("microsoft_ads", c, 20.0, [3.25]) for c in ["bing_brand", "bing_generic"]
    ])
    out = clean_channel_spend(raw).set_index("channel")
    assert out.loc["paid_search_nonbrand", "spend"] == 300.0
    assert out.loc["paid_search_nonbrand", "platform_reported_conversions"] == 1.0
    assert out.loc["paid_social_meta", "platform_reported_conversions"] == 1.2
    assert out.loc["microsoft_ads", "platform_reported_conversions"] == 6.5
    assert out.loc["paid_search_nonbrand", "n_campaigns"] == 3


def test_cpm_is_spend_per_thousand_impressions():
    out = clean_channel_spend(_rows("paid_search_brand", "brand_exact", 14.0, [0.0], impressions=1000))
    assert out.cpm.iloc[0] == 14.0


@pytest.fixture(scope="module")
def real():
    raw = pd.read_csv(RAW_PATH, parse_dates=["spend_date"])
    return raw, clean_channel_spend(raw)


def test_real_table_is_one_row_per_channel_day_with_no_gaps(real):
    _, clean = real
    days = pd.date_range("2016-01-01", "2020-02-29")
    assert len(clean) == 6 * len(days)
    assert not clean.duplicated(["spend_date", "channel"]).any()
    assert (clean.groupby("channel").spend_date.nunique() == len(days)).all()


def test_real_spend_reconciles_to_raw(real):
    raw, clean = real
    raw_by_ch = raw.groupby("channel").spend.sum()
    clean_by_ch = clean.groupby("channel").spend.sum()
    assert clean_by_ch["apple_search_ads"] == pytest.approx(raw_by_ch["apple_search_ads"] / 3, abs=0.05)
    others = raw_by_ch.index.drop("apple_search_ads")
    assert clean_by_ch[others].to_numpy() == pytest.approx(raw_by_ch[others].to_numpy(), abs=0.05)


def test_real_apple_conversions_survive_dedup(real):
    raw, clean = real
    raw_apple = raw[raw.channel.eq("apple_search_ads")].platform_reported_conversions.sum()
    clean_apple = clean[clean.channel.eq("apple_search_ads")].platform_reported_conversions.sum()
    assert raw_apple == clean_apple == 94


def test_real_nonbrand_conversions_are_whole_numbers(real):
    _, clean = real
    nb = clean[clean.channel.eq("paid_search_nonbrand")].platform_reported_conversions
    assert (nb == nb.round()).all()


def test_real_cpm_is_constant_per_channel(real):
    _, clean = real
    spread = clean.groupby("channel").cpm.agg(lambda x: x.max() - x.min())
    assert (spread < 0.01).all()
