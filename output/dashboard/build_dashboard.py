"""Tannerhill "Are we OK?" dashboard.

Reads the spreadsheets in dashboard-data/ (read-only), works out the 4 metrics,
and writes output/dashboard/index.html. Every number on the page comes from a
function in this file, so each one can be checked by hand.

Run:  python3 output/dashboard/build_dashboard.py [--as-of "2026-10-08 09:00"]
"""

import argparse
import html
import os
from datetime import date, datetime, timedelta

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(REPO, "dashboard-data")
FEED = os.path.join(HERE, "feed")  # drop live revenue exports here (see README)
OUT = os.path.join(HERE, "index.html")

FILES = {
    "fin": "D02-02_Tannerhill_FY2025_Financial_Summary_.xlsx",
    "stock_terms": "D04-01_Stock_Position_and_Supplier_Terms.xlsx",
    "ads_monthly": "D04-02_BidWorks_Monthly_Report_FY2025.xlsx",
    "ads_share": "D04-03_BidWorks_Spend_by_Product_FY2025.xlsx",
    "margins": "D04-04_Product_Margins_FY2025.xlsx",
    "tpl": "D07-01_3PL_Daily_Export.xlsx",
    "crosswalk": "D07-06_SKU_Crosswalk.xlsx",
    "sales": "D07-07_Sales_History.xlsx",
    "pos": "D07-08_Y-Supplier_PO_History.xlsx",
    "amz_report": "D09-01_Amazon_Business_Report_Q2.xlsx",
    "amz_payments": "D09-02_Amazon_Payments_Summary_Q2.xlsx",
    "shopify": "D09-03_Shopify_Sales_by_Product_Q2.xlsx",
    "qb": "D09-05_QuickBooks_PL_Q2.xlsx",
}

# Choices confirmed by the user
INCLUDE_KICKSTARTER = True   # Kickstarter pledges count in revenue (treated as shipped)
SALES_WINDOW_DAYS = 28       # daily sales = average of the last 28 days in D07-07
REORDER_DAYS = 56            # reorder point = daily sales x 56 days
BUFFER_DAYS = 14             # green = more than 14 days of sales above the reorder point

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------- reading

def rows(key, tab=None, data_dir=DATA, path=None):
    """All rows of one tab as tuples (values, not formulas)."""
    wb = openpyxl.load_workbook(path or os.path.join(data_dir, FILES[key]), data_only=True)
    ws = wb[tab] if tab else wb.worksheets[0]
    return [r for r in ws.iter_rows(values_only=True)]


def table(key, header_first_cell, tab=None, data_dir=DATA, path=None):
    """Rows under the header row whose first cell is header_first_cell, as dicts.
    Stops at the first blank row or a 'Total' row."""
    all_rows = rows(key, tab, data_dir, path)
    for i, r in enumerate(all_rows):
        if r[0] == header_first_cell:
            header = r
            break
    else:
        raise ValueError(f"{key}: header '{header_first_cell}' not found")
    out = []
    for r in all_rows[i + 1:]:
        if r[0] is None or str(r[0]).strip() == "Total":
            break
        out.append({h: v for h, v in zip(header, r) if h is not None})
    return out


def num(v):
    return 0.0 if v in (None, "", "-") else float(v)


def dmy(s):
    """D07-08 dates are DD/MM/YYYY."""
    return datetime.strptime(s, "%d/%m/%Y").date() if s else None


# ---------------------------------------------------------------- crosswalk

def load_crosswalk(data_dir=DATA):
    """Our SKU <-> 3PL item code <-> Shopify handle <-> Amazon seller SKU (D07-06)."""
    cw = []
    for r in table("crosswalk", "Our SKU", data_dir=data_dir):
        notes = (r.get("Notes") or "").lower()
        cw.append({
            "sku": r["Our SKU"],
            "product": r["Product"],
            "tpl": r["3PL item code"],
            "shopify": r["Shopify handle"],
            "amazon": r["Amazon seller SKU"],
            "notes": r.get("Notes") or "",
            # a blank code only means "not sold there" when the notes say so
            "not_on_amazon": "not on amazon" in notes,
            "not_on_shopify": "not on shopify" in notes,
        })
    return cw


