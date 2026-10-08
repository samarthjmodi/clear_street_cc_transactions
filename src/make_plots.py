"""Render submission plots from analysis outputs. Run from repo root."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "active_ds_takehome_handout" / "analysis"
PLOTS = ROOT / "plots"


def main() -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    ch = pd.read_csv(DATA / "channels/channel_platform_metrics.csv").sort_values(
        "platform_cac"
    )
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(ch.channel, ch.platform_cac, color="#1f4e79")
    ax.axvline(770, color="#c45c26", ls="--", lw=1, label="VP claim ~$770")
    ax.set_xlabel("Platform-reported CAC ($)")
    ax.set_title("Platform CAC by channel (Apple spend de-triplicated)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(PLOTS / "platform_cac_by_channel.png", dpi=150)
    plt.close()

    seg = pd.read_csv(DATA / "q1/segment_summary.csv").set_index("segment")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(
        range(len(seg)),
        seg.avg_interchange,
        color=["#9aa0a6", "#9aa0a6", "#1f4e79", "#5b8fad"],
    )
    ax.set_xticks(range(len(seg)))
    ax.set_xticklabels([s.replace(" ", "\n") for s in seg.index], fontsize=8)
    ax.set_ylabel("Mean annual interchange ($)")
    ax.set_title("Customer value proxy by segment (Nov 2018–Oct 2019)")
    fig.tight_layout()
    fig.savefig(PLOTS / "segment_interchange.png", dpi=150)
    plt.close()

    life = pd.read_csv(DATA / "lifecycle/lifecycle_summary.csv")
    status_col = life.columns[0]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(life[status_col], life.customers, color="#1f4e79")
    ax.set_xlabel("Customers")
    ax.set_title("Lifecycle status (operational definitions)")
    fig.tight_layout()
    fig.savefig(PLOTS / "lifecycle_status.png", dpi=150)
    plt.close()

    ret = pd.read_csv(DATA / "lifecycle/month_to_month_retention.csv")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(ret.from_month, ret.retention_rate, marker="o", color="#1f4e79")
    ax.set_ylim(0.95, 1.005)
    ax.set_ylabel("Retention rate")
    ax.set_xlabel("From month")
    ax.set_title("Month-to-month retention among purchasing customers")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(PLOTS / "m2m_retention.png", dpi=150)
    plt.close()
    print("Wrote plots to", PLOTS)


if __name__ == "__main__":
    main()
