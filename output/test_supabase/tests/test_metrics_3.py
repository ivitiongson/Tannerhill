"""Checks for the dashboard logic (output/test_supabase, test_build_dashboard_3.py: seasonal reorder point), run on the
clean load files (the same rows that go into Supabase). Each test prints PASS or FAIL
with expected and actual.

Run:  python3 output/test_supabase/tests/test_metrics_3.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import test_build_dashboard_3 as bd  # noqa: E402

results = []


def check(name, ok, expected, actual):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}\n      expected: {expected}\n      actual:   {actual}")


def cents(v):
    return round(v * 100)


T = bd.table
fin = {bd.iso(r["month"]): r for r in T("fin")}
ledger = T("ledger")

# ---------------------------------------------------------------- mapping "Checks" tab

check("C1. D10-01 ledger rows = 25,152", len(ledger) == 25152, "25,152", f"{len(ledger):,}")

feb = bd.num(fin[date(2026, 2, 1)]["total_revenue"])
led_feb = sum(bd.num(r["net_revenue"]) for r in ledger if r["order_date"].startswith("2026-02"))
check("C2. Feb 2026 total revenue = $93,127.60 (D10-02, and ledger)",
      cents(feb) == 9312760 and cents(led_feb) == 9312760, "$93,127.60",
      f"D10-02 ${feb:,.2f} · ledger ${led_feb:,.2f}")

dec = bd.num(fin[date(2025, 12, 1)]["total_revenue"])
check("C3. Dec 2025 total revenue = $135,912", cents(dec) == 13591200, "$135,912", f"${dec:,.2f}")

by = {}
for r in ledger:
    if r["channel"] in ("amazon", "shopify"):
        k = (r["order_date"][:7], r["channel"])
        by[k] = by.get(k, 0.0) + bd.num(r["net_revenue"])
bad = []
for d, r in fin.items():
    m = d.strftime("%Y-%m")
    for ch, col in (("amazon", "amazon_net_of_refunds"), ("shopify", "shopify_net_of_discounts_and_returns")):
        if cents(by.get((m, ch), 0.0)) != cents(bd.num(r[col])):
            bad.append(f"{m} {ch}: ledger {by.get((m, ch), 0.0):,.2f} vs D10-02 {bd.num(r[col]):,.2f}")
check("C4. Ledger net_revenue by month = D10-02 Amazon and Shopify, all 15 months",
      not bad and len(fin) == 15, "30 of 30 equal", "; ".join(bad) or f"{2 * len(fin)} of {2 * len(fin)} equal")

sales, refunds = {}, {}
for r in T("amz_report"):
    sales[r["month"]] = sales.get(r["month"], 0.0) + bd.num(r["ordered_product_sales"])
for r in T("amz_refunds"):
    refunds[r["order_month"]] = refunds.get(r["order_month"], 0.0) + bd.num(r["refund_amount"])
bad = [f"{d}: {sales.get(d.isoformat(), 0) - refunds.get(d.isoformat(), 0):,.2f} vs {bd.num(r['amazon_net_of_refunds']):,.2f}"
       for d, r in fin.items()
       if cents(sales.get(d.isoformat(), 0) - refunds.get(d.isoformat(), 0)) != cents(bd.num(r["amazon_net_of_refunds"]))]
check("C5. D10-03 sales - D10-04 refunds = D10-02 Amazon, all 15 months",
      not bad, "15 of 15 equal", "; ".join(bad) or "15 of 15 equal")

ks = bd.kickstarter_by_month()
ks_rows = [r for r in ledger if r["channel"] == "kickstarter"]
gross = sum(bd.num(r["gross_sales"]) for r in ks_rows)
fee = sum(bd.num(r["kickstarter_fee"]) for r in ks_rows)
d02_sep = bd.num(fin[date(2025, 9, 1)]["kickstarter_recognized_when_rewards_ship"])
q2_zero = all(cents(ks.get((2025, m), 0.0)) == 0 and
              cents(bd.num(fin[date(2025, m, 1)]["kickstarter_recognized_when_rewards_ship"])) == 0
              for m in (4, 5, 6))
check("C6. Kickstarter Sep 2025 = $210,527 (ledger by recognized_date and D10-02); $0 Apr-Jun 2025",
      cents(ks.get((2025, 9), 0)) == 21052700 == cents(d02_sep) and q2_zero
      and round(gross) == 211585 and round(fee) == 1058,
      "$210,527 = 211,585 - 1,058; Apr-Jun $0",
      f"ledger ${ks.get((2025, 9), 0):,.2f} ({len(ks_rows):,} rows, gross {gross:,.0f} - fee {fee:,.0f}) · "
      f"D10-02 ${d02_sep:,.0f} · Apr-Jun zero: {q2_zero}")

tpl = T("tpl")
check("C7. D10-07 rows = 1,092 (91 snapshots x 12 items)",
      len(tpl) == 1092 and len({r["snapshot_ts"] for r in tpl}) == 91,
      "1,092 = 91 x 12", f"{len(tpl):,} rows, {len({r['snapshot_ts'] for r in tpl})} snapshots")

pos = bd.open_pos()
_, detail = bd.on_the_way()
lines = [d for d in detail if d["po"] == "PO-2602-011"]
check("C8. Open PO PO-2602-011 = 600 units, counted once",
      list(pos) == ["PO-2602-011"] and pos["PO-2602-011"]["open_qty"] == 600
      and len(lines) == 1 and lines[0]["qty"] == 600 and "counted once" in lines[0]["source"],
      "only open PO in D10-10 = PO-2602-011 600; one line of 600 on the page",
      f"open POs {pos}; lines {lines}")

# ---------------------------------------------------------------- dashboard logic

# 2. Last-year baseline, Q2 2025. Kickstarter now counts in the month rewards shipped
#    (Sep 2025), so Q2 2025 has no Kickstarter. Was: $688,713 with pledges collected.
q2 = ["Apr", "May", "Jun"]
base = bd.last_year_total(q2, include_kickstarter=False)
ly = bd.last_year_by_month()
ks_q2 = sum(ly[m]["kickstarter"] for m in q2)
both = bd.last_year_total(q2, include_kickstarter=True)
check("2a. Last-year baseline, D10-02 Amazon + Shopify Apr-Jun 2025 = $478,187",
      base == 478187, "166,554 + 163,223 + 148,410 = $478,187", f"${base:,.0f}")
check("2b. Kickstarter Apr-Jun 2025 = $0 (counted when rewards shipped, Sep 2025)",
      ks_q2 == 0, "$0", f"${ks_q2:,.0f}")
check("2c. Q2 2025 total with Kickstarter = $478,187 (no Kickstarter in Q2)",
      both == 478187, "$478,187", f"${both:,.0f}")

# 3. Contribution per unit, TH-GRL-01
c = bd.contribution_per_unit()["TH-GRL-01"]
check("3. Contribution per unit, Trailhead Portable Grill ~ $69.0",
      round(c["per_unit"], 1) == 69.0,
      "$165,722 / 2,402 = $69.0", f"${c['contribution']:,.0f} / {c['units']:,.0f} = ${c['per_unit']:.2f}")

# 4. Ad spend estimate, Windshield Panel Set, FY2025
spend = bd.monthly_spend()
fy = sum(v for (y, m), v in spend.items() if y == 2025)
share = bd.budget_share()["TH-ACC-WS"]
d0403 = next(bd.num(r["annual_ad_spend"]) for r in T("ads_share") if r["sku"] == "TH-ACC-WS")
check("4. Ad spend estimate, Windshield Panel Set FY2025 = $37,800 and = D04-03",
      round(fy * share) == 37800 == d0403,
      "$14,000 x 12 x 0.225 = $37,800 (D04-03 says ${:,.0f})".format(d0403),
      f"${fy:,.0f} x {share} = ${fy * share:,.0f}")

# 5. Stock table to check by hand
tbl, (season, start, end) = bd.stock_table()
snap = bd.snapshot_ts()
print(f"\n5. Stock at {snap} ({season} season rate {start} to {end}, reorder point = daily x {bd.REORDER_DAYS})")
print(f"   {'SKU':<10} {'3PL code':<10} {'On hand':>8} {'On way':>7} {'Total':>7} {'Daily':>6} {'ROP':>7}  Status")
for row in tbl:
    oh = row["on_hand"]
    tot = None if oh is None else oh + row["on_the_way"]
    n0 = lambda v: "–" if v is None else f"{v:,.0f}"
    print(f"   {row['sku']:<10} {str(row['tpl']):<10} {n0(oh):>8} {n0(row['on_the_way']):>7} "
          f"{n0(tot):>7} {row['daily']:>6.2f} {row['reorder_point']:>7.1f}  {row['status']} {row['check']}")
print("   On the way, line by line:")
for d in detail:
    print(f"     {d['sku']} {d['po']} {d['qty']:.0f}  ({d['source']})")
check("5. Stock table printed for every crosswalk product",
      len(tbl) == len(bd.load_crosswalk()), f"{len(bd.load_crosswalk())} rows", f"{len(tbl)} rows")

# 6. Crosswalk
print("\n6. Codes that don't match D07-06:")
um = bd.unmatched_codes()
for u in um:
    print(f"     {u['code']:<26} {u['where']:<40} {u['issue']:<32} {u['mapped'] or 'STILL UNMATCHED'}")
codes = {u["code"] for u in um}
check("6. Crosswalk lists TRAILHEAD-GRILL-PRO-V2, windshield-panel-set and TNHC-5001 (griddle plate)",
      {"TRAILHEAD-GRILL-PRO-V2", "windshield-panel-set", "TNHC-5001"} <= codes,
      "all three listed", f"{len(um)} listed: {sorted(codes)}")

# 7. Confirmed mappings are used, and still listed (not dropped)
inc = bd.incomplete_sales_skus()
listed = {u["code"] for u in um if u["mapped"]}
check("7. Confirmed mappings applied: TH-GRL-02 and TH-ACC-WS no longer incomplete, still listed as mapped",
      "TH-GRL-02" not in inc and "TH-ACC-WS" not in inc
      and {"TRAILHEAD-GRILL-PRO-V2", "windshield-panel-set"} <= listed,
      "no incomplete SKUs for TH-GRL-02 / TH-ACC-WS; both codes listed as mapped",
      f"incomplete = {sorted(inc) or 'none'}; mapped codes listed = {sorted(listed)}")

# 8. On hand = qty_available at the latest snapshot on or before 3 Apr 2026
hand = bd.on_hand()
snap_rows = [r for r in tpl if r["snapshot_ts"] == snap.strftime("%Y-%m-%d %H:%M")]
raw = {r["item_code"]: int(r["qty_available"]) for r in snap_rows}
check("8. On hand = D10-07 qty_available at 2026-04-01 06:00 (latest on or before 3 Apr); no HOLD- rows",
      snap == bd.datetime(2026, 4, 1, 6, 0) and {k: int(v) for k, v in hand.items()} == raw
      and hand["TNHC-1001"] == 272 and not bd.earmarked(),
      "snapshot 2026-04-01 06:00; TNHC-1001 = 272",
      f"snapshot {snap}; TNHC-1001 = {hand['TNHC-1001']:.0f}; earmarked rows = {len(bd.earmarked())}")

# 11. Seasons: the page date picks last year's same season
check("11a. 3 Apr 2026 (Jan-Jun ordering window) -> peak season rate, 1 Mar - 31 Aug 2025",
      bd.season_window(date(2026, 4, 3)) == ("peak", date(2025, 3, 1), date(2025, 8, 31)),
      "peak 2025-03-01 to 2025-08-31", bd.season_window(date(2026, 4, 3)))
check("11b. 1 Jul 2026 -> low season rate, 1 Sep 2025 - 28 Feb 2026; 1 Jul 2028 -> ends 29 Feb 2028 (leap year)",
      bd.season_window(date(2026, 7, 1)) == ("low", date(2025, 9, 1), date(2026, 2, 28))
      and bd.season_window(date(2028, 7, 1))[2] == date(2028, 2, 29)
      and bd.season_window(date(2026, 6, 30))[0] == "peak" and bd.season_window(date(2026, 12, 31))[0] == "low",
      "low 2025-09-01 to 2026-02-28; 2028-02-29", f"{bd.season_window(date(2026, 7, 1))}; {bd.season_window(date(2028, 7, 1))[2]}")
units = bd.daily_units()
g1 = {r["sku"]: r for r in tbl}
oos = {date(2025, 6, d) for d in range(8, 29)}
peak = [date(2025, 3, 1) + bd.timedelta(days=i) for i in range(184)]
exp_g1 = sum(units["TH-GRL-01"].get(d, 0) for d in peak if d not in oos) / (184 - 21)
check("11c. Portable Grill: 21 out-of-stock days (8-28 Jun 2025) left out -> 163 in-stock days",
      g1["TH-GRL-01"]["oos_days"] == 21 and g1["TH-GRL-01"]["days"] == 163
      and abs(g1["TH-GRL-01"]["daily"] - exp_g1) < 1e-9 and round(g1["TH-GRL-01"]["daily"], 2) == 8.92,
      f"{exp_g1:.2f}/day over 163 days (7.86 if the stockout were counted)",
      f"{g1['TH-GRL-01']['daily']:.2f}/day over {g1['TH-GRL-01']['days']} days, {g1['TH-GRL-01']['oos_days']} left out")
check("11d. Grill Pro reorder point = 2.18/day x 56 = 122 (was 72 on the last 90 days)",
      round(g1["TH-GRL-02"]["daily"], 2) == 2.18 and round(g1["TH-GRL-02"]["reorder_point"]) == 122,
      "2.18/day, 122", f"{g1['TH-GRL-02']['daily']:.2f}/day, {g1['TH-GRL-02']['reorder_point']:.0f}")
oos_all = bd.out_of_stock_days()
check("11e. Out-of-stock days found in D10-07: Grill Grate Cleaner 29 Mar 2026 (qty_available 0)",
      date(2026, 3, 29) in oos_all.get("TH-ACC-CL", set()), "TH-ACC-CL 2026-03-29",
      sorted((k, len(v)) for k, v in oos_all.items()))

# 9. Revenue this year = actuals (Q1): Jan-Mar 2026 vs Jan-Mar 2025, March labelled draft
rev = bd.metric_revenue(bd.REPORT_DATE)
check("9. Revenue YTD actuals Jan-Mar 2026 = $400,652.85 vs $349,130 (+14.8%, amber), March draft",
      cents(rev["this_year"]) == 40065285 and cents(rev["last_year"]) == 34913000
      and round(rev["change"] * 100, 1) == 14.8 and rev["status"] == "amber"
      and rev["drafts"] == ["Mar"] and rev["ly_ks"] == 0 and rev["ty_ks"] == 0,
      "85,805.15 + 93,127.60 + 221,720.10 = $400,652.85 vs 78,686 + 87,235 + 183,209 = $349,130, +14.8%, amber, draft = Mar",
      f"${rev['this_year']:,.2f} vs ${rev['last_year']:,.2f}, {rev['change']:+.1%}, {rev['status']}, draft = {rev['drafts']}")

# 9b. Ads month follows the page date: April page -> March 2026
ads = bd.metric_ads(bd.REPORT_DATE)
check("9b. Ads card covers Mar 2026 (last full month before 3 Apr)", ads["month"] == "2026-03" or ads["month"] == (2026, 3),
      "Mar 2026", ads["as_of"])

# 10. Revenue method on Dec 2025 within 5% of D10-02 Dec
est_dec = bd.revenue_estimate(date(2025, 12, 1), date(2025, 12, 31))["total"]
diff = est_dec / dec - 1
check("10. Revenue method, Dec 2025 within 5% of D10-02 Dec ($135,912)",
      abs(diff) <= 0.05, "within 5% of $135,912", f"${est_dec:,.0f} ({diff:+.1%})")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