def sales_columns(data_dir=DATA):
    """Column names (codes) in each D07-07 tab."""
    return {
        "amz_ordered": rows("sales", "Amazon units ordered", data_dir)[0][1:],
        "amz_refunded": rows("sales", "Amazon units refunded", data_dir)[0][1:],
        "shopify": rows("sales", "Shopify net quantity", data_dir)[0][1:],
    }


def unmatched_codes(data_dir=DATA):
    """Every code in D07-01 and D07-07 with no row in D07-06, plus crosswalk gaps."""
    cw = load_crosswalk(data_dir)
    tpl_codes = {c["tpl"] for c in cw if c["tpl"]}
    amz_codes = {c["amazon"] for c in cw if c["amazon"]}
    shp_codes = {c["shopify"] for c in cw if c["shopify"]}
    out = []
    for r in table("tpl", "snapshot_ts", data_dir=data_dir):
        if r["item_code"] not in tpl_codes and not any(u["code"] == r["item_code"] for u in out):
            out.append({"code": r["item_code"], "where": "D07-01 3PL item_code",
                        "issue": "not in D07-06 3PL item code column"})
    cols = sales_columns(data_dir)
    for tab, known, label in [("amz_ordered", amz_codes, "D07-07 Amazon units ordered"),
                              ("amz_refunded", amz_codes, "D07-07 Amazon units refunded"),
                              ("shopify", shp_codes, "D07-07 Shopify net quantity")]:
        for code in cols[tab]:
            if code and code not in known:
                out.append({"code": code, "where": label,
                            "issue": "not in D07-06"})
    # crosswalk entries that point at nothing in the sales history
    for c in cw:
        if c["amazon"] and c["amazon"] not in cols["amz_ordered"]:
            out.append({"code": c["amazon"], "where": f"D07-06 ({c['sku']} Amazon seller SKU)",
                        "issue": "no matching column in D07-07"})
        if not c["amazon"] and not c["not_on_amazon"]:
            out.append({"code": "(blank)", "where": f"D07-06 ({c['sku']} Amazon seller SKU)",
                        "issue": "blank in crosswalk"})
        if c["shopify"] and c["shopify"] not in cols["shopify"]:
            out.append({"code": c["shopify"], "where": f"D07-06 ({c['sku']} Shopify handle)",
                        "issue": "no matching column in D07-07"})
        if not c["shopify"] and not c["not_on_shopify"]:
            out.append({"code": "(blank)", "where": f"D07-06 ({c['sku']} Shopify handle)",
                        "issue": f"blank in crosswalk (note: '{c['notes']}')"})
    return out


def incomplete_sales_skus(data_dir=DATA):
    """Our SKUs whose sales can't be fully read from D07-07 because a code doesn't match."""
    cols = sales_columns(data_dir)
    bad = {}
    for c in load_crosswalk(data_dir):
        reasons = []
        if not c["not_on_amazon"] and (not c["amazon"] or c["amazon"] not in cols["amz_ordered"]):
            reasons.append(f"Amazon code '{c['amazon'] or 'blank'}' not found in D07-07")
        if not c["not_on_shopify"] and (not c["shopify"] or c["shopify"] not in cols["shopify"]):
            reasons.append(f"Shopify handle '{c['shopify'] or 'blank'}' not found in D07-07")
        if reasons:
            bad[c["sku"]] = "; ".join(reasons)
    return bad


# ---------------------------------------------------------------- sales history (D07-07)

def daily_units(data_dir=DATA):
    """{our_sku: {date: net units}} = Amazon ordered - Amazon refunded + Shopify net.
    Unmatched columns are left out here and reported by unmatched_codes()."""
    cw = load_crosswalk(data_dir)
    by_amz = {c["amazon"]: c["sku"] for c in cw if c["amazon"]}
    by_shp = {c["shopify"]: c["sku"] for c in cw if c["shopify"]}
    out = {c["sku"]: {} for c in cw}

    def add(tab, mapping, sign, parse):
        rs = rows("sales", tab, data_dir)
        header = rs[0]
        for r in rs[1:]:
            if r[0] is None:
                continue
            d = parse(r[0])
            for code, v in zip(header[1:], r[1:]):
                if code in mapping:
                    sku = mapping[code]
                    out[sku][d] = out[sku].get(d, 0.0) + sign * num(v)

    iso = lambda s: datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    mdy = lambda s: datetime.strptime(s, "%m/%d/%Y").date()
    add("Amazon units ordered", by_amz, +1, iso)
    add("Amazon units refunded", by_amz, -1, iso)
    add("Shopify net quantity", by_shp, +1, mdy)
    return out


