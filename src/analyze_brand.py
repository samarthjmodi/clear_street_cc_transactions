"""March 2019 brand-campaign proxy from cleaned spend + signups.

Run from repo root:
  .venv/bin/python src/analyze_brand.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_channels import clean_spend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
OUT = ROOT / "analysis" / "brand"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spend = pd.read_csv(ROOT / "channel_spend.csv", parse_dates=["spend_date"])
    signups = pd.read_csv(ROOT / "account_signups.csv", parse_dates=["signup_ts"])
    clean = clean_spend(spend)
    clean["month"] = clean.spend_date.dt.to_period("M").astype(str)

    brand = (
        clean.groupby("month")
        .agg(total_spend=("spend", "sum"))
        .join(
            clean[clean.campaign.eq("spring_launch")]
            .groupby("month")
            .spend.sum()
            .rename("spring_launch_spend")
        )
        .join(
            clean[clean.channel.eq("paid_search_brand")]
            .groupby("month")
            .spend.sum()
            .rename("paid_search_brand_spend")
        )
    )
    sig_m = (
        signups.groupby(signups.signup_ts.dt.to_period("M").astype(str))
        .size()
        .rename("signups")
    )
    brand = brand.join(sig_m, how="left").loc["2018-01":"2019-12"]
    brand["signups"] = brand.signups.fillna(0).astype(int)
    brand.to_csv(OUT / "monthly_brand_proxy.csv")

    adj = ["2019-02", "2019-04"]
    estimate = {
        "march_total_spend": float(brand.loc["2019-03", "total_spend"]),
        "adj_avg_total_spend": float(brand.loc[adj, "total_spend"].mean()),
        "march_incremental_spend_vs_adj": float(
            brand.loc["2019-03", "total_spend"] - brand.loc[adj, "total_spend"].mean()
        ),
        "march_signups": int(brand.loc["2019-03", "signups"]),
        "adj_avg_signups": float(brand.loc[adj, "signups"].mean()),
        "march_incremental_signups_vs_adj": float(
            brand.loc["2019-03", "signups"] - brand.loc[adj, "signups"].mean()
        ),
        "caveat": (
            "Descriptive only. Signup counts are tiny; this is not a causal "
            "incrementality estimate."
        ),
    }
    inc_s = estimate["march_incremental_signups_vs_adj"]
    inc_sp = estimate["march_incremental_spend_vs_adj"]
    estimate["naive_cost_per_incremental_signup"] = (
        float(inc_sp / inc_s) if inc_s else None
    )
    (OUT / "march_2019_estimate.json").write_text(json.dumps(estimate, indent=2))
    print(json.dumps(estimate, indent=2))


if __name__ == "__main__":
    main()
