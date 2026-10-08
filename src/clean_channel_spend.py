"""Clean channel_spend.csv into one row per channel x day, with CPM.

Run from repo root:
  .venv/bin/python src/clean_channel_spend.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

HANDOUT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
OUT = HANDOUT / "analysis" / "clean" / "clean_channel_spend.csv"
KEY = ["spend_date", "channel", "campaign"]
COLUMNS = ["spend_date", "channel", "spend", "impressions", "clicks",
           "platform_reported_conversions", "cpm", "n_campaigns", "raw_rows"]


def dedupe_campaign_days(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per date x channel x campaign.

    Apple Search Ads arrives as identical triplicates, except that a conversion is written to
    only one of the copies. Conversions therefore take the max across copies; keeping the last
    copy would drop every Apple conversion."""
    dup = raw[raw.duplicated(KEY, keep=False)]
    if len(dup):
        g = dup.groupby(KEY)
        if g[["spend", "impressions", "clicks"]].nunique().gt(1).any(axis=None):
            raise ValueError("duplicate rows disagree on spend, impressions or clicks")
        nonzero = dup[dup.platform_reported_conversions > 0].groupby(KEY).platform_reported_conversions.nunique()
        if nonzero.gt(1).any():
            raise ValueError("duplicate rows carry conflicting non-zero conversions")
    return (
        raw.groupby(KEY, as_index=False)
        .agg(spend=("spend", "first"), impressions=("impressions", "first"), clicks=("clicks", "first"),
             platform_reported_conversions=("platform_reported_conversions", "max"),
             raw_rows=("spend", "size"))
    )


def collapse_to_channel_day(campaign_days: pd.DataFrame) -> pd.DataFrame:
    """Sum campaigns into channel x day and add CPM.

    Each campaign's conversions were rounded to 2 decimals after an even split across the
    channel's campaigns, so one conversion over three campaigns sums to 0.99. Rounding the
    channel total to 0.1 restores it without touching genuine fractional units (1.2, 6.5)."""
    out = (
        campaign_days.groupby(["spend_date", "channel"], as_index=False)
        .agg(spend=("spend", "sum"), impressions=("impressions", "sum"), clicks=("clicks", "sum"),
             platform_reported_conversions=("platform_reported_conversions", "sum"),
             n_campaigns=("campaign", "nunique"), raw_rows=("raw_rows", "sum"))
    )
    out["spend"] = out.spend.round(2)
    out["platform_reported_conversions"] = out.platform_reported_conversions.round(1)
    out["cpm"] = (out.spend / out.impressions * 1000).round(4)
    return out[COLUMNS].sort_values(["spend_date", "channel"], ignore_index=True)


def clean_channel_spend(raw: pd.DataFrame) -> pd.DataFrame:
    return collapse_to_channel_day(dedupe_campaign_days(raw))


def main() -> None:
    raw = pd.read_csv(HANDOUT / "channel_spend.csv", parse_dates=["spend_date"])
    clean = clean_channel_spend(raw)
    assert not clean.duplicated(["spend_date", "channel"]).any()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUT, index=False)

    summary = clean.groupby("channel").agg(
        days=("spend_date", "nunique"), spend=("spend", "sum"),
        conversions=("platform_reported_conversions", "sum"),
        cpm_min=("cpm", "min"), cpm_max=("cpm", "max"),
    )
    summary["raw_spend"] = raw.groupby("channel").spend.sum()
    print(f"Wrote {len(clean):,} rows ({raw.shape[0]:,} raw) to {OUT.relative_to(HANDOUT.parent)}")
    print(summary.round(2).to_string())
    print(f"Total spend: raw ${raw.spend.sum():,.2f} | clean ${clean.spend.sum():,.2f}")


if __name__ == "__main__":
    main()