def last_sales_date(data_dir=DATA):
    rs = rows("sales", "Amazon units ordered", data_dir)
    return max(datetime.strptime(str(r[0])[:10], "%Y-%m-%d").date() for r in rs[1:] if r[0])


# ---------------------------------------------------------------- metric 1: revenue

def revenue_from_exports(amz_report_path, amz_payments_path, shopify_path):
    """Amazon ordered sales - refunds (by order date) + Shopify gross - discounts - returns.
    Exact duplicate Shopify rows (same week + same variant) are removed first.
    Same shape as D09-01 / D09-02 / D09-03, so a live feed can reuse it."""
    amz = sum(num(r["Ordered Product Sales"])
              for r in table(None, "Month", path=amz_report_path))
    refunds = sum(num(r["Refund amount"])
                  for r in table(None, "Order month", "Refunds by order date", path=amz_payments_path))
    seen, dupes = {}, []
    for r in table(None, "Week", path=shopify_path):
        k = (r["Week"], r["Product variant SKU"])
        if k in seen:
            dupes.append(r)
        else:
            seen[k] = r
    gross = sum(num(r["Gross sales"]) for r in seen.values())
    discounts = sum(num(r["Discounts"]) for r in seen.values())   # negative in export
    returns = sum(num(r["Returns"]) for r in seen.values())       # negative in export
    dup_gross = sum(num(r["Gross sales"]) for r in dupes)
    return {
        "amazon_ordered": amz, "amazon_refunds": refunds, "amazon_net": amz - refunds,
        "shopify_gross": gross, "shopify_dup_removed": dup_gross, "dup_rows": len(dupes),
        "dup_weeks": sorted({r["Week"].strftime("%Y-%m-%d") for r in dupes}),
        "shopify_discounts": discounts, "shopify_returns": returns,
        "shopify_net": gross + discounts + returns,
        "total": amz - refunds + gross + discounts + returns,
    }


def quickbooks_total_income(data_dir=DATA):
    for r in rows("qb", "P&L Q2", data_dir):
        if r[0] and str(r[0]).strip() == "Total Income":
            return num(r[1])
    raise ValueError("Total Income not found in D09-05")


def last_year_by_month(data_dir=DATA):
    """D02-02 'Revenue by Month': {month: {amazon, shopify, kickstarter}}."""
    out = {}
    for r in table("fin", "Month (2025)", "Revenue by Month", data_dir):
        out[r["Month (2025)"]] = {
            "amazon": num(r["Amazon"]), "shopify": num(r["Shopify"]),
            "kickstarter": num(r["Kickstarter (pledges collected)"]),
        }
    return out


def last_year_total(months, include_kickstarter=INCLUDE_KICKSTARTER, data_dir=DATA):
    by_month = last_year_by_month(data_dir)
    return sum(by_month[m]["amazon"] + by_month[m]["shopify"]
               + (by_month[m]["kickstarter"] if include_kickstarter else 0) for m in months)


def ytd_months(yesterday):
    """Full calendar months from Jan up to the month before `yesterday`'s month.
    D02-02 is monthly, so a part month can't be compared."""
    return MONTHS[:yesterday.month - 1]


def revenue_status(this_year, last_year):
    change = this_year / last_year - 1
    if change >= 0.25:
        return "green", change
    if change >= 0:
        return "amber", change
    return "red", change


