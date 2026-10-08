"""Test the VP's three channel beliefs: Microsoft Ads is most efficient (platform CAC ~$770),
Apple Search Ads is a money pit, and affiliate is free growth to scale.

Uses channel_spend, marketing_touchpoints and account_signups, plus cards_data to tell new
customers from existing ones, and the Q1 day-one segment values to price customer quality.

Run from repo root after q1_v3_cohorts.py and q1_v3_segments.py:
  .venv/bin/python src/vp_hypotheses.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_channels import clean_spend  # noqa: E402
from q1_revenue import load_cards  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
HANDOUT = REPO / "active_ds_takehome_handout"
V3 = HANDOUT / "analysis" / "q1_scratch" / "v3"
OUT = HANDOUT / "analysis" / "hypotheses"
PAID = ["paid_search_brand", "paid_search_nonbrand", "paid_social_meta", "paid_social_reddit",
        "microsoft_ads", "apple_search_ads"]
RULES = ["last", "first", "linear", "any"]
RNG = np.random.default_rng(7)


def load_linked_touches(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Touches carrying a client_id, plus touch volume by channel and year for all touches."""
    cols = ["touch_id", "client_id", "touch_ts", "channel", "utm_campaign"]
    linked, vol = [], []
    for ch in pd.read_csv(path, usecols=cols, parse_dates=["touch_ts"], chunksize=300_000):
        vol.append(ch.groupby([ch.channel, ch.touch_ts.dt.year.rename("year")]).size())
        linked.append(ch[ch.client_id.notna()])
    tp = pd.concat(linked, ignore_index=True)
    tp["client_id"] = tp.client_id.astype(int)
    volume = pd.concat(vol).groupby(level=[0, 1]).sum().unstack("year", fill_value=0)
    return tp, volume


