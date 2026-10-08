"""Checks for the dashboard logic (output/test_dashboard_v3, test_build_dashboard_4.py). Each test prints PASS or FAIL with expected and actual.

Run:  python3 output/test_dashboard_v3/tests/test_metrics_5.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import test_build_dashboard_4 as bd  # noqa: E402

results = []


def check(name, ok, expected, actual):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}\n      expected: {expected}\n      actual:   {actual}")


def path(key):
    return os.path.join(bd.DATA, bd.FILES[key])


# 1. Amazon + Shopify logic on Q2 2025
r = bd.revenue_from_exports(path("amz_report"), path("amz_payments"), path("shopify"))
qb = bd.quickbooks_total_income()
print(f"      Amazon ordered {r['amazon_ordered']:,.0f} - refunds {r['amazon_refunds']:,.0f} = {r['amazon_net']:,.0f}")
print(f"      Shopify gross {r['shopify_gross']:,.0f} (duplicate {', '.join(r['dup_weeks'])} week removed: "
      f"{r['dup_rows']} rows, {r['shopify_dup_removed']:,.0f}) {r['shopify_discounts']:,.0f} discounts "
      f"{r['shopify_returns']:,.0f} returns = {r['shopify_net']:,.2f}")
check("1. Amazon + Shopify logic, Q2 2025 = $478,187 and = QuickBooks Total Income",
      round(r["total"]) == 478187 and round(r["total"]) == round(qb),
      "$478,187 (QuickBooks D09-05: ${:,.0f})".format(qb), f"${r['total']:,.2f}")

# 2. Last-year baseline: Amazon + Shopify, Kickstarter, and the total with Kickstarter
q2 = ["Apr", "May", "Jun"]
base = bd.last_year_total(q2, include_kickstarter=False)
ly = bd.last_year_by_month()
ks = sum(ly[m]["kickstarter"] for m in q2)
both = bd.last_year_total(q2, include_kickstarter=True)
check("2a. Last-year baseline, D02-02 Amazon + Shopify Apr-Jun 2025 = $478,186, within $1 of test 1",
      base == 478186 and abs(base - r["total"]) <= 1, "$478,186", f"${base:,.0f}")
check("2b. Kickstarter Apr-Jun 2025 from D02-02 = $210,527",
      ks == 210527, "63,158 + 94,737 + 52,632 = $210,527",
      " + ".join(f"{ly[m]['kickstarter']:,.0f}" for m in q2) + f" = ${ks:,.0f}")
check("2c. Q2 2025 total with Kickstarter = $688,713",
      both == 688713, "$688,713", f"${both:,.0f}")

# 3. Contribution per unit, TH-GRL-01
c = bd.contribution_per_unit()["TH-GRL-01"]
check("3. Contribution per unit, Trailhead Portable Grill ~ $69.0",
      round(c["per_unit"], 1) == 69.0,
      "$165,722 / 2,402 = $69.0", f"${c['contribution']:,.0f} / {c['units']:,.0f} = ${c['per_unit']:.2f}")

# 4. Ad spend estimate, Windshield Panel Set, FY2025
spend = bd.monthly_spend()
fy = sum(v for (y, m), v in spend.items() if y == 2025)
share = bd.budget_share()["TH-ACC-WS"]
d0403 = next(row["Annual ad spend"] for row in bd.table("ads_share", "SKU") if row["SKU"] == "TH-ACC-WS")
check("4. Ad spend estimate, Windshield Panel Set FY2025 = $37,800 and = D04-03",
      round(fy * share) == 37800 == d0403,
      "$14,000 x 12 x 0.225 = $37,800 (D04-03 says ${:,.0f})".format(d0403),
      f"${fy:,.0f} x {share} = ${fy * share:,.0f}")

# 5. Stock table to check by hand
tbl, (start, end) = bd.stock_table()
print(f"\n5. Stock (daily sales window {start} to {end}, reorder point = daily x {bd.REORDER_DAYS})")
print(f"   {'SKU':<10} {'3PL code':<10} {'On hand':>8} {'On way':>7} {'Total':>7} {'Daily':>6} {'ROP':>7}  Status")
for row in tbl:
    oh = row["on_hand"]
    tot = None if oh is None else oh + row["on_the_way"]
    print(f"   {row['sku']:<10} {str(row['tpl']):<10} {bd.n0(oh):>8} {bd.n0(row['on_the_way']):>7} "
          f"{bd.n0(tot):>7} {row['daily']:>6.2f} {row['reorder_point']:>7.1f}  {row['status']} {row['check']}")
_, detail = bd.on_the_way()
print("   On the way, line by line:")
for d in detail:
    print(f"     {d['sku']} {d['po']} {d['qty']:.0f}  ({d['source']})")
check("5. Stock table printed for every crosswalk product",
      len(tbl) == len(bd.load_crosswalk()), f"{len(bd.load_crosswalk())} rows", f"{len(tbl)} rows")

# 6. Crosswalk
print("\n6. Codes that don't match D07-06:")
um = bd.unmatched_codes()
for u in um:
    print(f"     {u['code']:<26} {u['where']:<45} {u['issue']:<32} {u['mapped'] or 'STILL UNMATCHED'}")
check("6. Crosswalk finds TRAILHEAD-GRILL-PRO-V2 as unmatched",
      any(u["code"] == "TRAILHEAD-GRILL-PRO-V2" for u in um),
      "at least TRAILHEAD-GRILL-PRO-V2", f"{len(um)} unmatched")


# 7. Confirmed mappings are used, and still listed (not dropped)
units = bd.daily_units()
pro_v2 = units["TH-GRL-02"]
inc = bd.incomplete_sales_skus()
listed = {u["code"] for u in um if u["mapped"]}
check("7. Confirmed mappings applied: TH-GRL-02 and TH-ACC-WS no longer incomplete, still listed as mapped",
      "TH-GRL-02" not in inc and "TH-ACC-WS" not in inc
      and {"TRAILHEAD-GRILL-PRO-V2", "windshield-panel-set"} <= listed,
      "no incomplete SKUs for TH-GRL-02 / TH-ACC-WS; both codes listed as mapped",
      f"incomplete = {sorted(inc) or 'none'}; mapped codes listed = {sorted(listed)}")

# 8. Earmarked units are out of on hand
hand = bd.on_hand()
ear = bd.earmarked()
print("\n8. Earmarked rows left out of on hand:")
for e in ear:
    print(f"     {e['item_code']} {e['qty']:.0f} ({e['hold_ref']})")
check("8. Earmarked units excluded: TNHC-1001 96 - 66 = 30, TNHC-3001 153 - 115 = 38",
      hand["TNHC-1001"] == 30 and hand["TNHC-3001"] == 38,
      "TNHC-1001 = 30, TNHC-3001 = 38",
      f"TNHC-1001 = {hand['TNHC-1001']:.0f}, TNHC-3001 = {hand['TNHC-3001']:.0f}")


# 9. Revenue this year (estimate), 1 Jan - 15 Mar 2026 vs Jan + Feb + Mar x 15/31 2025
rev = bd.metric_revenue(bd.REPORT_DATE)
check("9. Revenue estimate YTD ~ $290,806 vs $254,571 (+14.2%, amber)",
      abs(rev["this_year"] - 290806) <= 1 and abs(rev["last_year"] - 254571) <= 1
      and round(rev["change"] * 100, 1) == 14.2 and rev["status"] == "amber",
      "$290,806 vs $254,571, +14.2%, amber",
      f"${rev['this_year']:,.0f} vs ${rev['last_year']:,.0f}, {rev['change']:+.1%}, {rev['status']}")

# 10. Revenue method on Dec 2025 within 5% of D02-02 Dec
from datetime import date  # noqa: E402
dec = bd.revenue_estimate(date(2025, 12, 1), date(2025, 12, 31))["total"]
ly_dec = bd.last_year_by_month()["Dec"]
actual_dec = ly_dec["amazon"] + ly_dec["shopify"] + ly_dec["kickstarter"]
diff = dec / actual_dec - 1
check("10. Revenue method, Dec 2025 within 5% of D02-02 Dec ($135,912), expect ~ $141,720",
      abs(diff) <= 0.05, "within 5% of $135,912 (about $141,720)",
      f"${dec:,.0f} ({diff:+.1%})")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