def metric_revenue(run_time, data_dir=DATA, feed_dir=FEED):
    yesterday = (run_time - timedelta(days=1)).date()
    months = ytd_months(yesterday)
    last = last_year_total(months, data_dir=data_dir)
    card = {
        "title": "Revenue vs last year", "kind": "Lagging", "owner": "Marisa",
        "refresh": "Daily, overnight",
        "last_year": last, "months": months,
    }
    feed = {k: os.path.join(feed_dir, f) for k, f in [
        ("amz", "amazon_business_report.xlsx"),
        ("pay", "amazon_payments_summary.xlsx"),
        ("shp", "shopify_sales_by_product.xlsx")]}
    if not all(os.path.exists(p) for p in feed.values()):
        card.update(status="gray", headline="No source yet",
                    as_of="Feed has never run",
                    note="No live revenue feed yet. Needs daily Amazon and Shopify exports "
                         "in the same shape as D09-01, D09-02 and D09-03, dropped into "
                         "output/dashboard/feed/.")
        return card
    this = revenue_from_exports(feed["amz"], feed["pay"], feed["shp"])["total"]
    last_run = datetime.fromtimestamp(min(os.path.getmtime(p) for p in feed.values()))
    status, change = revenue_status(this, last)
    card.update(status=status, headline=f"{change:+.0%}", this_year=this,
                as_of=last_run.strftime("%Y-%m-%d %H:%M"),
                stale=run_time - last_run > timedelta(days=1),
                note="This year has no Kickstarter source in the feed.")
    return card


# ---------------------------------------------------------------- metric 2: stock

def on_hand(data_dir=DATA):
    """Sum of qty_available per 3PL item_code (D07-01). qty_on_hand is not used."""
    out = {}
    for r in table("tpl", "snapshot_ts", data_dir=data_dir):
        out[r["item_code"]] = out.get(r["item_code"], 0.0) + num(r["qty_available"])
    return out


def snapshot_ts(data_dir=DATA):
    r = table("tpl", "snapshot_ts", data_dir=data_dir)[0]
    return datetime.strptime(r["snapshot_ts"], "%Y-%m-%d %H:%M")


def open_pos(data_dir=DATA):
    """D07-08 POs signed by Lena and not fully arrived: {po: {sku, open_qty}}.
    Part shipments share a PO number, so arrived qty is summed per PO."""
    pos = {}
    for r in table("pos", "PO #", data_dir=data_dir):
        po = r["PO #"]
        p = pos.setdefault(po, {"sku": r["Our SKU"], "qty": 0.0, "arrived": 0.0, "signed": None})
        p["qty"] += num(r["Qty"])
        p["arrived"] += num(r["Qty arrived"])
        if r["PO signed (Lena)"]:
            p["signed"] = dmy(r["PO signed (Lena)"])
    return {po: {"sku": p["sku"], "open_qty": p["qty"] - p["arrived"]}
            for po, p in pos.items() if p["signed"] and p["qty"] - p["arrived"] > 0}


def on_the_way(data_dir=DATA):
    """{our_sku: units} from D07-01 qty_expected, cross-checked with D07-08 open POs.
    A PO in both is counted once (3PL figure). Returns (totals, detail lines)."""
    cw = load_crosswalk(data_dir)
    tpl_to_sku = {c["tpl"]: c["sku"] for c in cw if c["tpl"]}
    totals, detail, seen_pos = {}, [], set()
    for r in table("tpl", "snapshot_ts", data_dir=data_dir):
        q = num(r["qty_expected"])
        if q <= 0:
            continue
        sku = tpl_to_sku.get(r["item_code"])
        po = r["hold_ref"]
        totals[sku] = totals.get(sku, 0.0) + q
        seen_pos.add(po)
        detail.append({"sku": sku, "po": po, "qty": q, "source": "D07-01 qty_expected"})
    pos = open_pos(data_dir)
    for po, p in pos.items():
        if po in seen_pos:
            line = next(d for d in detail if d["po"] == po)
            line["source"] += " + D07-08 (counted once)"
            if line["qty"] != p["open_qty"]:
                line["source"] += f" - MISMATCH: D07-08 says {p['open_qty']:.0f}"
        else:
            totals[p["sku"]] = totals.get(p["sku"], 0.0) + p["open_qty"]
            detail.append({"sku": p["sku"], "po": po, "qty": p["open_qty"],
                           "source": "D07-08 only (not on 3PL ASN yet)"})
    return totals, detail


