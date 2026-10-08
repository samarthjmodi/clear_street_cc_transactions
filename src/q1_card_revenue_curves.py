"""Q1: yearly revenue curve of a card as it ages (tenure year 1, 2, ...).

A card's tenure year k covers months [open + 12(k-1), open + 12k). Only full card-years inside
the transaction window (2010-01 to 2019-10) are used. Cards stop transacting after their
`expires` month, so a card-year starting after expiry counts as closed and earns $0.
Revenue = interchange at the Finance rate card + the Amex $95 fee for months the card is open.
Customers with no transactions at all are excluded.

Views
  opened_2010_plus   cards opened 2010-01 or later: every year since opening is visible
  balanced_8y        cards with at least 8 full years visible (opened 2010-01 to 2011-11)
  long_run           all cards incl. those opened before 2010, using the card-years inside the window

Run from repo root after build_card_month.py:
  .venv/bin/python src/q1_card_revenue_curves.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from q1_revenue import AMEX_FEE, WINDOW_END_MONTH, interchange, load_cards, month_index  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
OUT = HANDOUT / "analysis" / "q1_scratch" / "revenue_curves"
PLOTS = REPO / "plots"
FIRST_M = 2010 * 12 + 1
BALANCED_YEARS = 8
MIN_CARDS = 30
RNG = np.random.default_rng(23)
TYPE_LABEL = {"Credit": "Credit", "Debit": "Debit", "Debit (Prepaid)": "Prepaid"}
COLOR = {"Credit": "#1f4e79", "Debit": "#5b8fad", "Prepaid": "#a0a4aa"}


def card_years(cards: pd.DataFrame, cm: pd.DataFrame) -> pd.DataFrame:
    """One row per card x full tenure year inside the window, with revenue and status."""
    x = cm.merge(cards[["card_id", "open_m"]], on="card_id")
    x = x[x.m >= x.open_m]
    x["k"] = (x.m - x.open_m) // 12 + 1
    agg = x.groupby(["card_id", "k"]).agg(interchange=("rev", "sum"), purchases=("purchase_count", "sum"),
                                         purchase_volume=("purchase_volume", "sum"))
    max_k = int((WINDOW_END_MONTH - cards.open_m.min()) // 12 + 1)
    grid = cards[["card_id", "client_id", "card_type", "card_brand", "open_m", "exp_m", "first_card"]].merge(
        pd.DataFrame({"k": np.arange(1, max_k + 1)}), how="cross")
    grid["start_m"] = grid.open_m + 12 * (grid.k - 1)
    grid = grid[(grid.start_m >= FIRST_M) & (grid.start_m + 11 <= WINDOW_END_MONTH)]
    cy = grid.merge(agg, left_on=["card_id", "k"], right_index=True, how="left")
    cy[["interchange", "purchases", "purchase_volume"]] = cy[["interchange", "purchases", "purchase_volume"]].fillna(0)
    cy["is_open"] = cy.exp_m >= cy.start_m
    open_months = np.clip(np.minimum(cy.start_m + 12, cy.exp_m + 1) - cy.start_m, 0, 12)
    amex = cy.card_brand.eq("Amex") & cy.card_type.eq("Credit")
    cy["amex_fee"] = np.where(amex, AMEX_FEE * open_months / 12, 0.0)
    cy["revenue"] = cy.interchange + cy.amex_fee
    cy["active"] = cy.purchases > 0
    cy["type"] = cy.card_type.map(TYPE_LABEL)
    cy["role"] = np.where(cy.first_card, "First card", "Extra card")
    return cy


def cluster_ci(g: pd.DataFrame, col: str, n: int = 1000) -> tuple[float, float]:
    s = g.groupby("client_id")[col].agg(["sum", "count"])
    if len(s) < 2:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(s), size=(n, len(s)))
    m = s["sum"].to_numpy()[idx].sum(axis=1) / s["count"].to_numpy()[idx].sum(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def curve(cy: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in cy.groupby(by + ["k"]):
        if len(g) < MIN_CARDS:
            continue
        lo, hi = cluster_ci(g, "revenue")
        op = g[g.is_open]
        rows.append({
            **dict(zip(by + ["k"], key)),
            "cards": len(g),
            "customers": g.client_id.nunique(),
            "revenue_per_card": g.revenue.mean(),
            "ci_low": lo,
            "ci_high": hi,
            "median_revenue": g.revenue.median(),
            "pct_open": g.is_open.mean(),
            "pct_active": g.active.mean(),
            "revenue_per_open_card": op.revenue.mean() if len(op) else np.nan,
            "revenue_per_active_card": g[g.active].revenue.mean() if g.active.any() else np.nan,
            "purchase_volume_per_card": g.purchase_volume.mean(),
        })
    return pd.DataFrame(rows)


def plot(c10: pd.DataFrame, bal: pd.DataFrame, role: pd.DataFrame, lr: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(13, 9.5))

    ax = axes[0, 0]
    for t in ["Credit", "Debit", "Prepaid"]:
        d = c10[c10.type.eq(t)]
        ax.plot(d.k, d.revenue_per_card, "o-", color=COLOR[t], lw=2, label=t)
        ax.fill_between(d.k, d.ci_low, d.ci_high, color=COLOR[t], alpha=0.15)
        for r in d.itertuples():
            if t != "Prepaid":
                ax.text(r.k, r.ci_high + 12, f"{r.cards}", ha="center", fontsize=6.5, color=COLOR[t])
    ax.set_xlabel("Card age (year since opening)")
    ax.set_ylabel("Revenue per card opened ($/year), 95% CI")
    ax.set_title("Cards opened 2010 or later (labels: cards in each year)")
    ax.set_xticks(sorted(c10.k.unique()))
    ax.set_ylim(0, None)
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    for t in ["Credit", "Debit"]:
        d = bal[bal.type.eq(t)]
        ax.plot(d.k, d.revenue_per_card, "o-", color=COLOR[t], lw=2, label=f"{t}: per card opened")
        ax.plot(d.k, d.revenue_per_open_card, "s--", color=COLOR[t], lw=1.2, label=f"{t}: per card still open")
    ax.set_xlabel("Card age (year since opening)")
    ax.set_ylabel("Revenue ($/year)")
    n_cr, n_db = (int(bal[bal.type.eq(t)].cards.iloc[0]) for t in ["Credit", "Debit"])
    ax.set_title(f"Same cards followed for {BALANCED_YEARS} years ({n_cr} credit, {n_db} debit)")
    ax.set_xticks(range(1, BALANCED_YEARS + 1))
    ax.set_ylim(0, None)
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    for t in ["Credit", "Debit", "Prepaid"]:
        d = c10[c10.type.eq(t)]
        ax.plot(d.k, d.pct_open * 100, "o-", color=COLOR[t], lw=2, label=f"{t}: still open")
        ax.plot(d.k, d.pct_active * 100, "x:", color=COLOR[t], lw=1.5, label=f"{t}: any purchase in year")
    ax.set_xlabel("Card age (year since opening)")
    ax.set_ylabel("Share of cards opened (%)")
    ax.set_title("Survival: cards still open, and cards used, by age (opened 2010+)")
    ax.set_xticks(sorted(c10.k.unique()))
    ax.set_ylim(70, 101)
    ax.legend(fontsize=7.5, ncol=2, loc="lower left")

    ax = axes[1, 1]
    for t in ["Credit", "Debit"]:
        d = lr[lr.type.eq(t)]
        ax.plot(d.k, d.revenue_per_card, "-", color=COLOR[t], lw=2, label=f"{t}: per card")
        ax.fill_between(d.k, d.ci_low, d.ci_high, color=COLOR[t], alpha=0.15)
        ax.plot(d.k, d.revenue_per_open_card, "--", color=COLOR[t], lw=1.2, label=f"{t}: per card still open")
    ax.set_xlabel("Card age (year since opening)")
    ax.set_ylabel("Revenue ($/year), 95% CI")
    ax.set_title(f"Long run: all cards, card-years observed 2010–2019 ({MIN_CARDS}+ cards per point)")
    ax.set_ylim(0, None)
    ax.legend(fontsize=8)

    fig.suptitle("Yearly revenue of a card as it ages (customers with transaction data)", fontsize=12)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_card_revenue_curves.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    for (t, rl), d in role.groupby(["type", "role"]):
        if t == "Prepaid":
            continue
        ax.plot(d.k, d.revenue_per_card, "o-" if rl == "First card" else "o--", color=COLOR[t], lw=2,
                label=f"{t}, {rl.lower()}")
    ax.set_xlabel("Card age (year since opening)")
    ax.set_ylabel("Revenue per card opened ($/year)")
    ax.set_title(f"First card versus extra card, cards opened 2010+ ({MIN_CARDS}+ cards per point)")
    ax.set_ylim(0, None)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(PLOTS / "q1_card_revenue_curves_first_vs_extra.png", dpi=150)
    plt.close(fig)


def replacement_check(cards: pd.DataFrame, cm: pd.DataFrame, window: int = 12) -> dict:
    """Is an expiring card replaced by a new card more often than chance, and does the customer stay?"""
    e = cards[(cards.exp_m >= FIRST_M) & (cards.exp_m < WINDOW_END_MONTH - window)]
    others = cards[["card_id", "client_id", "open_m"]].rename(columns={"card_id": "new_id"})

    def share_with_new_card(ref: pd.Series) -> float:
        m = e[["card_id", "client_id"]].assign(ref=ref.to_numpy()).merge(others, on="client_id")
        m = m[(m.new_id != m.card_id) & m.open_m.between(m.ref - window, m.ref + window)]
        return float(e.card_id.isin(m.card_id).mean())

    random_ref = pd.Series(RNG.integers(FIRST_M, WINDOW_END_MONTH - window, len(e)))
    last = cm[cm.purchase_count > 0].groupby("client_id").m.max()
    return {
        "cards_expired_in_window": len(e),
        f"new_card_within_{window}m_of_expiry": share_with_new_card(e.exp_m),
        f"new_card_within_{window}m_of_random_month": share_with_new_card(random_ref),
        f"customer_still_transacting_{window}m_after_expiry": float((e.client_id.map(last) >= e.exp_m + window).mean()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(exist_ok=True)
    cards = load_cards(HANDOUT / "cards_data.csv")
    cards["exp_m"] = month_index(pd.to_datetime(cards.expires, format="%m/%Y"))
    cards["first_card"] = cards.open_m.eq(cards.groupby("client_id").open_m.transform("min"))
    cm = pd.read_csv(V3 / "card_month.csv")
    cm["m"] = month_index(cm.month)
    observed = set(cm.client_id)
    cm["rev"] = interchange(cm, cm.card_id.map(cards.set_index("card_id").card_type))
    cards = cards[cards.client_id.isin(observed)]

    cy = card_years(cards, cm)
    cy.to_csv(OUT / "card_years.csv", index=False)
    c10 = curve(cy[cy.open_m >= FIRST_M], ["type"])
    bal_cards = cy[(cy.open_m >= FIRST_M) & (cy.open_m + 12 * BALANCED_YEARS - 1 <= WINDOW_END_MONTH)]
    bal = curve(bal_cards[bal_cards.k <= BALANCED_YEARS], ["type"])
    role = curve(cy[cy.open_m >= FIRST_M], ["type", "role"])
    lr = curve(cy, ["type"])
    for name, t in {"curve_opened_2010_plus": c10, "curve_balanced_8y": bal,
                    "curve_first_vs_extra": role, "curve_long_run": lr}.items():
        t.to_csv(OUT / f"{name}.csv", index=False)

    expired = cards[cards.exp_m < WINDOW_END_MONTH]
    life = (cards.exp_m - cards.open_m) / 12
    notes = {
        "cards": len(cards),
        "card_years": len(cy),
        "card_years_opened_2010_plus": int((cy.open_m >= FIRST_M).sum()),
        "balanced_cards": bal_cards.drop_duplicates("card_id").type.value_counts().to_dict(),
        "cards_expired_before_window_end": len(expired),
        "card_life_years_open_to_expiry": life.describe().round(2).to_dict(),
        "card_life_years_by_type_median": life.groupby(cards.card_type).median().round(2).to_dict(),
        "replacement_at_expiry": replacement_check(cards, cm),
        "txn_share_after_expiry": float((cm.merge(cards[["card_id", "exp_m"]], on="card_id")
                                         .pipe(lambda d: (d.txn_count * (d.m > d.exp_m)).sum() / d.txn_count.sum()))),
    }
    (OUT / "curve_notes.json").write_text(json.dumps(notes, indent=2, default=str))
    plot(c10, bal, role, lr)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    for name, t in [("opened 2010+", c10), ("balanced", bal), ("first vs extra", role), ("long run", lr)]:
        print(name)
        print(t.round(2).to_string(index=False), "\n")
    print(json.dumps(notes, indent=2, default=str))


if __name__ == "__main__":
    main()
