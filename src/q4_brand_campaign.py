"""Q4: incremental impact of the March 2019 brand campaign.

Built step by step; each step writes its outputs to analysis/q4/step<N>_*.
Counts and baselines use data from Jan 2018 onward. Whether a customer is new or
existing still uses their full card history, back to 1991.

Run from repo root after src/clean_channel_spend.py (all steps, or the ones listed):
  .venv/bin/python src/q4_brand_campaign.py [1 2 ...]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_channel_spend import dedupe_campaign_days  # noqa: E402
from q4_did import (YEAR, gap_did, period_means, placebo_starts, placebo_summary, shift, span,  # noqa: E402
                    upper_90, yoy_did)

HANDOUT = Path(__file__).resolve().parents[1] / "active_ds_takehome_handout"
SPEND = HANDOUT / "analysis" / "clean" / "clean_channel_spend.csv"
OUT = HANDOUT / "analysis" / "q4"

ANALYSIS_START = "2018-01-01"

# Step 1 definitions
PERIODS = {
    "pre": ("2019-02-18", "2019-03-03"),
    "campaign": ("2019-03-04", "2019-03-17"),
    "post": ("2019-03-18", "2019-03-31"),
}
PRE, CAMPAIGN, POST = PERIODS["pre"], PERIODS["campaign"], PERIODS["post"]
COHORTS = ("existing", "campaign", "post", "later")
OUTCOMES = {
    "new_accounts": "All cards opened in the period (one signup = one card), split into cards opened by "
                    "new customers and cards opened by existing customers",
    "transactions": "Settled purchases (amount > 0, no error) in the period by all customers, split into "
                    "new customers (first signup on or after 2019-03-04) and existing customers (everyone else)",
}


def load_daily_spend() -> pd.DataFrame:
    """Wide table: one row per day, one column per channel."""
    if not SPEND.exists():
        raise FileNotFoundError(f"{SPEND} missing; run src/clean_channel_spend.py first")
    s = pd.read_csv(SPEND, parse_dates=["spend_date"])
    return s.pivot(index="spend_date", columns="channel", values="spend")


def load_cards() -> pd.DataFrame:
    cards = pd.read_csv(HANDOUT / "cards_data.csv", usecols=["id", "client_id", "acct_open_date"])
    cards["open_m"] = pd.to_datetime(cards.acct_open_date, format="%m/%Y").dt.to_period("M")
    return cards.rename(columns={"id": "card_id"})


def classify_signups(signups: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    """kind = new_customer (first signup in the customer's first-card month),
    new_customer_extra_card (another card that same month) or existing_customer."""
    first_m = cards.groupby("client_id").open_m.min()
    s = signups.sort_values(["signup_ts", "signup_id"]).copy()
    s["month"] = s.signup_ts.dt.to_period("M")
    in_first_month = s.month.eq(s.client_id.map(first_m))
    first_signup = ~s.client_id.duplicated()
    s["kind"] = np.select([in_first_month & first_signup, in_first_month],
                          ["new_customer", "new_customer_extra_card"], "existing_customer")
    return s


def days_in(period: tuple[str, str]) -> int:
    return len(pd.date_range(*period))


def first_and_last_line_dates(path: Path, col: int) -> list[str]:
    with open(path, "rb") as f:
        f.readline()
        first = f.readline().decode().split(",")[col]
        f.seek(-2, 2)
        while f.read(1) != b"\n":
            f.seek(-2, 1)
        last = f.readline().decode().split(",")[col]
    return [first, last]


def customer_first_card(cards: pd.DataFrame, signups: pd.DataFrame) -> pd.Series:
    """Time each customer got their first card: the earliest signup in their first-card month,
    or the start of that month when it has no signup (cards opened before 2016)."""
    first_m = cards.groupby("client_id").open_m.min()
    s = signups[signups.signup_ts.dt.to_period("M").eq(signups.client_id.map(first_m))]
    ts = s.groupby("client_id").signup_ts.min().reindex(first_m.index)
    return ts.fillna(first_m.dt.start_time).rename("first_card_ts")


def acquisition_cohort(first_card: pd.Series) -> pd.Series:
    """existing = first card before the campaign; campaign / post = acquired in that period;
    later = acquired after the post period."""
    edges = [pd.Timestamp(CAMPAIGN[0]), pd.Timestamp(POST[0]), pd.Timestamp(POST[1]) + pd.Timedelta(days=1)]
    kind = np.select([first_card < e for e in edges], COHORTS[:3], COHORTS[3])
    return pd.Series(kind, index=first_card.index, name="cohort")


def parse_amount(amount: pd.Series) -> pd.Series:
    return pd.to_numeric(amount.str.replace(r"[$,]", "", regex=True), errors="coerce")


def monthly_purchases(start: str, end: str) -> pd.DataFrame:
    """Settled purchases (amount > 0, no error), their dollars, and purchasing customers per
    month, for transactions dated start to end inclusive."""
    reader = pd.read_csv(HANDOUT / "transactions_data.csv", usecols=["date", "client_id", "amount", "errors"],
                         dtype={"date": "string", "amount": "string", "errors": "string"}, chunksize=1_000_000)
    parts, customers = [], []
    for chunk in reader:
        chunk = chunk[(chunk.date >= start) & (chunk.date < str((pd.Timestamp(end) + pd.Timedelta(days=1)).date()))]
        amt = parse_amount(chunk["amount"])
        p = chunk[(chunk["errors"].isna() | chunk["errors"].eq("")) & (amt > 0)].assign(
            amount=amt, month=lambda d: d.date.str[:7])
        parts.append(p.groupby("month").amount.agg(purchase_count="size", purchase_volume="sum"))
        customers.append(p[["month", "client_id"]].drop_duplicates())
    out = pd.concat(parts).groupby(level=0).sum()
    out["purchasing_customers"] = pd.concat(customers).drop_duplicates().groupby("month").size()
    return out


def daily_transactions(chunk: pd.DataFrame, cohort_of_client: pd.Series) -> pd.DataFrame:
    """Day x cohort: rows, settled purchases (amount > 0, no error) and their dollars,
    refunds (amount < 0, no error) and failed attempts (any error)."""
    amt = parse_amount(chunk["amount"])
    settled = chunk["errors"].isna() | chunk["errors"].eq("")
    purchase = settled & (amt > 0)
    refund = settled & (amt < 0)
    cohort = chunk["client_id"].map(cohort_of_client)
    if cohort.isna().any():
        raise ValueError("transactions from customers with no card")
    df = pd.DataFrame({
        "date": chunk["date"].str.slice(0, 10),
        "cohort": cohort,
        "rows": 1,
        "purchases": purchase.astype(int),
        "purchase_volume": amt.where(purchase, 0.0),
        "refunds": refund.astype(int),
        "refund_volume": (-amt).where(refund, 0.0),
        "failed": (~settled).astype(int),
    })
    return df.groupby(["date", "cohort"], as_index=False).sum()


def daily_signups(classified: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Day: accounts opened, split by new and existing customers, and new customers."""
    s = classified[classified.signup_ts.between(start, end + " 23:59:59")]
    day = s.signup_ts.dt.normalize()
    by_new = s.kind.ne("existing_customer")
    out = pd.DataFrame({
        "accounts": day.value_counts(),
        "accounts_by_new_customers": day[by_new].value_counts(),
        "accounts_by_existing_customers": day[~by_new].value_counts(),
        "new_customers": day[s.kind.eq("new_customer")].value_counts(),
    })
    out = out.reindex(pd.date_range(start, end, name="date")).fillna(0).astype(int)
    return out


def date_runs(dates) -> list[list[str]]:
    """Collapse dates into [first, last] runs of consecutive days."""
    d = pd.DatetimeIndex(sorted(dates))
    if d.empty:
        return []
    gaps = np.flatnonzero(np.diff(d.values) > np.timedelta64(1, "D"))
    starts, ends = np.r_[0, gaps + 1], np.r_[gaps, len(d) - 1]
    return [[str(d[s].date()), str(d[e].date())] for s, e in zip(starts, ends)]


def plain(obj):
    """Make nested results JSON-safe: numpy scalars, Periods, Timestamps and non-str keys."""
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(v) for v in obj]
    if isinstance(obj, (np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, (float, np.floating)):
        return None if np.isnan(obj) else round(float(obj), 4)
    if obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp, pd.Period)):
        return str(obj)
    return obj


