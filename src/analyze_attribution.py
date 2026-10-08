"""Attribute signups to channels via marketing touchpoints; compute CRM CAC.

Run from repo root:
  PYTHONPATH=src .venv/bin/python src/analyze_attribution.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_channels import clean_spend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
OUT = ROOT / "analysis" / "channels"
PLOTS = Path(__file__).resolve().parents[1] / "plots"


def load_linked_touchpoints() -> pd.DataFrame:
    """Load touches with a customer id. File is large; linked rows are dense early on."""
    cols = [
        "touch_id",
        "anonymous_id",
        "client_id",
        "touch_ts",
        "channel",
        "utm_campaign",
        "device",
    ]
    parts = []
    for chunk in pd.read_csv(
        ROOT / "marketing_touchpoints.csv",
        usecols=cols,
        parse_dates=["touch_ts"],
        chunksize=250_000,
    ):
        linked = chunk[chunk.client_id.notna()].copy()
        if len(linked):
            linked["client_id"] = linked.client_id.astype(int)
            parts.append(linked)
    tp = pd.concat(parts, ignore_index=True)
    assert tp.touch_id.is_unique
    return tp


def attribute(signups: pd.DataFrame, tp: pd.DataFrame) -> pd.DataFrame:
    """First-touch and last-touch before each card signup."""
    # One attribution row per signup (card-level), using touches for that client
    # with touch_ts <= signup_ts.
    s = signups.copy()
    touches = tp.sort_values(["client_id", "touch_ts", "touch_id"])
    rows = []
    by_client = {cid: g for cid, g in touches.groupby("client_id", sort=False)}
    for r in s.itertuples(index=False):
        g = by_client.get(int(r.client_id))
        if g is None:
            rows.append(
                {
                    "signup_id": r.signup_id,
                    "client_id": r.client_id,
                    "card_id": r.card_id,
                    "signup_ts": r.signup_ts,
                    "self_reported_source": r.self_reported_source,
                    "n_touches_before": 0,
                    "first_touch_channel": None,
                    "first_touch_ts": None,
                    "last_touch_channel": None,
                    "last_touch_ts": None,
                    "last_touch_campaign": None,
                }
            )
            continue
        pre = g[g.touch_ts <= r.signup_ts]
        if pre.empty:
            rows.append(
                {
                    "signup_id": r.signup_id,
                    "client_id": r.client_id,
                    "card_id": r.card_id,
                    "signup_ts": r.signup_ts,
                    "self_reported_source": r.self_reported_source,
                    "n_touches_before": 0,
                    "first_touch_channel": None,
                    "first_touch_ts": None,
                    "last_touch_channel": None,
                    "last_touch_ts": None,
                    "last_touch_campaign": None,
                }
            )
            continue
        first = pre.iloc[0]
        last = pre.iloc[-1]
        rows.append(
            {
                "signup_id": r.signup_id,
                "client_id": r.client_id,
                "card_id": r.card_id,
                "signup_ts": r.signup_ts,
                "self_reported_source": r.self_reported_source,
                "n_touches_before": int(len(pre)),
                "first_touch_channel": first.channel,
                "first_touch_ts": first.touch_ts,
                "last_touch_channel": last.channel,
                "last_touch_ts": last.touch_ts,
                "last_touch_campaign": last.utm_campaign,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)

    signups = pd.read_csv(ROOT / "account_signups.csv", parse_dates=["signup_ts"])
    cm = pd.read_csv(ROOT / "analysis/q1/customer_metrics.csv")
    spend = clean_spend(pd.read_csv(ROOT / "channel_spend.csv", parse_dates=["spend_date"]))

    print("Loading linked touchpoints...", flush=True)
    tp = load_linked_touchpoints()
    print(f"Linked touches: {len(tp):,} customers: {tp.client_id.nunique()}", flush=True)

    attr = attribute(signups, tp)
    # Customer-level first acquisition = earliest signup per client
    first_acq = (
        attr.sort_values("signup_ts")
        .groupby("client_id", as_index=False)
        .first()
        .rename(columns={"signup_ts": "first_signup_ts"})
    )
    first_acq = first_acq.merge(
        cm[
            [
                "client_id",
                "segment",
                "interchange",
                "purchase_count",
                "active_months",
                "credit_share",
            ]
        ],
        on="client_id",
        how="left",
    )
    first_acq["established"] = first_acq.active_months.ge(9) & first_acq.purchase_count.gt(0)
    first_acq["credit_led"] = first_acq.segment.eq("Regular credit-led")
    first_acq.to_csv(OUT / "customer_attribution.csv", index=False)
    attr.to_csv(OUT / "signup_attribution.csv", index=False)

    # Restrict CRM CAC to customers whose first signup falls in the spend window years
    # Use full history for channel mix; for CAC use 2016-01-01 to 2020-02-29 to match spend.
    acq = first_acq[first_acq.first_signup_ts.notna()].copy()
    # Last-touch paid channels only for CAC denominator alignment with spend channels
    paid = {
        "microsoft_ads",
        "apple_search_ads",
        "paid_search_brand",
        "paid_search_nonbrand",
        "paid_social_meta",
        "paid_social_reddit",
    }

    def channel_table(channel_col: str) -> pd.DataFrame:
        g = acq.groupby(channel_col, dropna=False).agg(
            customers=("client_id", "size"),
            established=("established", "sum"),
            credit_led=("credit_led", "sum"),
            mean_interchange=("interchange", "mean"),
            median_interchange=("interchange", "median"),
            total_interchange=("interchange", "sum"),
            active_rate=("purchase_count", lambda s: float((s > 0).mean())),
        )
        g["credit_led_share"] = g.credit_led / g.customers
        g["established_share"] = g.established / g.customers
        return g.sort_values("customers", ascending=False)

    last_mix = channel_table("last_touch_channel")
    first_mix = channel_table("first_touch_channel")
    last_mix.to_csv(OUT / "last_touch_channel_quality.csv")
    first_mix.to_csv(OUT / "first_touch_channel_quality.csv")

    # CRM CAC: clean spend / last-touch attributed first acquisitions on paid channels
    # Count each customer once at first signup.
    spend_tot = spend.groupby("channel").spend.sum()
    plat = spend.groupby("channel").platform_reported_conversions.sum()
    last_paid = acq[acq.last_touch_channel.isin(paid)]
    crm_counts = last_paid.last_touch_channel.value_counts()
    est_counts = last_paid.loc[last_paid.established, "last_touch_channel"].value_counts()
    credit_counts = last_paid.loc[last_paid.credit_led, "last_touch_channel"].value_counts()

    cac = pd.DataFrame(
        {
            "spend": spend_tot,
            "platform_conversions": plat,
            "crm_first_acq_last_touch": crm_counts,
            "crm_established_last_touch": est_counts,
            "crm_credit_led_last_touch": credit_counts,
        }
    ).fillna(0)
    cac["platform_cac"] = cac.spend / cac.platform_conversions.replace(0, np.nan)
    cac["crm_cac"] = cac.spend / cac.crm_first_acq_last_touch.replace(0, np.nan)
    cac["crm_cac_established"] = cac.spend / cac.crm_established_last_touch.replace(0, np.nan)
    cac["crm_cac_credit_led"] = cac.spend / cac.crm_credit_led_last_touch.replace(0, np.nan)
    cac["mean_interchange_last_touch"] = last_paid.groupby("last_touch_channel").interchange.mean()
    cac = cac.sort_values("crm_cac")
    cac.to_csv(OUT / "channel_cac_comparison.csv")

    # Affiliate / unpaid channels detail
    unpaid = acq[acq.last_touch_channel.isin(["affiliate", "organic_search", "direct", "referral", "email_lifecycle"])]
    unpaid_summary = unpaid.groupby("last_touch_channel").agg(
        customers=("client_id", "size"),
        established=("established", "sum"),
        credit_led=("credit_led", "sum"),
        mean_interchange=("interchange", "mean"),
    )
    unpaid_summary.to_csv(OUT / "unpaid_channel_quality.csv")

    # Pre-2020 only (transaction window overlap) for value honesty
    pre = acq[acq.first_signup_ts < "2020-01-01"]
    pre_last = (
        pre.groupby("last_touch_channel")
        .agg(
            customers=("client_id", "size"),
            established=("established", "sum"),
            credit_led=("credit_led", "sum"),
            mean_interchange=("interchange", "mean"),
            active_rate=("purchase_count", lambda s: float((s > 0).mean())),
        )
        .sort_values("customers", ascending=False)
    )
    pre_last.to_csv(OUT / "last_touch_quality_pre2020.csv")

    audit = {
        "linked_touches": int(len(tp)),
        "linked_customers_in_touches": int(tp.client_id.nunique()),
        "signup_rows": int(len(signups)),
        "unique_signup_customers": int(signups.client_id.nunique()),
        "first_acq_with_last_touch": int(acq.last_touch_channel.notna().sum()),
        "first_acq_missing_touch": int(acq.last_touch_channel.isna().sum()),
        "affiliate_last_touch_customers": int(
            (acq.last_touch_channel == "affiliate").sum()
        ),
        "microsoft_crm_cac": float(cac.loc["microsoft_ads", "crm_cac"])
        if "microsoft_ads" in cac.index
        else None,
        "apple_crm_cac": float(cac.loc["apple_search_ads", "crm_cac"])
        if "apple_search_ads" in cac.index
        else None,
        "microsoft_platform_cac": float(cac.loc["microsoft_ads", "platform_cac"])
        if "microsoft_ads" in cac.index
        else None,
        "note": (
            "CRM CAC = cleaned channel spend / customers whose first signup "
            "last-touch is that paid channel. Platform conversions are not CRM."
        ),
    }
    (OUT / "attribution_audit.json").write_text(json.dumps(audit, indent=2))

    # Plots
    import matplotlib.pyplot as plt

    plt.style.use("seaborn-v0_8-whitegrid")
    plot_df = cac.dropna(subset=["crm_cac"]).sort_values("crm_cac")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    y = np.arange(len(plot_df))
    ax.barh(y - 0.2, plot_df.platform_cac, height=0.4, color="#9aa0a6", label="Platform CAC")
    ax.barh(y + 0.2, plot_df.crm_cac, height=0.4, color="#1f4e79", label="CRM last-touch CAC")
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df.index)
    ax.set_xlabel("CAC ($)")
    ax.set_title("Platform vs CRM last-touch CAC (Apple spend de-triplicated)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "platform_vs_crm_cac.png", dpi=150)
    plt.close()

    mix = last_mix.dropna(axis=0, how="all").copy()
    mix = mix[mix.index.notna()]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.barh(mix.index.astype(str), mix.credit_led_share, color="#1f4e79")
    ax.set_xlabel("Share credit-led among attributed customers")
    ax.set_title("Credit-led mix by last-touch channel")
    fig.tight_layout()
    fig.savefig(PLOTS / "credit_led_mix_by_channel.png", dpi=150)
    plt.close()

    print("\n=== CAC comparison ===")
    print(
        cac[
            [
                "spend",
                "platform_conversions",
                "crm_first_acq_last_touch",
                "platform_cac",
                "crm_cac",
                "crm_cac_established",
                "mean_interchange_last_touch",
            ]
        ].to_string()
    )
    print("\n=== Last-touch quality (all) ===")
    print(last_mix.to_string())
    print("\n=== Unpaid ===")
    print(unpaid_summary.to_string())
    print("\nAUDIT", json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