def lead_times(data_dir=DATA):
    """Lead time per our SKU: D04-01 'Stock on hand' supplier code -> 'Supplier terms'.
    Supplier code is matched to the supplier's initials (YM = Yuhang Metalworks)."""
    terms = {"".join(w[0] for w in r["Supplier"].split()): r["Lead time"]
             for r in table("stock_terms", "Supplier", "Supplier terms", data_dir)}
    return {r["SKU"]: terms.get(r["Supplier"], "UNSURE: supplier not in terms").split(" (")[0]
            for r in table("stock_terms", "SKU", "Stock on hand", data_dir)}


def stock_status(available, reorder_point, daily):
    above = available - reorder_point
    if above <= 0:
        return "red"
    if above <= BUFFER_DAYS * daily:
        return "amber"
    return "green"


def stock_table(data_dir=DATA, window=SALES_WINDOW_DAYS):
    cw = load_crosswalk(data_dir)
    hand = on_hand(data_dir)
    way, _ = on_the_way(data_dir)
    units = daily_units(data_dir)
    end = last_sales_date(data_dir)
    start = end - timedelta(days=window - 1)
    incomplete = incomplete_sales_skus(data_dir)
    leads = lead_times(data_dir)
    out = []
    for c in cw:
        sold = sum(v for d, v in units[c["sku"]].items() if start <= d <= end)
        daily = sold / window
        row = {"sku": c["sku"], "product": c["product"], "tpl": c["tpl"],
               "on_hand": hand.get(c["tpl"]), "on_the_way": way.get(c["sku"], 0.0),
               "daily": daily, "reorder_point": daily * REORDER_DAYS,
               "lead_time": leads.get(c["sku"], "UNSURE: not in D04-01"), "check": ""}
        if row["on_hand"] is None:
            row.update(status="gray", check="No rows in 3PL export for " + str(c["tpl"]))
        elif c["sku"] in incomplete:
            row.update(status="gray", check="Sales incomplete: " + incomplete[c["sku"]])
        else:
            row["status"] = stock_status(row["on_hand"] + row["on_the_way"],
                                         row["reorder_point"], daily)
        out.append(row)
    order = {"red": 0, "amber": 1, "gray": 2, "green": 3}
    out.sort(key=lambda r: (order[r["status"]], r["product"]))
    return out, (start, end)


def metric_stock(run_time, data_dir=DATA):
    tbl, (start, end) = stock_table(data_dir)
    snap = snapshot_ts(data_dir)
    red = sum(r["status"] == "red" for r in tbl)
    amber = sum(r["status"] == "amber" for r in tbl)
    gray = sum(r["status"] == "gray" for r in tbl)
    status = "red" if red else "amber" if amber else "green"
    return {
        "title": "Stock running low", "kind": "Leading", "owner": "Marco",
        "refresh": "Daily, 06:00", "status": status,
        "headline": f"{red} red · {amber} amber",
        "sub": f"{gray} to check by hand" if gray else "",
        "as_of": snap.strftime("%Y-%m-%d %H:%M") + " (snapshot_ts)",
        "stale": run_time - snap > timedelta(days=1),
        "table": tbl, "window": (start, end),
        "note": f"Daily sales = average of {SALES_WINDOW_DAYS} days, "
                f"{start:%d %b} to {end:%d %b %Y} (D07-07). Reorder point = daily sales x {REORDER_DAYS}.",
    }


# ---------------------------------------------------------------- metric 3: ads

def contribution_per_unit(data_dir=DATA):
    return {r["SKU"]: {"product": r["Product"],
                       "per_unit": num(r["Contribution FY25"]) / num(r["Units sold FY25"]),
                       "contribution": num(r["Contribution FY25"]), "units": num(r["Units sold FY25"])}
            for r in table("margins", "SKU", data_dir=data_dir)}


def monthly_spend(data_dir=DATA):
    """{(year, month): spend} from D04-02."""
    return {(r["Month"].year, r["Month"].month): num(r["Spend"])
            for r in table("ads_monthly", "Month", data_dir=data_dir)
            if isinstance(r["Month"], datetime)}


def budget_share(data_dir=DATA):
    return {r["SKU"]: num(r["Share of budget"]) for r in table("ads_share", "SKU", data_dir=data_dir)}


def ads_month(data_dir=DATA):
    """Latest full calendar month present in both D07-07 (units) and D04-02 (spend)."""
    units = daily_units(data_dir)
    days = {d for per in units.values() for d in per}
    spend = monthly_spend(data_dir)
    full = []
    for (y, m) in spend:
        first = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        n = (nxt - first).days
        if all(first + timedelta(days=i) in days for i in range(n)):
            full.append((y, m))
    return max(full) if full else None


