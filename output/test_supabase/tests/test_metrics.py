"""Checks for the dashboard logic (output/test_supabase, build_dashboard.py), run on the
clean load files (the same rows that go into Supabase). Each test prints PASS or FAIL
with expected and actual.

Run:  python3 output/test_supabase/tests/test_metrics.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_dashboard as bd  # noqa: E402

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
tbl, (start, end) = bd.stock_table()
snap = bd.snapshot_ts()
print(f"\n5. Stock at {snap} (daily sales window {start} to {end}, reorder point = daily x {bd.REORDER_DAYS})")
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

# 8. On hand = qty_available at the latest snapshot on or before the report date
hand = bd.on_hand()
snap_rows = [r for r in tpl if r["snapshot_ts"] == snap.strftime("%Y-%m-%d %H:%M")]
raw = {r["item_code"]: int(r["qty_available"]) for r in snap_rows}
check("8. On hand = D10-07 qty_available at 2026-03-19 06:00 (not qty_on_hand); no HOLD- rows",
      snap == bd.datetime(2026, 3, 19, 6, 0) and {k: int(v) for k, v in hand.items()} == raw
      and hand["TNHC-1001"] == 65 and not bd.earmarked(),
      "snapshot 2026-03-19 06:00; TNHC-1001 = 65 (on hand 97)",
      f"snapshot {snap}; TNHC-1001 = {hand['TNHC-1001']:.0f}; earmarked rows = {len(bd.earmarked())}")

# 9. Revenue this year (estimate), 1 Jan - 19 Mar 2026 vs Jan + Feb + Mar x 19/31 2025
rev = bd.metric_revenue(bd.REPORT_DATE)
check("9. Revenue estimate YTD to 19 Mar ~ $317,258 vs $278,210 (+14.0%, amber), Kickstarter $0 both years",
      abs(rev["this_year"] - 317258) <= 1 and abs(rev["last_year"] - 278210) <= 1
      and round(rev["change"] * 100, 1) == 14.0 and rev["status"] == "amber"
      and rev["ly_ks"] == 0 and rev["ty_ks"] == 0,
      "$317,258 vs 78,686 + 87,235 + 183,209 x 19/31 = $278,210, +14.0%, amber",
      f"${rev['this_year']:,.0f} vs ${rev['last_year']:,.0f}, {rev['change']:+.1%}, {rev['status']}, "
      f"KS last year ${rev['ly_ks']:,.0f} / this year ${rev['ty_ks']:,.0f}")

# 10. Revenue method on Dec 2025 within 5% of D10-02 Dec
est_dec = bd.revenue_estimate(date(2025, 12, 1), date(2025, 12, 31))["total"]
diff = est_dec / dec - 1
check("10. Revenue method, Dec 2025 within 5% of D10-02 Dec ($135,912)",
      abs(diff) <= 0.05, "within 5% of $135,912", f"${est_dec:,.0f} ({diff:+.1%})")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
