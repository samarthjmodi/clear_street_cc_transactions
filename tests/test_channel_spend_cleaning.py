"""Tests for spend cleaning choices that change CAC conclusions."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyze_channels import clean_spend  # noqa: E402


def test_apple_search_ads_is_triplicated_in_raw():
    spend = pd.read_csv(
        ROOT / "active_ds_takehome_handout/channel_spend.csv", parse_dates=["spend_date"]
    )
    apple = spend[spend.channel.eq("apple_search_ads")]
    counts = apple.groupby(["spend_date", "campaign"]).size()
    assert counts.min() == 3
    assert counts.max() == 3


def test_clean_spend_removes_apple_triplication_and_preserves_other_channels():
    spend = pd.read_csv(
        ROOT / "active_ds_takehome_handout/channel_spend.csv", parse_dates=["spend_date"]
    )
    clean = clean_spend(spend)
    apple_clean = clean[clean.channel.eq("apple_search_ads")]
    assert apple_clean.duplicated(["spend_date", "campaign"]).sum() == 0
    assert len(apple_clean) == len(spend[spend.channel.eq("apple_search_ads")]) // 3

    # Microsoft should be unchanged by the apple-specific logic.
    ms_raw = spend[spend.channel.eq("microsoft_ads")].spend.sum()
    ms_clean = clean[clean.channel.eq("microsoft_ads")].spend.sum()
    assert abs(ms_raw - ms_clean) < 1e-6


def test_microsoft_platform_cac_near_vp_claim():
    spend = pd.read_csv(
        ROOT / "active_ds_takehome_handout/channel_spend.csv", parse_dates=["spend_date"]
    )
    clean = clean_spend(spend)
    ms = clean[clean.channel.eq("microsoft_ads")]
    cac = ms.spend.sum() / ms.platform_reported_conversions.sum()
    # VP said ~$770; cleaned platform math is ~$802.
    assert 750 < cac < 850