def ads_status(ad_spend, contribution):
    if contribution <= 0:
        return "red" if ad_spend > 0 else "green"
    pct = ad_spend / contribution
    if pct > 1:
        return "red"
    if pct >= 0.5:
        return "amber"
    return "green"


def ads_table(data_dir=DATA):
    ym = ads_month(data_dir)
    if ym is None:
        return [], None
    y, m = ym
    units = daily_units(data_dir)
    cpu = contribution_per_unit(data_dir)
    share = budget_share(data_dir)
    spend = monthly_spend(data_dir)[ym]
    incomplete = incomplete_sales_skus(data_dir)
    out = []
    for sku, c in cpu.items():
        u = sum(v for d, v in units.get(sku, {}).items() if d.year == y and d.month == m)
        contrib = u * c["per_unit"]
        row = {"sku": sku, "product": c["product"], "units": u, "per_unit": c["per_unit"],
               "contribution": contrib, "check": ""}
        if sku not in share:
            row.update(ad_spend=None, pct=None, status="gray", check="No share in D04-03")
        else:
            row["ad_spend"] = spend * share[sku]
            row["pct"] = row["ad_spend"] / contrib if contrib > 0 else None
            if sku in incomplete:
                row.update(status="gray", check="Units incomplete: " + incomplete[sku])
            elif sku not in units:
                row.update(status="gray", check="Not in D07-06 crosswalk")
            else:
                row["status"] = ads_status(row["ad_spend"], contrib)
        out.append(row)
    order = {"red": 0, "amber": 1, "gray": 2, "green": 3}
    out.sort(key=lambda r: (order[r["status"]], r["product"]))
    return out, ym


def metric_ads(run_time, data_dir=DATA):
    tbl, ym = ads_table(data_dir)
    card = {"title": "Ads: contribution after ads", "kind": "Lagging", "owner": "Priya",
            "refresh": "Monthly, on the 1st"}
    if ym is None:
        card.update(status="gray", headline="No source yet", as_of="-",
                    note="No full month in both D07-07 and D04-02.")
        return card
    y, m = ym
    red = sum(r["status"] == "red" for r in tbl)
    amber = sum(r["status"] == "amber" for r in tbl)
    gray = sum(r["status"] == "gray" for r in tbl)
    expected = (run_time.replace(day=1) - timedelta(days=1))
    card.update(
        status="red" if red else "amber" if amber else "green",
        headline=f"{red} losing money",
        sub=(f"{amber} amber" + (f" · {gray} to check by hand" if gray else "")),
        as_of=f"Covers {MONTHS[m - 1]} {y}",
        stale=(y, m) < (expected.year, expected.month),
        table=tbl, month=ym,
        note="Ad spend is an estimate. No ad account access yet. "
             f"{MONTHS[m - 1]} {y} is the latest full month in both D07-07 (units) and D04-02 (spend).")
    return card


# ---------------------------------------------------------------- metric 4: cash

def metric_cash(run_time, data_dir=DATA):
    return {"title": "Cash in the bank", "kind": "Leading", "owner": "Marisa",
            "refresh": "-", "status": "gray", "headline": "No source yet", "as_of": "No source",
            "note": "No source yet. Needs a read-only bank feed, or one known balance plus "
                    "Amazon deposits (D09-02) and PO payments (D07-08).",
            "thresholds": "When sourced: green = covers 8+ weeks · amber = 4-8 weeks · red = under 4 weeks."}


# ---------------------------------------------------------------- page

STATUS_LABEL = {"green": ("●", "OK"), "amber": ("▲", "Watch"),
                "red": ("■", "Act"), "gray": ("○", "No source / check")}


def esc(v):
    return html.escape(str(v))


def chip(status, text=None):
    icon, label = STATUS_LABEL[status]
    return f'<span class="chip {status}">{icon} {esc(text or label)}</span>'


def money(v):
    return "-" if v is None else f"${v:,.0f}"


def pct(v):
    return "-" if v is None else f"{v:.0%}"


def n0(v):
    return "-" if v is None else f"{v:,.0f}"