# ---------- step 1: facts behind the definitions ----------

def step1() -> dict:
    daily = load_daily_spend()
    raw = pd.read_csv(HANDOUT / "channel_spend.csv", parse_dates=["spend_date"])
    camp = dedupe_campaign_days(raw)
    identical = {
        ch: float(g.pivot(index="spend_date", columns="campaign", values="spend").nunique(axis=1).eq(1).mean())
        for ch, g in camp.groupby("channel")
    }

    monthly = daily.groupby(daily.index.to_period("M")).sum().loc["2018-01":"2019-12"]
    monthly.to_csv(OUT / "step1_monthly_spend.csv")
    per_day = daily.groupby(daily.index.to_period("M")).mean()
    march_vs_neighbours = per_day.loc["2019-03"] / per_day.loc[["2019-02", "2019-04"]].mean() - 1

    cards = load_cards()
    signups = classify_signups(pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"]), cards)
    in_flight = signups.signup_ts.between(CAMPAIGN[0], POST[1] + " 23:59:59")
    base = signups[signups.signup_ts.between(ANALYSIS_START, "2019-12-31 23:59:59") & ~in_flight]
    base_days = days_in((ANALYSIS_START, "2019-12-31")) - days_in((CAMPAIGN[0], POST[1]))
    per_day_new_accounts = len(base) / base_days
    per_day_accounts_by_existing = (base.kind == "existing_customer").sum() / base_days

    cm12 = monthly_purchases("2018-03-01", "2019-02-28")
    txn_days = days_in(("2018-03-01", "2019-02-28"))
    active_customers = cm12.purchasing_customers

    touch_ts = pd.read_csv(HANDOUT / "marketing_touchpoints.csv", usecols=["touch_ts"]).touch_ts

    windows = {name: days_in(p) for name, p in PERIODS.items()}
    facts = {
        "spend": {
            "channels": sorted(daily.columns),
            "share_of_days_campaigns_identical_within_channel": identical,
            "march_2019_spend_per_day_vs_feb_apr_avg": march_vs_neighbours.round(3).to_dict(),
        },
        "volumes_per_day": {
            "new_accounts_2018_2019_excl_mar4_31_2019": float(per_day_new_accounts),
            "new_accounts_by_new_customers_2018_2019_excl_mar4_31_2019":
                float(per_day_new_accounts - per_day_accounts_by_existing),
            "new_accounts_by_existing_customers_2018_2019_excl_mar4_31_2019": float(per_day_accounts_by_existing),
            "settled_purchases_mar2018_feb2019": float(cm12.purchase_count.sum() / txn_days),
            "purchase_volume_mar2018_feb2019": float(cm12.purchase_volume.sum() / txn_days),
            "customers_with_purchases_per_month_mar2018_feb2019": float(active_customers.mean()),
        },
        "expected_counts_without_campaign_naive": {
            name: {"days": d,
                   "new_accounts": float(per_day_new_accounts * d),
                   "new_accounts_by_existing_customers": float(per_day_accounts_by_existing * d),
                   "settled_purchases": float(cm12.purchase_count.sum() / txn_days * d)}
            for name, d in windows.items()
        },
        "coverage": {
            "spend": [str(daily.index.min().date()), str(daily.index.max().date())],
            "signups": [str(signups.signup_ts.min()), str(signups.signup_ts.max())],
            "touchpoints": [touch_ts.min(), touch_ts.max()],
            "transactions": first_and_last_line_dates(HANDOUT / "transactions_data.csv", col=1),
        },
    }
    framing = {
        "periods": PERIODS,
        "outcomes": OUTCOMES,
        "facts": facts,
    }
    (OUT / "step1_framing.json").write_text(json.dumps(framing, indent=2, default=str))
    return framing


# ---------- step 2: data audit (Jan 2018 onward) ----------

def audit_signups(raw: pd.DataFrame, classified: pd.DataFrame, cards: pd.DataFrame,
                  first_card: pd.Series) -> dict:
    users = pd.read_csv(HANDOUT / "users_data.csv", usecols=["id"])
    win = classified[classified.signup_ts >= ANALYSIS_START]
    by_card = cards.set_index("card_id")
    cards_win = cards[cards.open_m >= pd.Period(ANALYSIS_START, "M")]
    integrity = {
        "signups": len(win),
        "unique_signup_ids": win.signup_id.nunique(),
        "unique_card_ids": win.card_id.nunique(),
        "null_values": int(win[raw.columns].isna().sum().sum()),
        "card_not_in_cards_data": int((~win.card_id.isin(cards.card_id)).sum()),
        "client_not_in_users_data": int((~win.client_id.isin(users.id)).sum()),
        "client_differs_from_card_owner": int(win.card_id.map(by_card.client_id).ne(win.client_id).sum()),
        "signup_month_differs_from_card_open_month": int(win.card_id.map(by_card.open_m).ne(win.month).sum()),
        "cards_opened_in_window": len(cards_win),
        "cards_opened_in_window_without_signup": int((~cards_win.card_id.isin(raw.card_id)).sum()),
    }

    kinds = ["new_customer", "new_customer_extra_card", "existing_customer"]
    by_year = win.groupby([win.signup_ts.dt.year, "kind"]).size().unstack(fill_value=0).reindex(columns=kinds, fill_value=0)
    first_card_year = cards.groupby("client_id").open_m.min().dt.year.value_counts()
    by_month = win.groupby([win.month, "kind"]).size().unstack(fill_value=0).reindex(columns=kinds, fill_value=0)
    march = first_card[(first_card >= "2019-03-01") & (first_card < "2019-04-01")]
    classification = {
        "by_year": by_year.to_dict(orient="index"),
        "new_customers_vs_customers_whose_first_card_opened_that_year":
            {y: [int(by_year.loc[y, "new_customer"]), int(first_card_year.get(y, 0))] for y in by_year.index},
        "by_month": {str(m): r for m, r in by_month.to_dict(orient="index").items()},
        "new_customers_march_2019": [
            {"client_id": c, "first_card_ts": t, "cohort": acquisition_cohort(pd.Series([t])).iloc[0]}
            for c, t in march.sort_values().items()],
    }

    pre2020 = win[win.signup_ts < "2020-01-01"].signup_ts
    timestamps = {
        "scope": "2018-2019 signups",
        "share_with_zero_seconds": float((pre2020.dt.second == 0).mean()),
        "share_at_exact_midnight": float((pre2020.dt.hour.eq(0) & pre2020.dt.minute.eq(0)).mean()),
        "signups_sharing_a_timestamp": int(pre2020.duplicated(keep=False).sum()),
        "by_hour": pre2020.dt.hour.value_counts().sort_index().to_dict(),
        "by_weekday": pre2020.dt.day_name().value_counts().to_dict(),
    }

    end = str(classified.signup_ts.max().to_period("M").end_time.date())
    daily = daily_signups(classified, ANALYSIS_START, end)
    daily.to_csv(OUT / "step2_daily_signups.csv")
    return {"integrity": integrity, "classification": classification, "timestamps": timestamps,
            "daily_file_days": len(daily)}


def audit_transactions(cards: pd.DataFrame, classified: pd.DataFrame, first_card: pd.Series) -> dict:
    cohort = acquisition_cohort(first_card)
    owner = cards.set_index("card_id").client_id
    open_month = cards.set_index("card_id").open_m.astype(str)
    parts, ids, first_by_card, first_by_client = [], [], [], []
    checks = Counter()
    hours = Counter()
    reasons = Counter()
    reader = pd.read_csv(
        HANDOUT / "transactions_data.csv",
        usecols=["id", "date", "client_id", "card_id", "amount", "errors"],
        dtype={"errors": "string", "amount": "string", "date": "string"},
        chunksize=1_000_000,
    )
    for chunk in reader:
        chunk = chunk[chunk.date >= ANALYSIS_START]
        if chunk.empty:
            continue
        parts.append(daily_transactions(chunk, cohort))
        ids.append(chunk.id.to_numpy())
        checks["rows"] += len(chunk)
        checks["null_key_fields"] += int(chunk[["id", "date", "client_id", "card_id", "amount"]].isna().sum().sum())
        checks["amount_not_parsed"] += int(parse_amount(chunk.amount).isna().sum())
        checks["timestamp_seconds_not_zero"] += int(chunk.date.str.slice(17, 19).ne("00").sum())
        checks["card_owner_differs"] += int(chunk.card_id.map(owner).ne(chunk.client_id).sum())
        checks["before_card_open_month"] += int((chunk.date.str.slice(0, 7) < chunk.card_id.map(open_month)).sum())
        hours.update(chunk.date.str.slice(11, 13).astype(int).value_counts().to_dict())
        reasons.update(chunk.errors.dropna().str.split(",").explode().str.strip().value_counts().to_dict())
        first_by_card.append(chunk.groupby("card_id").date.min())
        first_by_client.append(chunk.groupby("client_id").date.min())

    ids = np.concatenate(ids)
    daily = pd.concat(parts).groupby(["date", "cohort"]).sum()
    dates = pd.date_range(ANALYSIS_START, daily.index.get_level_values("date").max())
    grid = pd.MultiIndex.from_product([dates.strftime("%Y-%m-%d"), COHORTS], names=["date", "cohort"])
    daily = daily.reindex(grid, fill_value=0).reset_index()
    daily.to_csv(OUT / "step2_daily_transactions.csv", index=False)
    if daily.rows.sum() != checks["rows"]:
        raise AssertionError("rows lost in daily aggregation")

    total = daily.groupby("date").sum(numeric_only=True)
    total.index = pd.to_datetime(total.index)
    p = total.purchases
    neighbours = pd.concat([p.shift(k) for k in (-28, -21, -14, -7, 7, 14, 21, 28)], axis=1).median(axis=1)
    ratio = (p / neighbours).dropna()
    monthly = total.resample("MS").sum()

    integrity = dict(checks)
    integrity.update({
        "duplicate_ids": int(len(ids) - len(np.unique(ids))),
        "days_with_no_rows": date_runs(total.index[total.rows.eq(0)]),
        "failed_share_of_rows": float(total.failed.sum() / total.rows.sum()),
        "top_failure_reasons": dict(reasons.most_common(5)),
        "refund_dollars_as_share_of_purchase_dollars": float(total.refund_volume.sum() / total.purchase_volume.sum()),
        "rows_by_hour": dict(sorted(hours.items())),
    })
    patterns = {
        "purchases_per_day_mean": float(p.mean()),
        "weekday_index": (p.groupby(p.index.day_name()).mean() / p.mean()).to_dict(),
        "monthly_purchases": {str(k.date())[:7]: int(v) for k, v in monthly.purchases.items()},
        "monthly_purchase_volume": {str(k.date())[:7]: float(v) for k, v in monthly.purchase_volume.items()},
        "day_vs_same_weekday_neighbours": {
            "p01": float(ratio.quantile(0.01)), "p99": float(ratio.quantile(0.99)),
            "days_outside_0.85_1.15": int(((ratio < 0.85) | (ratio > 1.15)).sum()),
            "lowest_days": ratio.nsmallest(5).round(3).rename(lambda d: str(d.date())).to_dict(),
            "highest_days": ratio.nlargest(5).round(3).rename(lambda d: str(d.date())).to_dict(),
        },
        "share_of_purchases_by_cohort_mar_2019":
            daily[daily.date.between("2019-03-01", "2019-03-31")].groupby("cohort").purchases.sum()
            .pipe(lambda s: (s / s.sum()).to_dict()),
    }

    first_card_txn = pd.to_datetime(pd.concat(first_by_card).groupby(level=0).min())
    first_client_txn = pd.to_datetime(pd.concat(first_by_client).groupby(level=0).min())
    data_end = str(dates.max().date()) + " 23:59:59"
    acquired = first_card[first_card.between(ANALYSIS_START, data_end)]
    lag_c = (first_client_txn.reindex(acquired.index) - acquired).dt.days
    opened = classified[classified.signup_ts.between(ANALYSIS_START, data_end)].copy()
    opened["first_txn"] = opened.card_id.map(first_card_txn)
    opened["lag_days"] = (opened.first_txn - opened.signup_ts).dt.total_seconds() / 86400
    opened["customer_transacts"] = opened.client_id.isin(first_client_txn.index)
    opened["is_new"] = opened.kind.ne("existing_customer")

    def lag_summary(g: pd.DataFrame) -> dict:
        lag = g.lag_days.dropna()
        n = max(len(g), 1)
        return {"cards": len(g), "with_any_transaction": int(g.first_txn.notna().sum()),
                "customer_has_transactions_on_other_cards": int(g.customer_transacts.sum()),
                "first_txn_before_signup": int((lag < 0).sum()),
                "lag_days_median": float(lag.median()) if len(lag) else None,
                "share_transacting_within_7_days": float((lag <= 7).sum() / n),
                "share_transacting_within_28_days": float((lag <= 28).sum() / n)}

    in_march = opened.signup_ts.between("2019-03-01", "2019-03-31 23:59:59")
    same_month = opened.dropna(subset=["first_txn"])
    same_month = same_month[same_month.first_txn.dt.to_period("M").eq(same_month.month)]
    coverage = {
        "customers_transacting_in_window": int(len(first_client_txn)),
        "latest_first_card_among_transacting_customers": first_card.reindex(first_client_txn.index).max(),
        "cards_first_transacting_in_open_month": {
            "cards": len(same_month),
            "first_txn_day_of_month_quantiles": same_month.first_txn.dt.day.quantile([.25, .5, .75]).to_dict(),
            "signup_day_of_month_quantiles": same_month.signup_ts.dt.day.quantile([.25, .5, .75]).to_dict(),
            "share_first_txn_before_signup": float((same_month.first_txn < same_month.signup_ts).mean()),
            "corr_signup_day_first_txn_day": float(same_month.signup_ts.dt.day.corr(same_month.first_txn.dt.day)),
        },
        "customers_acquired_in_window": len(acquired),
        "acquired_with_any_transaction": int(lag_c.notna().sum()),
        "acquired_lag_days_to_first_txn_median": float(lag_c.median()),
        "cards_opened_in_window_by_new_customers": lag_summary(opened[opened.is_new]),
        "cards_opened_in_window_by_existing_customers": lag_summary(opened[~opened.is_new]),
        "cards_opened_march_2019": [
            {"card_id": r.card_id, "client_id": r.client_id, "signup_ts": r.signup_ts, "kind": r.kind,
             "first_txn": r.first_txn, "customer_has_transactions": r.customer_transacts}
            for r in opened[in_march].sort_values("signup_ts").itertuples()],
    }
    return {"integrity": integrity, "patterns": patterns, "coverage": coverage}


def audit_touchpoints() -> dict:
    t = pd.read_csv(HANDOUT / "marketing_touchpoints.csv", usecols=["touch_ts", "channel", "client_id"])
    t = t[t.touch_ts >= ANALYSIS_START]
    t["date"] = pd.to_datetime(t.touch_ts.str.slice(0, 10))
    daily = t.pivot_table(index="date", columns="channel", values="touch_ts", aggfunc="size", fill_value=0)
    daily = daily.reindex(pd.date_range(ANALYSIS_START, daily.index.max(), name="date"), fill_value=0)
    daily.to_csv(OUT / "step2_daily_touchpoints.csv")

    spend = load_daily_spend().loc[ANALYSIS_START:daily.index.max()]
    camp, prior = slice(*CAMPAIGN), slice("2019-02-04", "2019-03-03")
    by_channel = {}
    for ch in spend.columns:
        weekly = pd.DataFrame({"touches": daily[ch], "spend": spend[ch]}).resample("W-SUN").sum()
        by_channel[ch] = {
            "daily_corr_touches_spend": float(daily[ch].corr(spend[ch])),
            "weekly_corr_touches_spend": float(weekly.touches.corr(weekly.spend)),
            "campaign_vs_prior_4_weeks_touches": float(daily.loc[camp, ch].mean() / daily.loc[prior, ch].mean() - 1),
            "campaign_vs_prior_4_weeks_spend": float(spend.loc[camp, ch].mean() / spend.loc[prior, ch].mean() - 1),
            "zero_touch_days": date_runs(daily.index[daily[ch].eq(0)]),
        }
    direct_share = daily["direct"] / daily.sum(axis=1)
    return {
        "touches": len(t),
        "touches_with_client_id": int(t.client_id.notna().sum()),
        "touches_per_day_by_year": (daily.sum(axis=1).groupby(daily.index.year).mean()).to_dict(),
        "paid_channels": by_channel,
        "direct_share_median": float(direct_share.median()),
        "days_direct_over_half_of_touches": date_runs(direct_share.index[direct_share > 0.5]),
    }


def step2() -> dict:
    cards = load_cards()
    raw = pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"])
    classified = classify_signups(raw, cards)
    first_card = customer_first_card(cards, raw)
    audit = plain({
        "analysis_window_start": ANALYSIS_START,
        "signups": audit_signups(raw, classified, cards, first_card),
        "transactions": audit_transactions(cards, classified, first_card),
        "touchpoints": audit_touchpoints(),
    })
    (OUT / "step2_audit.json").write_text(json.dumps(audit, indent=2))
    return audit


# ---------- step 3: difference-in-differences ----------

TREATED = "paid_search_brand"
CO_TREATED = "paid_social_meta"
CONTROLS = ["paid_search_nonbrand", "apple_search_ads", "microsoft_ads", "paid_social_reddit"]
TOUCH_OUTAGE = ("2019-06-03", "2019-06-23")
PLOTS = HANDOUT.parent / "plots"
EXTENDED_POST = {**PERIODS, "post": (POST[0], "2019-04-28")}
CALENDAR_MONTHS = (
    {"pre": ("2019-01-01", "2019-02-28"), "campaign": ("2019-03-01", "2019-03-31"), "post": ("2019-04-01", "2019-04-30")},
    {"pre": ("2018-01-01", "2018-02-28"), "campaign": ("2018-03-01", "2018-03-31"), "post": ("2018-04-01", "2018-04-30")},
)


def load_rates() -> dict:
    r = pd.read_csv(HANDOUT / "revenue_assumptions.csv").set_index("assumption_key").assumption_value
    return {"credit": r["interchange_credit_bps"] / 1e4, "debit": r["interchange_debit_bps"] / 1e4,
            "debit_fixed": r["interchange_debit_fixed_cents"] / 100}


def interchange(amount: np.ndarray, card_type: np.ndarray, rates: dict) -> np.ndarray:
    """Interchange on settled purchases. Prepaid earns none: the rate card doesn't cover it
    and Q1 used $0."""
    return np.where(card_type == "Credit", amount * rates["credit"],
                    np.where(card_type == "Debit", amount * rates["debit"] + rates["debit_fixed"], 0.0))


def load_card_info() -> pd.DataFrame:
    c = pd.read_csv(HANDOUT / "cards_data.csv", usecols=["id", "card_type", "acct_open_date"])
    opened = pd.to_datetime(c.acct_open_date, format="%m/%Y")
    return pd.DataFrame({"card_type": c.card_type.to_numpy(),
                         "open_idx": (opened.dt.year * 12 + opened.dt.month).to_numpy()}, index=c.id.rename("card_id"))


def daily_purchases(chunk: pd.DataFrame, card_info: pd.DataFrame, rates: dict) -> pd.DataFrame:
    """Day x card type x new_card: settled purchases, dollars and interchange.
    new_card = the card opened in the purchase's month or the month before."""
    amt = parse_amount(chunk["amount"])
    keep = ((chunk["errors"].isna() | chunk["errors"].eq("")) & (amt > 0)).to_numpy(dtype=bool)
    p, a = chunk[keep], amt[keep].to_numpy()
    info = card_info.reindex(p.card_id)
    if info.card_type.isna().any():
        raise ValueError("purchases on cards missing from cards_data")
    month_idx = p.date.str.slice(0, 4).astype(int).to_numpy() * 12 + p.date.str.slice(5, 7).astype(int).to_numpy()
    ct = info.card_type.to_numpy()
    df = pd.DataFrame({
        "date": p.date.str.slice(0, 10).to_numpy(),
        "card_type": ct,
        "new_card": month_idx - info.open_idx.to_numpy() <= 1,
        "purchases": 1,
        "purchase_volume": a,
        "interchange": interchange(a, ct, rates),
    })
    return df.groupby(["date", "card_type", "new_card"], as_index=False).sum()


def build_daily_purchases() -> pd.DataFrame:
    rates, info = load_rates(), load_card_info()
    reader = pd.read_csv(HANDOUT / "transactions_data.csv", usecols=["date", "card_id", "amount", "errors"],
                         dtype={"errors": "string", "amount": "string", "date": "string"}, chunksize=1_000_000)
    parts = []
    for chunk in reader:
        chunk = chunk[chunk.date >= ANALYSIS_START]
        if len(chunk):
            parts.append(daily_purchases(chunk, info, rates))
    d = pd.concat(parts).groupby(["date", "card_type", "new_card"], as_index=False).sum()
    d.to_csv(OUT / "step3_daily_purchases.csv", index=False)
    d["date"] = pd.to_datetime(d.date)
    return d


def channel_panels() -> dict[str, pd.DataFrame]:
    s = pd.read_csv(SPEND, parse_dates=["spend_date"])
    panels = {m: s.pivot(index="spend_date", columns="channel", values=m).loc[ANALYSIS_START:]
              for m in ["spend", "impressions", "clicks", "platform_reported_conversions"]}
    touches = OUT / "step2_daily_touchpoints.csv"
    if not touches.exists():
        raise FileNotFoundError(f"{touches} missing; run step 2 first")
    panels["touches"] = pd.read_csv(touches, index_col=0, parse_dates=True)
    return panels


def pct(log_effect):
    return np.expm1(log_effect)


def channel_did(panels: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    start = span(PERIODS)[0]
    starts = placebo_starts(PERIODS, ANALYSIS_START, "2019-12-31", exclude=[TOUCH_OUTAGE])
    results, means, placebos = {}, [], []
    for metric in ["spend", "impressions", "clicks", "touches"]:
        p = panels[metric]
        est = gap_did(p, TREATED, CONTROLS, PERIODS)
        dates = pd.Series({s: gap_did(p, TREATED, CONTROLS, shift(PERIODS, s - start))["campaign"] for s in starts})
        placebos.append(pd.DataFrame({"design": "channel", "outcome": metric, "start": dates.index,
                                      "estimate": pct(dates.to_numpy())}))
        results[metric] = {
            "campaign_effect": pct(est["campaign"]),
            "post_effect": pct(est["post"]),
            "campaign_effect_without_microsoft":
                pct(gap_did(p, TREATED, [c for c in CONTROLS if c != "microsoft_ads"], PERIODS)["campaign"]),
            "meta_campaign_effect": pct(gap_did(p, CO_TREATED, CONTROLS, PERIODS)["campaign"]),
            "placebo_channels_campaign_effect": {
                c: pct(gap_did(p, c, [x for x in CONTROLS if x != c], PERIODS)["campaign"]) for c in CONTROLS},
            "placebo_dates": placebo_summary(pct(est["campaign"]), pct(dates)),
        }
        for ch in [TREATED, CO_TREATED, *CONTROLS]:
            means.append({"metric": metric, "channel": ch, **period_means(p[ch], PERIODS).to_dict()})
        means.append({"metric": metric, "channel": "controls_total",
                      **period_means(p[CONTROLS].sum(axis=1), PERIODS).to_dict()})
    return results, pd.DataFrame(means), pd.concat(placebos)


def weekly_gap(p: pd.DataFrame, start: str = "2019-01-07", end: str = "2019-04-28") -> pd.Series:
    """Brand-minus-controls log gap by week, relative to the pre period, as a % effect."""
    y = np.log(p.loc[start:end, [TREATED, *CONTROLS]])
    gap = y[TREATED] - y[CONTROLS].mean(axis=1)
    weekly = gap.resample("W-MON", label="left", closed="left").mean()
    return pct(weekly - gap.loc[slice(*PRE)].mean())


def sparse_channel_counts(panels: dict) -> dict:
    t = pd.read_csv(HANDOUT / "marketing_touchpoints.csv", usecols=["client_id", "touch_ts", "channel"])
    t = t[t.client_id.notna()]
    groups = {"brand": [TREATED], "meta": [CO_TREATED], "controls": CONTROLS}
    out = {}
    for name, (a, z) in PERIODS.items():
        in_p = t[t.touch_ts.between(a, z + " 23:59:59")]
        conv = panels["platform_reported_conversions"].loc[a:z]
        out[name] = {g: {"platform_conversions": float(conv[chs].sum().sum()),
                         "linked_customers": int(in_p[in_p.channel.isin(chs)].client_id.nunique())}
                     for g, chs in groups.items()}
    return out


def yoy_dids(accounts: pd.DataFrame, purchases: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    tot = purchases.groupby("date")[["purchases", "purchase_volume", "interchange"]].sum()
    new_cards = purchases[purchases.new_card].groupby("date").purchases.sum().reindex(tot.index, fill_value=0)
    series = {
        "accounts": accounts.accounts,
        "accounts_by_existing_customers": accounts.accounts_by_existing_customers,
        "settled_purchases": tot.purchases,
        "purchase_volume": tot.purchase_volume,
        "interchange": tot.interchange,
        "purchases_on_new_cards": new_cards,
    }
    data_end = {k: ("2019-12-31" if k.startswith("accounts") else str(tot.index.max().date())) for k in series}
    designs = {"main": (PERIODS, None), "post_extended_6_weeks": (EXTENDED_POST, None),
               "calendar_months": CALENDAR_MONTHS}
    start = span(PERIODS)[0]
    results, rows, placebos = {}, [], []
    for name, s in series.items():
        results[name] = {}
        for design, (this, last) in designs.items():
            lvl = yoy_did(s, this, last)
            days = pd.Series({k: len(pd.date_range(*this[k])) for k in lvl.index})
            entry = {"per_day": lvl.did.to_dict(), "total": (lvl.did * days).to_dict()}
            if not name.startswith("accounts"):
                entry["pct"] = pct(yoy_did(s, this, last, log=True).did).to_dict()
            results[name][design] = entry
            last = last or shift(this, -YEAR)
            for k in this:
                rows.append({"outcome": name, "design": design, "period": k, "this_year": this[k],
                             "last_year": last[k], "this_year_mean": s.loc[slice(*this[k])].mean(),
                             "last_year_mean": s.loc[slice(*last[k])].mean()})
        starts = placebo_starts(PERIODS, "2018-12-31", data_end[name])
        log = not name.startswith("accounts")
        est = yoy_did(s, PERIODS, log=log).did["campaign"]
        pl = pd.Series({st: yoy_did(s, shift(PERIODS, st - start), log=log).did["campaign"] for st in starts})
        scale = 14 if not log else 1
        results[name]["main"]["placebo_campaign"] = placebo_summary(
            (pct(est) if log else est * scale), (pct(pl) if log else pl * scale))
        placebos.append(pd.DataFrame({"design": "yoy", "outcome": name, "start": pl.index,
                                      "estimate": pct(pl.to_numpy()) if log else pl.to_numpy() * scale}))

    def counts(s, periods):
        return {k: int(round(s.loc[slice(*v)].sum())) for k, v in periods.items()}
    c19, c18 = counts(accounts.accounts, PERIODS), counts(accounts.accounts, shift(PERIODS, -YEAR))
    results["accounts"]["main"]["counts"] = {"2019": c19, "2018_same_weekdays": c18}
    results["accounts"]["main"]["poisson_se_total"] = {
        k: float(np.sqrt(c19[k] + c19["pre"] + c18[k] + c18["pre"])) for k in ("campaign", "post")}
    return results, pd.DataFrame(rows), pd.concat(placebos)


def incremental_spend(panels: dict) -> dict:
    """Spend above what the channel would have spent had it moved like the controls:
    pre-period level x controls' change, summed over the period's days."""
    sp = panels["spend"]
    ctrl = period_means(sp[CONTROLS].sum(axis=1), PERIODS)
    out = {}
    for ch in [TREATED, CO_TREATED]:
        m = period_means(sp[ch], PERIODS)
        out[ch] = {k: float((m[k] - m["pre"] * ctrl[k] / ctrl["pre"]) * len(pd.date_range(*PERIODS[k])))
                   for k in ("campaign", "post")}
    return out


def plot_step3(panels: dict, accounts: pd.DataFrame, purchases: pd.DataFrame, placebos: pd.DataFrame,
               real: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PLOTS.mkdir(exist_ok=True)
    lo, hi = "2019-02-04", "2019-04-14"

    def shade(ax):
        ax.axvspan(pd.Timestamp(CAMPAIGN[0]), pd.Timestamp(CAMPAIGN[1]) + pd.Timedelta(hours=23), color="tab:orange", alpha=0.15, label="campaign")
        for d in (PRE[0], POST[1]):
            ax.axvline(pd.Timestamp(d), color="grey", lw=0.8, ls=":")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, metric in zip(axes, ["clicks", "touches"]):
        p = panels[metric].loc[lo:hi]
        idx = p / p.loc[slice(*PRE)].mean() * 100
        ax.plot(idx.index, idx[TREATED], color="tab:blue", label="brand search")
        ax.plot(idx.index, idx[CONTROLS].mean(axis=1), color="black", label="control channels (avg)")
        shade(ax)
        ax.set_title({"clicks": "Platform-reported clicks", "touches": "Site touches"}[metric])
        ax.set_ylabel("index, pre period = 100")
        ax.tick_params(axis="x", rotation=45)
    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle("Brand search vs control channels: clicks doubled, site touches did not")
    fig.tight_layout()
    fig.savefig(PLOTS / "q4_brand_vs_controls.png", dpi=150)
    plt.close(fig)

    tot = purchases.groupby("date").purchases.sum()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    wk = accounts.accounts.resample("W-MON", label="left", closed="left").sum()
    w19 = wk.loc["2019-01-07":"2019-04-22"]
    w18 = wk.reindex(w19.index - YEAR).to_numpy()
    x = np.arange(len(w19))
    axes[0].bar(x - 0.2, w18, 0.4, color="lightgrey", label="same weeks 2018")
    axes[0].bar(x + 0.2, w19.to_numpy(), 0.4, color="tab:blue", label="2019")
    camp_weeks = [i for i, d in enumerate(w19.index) if CAMPAIGN[0] <= str(d.date()) <= CAMPAIGN[1]]
    axes[0].axvspan(min(camp_weeks) - 0.5, max(camp_weeks) + 0.5, color="tab:orange", alpha=0.15)
    axes[0].set_xticks(x, [d.strftime("%b %d") for d in w19.index], rotation=45, fontsize=8)
    axes[0].set_title("Accounts opened per week")
    axes[0].legend(fontsize=8)
    wp = tot.resample("W-MON", label="left", closed="left").sum()
    p19 = wp.reindex(w19.index)
    change = (p19.to_numpy() / wp.reindex(w19.index - YEAR).to_numpy() - 1) * 100
    axes[1].bar(x, change, 0.6, color="tab:blue")
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].axvspan(min(camp_weeks) - 0.5, max(camp_weeks) + 0.5, color="tab:orange", alpha=0.15)
    axes[1].set_xticks(x, [d.strftime("%b %d") for d in w19.index], rotation=45, fontsize=8)
    axes[1].set_ylabel("% vs same week 2018")
    axes[1].set_title("Settled purchases per week, 2019 vs 2018")
    fig.suptitle("Accounts and transactions in 2019 vs the same weeks of 2018")
    fig.tight_layout()
    fig.savefig(PLOTS / "q4_yoy_outcomes.png", dpi=150)
    plt.close(fig)

    panels_spec = [("channel", "touches", "Brand touches vs controls (% effect)", True),
                   ("yoy", "settled_purchases", "Settled purchases vs 2018 (% effect)", True),
                   ("yoy", "accounts", "Accounts vs 2018 (accounts over 14 days)", False)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (design, outcome, title, as_pct) in zip(axes, panels_spec):
        scale = 100 if as_pct else 1
        pl = placebos[(placebos.design == design) & (placebos.outcome == outcome)].estimate
        ax.hist(pl * scale, bins=20, color="lightgrey", edgecolor="grey", label="placebo windows")
        r = real[(design, outcome)] * scale
        ax.axvline(r, color="tab:red", lw=2, label="March 2019")
        lo_x, hi_x = min(pl.min() * scale, r), max(pl.max() * scale, r)
        ax.set_xlim(lo_x - 0.1 * (hi_x - lo_x), hi_x + 0.1 * (hi_x - lo_x))
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("placebo windows")
    axes[0].legend(fontsize=8)
    fig.suptitle("The March 2019 estimates against the same design on other weeks")
    fig.tight_layout()
    fig.savefig(PLOTS / "q4_placebos.png", dpi=150)
    plt.close(fig)


def step3() -> dict:
    panels = channel_panels()
    channel, channel_means, channel_placebos = channel_did(panels)
    accounts = pd.read_csv(OUT / "step2_daily_signups.csv", index_col=0, parse_dates=True)
    purchases = build_daily_purchases()
    yoy, yoy_means, yoy_placebos = yoy_dids(accounts, purchases)
    spend = incremental_spend(panels)

    incr_accounts = yoy["accounts"]["main"]["total"]["campaign"]
    brand, meta = spend[TREATED]["campaign"], spend[CO_TREATED]["campaign"]
    actual = yoy_means[(yoy_means.design == "main") & (yoy_means.period == "campaign")].set_index(
        "outcome").this_year_mean * len(pd.date_range(*CAMPAIGN))
    upper = {"accounts": incr_accounts + 1.645 * yoy["accounts"]["main"]["poisson_se_total"]["campaign"]}
    for o in ("settled_purchases", "interchange"):
        upper[o] = upper_90(yoy[o]["main"]["total"]["campaign"], actual[o],
                            yoy[o]["main"]["placebo_campaign"]["placebo_sd"])
    cost = {
        "incremental_spend_campaign": {"brand_search": brand, "meta": meta, "brand_plus_meta": brand + meta},
        "incremental_campaign": {o: yoy[o]["main"]["total"]["campaign"] for o in upper},
        "incremental_campaign_upper_90": upper,
        "interchange_per_dollar_of_brand_spend": {
            "estimate": yoy["interchange"]["main"]["total"]["campaign"] / brand,
            "upper_90": upper["interchange"] / brand},
    }

    channel_means.to_csv(OUT / "step3_channel_period_means.csv", index=False)
    yoy_means.to_csv(OUT / "step3_yoy_period_means.csv", index=False)
    placebos = pd.concat([channel_placebos, yoy_placebos])
    placebos.to_csv(OUT / "step3_placebos.csv", index=False)
    plot_step3(panels, accounts, purchases, placebos, real={
        ("channel", "touches"): channel["touches"]["campaign_effect"],
        ("yoy", "settled_purchases"): yoy["settled_purchases"]["main"]["pct"]["campaign"],
        ("yoy", "accounts"): incr_accounts,
    })

    out = plain({
        "periods": PERIODS,
        "controls": CONTROLS,
        "channel_did": channel,
        "weekly_gap_vs_pre": {m: {str(k.date()): v for k, v in weekly_gap(panels[m]).items()}
                              for m in ["clicks", "touches"]},
        "sparse_channel_counts": sparse_channel_counts(panels),
        "yoy_did": yoy,
        "cost": cost,
    })
    (OUT / "step3_did.json").write_text(json.dumps(out, indent=2))
    return out


STEPS = {1: step1, 2: step2, 3: step3}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n in [int(a) for a in sys.argv[1:]] or STEPS:
        print(f"=== step {n} ===")
        print(json.dumps(STEPS[n](), indent=2, default=str))


if __name__ == "__main__":
    main()
