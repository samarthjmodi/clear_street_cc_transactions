"""Plots for Q3 channel quality / budget and the VP's channel beliefs.

Run from repo root after vp_hypotheses.py has written the monthly table:
  .venv/bin/python src/plot_vp_beliefs.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
HYP = REPO / "active_ds_takehome_handout" / "analysis" / "hypotheses"
MONTHLY = HYP / "monthly_channel_spend_touches.csv"
PLOTS = REPO / "plots"

SEG_ORDER = ["Premium credit", "Core credit", "Debit", "Prepaid"]
SEG_COLORS = {
    "Premium credit": "#1f4e79",
    "Core credit": "#5b8fad",
    "Debit": "#9fbfd6",
    "Prepaid": "#c0392b",
}


def plot_microsoft(monthly: pd.DataFrame) -> Path:
    m = monthly[monthly.channel.eq("microsoft_ads")].set_index("month")
    x = pd.to_datetime(m.index)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(x, m.spend / 1000, width=20, color="#9aa0a6", label="Monthly spend (\\$k, left)")
    ax.set_ylabel("Spend (\\$k)")
    ax2 = ax.twinx()
    ax2.plot(x, m.platform_reported_conversions, color="#1f4e79", marker="o", markersize=3,
             label="Platform-reported conversions (right)")
    ax2.set_ylabel("Platform-reported conversions")
    ax2.annotate("Jan–Feb 2020: 293 and 436", xy=(x[-1], m.platform_reported_conversions.iloc[-1]),
                 xytext=(pd.Timestamp("2017-06-01"), 380), arrowprops={"arrowstyle": "->", "color": "#1f4e79"},
                 color="#1f4e79")
    ax.set_title("Microsoft Ads: spend tripled, platform-reported conversions stayed at 0–26 a month until 2020")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left")
    fig.tight_layout()
    out = PLOTS / "belief1_microsoft_spend_vs_platform_conversions.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


LABEL = {"paid_search_brand": "Google branded search", "microsoft_ads": "Microsoft Ads",
         "paid_social_meta": "Meta", "paid_search_nonbrand": "Google non-brand search",
         "paid_social_reddit": "Reddit", "apple_search_ads": "Apple Search Ads"}


def plot_apple(monthly: pd.DataFrame, raw_spend: pd.DataFrame, cac: pd.DataFrame) -> Path:
    paid = monthly.dropna(subset=["spend"])
    a = paid[paid.channel.eq("apple_search_ads")].set_index("month")
    share = a.spend / paid.groupby("month").spend.sum()
    raw = raw_spend[raw_spend.channel.eq("apple_search_ads")].copy()
    raw["month"] = raw.spend_date.str[:7]
    raw_m = raw.groupby("month").spend.sum().reindex(a.index)
    x = pd.to_datetime(a.index)

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1.3, 1]})
    ax.plot(x, raw_m / 1000, color="#c0392b", linestyle="--", label="Raw file (rows tripled)")
    ax.plot(x, a.spend / 1000, color="#1f4e79", label="Actual, duplicates removed")
    ax.set_ylabel("Apple monthly spend (\\$k)")
    ax2 = ax.twinx()
    ax2.plot(x, share * 100, color="#9aa0a6", linewidth=1, label="Apple share of paid spend (%, right)")
    ax2.set_ylim(0, 40)
    ax2.set_ylabel("Share of paid spend (%)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    ax.set_title("Spend climbs like every channel; share stays ~12%")

    c = cac.reindex(list(LABEL)).iloc[::-1]
    y = range(len(c))
    colors = ["#c0392b" if ch == "apple_search_ads" else "#1f4e79" for ch in c.index]
    bx.barh(list(y), c.cac_linear, color=colors,
            xerr=[c.cac_linear - c.cac_low, c.cac_high - c.cac_linear], ecolor="#555", capsize=3)
    bx.set_yticks(list(y))
    bx.set_yticklabels([LABEL[ch] for ch in c.index])
    for i, v in zip(y, c.cac_linear):
        bx.text(v + 300, i + 0.25, f"\\${v:,.0f}", fontsize=8)
    bx.set_xlabel("Cost per new customer, Jan–Feb 2020 (\\$)")
    bx.set_title("Apple is the most expensive paid channel\n(linear attribution, 95% CI)", fontsize=11)
    fig.tight_layout()
    out = PLOTS / "belief2_apple_spend_and_cost_per_customer.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_affiliate(monthly: pd.DataFrame, notes: dict, cac: pd.DataFrame) -> Path:
    aff = notes["affiliate"]
    m = monthly[monthly.channel.eq("affiliate")].set_index("month")
    months = pd.period_range("2016-01", "2020-02", freq="M").astype(str)
    touches = m.touches.reindex(months).fillna(0)
    signups = sum(aff["signups_touched_2020"].values())
    linear_new = aff["linear_new_customers_2020"]
    value = aff["expected_3yr_touched"]

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 4.8))
    ax.bar(pd.to_datetime(touches.index), touches, width=20, color="#1f4e79")
    ax.set_ylabel("Affiliate touches per month")
    ax.set_title("Affiliate volume: near zero until Dec 2019, no spend row ever")
    ax.annotate("Never more than 7 a month, 2016 to Oct 2019", xy=(pd.Timestamp("2018-01-01"), 7),
                xytext=(pd.Timestamp("2016-03-01"), 60), fontsize=9,
                arrowprops={"arrowstyle": "->", "color": "#555"})

    commission = pd.Series(range(0, 401, 10))
    bx.plot(commission, commission * signups / linear_new, color="#c0392b",
            label=f"Paid on every touched signup ({signups})")
    bx.plot(commission, commission * aff["last_touch_signups_2020"] / linear_new, color="#c0392b",
            linestyle="--", label=f"Paid only on last-touch signups ({aff['last_touch_signups_2020']})")
    refs = {"Google branded search": cac.loc["paid_search_brand", "cac_linear"],
            "Microsoft Ads": cac.loc["microsoft_ads", "cac_linear"],
            "3-year revenue per affiliate customer": value}
    for (name, v), style in zip(refs.items(), [":", ":", "-"]):
        bx.axhline(v, color="#555", linestyle=style, linewidth=1)
        bx.text(398, v + 60, f"{name} \\${v:,.0f}", fontsize=8, color="#333", ha="right")
    bx.set_ylim(0, 3200)
    bx.set_xlabel("Commission per signup (\\$)")
    bx.set_ylabel("Cost per new customer, Jan–Feb 2020 (\\$)")
    bx.set_title("Cost depends on the payout, which we can't see")
    bx.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    out = PLOTS / "belief3_affiliate_volume_and_commission_scenarios.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_channel_quality(quality: pd.DataFrame, cac: pd.DataFrame) -> Path:
    """Segment mix (left) and value per CAC dollar (right) for paid channels + affiliate."""
    channels = [
        "paid_search_brand", "microsoft_ads", "paid_social_meta",
        "paid_search_nonbrand", "paid_social_reddit", "apple_search_ads", "affiliate",
    ]
    display = {**LABEL, "affiliate": "Affiliate"}
    mix = quality.reindex(channels)
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.35, 1]})

    bottom = pd.Series(0.0, index=channels)
    for seg in SEG_ORDER:
        vals = mix[seg].fillna(0) * 100
        ax.barh([display[c] for c in channels], vals, left=bottom, color=SEG_COLORS[seg],
                label=seg, height=0.7)
        bottom = bottom + vals
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of credited new customers (%)")
    ax.set_title("Day-one mix barely differs by channel\n(Premium = credit limit ≥ $10k)")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.95)
    ax.invert_yaxis()

    paid = cac.reindex([c for c in channels if c in cac.index]).copy()
    paid["label"] = [LABEL[c] for c in paid.index]
    paid = paid.sort_values("value_per_dollar_linear")
    colors = ["#1f4e79" if c == "paid_search_brand" else
              "#c0392b" if c == "apple_search_ads" else "#5b8fad" for c in paid.index]
    y = range(len(paid))
    bx.barh(list(y), paid.value_per_dollar_linear, color=colors)
    bx.set_yticks(list(y))
    bx.set_yticklabels(paid.label)
    for i, (v, cac_v) in enumerate(zip(paid.value_per_dollar_linear, paid.cac_linear)):
        bx.text(v + 0.04, i, f"{v:.2f}×  (CAC ${cac_v:,.0f})", fontsize=8, va="center")
    bx.axvline(1.0, color="#555", linestyle=":", linewidth=1)
    bx.set_xlabel("Expected 3-year revenue per $1 of CAC (linear)")
    bx.set_title("Efficiency separates channels; brand alone clears 1×")
    bx.set_xlim(0, max(paid.value_per_dollar_linear.max() * 1.35, 1.2))
    fig.suptitle("Q3: channels differ on cost, not on who they bring", fontsize=12, y=1.02)
    fig.tight_layout()
    out = PLOTS / "q3_channel_quality.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    monthly = pd.read_csv(MONTHLY)
    print(plot_microsoft(monthly))
    raw = pd.read_csv(REPO / "active_ds_takehome_handout" / "channel_spend.csv")
    cac = pd.read_csv(HYP / "cac_vs_value_2020.csv", index_col=0)
    print(plot_apple(monthly, raw, cac))
    notes = json.loads((HYP / "hypotheses_notes.json").read_text())
    print(plot_affiliate(monthly, notes, cac))
    quality = pd.read_csv(HYP / "new_customer_quality_by_channel.csv", index_col=0)
    print(plot_channel_quality(quality, cac))


if __name__ == "__main__":
    main()