def card_html(c, body=""):
    stale = '<span class="stale">STALE</span>' if c.get("stale") else ""
    sub = f'<div class="sub">{esc(c["sub"])}</div>' if c.get("sub") else ""
    note = f'<p class="note">{esc(c["note"])}</p>' if c.get("note") else ""
    extra = f'<p class="note">{esc(c["thresholds"])}</p>' if c.get("thresholds") else ""
    return f"""
<section class="card {c['status']}">
  <header>
    <div><h2>{esc(c['title'])}</h2><div class="kind">{esc(c['kind'])}</div></div>
    {chip(c['status'])}
  </header>
  <div class="value">{esc(c['headline'])}</div>{sub}
  <dl>
    <dt>Owner</dt><dd>{esc(c['owner'])}</dd>
    <dt>As of</dt><dd>{esc(c['as_of'])} {stale}</dd>
    <dt>Refresh</dt><dd>{esc(c['refresh'])}</dd>
  </dl>
  {note}{extra}{body}
</section>"""


def build_html(run_time, data_dir=DATA, feed_dir=FEED):
    rev = metric_revenue(run_time, data_dir, feed_dir)
    stock = metric_stock(run_time, data_dir)
    ads = metric_ads(run_time, data_dir)
    cash = metric_cash(run_time, data_dir)
    unmatched = unmatched_codes(data_dir)

    m = rev["months"]
    rev_body = (f'<p class="note">Last year, {m[0]}-{m[-1]} 2025 (D02-02, Amazon + Shopify'
                f'{" + Kickstarter" if INCLUDE_KICKSTARTER else ""}): <b>{money(rev["last_year"])}</b>.</p>'
                if m else "")
    if rev.get("this_year") is not None:
        rev_body += f'<p class="note">This year: <b>{money(rev["this_year"])}</b>.</p>'
    rev_body += ('<p class="thr">Green = 25%+ above last year · Amber = level to 25% above · '
                 'Red = below last year</p>')

    srows = "".join(
        f"<tr><td>{esc(r['product'])}<div class='muted'>{esc(r['sku'])} · {esc(r['tpl'])}</div></td>"
        f"<td class=n>{n0(r['on_hand'])}</td><td class=n>{n0(r['on_the_way'])}</td>"
        f"<td class=n>{r['daily']:.1f}</td><td class=n>{n0(r['reorder_point'])}</td>"
        f"<td>{esc(r['lead_time'])}</td>"
        f"<td>{chip(r['status'], STATUS_LABEL[r['status']][1] if r['status'] != 'gray' else 'Check')}"
        f"{'<div class=muted>' + esc(r['check']) + '</div>' if r['check'] else ''}</td></tr>"
        for r in stock["table"])
    stock_body = f"""
  <div class="scroll"><table>
    <thead><tr><th>Product</th><th class=n>On hand</th><th class=n>On the way</th>
    <th class=n>Daily sales</th><th class=n>Reorder point</th><th>Lead time</th><th>Status</th></tr></thead>
    <tbody>{srows}</tbody></table></div>
  <p class="thr">Green = more than 14 days of sales above reorder point · Amber = within 14 days · Red = at or below</p>"""

    arows = "".join(
        f"<tr><td>{esc(r['product'])}<div class='muted'>{esc(r['sku'])}</div></td>"
        f"<td class=n>{n0(r['units'])}</td><td class=n>{money(r['contribution'])}</td>"
        f"<td class=n>{money(r['ad_spend'])}</td>"
        f"<td class=n>{pct(r['pct'])}</td>"
        f"<td>{chip(r['status'], STATUS_LABEL[r['status']][1] if r['status'] != 'gray' else 'Check')}"
        f"{'<div class=muted>' + esc(r['check']) + '</div>' if r['check'] else ''}</td></tr>"
        for r in ads.get("table", []))
    ads_body = f"""
  <div class="scroll"><table>
    <thead><tr><th>Product</th><th class=n>Units</th><th class=n>Contribution</th>
    <th class=n>Ad spend (est.)</th><th class=n>Ad % of contribution</th><th>Status</th></tr></thead>
    <tbody>{arows}</tbody></table></div>
  <p class="thr">Green = ad spend under 50% of contribution · Amber = 50-100% · Red = over 100%</p>"""

    urows = "".join(f"<tr><td><code>{esc(u['code'])}</code></td><td>{esc(u['where'])}</td>"
                    f"<td>{esc(u['issue'])}</td></tr>" for u in unmatched)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Are We OK?</title>
