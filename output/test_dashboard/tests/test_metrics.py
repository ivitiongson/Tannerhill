"""Checks for the dashboard logic (output/test_dashboard). Each test prints PASS or FAIL with expected and actual.

Run:  python3 output/test_dashboard/tests/test_metrics.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_dashboard as bd  # noqa: E402

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
    print(f"     {u['code']:<26} {u['where']:<45} {u['issue']}")
check("6. Crosswalk finds TRAILHEAD-GRILL-PRO-V2 as unmatched",
      any(u["code"] == "TRAILHEAD-GRILL-PRO-V2" for u in um),
      "at least TRAILHEAD-GRILL-PRO-V2", f"{len(um)} unmatched")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