def flag_acquisitions(signups: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    """A signup is an acquisition if it is the customer's first signup and falls in the month
    of their first card. Other signups in that month are a new customer's extra cards; later
    ones are existing customers' extra cards."""
    s = signups.sort_values(["signup_ts", "signup_id"]).copy()
    first_m = cards.groupby("client_id").open_m.min()
    in_first_month = (s.signup_ts.dt.year * 12 + s.signup_ts.dt.month).eq(s.client_id.map(first_m))
    s["acquisition"] = in_first_month & ~s.client_id.duplicated()
    s["kind"] = np.select([s.acquisition, in_first_month],
                          ["acquisition", "new_customer_extra_card"], "existing_customer")
    s["period"] = np.where(s.signup_ts.dt.year >= 2020, "2020", "2016-19")
    return s


def journeys(tp: pd.DataFrame, signups: pd.DataFrame) -> pd.DataFrame:
    """Assign each touch to the customer's next signup at or after it; drop touches after the
    customer's last signup (lifecycle email)."""
    t = pd.merge_asof(
        tp.sort_values("touch_ts"),
        signups[["client_id", "signup_id", "signup_ts", "acquisition", "period"]].sort_values("signup_ts"),
        left_on="touch_ts", right_on="signup_ts", by="client_id", direction="forward",
    )
    return t[t.signup_id.notna()].sort_values(["signup_id", "touch_ts", "touch_id"])


def credits(j: pd.DataFrame) -> pd.DataFrame:
    """Credit per (signup, channel) under each rule. Each signup sums to 1 for last, first and
    linear; 'any' gives 1 to every channel in the journey."""
    g = j.groupby("signup_id")
    n = g.channel.transform("size")
    j = j.assign(last=(g.cumcount(ascending=False) == 0).astype(float),
                 first=(g.cumcount() == 0).astype(float), linear=1 / n)
    c = j.groupby(["signup_id", "channel"])[["last", "first", "linear"]].sum()
    c["any"] = 1.0
    return c.reset_index()


def cac_table(cr: pd.DataFrame, spend: pd.Series) -> pd.DataFrame:
    att = cr.groupby("channel")[RULES].sum().reindex(PAID).fillna(0)
    out = att.add_prefix("customers_")
    for r in RULES:
        out[f"cac_{r}"] = spend.reindex(PAID) / att[r].replace(0, np.nan)
    out.insert(0, "spend", spend.reindex(PAID))
    return out


def boot_cac(cr: pd.DataFrame, spend: pd.Series, rule: str = "linear", n: int = 2000) -> pd.DataFrame:
    """Resample acquired customers to get a CI on each channel's CAC under one rule."""
    w = cr.pivot_table(index="signup_id", columns="channel", values=rule, aggfunc="sum", fill_value=0)
    w = w.reindex(columns=PAID, fill_value=0).to_numpy()
    idx = RNG.integers(0, len(w), (n, len(w)))
    att = w[idx].sum(axis=1)
    cac = np.where(att > 0, spend.reindex(PAID).to_numpy() / np.where(att > 0, att, 1), np.inf)
    return pd.DataFrame({"cac_low": np.percentile(cac, 2.5, axis=0),
                         "cac_high": np.percentile(cac, 97.5, axis=0)}, index=PAID)


def segment_value_by_channel(cr: pd.DataFrame, seg: pd.Series, value: dict) -> pd.DataFrame:
    x = cr.assign(segment=cr.client_id.map(seg))
    mix = x.pivot_table(index="channel", columns="segment", values="linear", aggfunc="sum", fill_value=0)
    n = mix.sum(axis=1)
    mix = mix.div(n, axis=0)
    mix["customers_linear"] = n
    mix["expected_3yr_value"] = sum(mix.get(s, 0) * v for s, v in value.items())
    return mix


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(HANDOUT / "channel_spend.csv", parse_dates=["spend_date"])
    spend = clean_spend(raw)
    spend["year"] = spend.spend_date.dt.year
    spend["period"] = np.where(spend.year >= 2020, "2020", "2016-19")
    cards = load_cards(HANDOUT / "cards_data.csv")
    signups = flag_acquisitions(pd.read_csv(HANDOUT / "account_signups.csv", parse_dates=["signup_ts"]), cards)
    tp, volume = load_linked_touches(HANDOUT / "marketing_touchpoints.csv")
    j = journeys(tp, signups)
    cr = credits(j).merge(signups[["signup_id", "client_id", "acquisition", "kind", "period"]], on="signup_id")
    out: dict = {}

    # Spend: by year and channel, raw vs deduplicated, shares and growth
    by_year = spend.pivot_table(index="channel", columns="year", values="spend", aggfunc="sum")
    by_year["growth_2016_2019"] = by_year[2019] / by_year[2016] - 1
    by_year["share_2016"] = by_year[2016] / by_year[2016].sum()
    by_year["share_2019"] = by_year[2019] / by_year[2019].sum()
    by_year["raw_total"] = raw.groupby("channel").spend.sum()
    by_year["clean_total"] = spend.groupby("channel").spend.sum()
    by_year.to_csv(OUT / "spend_by_channel_year.csv")
    volume.to_csv(OUT / "touch_volume_by_channel_year.csv")

    # Platform-reported conversions vs CRM signups
    plat = spend.pivot_table(index="channel", columns="period", values="platform_reported_conversions",
                             aggfunc="sum")
    sp = spend.pivot_table(index="channel", columns="period", values="spend", aggfunc="sum")
    touched_any = cr.groupby(["channel", "period"]).signup_id.nunique().unstack()
    touched_new = cr[cr.acquisition].groupby(["channel", "period"]).signup_id.nunique().unstack()
    platform = pd.DataFrame({
        "spend_2016_19": sp["2016-19"], "spend_2020": sp["2020"],
        "platform_conv_2016_19": plat["2016-19"], "platform_conv_2020": plat["2020"],
        "signups_touched_2016_19": touched_any["2016-19"], "signups_touched_2020": touched_any["2020"],
        "new_customers_touched_2020": touched_new["2020"],
    }).reindex(PAID)
    platform["platform_cac_all"] = spend.groupby("channel").spend.sum() / spend.groupby("channel").platform_reported_conversions.sum()
    platform["platform_cac_2016_19"] = platform.spend_2016_19 / platform.platform_conv_2016_19
    platform["platform_cac_2020"] = platform.spend_2020 / platform.platform_conv_2020
    platform.to_csv(OUT / "platform_vs_crm.csv")
    out["total_platform_conv_2020"] = float(plat["2020"].sum())
    out["signups_2020"] = int(signups.period.eq("2020").sum())
    out["new_customers_2020"] = int((signups.period.eq("2020") & signups.acquisition).sum())
    out["new_customers_2016_19"] = int((signups.period.eq("2016-19") & signups.acquisition).sum())

    # CRM CAC on new customers, per attribution rule
    cac = {}
    for p in ["2020", "2016-19"]:
        acq = cr[cr.acquisition & cr.period.eq(p)]
        t = cac_table(acq, sp[p])
        if p == "2020":
            t = t.join(boot_cac(acq, sp[p]))
            t = t.join(boot_cac(acq, sp[p], rule="first").add_suffix("_first"))
        t.to_csv(OUT / f"crm_cac_new_customers_{p}.csv")
        cac[p] = t

    # Customer quality by channel: day-one segment mix priced at Q1 3-year values
    seg = (pd.read_csv(V3 / "card_openings_classified.csv")
           .drop_duplicates("client_id").set_index("client_id").day_one_segment)
    ci = pd.read_csv(V3 / "new_customer_value_ci.csv")
    cum3 = ci[ci.year.eq("cum3")].set_index("segment")
    value = cum3["mean"].to_dict()
    value_zero = cum3["mean_missing_as_zero"].to_dict()
    out["segment_value_3yr"] = {"with_data": value, "missing_as_zero": value_zero}
    acq_all = cr[cr.acquisition]
    quality = segment_value_by_channel(acq_all, seg, value)
    quality["expected_3yr_value_missing_as_zero"] = segment_value_by_channel(
        acq_all, seg, value_zero).expected_3yr_value
    base_mix = acq_all.drop_duplicates("signup_id").client_id.map(seg).value_counts(normalize=True)
    out["all_new_customers_expected_3yr"] = float(sum(base_mix.get(s, 0) * v for s, v in value.items()))
    quality.to_csv(OUT / "new_customer_quality_by_channel.csv")
    v2020 = cac["2020"].join(quality[["expected_3yr_value", "expected_3yr_value_missing_as_zero"]])
    v2020["value_per_dollar_linear"] = v2020.expected_3yr_value / v2020.cac_linear
    v2020["value_per_dollar_linear_missing_as_zero"] = v2020.expected_3yr_value_missing_as_zero / v2020.cac_linear
    v2020.to_csv(OUT / "cac_vs_value_2020.csv")

    # Attribution roles by channel, new customers vs existing-customer extra cards
    roles = (cr.groupby(["period", "acquisition", "channel"])[RULES].sum().round(1))
    roles.to_csv(OUT / "attribution_roles.csv")

    # Affiliate specifics
    aff_sig = cr[cr.channel.eq("affiliate")]
    aff_touch = j[j.channel.eq("affiliate")]
    new_aff = acq_all.groupby("client_id").channel.apply(lambda s: "affiliate" in set(s))
    mix_aff = pd.crosstab(new_aff, new_aff.index.map(seg), normalize="index")
    nxt = j.groupby("signup_id").channel.apply(list)
    after_aff = [ch for lst in nxt for i, ch in enumerate(lst) if i > 0 and lst[i - 1] == "affiliate"]
    out["affiliate"] = {
        "touches_total_in_file": int(volume.loc["affiliate"].sum()),
        "touches_linked_to_customer": int(len(aff_touch)),
        "touches_by_year": volume.loc["affiliate"].to_dict(),
        "signups_touched_2020": aff_sig[aff_sig.period.eq("2020")].groupby("kind").signup_id.nunique().to_dict(),
        "new_customers_touched_all": int(new_aff.sum()),
        "new_customers_not_touched": int((~new_aff).sum()),
        "segment_mix_touched_vs_not": mix_aff.round(3).to_dict(orient="index"),
        "expected_3yr_touched": float(sum(mix_aff.loc[True].get(s, 0) * v for s, v in value.items())),
        "expected_3yr_not_touched": float(sum(mix_aff.loc[False].get(s, 0) * v for s, v in value.items())),
        "campaign_touches": aff_touch.utm_campaign.value_counts().to_dict(),
        "next_touch_after_affiliate": pd.Series(after_aff).value_counts().to_dict(),
        "max_commission_per_signup_breakeven_3yr_revenue_2020": None,
    }
    a20 = out["affiliate"]["signups_touched_2020"]
    out["affiliate"]["max_commission_per_signup_breakeven_3yr_revenue_2020"] = float(
        out["affiliate"]["expected_3yr_touched"] * a20["acquisition"] / sum(a20.values()))
    aff20 = aff_sig[aff_sig.period.eq("2020")]
    linear_new = float(aff20.loc[aff20.acquisition, "linear"].sum())
    out["affiliate"]["linear_new_customers_2020"] = linear_new
    out["affiliate"]["last_touch_signups_2020"] = int(aff20["last"].sum())
    out["affiliate"]["breakeven_commission_per_touched_signup_linear"] = float(
        out["affiliate"]["expected_3yr_touched"] * linear_new / sum(a20.values()))
    out["affiliate"]["touched_signups_by_campaign_2020"] = (
        aff_touch.merge(signups[["signup_id", "kind"]], on="signup_id")
        .loc[lambda d: d.period.eq("2020")].groupby(["utm_campaign", "kind"]).signup_id.nunique()
        .unstack().fillna(0).astype(int).to_dict(orient="index"))

    # Self-reported source vs tracked touches (is Apple under-tracked?)
    sr = signups.set_index("signup_id").self_reported_source
    x = cr.assign(sr=cr.signup_id.map(sr))
    out["self_reported_app_store"] = {
        "signups": int(sr.eq("app_store").sum()),
        "with_apple_touch": int(x[x.sr.eq("app_store") & x.channel.eq("apple_search_ads")].signup_id.nunique()),
    }

    (OUT / "hypotheses_notes.json").write_text(json.dumps(out, indent=2, default=str))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    for name, t in [("spend", by_year), ("platform", platform), ("cac 2020", cac["2020"]),
                    ("cac 2016-19", cac["2016-19"]), ("quality", quality), ("value 2020", v2020)]:
        print(f"\n== {name}\n", t.round(3).to_string())
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
