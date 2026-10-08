"""Channel efficiency from channel_spend (+ optional touchpoints when LFS is present).

Run from repo root:
  .venv/bin/python src/analyze_channels.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
OUT = ROOT / "analysis" / "channels"
PLOTS = Path(__file__).resolve().parents[1] / "plots"


def is_lfs_pointer(path: Path) -> bool:
    try:
        return path.read_text(errors="ignore").startswith("version https://git-lfs")
    except Exception:
        return True


def clean_spend(spend: pd.DataFrame) -> pd.DataFrame:
    """Apple Search Ads rows are exact triplicates on spend_date x campaign."""
    apple_mask = spend.channel.eq("apple_search_ads")
    apple = (
        spend.loc[apple_mask]
        .groupby(["spend_date", "channel", "campaign"], as_index=False)
        .agg(
            spend=("spend", "first"),
            impressions=("impressions", "first"),
            clicks=("clicks", "first"),
            platform_reported_conversions=("platform_reported_conversions", "max"),
        )
    )
    other = spend.loc[~apple_mask].drop_duplicates(
        ["spend_date", "channel", "campaign"], keep="first"
    )
    clean = pd.concat([other, apple], ignore_index=True)
    assert not clean.duplicated(["spend_date", "channel", "campaign"]).any()
    return clean.sort_values(["spend_date", "channel", "campaign"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)

    spend = pd.read_csv(ROOT / "channel_spend.csv", parse_dates=["spend_date"])
    clean = clean_spend(spend)
    ch = (
        clean.groupby("channel")
        .agg(
            spend=("spend", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            platform_conversions=("platform_reported_conversions", "sum"),
        )
        .reset_index()
    )
    ch["platform_cac"] = ch.spend / ch.platform_conversions.replace(0, np.nan)
    ch["cpc"] = ch.spend / ch.clicks.replace(0, np.nan)
    ch["raw_spend_before_dedup"] = ch.channel.map(spend.groupby("channel").spend.sum())
    ch["spend_inflation_factor"] = ch.raw_spend_before_dedup / ch.spend
    ch.to_csv(OUT / "channel_platform_metrics.csv", index=False)

    clean["month"] = clean.spend_date.dt.to_period("M").astype(str)
    clean.groupby(["month", "channel"], as_index=False).spend.sum().to_csv(
        OUT / "monthly_spend_by_channel.csv", index=False
    )

    # Weak quality proxy until touchpoint attribution is available.
    signups = pd.read_csv(ROOT / "account_signups.csv", parse_dates=["signup_ts"])
    cm = pd.read_csv(ROOT / "analysis/q1/customer_metrics.csv")
    first = signups.sort_values("signup_ts").groupby("client_id", as_index=False).first()
    pre = first.merge(cm, on="client_id")
    pre = pre[pre.signup_ts < "2020-01-01"]
    (
        pre.groupby("self_reported_source")
        .agg(
            n=("client_id", "size"),
            mean_interchange=("interchange", "mean"),
            median_interchange=("interchange", "median"),
            active_rate=("purchase_count", lambda s: float((s > 0).mean())),
        )
        .sort_values("mean_interchange", ascending=False)
        .to_csv(OUT / "self_reported_source_value.csv")
    )

    tp_path = ROOT / "marketing_touchpoints.csv"
    touchpoints_ready = tp_path.exists() and not is_lfs_pointer(tp_path)
    audit = {
        "raw_total_spend": float(spend.spend.sum()),
        "clean_total_spend": float(clean.spend.sum()),
        "spend_removed_by_dedup": float(spend.spend.sum() - clean.spend.sum()),
        "affiliate_in_spend": bool("affiliate" in set(clean.channel)),
        "touchpoints_file_available": touchpoints_ready,
        "platform_cac_microsoft": float(
            ch.loc[ch.channel.eq("microsoft_ads"), "platform_cac"].iloc[0]
        ),
        "platform_cac_apple": float(
            ch.loc[ch.channel.eq("apple_search_ads"), "platform_cac"].iloc[0]
        ),
        "note": (
            "Platform CAC uses platform_reported_conversions, not CRM signups. "
            "True CAC / segment mix needs marketing_touchpoints.csv via git lfs pull."
        ),
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2))
    print(ch.sort_values("platform_cac").to_string(index=False))
    print("AUDIT", audit)


if __name__ == "__main__":
    main()
