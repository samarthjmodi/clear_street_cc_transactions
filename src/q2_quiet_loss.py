"""Q2 (quiet loss): when do we know a customer has quietly gone away?

Tight scope on the Nov 2018 – Oct 2019 active base (settled purchases), broken down by
Q1 day-one segments (credit $10k+, credit under $10k, debit, prepaid).

1. Gap distribution / max gap between purchase days
2. For N in {7, 14, 30, 60}: share who ever hit N days silent, and among inter-purchase
   silence episodes, share who returned within 30 days of the N-day alert
3. Structural exit: no card open at the Feb 2020 snapshot
4. Caveats: missing-txn customers and pre-2020 leavers are out of scope

Run from repo root:  .venv/bin/python src/q2_quiet_loss.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_customer_value import HANDOUT, PLOTS, money, mm_yyyy_idx  # noqa: E402
from q1_part1_profile import WINDOW_END, load_window  # noqa: E402
from q1_part2_value import day_one_cards  # noqa: E402

OUT = HANDOUT / "analysis" / "q2_quiet_loss"
SILENCE_NS = (7, 14, 30, 60)
RETURN_DAYS = 30
SNAPSHOT_IDX = 2020 * 12 + 2
SEGMENT_ORDER = [
    "Credit, limit $10k+",
    "Credit, limit under $10k",
    "Debit",
    "Prepaid",
]


def day_one_segment(product: pd.Series, max_limit: pd.Series) -> pd.Series:
    """Q1 headline day-one cut: credit by $10k limit, else debit / prepaid."""
    out = pd.Series(index=product.index, dtype=object)
    credit = product.eq("Credit")
    out.loc[credit & max_limit.ge(10_000)] = "Credit, limit $10k+"
    out.loc[credit & (max_limit.isna() | max_limit.lt(10_000))] = "Credit, limit under $10k"
    out.loc[product.eq("Debit")] = "Debit"
    out.loc[product.eq("Prepaid")] = "Prepaid"
    return out


def purchase_days(window: pd.DataFrame) -> pd.DataFrame:
    """One row per client_id × calendar day with a settled purchase."""
    ok = window.errors.isna() & (window.amt > 0)
    d = window.loc[ok, ["client_id", "ts"]].copy()
    d["day"] = d.ts.dt.normalize()
    return d[["client_id", "day"]].drop_duplicates().sort_values(["client_id", "day"])


def gap_features(days: pd.DataFrame, end: pd.Timestamp = WINDOW_END) -> pd.DataFrame:
    """Per-customer inter-purchase gap stats and terminal silence to window end."""
    d = days.sort_values(["client_id", "day"]).copy()
    d["gap"] = d.groupby("client_id").day.diff().dt.days
    g = d.groupby("client_id")
    out = pd.DataFrame(index=g.size().index)
    out["purchase_days"] = g.size()
    out["median_gap_days"] = g.gap.median()
    out["p90_gap_days"] = g.gap.quantile(0.9)
    out["max_gap_days"] = g.gap.max()
    last = g.day.max()
    out["last_purchase_day"] = last
    out["terminal_silence_days"] = (end - last).dt.days
    out["max_gap_incl_terminal"] = out[["max_gap_days", "terminal_silence_days"]].max(axis=1)
    return out


def silence_episodes(days: pd.DataFrame, n: int, end: pd.Timestamp = WINDOW_END,
                     return_days: int = RETURN_DAYS) -> pd.DataFrame:
    """Inter-purchase silence episodes of at least n days.

    An episode starts n days after purchase day t_i when the next purchase is later.
    Returned within `return_days` of the alert means the next purchase falls on or before
    t_i + n + return_days (equivalently gap <= n + return_days).

    Terminal silence to window end is flagged separately and excluded from the return rate.
    """
    d = days.sort_values(["client_id", "day"]).copy()
    d["next_day"] = d.groupby("client_id").day.shift(-1)
    d["gap"] = (d.next_day - d.day).dt.days
    rows = []
    inter = d[d.gap.notna() & (d.gap >= n)]
    for r in inter.itertuples(index=False):
        rows.append({
            "client_id": r.client_id,
            "n": n,
            "gap_days": int(r.gap),
            "terminal": False,
            "returned_within_return_window": bool(r.gap <= n + return_days),
        })
    # terminal: last purchase to window end
    last = d.groupby("client_id").day.max()
    term = (end - last).dt.days
    for cid, silence in term[term >= n].items():
        rows.append({
            "client_id": cid,
            "n": n,
            "gap_days": int(silence),
            "terminal": True,
            "returned_within_return_window": pd.NA,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["client_id", "n", "gap_days", "terminal", "returned_within_return_window"])


def _as_bool(s: pd.Series) -> pd.Series:
    """Normalise bool/object flags; do not use ~ on object dtype (it mis-handles True)."""
    return s.fillna(False).astype(bool)


def silence_summary(customers: pd.DataFrame, episodes: pd.DataFrame, n: int) -> pd.DataFrame:
    """Hit rate and return rate by day-one segment for one silence threshold."""
    ep = episodes.copy()
    ep["client_id"] = ep.client_id.astype(int)
    ep["n"] = ep.n.astype(int)
    ep["terminal"] = _as_bool(ep.terminal)
    hit_ids = set(ep.loc[ep.n.eq(n), "client_id"])
    inter = ep[ep.n.eq(n) & ~ep.terminal]
    terminal = ep[ep.n.eq(n) & ep.terminal]
    rows = []
    for seg, idx in customers.groupby("day_one_segment").groups.items():
        ids = set(idx)
        hit = ids & hit_ids
        seg_inter = inter[inter.client_id.isin(ids)]
        ret = seg_inter.returned_within_return_window.astype("boolean")
        rows.append({
            "silence_days": n,
            "day_one_segment": seg,
            "customers": len(ids),
            "hit_customers": len(hit),
            "hit_rate": len(hit) / len(ids) if ids else np.nan,
            "inter_purchase_episodes": int(len(seg_inter)),
            "returned_within_30d_of_alert": int(ret.sum()) if len(seg_inter) else 0,
            "return_rate_given_inter_purchase_silence": float(ret.mean()) if len(seg_inter) else np.nan,
            "terminal_silence_customers": int(terminal[terminal.client_id.isin(ids)].client_id.nunique()),
        })
    # overall
    ids = set(customers.index)
    hit = ids & hit_ids
    seg_inter = inter[inter.client_id.isin(ids)]
    ret = seg_inter.returned_within_return_window.astype("boolean")
    rows.append({
        "silence_days": n,
        "day_one_segment": "All active",
        "customers": len(ids),
        "hit_customers": len(hit),
        "hit_rate": len(hit) / len(ids) if ids else np.nan,
        "inter_purchase_episodes": int(len(seg_inter)),
        "returned_within_30d_of_alert": int(ret.sum()) if len(seg_inter) else 0,
        "return_rate_given_inter_purchase_silence": float(ret.mean()) if len(seg_inter) else np.nan,
        "terminal_silence_customers": int(terminal.client_id.nunique()),
    })
    return pd.DataFrame(rows)


def structural_exit(cards: pd.DataFrame, client_ids: pd.Index,
                    snapshot_idx: int = SNAPSHOT_IDX) -> pd.Series:
    """True if the customer has no card open at the Feb 2020 snapshot."""
    open_now = cards[(cards.open_idx <= snapshot_idx) & (cards.expires_idx >= snapshot_idx)]
    n_open = open_now.groupby("client_id").size().reindex(client_ids, fill_value=0)
    return n_open.eq(0).rename("no_open_card")


def gap_summary(customers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seg, g in list(customers.groupby("day_one_segment")) + [("All active", customers)]:
        rows.append({
            "day_one_segment": seg,
            "customers": len(g),
            "median_gap_days": float(g.median_gap_days.median()),
            "p90_gap_days": float(g.p90_gap_days.median()),
            "median_of_max_gap_days": float(g.max_gap_days.median()),
            "p90_of_max_gap_days": float(g.max_gap_days.quantile(0.9)),
            "max_of_max_gap_days": float(g.max_gap_days.max()),
            "median_terminal_silence_days": float(g.terminal_silence_days.median()),
            "max_terminal_silence_days": float(g.terminal_silence_days.max()),
            "share_max_gap_ge_7": float(g.max_gap_incl_terminal.ge(7).mean()),
            "share_max_gap_ge_14": float(g.max_gap_incl_terminal.ge(14).mean()),
            "share_max_gap_ge_30": float(g.max_gap_incl_terminal.ge(30).mean()),
            "share_max_gap_ge_60": float(g.max_gap_incl_terminal.ge(60).mean()),
            "share_no_open_card": float(g.no_open_card.mean()),
        })
    return pd.DataFrame(rows)


def plot_quiet_loss(gap: pd.DataFrame, silence: pd.DataFrame, customers: pd.DataFrame) -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))

    # max gap distribution by segment
    ax = axes[0]
    for seg in SEGMENT_ORDER:
        x = customers.loc[customers.day_one_segment.eq(seg), "max_gap_incl_terminal"].dropna()
        if len(x) == 0:
            continue
        caps = np.clip(x, 0, 60)
        ax.hist(caps, bins=np.arange(0, 62, 2), histtype="step", density=True, label=seg, linewidth=1.5)
    ax.set_xlabel("Longest silence in window (days, capped at 60)")
    ax.set_ylabel("Density")
    ax.set_title("Longest quiet spell")
    ax.legend(fontsize=7, loc="upper right")

    # hit rates
    ax = axes[1]
    s = silence[silence.day_one_segment.ne("All active")]
    wide = s.pivot(index="silence_days", columns="day_one_segment", values="hit_rate")
    wide = wide.reindex(columns=[c for c in SEGMENT_ORDER if c in wide.columns])
    wide.plot(ax=ax, marker="o")
    ax.set_xticks(list(SILENCE_NS))
    ax.set_ylim(0, min(1.05, max(0.2, wide.max().max() * 1.2) if len(wide) else 1))
    ax.set_xlabel("Silence threshold N (days)")
    ax.set_ylabel("Share of customers who ever hit N")
    ax.set_title("Silence hit rate")
    ax.legend(fontsize=7)

    # structural exit
    ax = axes[2]
    g = gap[gap.day_one_segment.ne("All active")].set_index("day_one_segment").reindex(SEGMENT_ORDER)
    ax.bar(range(len(g)), g.share_no_open_card.values, color="steelblue")
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(SEGMENT_ORDER, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Share with no open card (Feb 2020)")
    ax.set_title("Structural exit")
    ax.set_ylim(0, max(0.05, g.share_no_open_card.max() * 1.3 if g.share_no_open_card.notna().any() else 0.05))

    fig.suptitle("Quiet loss among Nov 2018 – Oct 2019 active customers, by day-one segment")
    fig.tight_layout()
    fig.savefig(PLOTS / "q2_quiet_loss.png", dpi=150)
    plt.close(fig)


def build_customers() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cards = pd.read_csv(HANDOUT / "cards_data.csv")
    cards["credit_limit"] = money(cards.credit_limit)
    cards["open_idx"] = mm_yyyy_idx(cards.acct_open_date)
    cards["expires_idx"] = mm_yyyy_idx(cards.expires)
    first = cards.groupby("client_id").open_idx.min()
    d1 = day_one_cards(cards, first)
    seg = day_one_segment(d1.day_one_product, d1.day_one_max_limit)

    print("Loading window transactions…")
    window = load_window()
    days = purchase_days(window)
    active_ids = days.client_id.unique()
    print(f"Active customers with settled purchases: {len(active_ids):,}")

    gaps = gap_features(days)
    cust = gaps.copy()
    cust["day_one_segment"] = seg.reindex(cust.index)
    cust["day_one_product"] = d1.day_one_product.reindex(cust.index)
    cust["day_one_max_limit"] = d1.day_one_max_limit.reindex(cust.index)
    cust["no_open_card"] = structural_exit(cards, cust.index)
    # drop anyone missing a day-one segment (shouldn't happen)
    missing = cust.day_one_segment.isna().sum()
    if missing:
        print(f"WARNING: {missing} active customers missing day-one segment")
        cust = cust[cust.day_one_segment.notna()]

    ep_parts = [silence_episodes(days, n) for n in SILENCE_NS]
    episodes = pd.concat(ep_parts, ignore_index=True) if ep_parts else pd.DataFrame(
        columns=["client_id", "n", "gap_days", "terminal", "returned_within_return_window"])
    if len(episodes):
        episodes["client_id"] = episodes.client_id.astype(int)
        episodes["n"] = episodes.n.astype(int)
        episodes["gap_days"] = episodes.gap_days.astype(int)
        episodes["terminal"] = _as_bool(episodes.terminal)
    return cust, days, episodes


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    customers, days, episodes = build_customers()
    customers.to_csv(OUT / "customer_gaps.csv")

    gap = gap_summary(customers)
    gap.to_csv(OUT / "gap_summary_by_segment.csv", index=False)

    silence_rows = [silence_summary(customers, episodes, n) for n in SILENCE_NS]
    silence = pd.concat(silence_rows, ignore_index=True)
    silence.to_csv(OUT / "silence_by_segment.csv", index=False)
    episodes.to_csv(OUT / "silence_episodes.csv", index=False)

    structural = (customers.groupby("day_one_segment")
                  .agg(customers=("no_open_card", "size"),
                       no_open_card=("no_open_card", "sum"),
                       share_no_open_card=("no_open_card", "mean"))
                  .reset_index())
    structural.to_csv(OUT / "structural_exit_by_segment.csv", index=False)

    plot_quiet_loss(gap, silence, customers)

    audit = {
        "active_customers": int(len(customers)),
        "purchase_day_rows": int(len(days)),
        "segment_counts": customers.day_one_segment.value_counts().reindex(SEGMENT_ORDER).fillna(0).astype(int).to_dict(),
        "overall_median_gap_days": float(customers.median_gap_days.median()),
        "overall_max_of_max_gap_incl_terminal": float(customers.max_gap_incl_terminal.max()),
        "overall_share_no_open_card": float(customers.no_open_card.mean()),
        "silence_ns": list(SILENCE_NS),
        "return_days_after_alert": RETURN_DAYS,
        "caveats": [
            "Population is the 1,206 customers with settled purchases Nov 2018 – Oct 2019.",
            "Customers with no transaction rows (including ~394 eligible with missing history) are out of scope.",
            "users_data is a Feb 2020 survivor snapshot; customers who left before then are invisible.",
            "Day-one segment uses cards opened in the customer's first-card month (Q1 definition).",
        ],
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2))

    print("\n=== Gap summary ===")
    print(gap.to_string(index=False))
    print("\n=== Silence hit / return ===")
    show = silence[["silence_days", "day_one_segment", "customers", "hit_customers", "hit_rate",
                    "inter_purchase_episodes", "return_rate_given_inter_purchase_silence",
                    "terminal_silence_customers"]]
    print(show.to_string(index=False))
    print("\n=== Structural exit ===")
    print(structural.to_string(index=False))
    print(f"\nWrote {OUT} and {PLOTS / 'q2_quiet_loss.png'}")


if __name__ == "__main__":
    main()