<style>
:root {{
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3de;
  --good:#0ca30c; --warn:#fab219; --crit:#d03b3b; --gray:#8a8984;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --line:#33332f; }}
}}
:root[data-theme="dark"] {{ --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --line:#33332f; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--page); color:var(--ink);
  font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1200px; margin:0 auto; padding:24px 16px 48px }}
h1 {{ font-size:26px; margin:0 0 4px }}
.lede {{ color:var(--ink2); margin:0 0 20px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr)); gap:16px }}
.card {{ background:var(--surface); border:1px solid var(--line); border-top:4px solid var(--gray);
  border-radius:10px; padding:16px; min-width:0 }}
.card.green {{ border-top-color:var(--good) }} .card.amber {{ border-top-color:var(--warn) }}
.card.red {{ border-top-color:var(--crit) }}
.card.wide {{ grid-column:1/-1 }}
header {{ display:flex; justify-content:space-between; gap:8px; align-items:flex-start }}
h2 {{ font-size:16px; margin:0 }}
.kind,.muted,.thr {{ color:var(--ink2); font-size:12px }}
.value {{ font-size:34px; font-weight:600; margin:10px 0 0 }}
.sub {{ color:var(--ink2) }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:2px 10px; margin:12px 0; font-size:13px }}
dt {{ color:var(--ink2) }} dd {{ margin:0 }}
.note {{ font-size:13px; margin:8px 0 }}
.chip {{ display:inline-block; white-space:nowrap; font-size:12px; font-weight:600; padding:2px 8px;
  border-radius:999px; border:1px solid currentColor }}
.chip.green {{ color:var(--good) }} .chip.amber {{ color:#9a6a00 }} .chip.red {{ color:var(--crit) }}
.chip.gray {{ color:var(--gray) }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) .chip.amber {{ color:var(--warn) }} }}
:root[data-theme="dark"] .chip.amber {{ color:var(--warn) }}
.stale {{ background:var(--crit); color:#fff; font-size:11px; font-weight:700; padding:1px 6px; border-radius:4px }}
.scroll {{ overflow-x:auto }}
table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:8px }}
th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top }}
th {{ color:var(--ink2); font-weight:600 }}
.n {{ text-align:right; font-variant-numeric:tabular-nums }}
ul {{ margin:6px 0; padding-left:20px }}
</style></head>
<body><main>
<h1>Are we OK?</h1>
<p class="lede">Tannerhill Co. · page built {run_time:%Y-%m-%d %H:%M} · sandbox data only</p>
<div class="grid">
{card_html(rev, rev_body)}
{card_html(cash)}
{card_html(dict(stock, status=stock['status']), stock_body).replace('class="card', 'class="card wide', 1)}
{card_html(ads, ads_body).replace('class="card', 'class="card wide', 1)}
<section class="card gray wide">
  <header><div><h2>Unmatched product codes</h2>
  <div class="kind">Codes with no row in D07-06 SKU Crosswalk. Not dropped: listed here until mapped.</div></div>
  {chip('gray', f'{len(unmatched)} codes')}</header>
  <div class="scroll"><table><thead><tr><th>Code</th><th>Where</th><th>Issue</th></tr></thead>
  <tbody>{urows}</tbody></table></div>
</section>
<section class="card gray wide">
  <header><div><h2>Not answered yet</h2></div>{chip('gray', 'No source')}</header>
  <ul>
    <li><b>Reviews / star rating:</b> no source. Needs a weekly ratings export by product from Amazon and Shopify, with one named owner.</li>
    <li><b>Cash in the bank:</b> no source (see the cash card).</li>
  </ul>
</section>
</div>
</main></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", help='run time, e.g. "2026-10-08 09:00" (default: now)')
    args = ap.parse_args()
    run_time = datetime.strptime(args.as_of, "%Y-%m-%d %H:%M") if args.as_of else datetime.now()
    page = build_html(run_time)
    with open(OUT, "w") as f:
        f.write(page)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
