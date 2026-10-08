"""Tannerhill "Are we okay?" dashboard.

Reads the spreadsheets in data/ (read-only), works out the 4 metrics, and
writes index.html next to this file. Every number on the page comes from a
function in this file, so each one can be checked by hand.

Run:  python3 test_build_dashboard_6.py [--overwrite]
"""

import argparse
import html
import os
from datetime import date, datetime, timedelta

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FEED = os.path.join(HERE, "feed")  # drop live revenue exports here (see README)
OUT = os.path.join(HERE, "test_index_6.html")
CHECKS = os.path.join(HERE, "checks.md")

# Simulated "today" is worked out in the browser each time the page opens:
# SIM_START + (real days since SIM_ANCHOR). STALE labels and the hiding of data dated
# after today are done there too (see JS). The build uses SIM_START as its run date.
SIM_START = date(2026, 3, 19)    # simulated today on the anchor day
SIM_ANCHOR = date(2026, 10, 8)   # real date that shows as SIM_START
REPORT_DATE = datetime(SIM_START.year, SIM_START.month, SIM_START.day, 9, 0)

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

# Set by the prompt
INCLUDE_KICKSTARTER = True   # Kickstarter pledges counted when collected, by month collected
SALES_WINDOW_DAYS = 90       # daily sales = average of the last 90 days of data in D07-07
REORDER_DAYS = 56            # reorder point = daily sales x 56 days
BUFFER_DAYS = 14             # green = more than 14 days of sales above the reorder point

# Code mappings missing from D07-06, confirmed by hand in chat on 2026-10-08.
# D07-06 itself is a source file and is not edited.
CONFIRMED_MAPPINGS = [
    {"sku": "TH-GRL-02", "field": "amazon", "code": "TRAILHEAD-GRILL-PRO-V2",
     "was": "TRAILHEAD-GRILL-PRO"},
    {"sku": "TH-ACC-WS", "field": "shopify", "code": "windshield-panel-set", "was": None},
]
CONFIRMED_ON = "2026-10-08"

# 3PL rows marked AVAILABLE but earmarked with a HOLD- reference (e.g. HOLD-KS26-CREATOR,
# HOLD-HS-GIVEAWAY) are taken out of on hand. Confirmed in chat on 2026-10-08.
EXCLUDE_HOLD_PREFIX = "HOLD-"

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

def load_crosswalk(data_dir=DATA, apply_confirmed=True):
    """Our SKU <-> 3PL item code <-> Shopify handle <-> Amazon seller SKU (D07-06),
    with CONFIRMED_MAPPINGS applied on top unless apply_confirmed=False."""
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
    if apply_confirmed:
        for m in CONFIRMED_MAPPINGS:
            for c in cw:
                if c["sku"] == m["sku"]:
                    c[m["field"]] = m["code"]
    return cw


def confirmed_note(code):
    """'Mapped by hand' text for a code covered by CONFIRMED_MAPPINGS, else ''."""
    for m in CONFIRMED_MAPPINGS:
        if code in (m["code"], m["was"]):
            return f"Mapped by hand to {m['sku']} {m['field']} code {m['code']} (confirmed {CONFIRMED_ON})"
    return ""


def sales_columns(data_dir=DATA):
    """Column names (codes) in each D07-07 tab."""
    return {
        "amz_ordered": rows("sales", "Amazon units ordered", data_dir)[0][1:],
        "amz_refunded": rows("sales", "Amazon units refunded", data_dir)[0][1:],
        "shopify": rows("sales", "Shopify net quantity", data_dir)[0][1:],
    }


def unmatched_codes(data_dir=DATA):
    """Every code in D07-01 and D07-07 with no row in D07-06, plus crosswalk gaps.
    Checked against D07-06 as it is; codes fixed by CONFIRMED_MAPPINGS stay listed,
    marked "mapped", so nothing disappears silently."""
    cw = load_crosswalk(data_dir, apply_confirmed=False)
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
    for u in out:
        code = u["code"]
        if code == "(blank)":
            sku = u["where"].split("(")[1].split()[0]
            m = next((m for m in CONFIRMED_MAPPINGS if m["sku"] == sku and m["was"] is None), None)
            code = m["code"] if m else code
        u["mapped"] = confirmed_note(code)
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
            if d > REPORT_DATE.date():
                continue
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
    last = max(datetime.strptime(str(r[0])[:10], "%Y-%m-%d").date() for r in rs[1:] if r[0])
    return min(last, REPORT_DATE.date())


# ---------------------------------------------------------------- metric 1: revenue

def revenue_from_exports(amz_report_path, amz_payments_path, shopify_path):
    """Amazon ordered sales - refunds (by order date) + Shopify gross - discounts - returns.
    Exact duplicate Shopify rows (same week + same variant) are removed first.
    Same shape as D09-01 / D09-02 / D09-03, so a live feed can reuse it.
    Also returns the same sum split by month ('Jan', 'Feb', ...)."""
    by_month = {}

    def add(month, v):
        by_month[month] = by_month.get(month, 0.0) + v

    amz = refunds = 0.0
    for r in table(None, "Month", path=amz_report_path):
        v = num(r["Ordered Product Sales"])
        amz += v
        add(str(r["Month"])[:3], v)
    for r in table(None, "Order month", "Refunds by order date", path=amz_payments_path):
        v = num(r["Refund amount"])
        refunds += v
        add(str(r["Order month"])[:3], -v)
    seen, dupes = {}, []
    for r in table(None, "Week", path=shopify_path):
        k = (r["Week"], r["Product variant SKU"])
        if k in seen:
            dupes.append(r)
        else:
            seen[k] = r
    for r in seen.values():
        # a week is filed under the month its first day falls in
        add(MONTHS[r["Week"].month - 1],
            num(r["Gross sales"]) + num(r["Discounts"]) + num(r["Returns"]))
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
        "by_month": by_month,
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


def net_revenue_per_unit(data_dir=DATA):
    """D04-04 'Net revenue FY25' / 'Units sold FY25' per our SKU."""
    return {r["SKU"]: num(r["Net revenue FY25"]) / num(r["Units sold FY25"])
            for r in table("margins", "SKU", data_dir=data_dir)}


def revenue_estimate(start, end, data_dir=DATA):
    """Estimated revenue between two dates (inclusive): D07-07 net units per SKU
    (Amazon ordered - Amazon refunded + Shopify net) x FY25 net revenue per unit.
    Returns {"total", "by_month": {(year, month): $}}."""
    units = daily_units(data_dir)
    price = net_revenue_per_unit(data_dir)
    by_month = {}
    for sku, per_day in units.items():
        for d, u in per_day.items():
            if start <= d <= end:
                by_month[(d.year, d.month)] = by_month.get((d.year, d.month), 0.0) + u * price.get(sku, 0.0)
    return {"total": sum(by_month.values()), "by_month": by_month}


def days_in_month(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days


def metric_revenue(run_time, data_dir=DATA, feed_dir=FEED):
    """Year to date (1 Jan to the last day of sales data) vs the same period last year.
    This year is an estimate (revenue_estimate). Last year comes from D02-02 by month;
    the last, part month is pro-rated by days (e.g. March x 15/31)."""
    end = last_sales_date(data_dir)
    start = date(end.year, 1, 1)
    est = revenue_estimate(start, end, data_dir)
    ly = last_year_by_month(data_dir)
    chart, ly_as, ly_ks = [], 0.0, 0.0
    for mo in range(1, end.month + 1):
        name = MONTHS[mo - 1]
        part = end.month == mo and end.day < days_in_month(end.year, mo)
        share = end.day / days_in_month(end.year - 1, mo) if part else 1.0
        a = (ly[name]["amazon"] + ly[name]["shopify"]) * share
        k = ly[name]["kickstarter"] * share
        ly_as, ly_ks = ly_as + a, ly_ks + k
        chart.append({"m": f"1–{end.day} {name}" if part else name, "ly": a, "ly_ks": k,
                      "ty": est["by_month"].get((end.year, mo), 0.0)})
    last = ly_as + (ly_ks if INCLUDE_KICKSTARTER else 0)
    this = est["total"]
    status, change = revenue_status(this, last)
    return {
        "title": "Revenue vs last year", "kind": "ESTIMATE", "owner": "Marisa",
        "refresh": "Daily, overnight", "chart": chart, "start": start, "end": end,
        "ly_as": ly_as, "ly_ks": ly_ks, "last_year": last, "this_year": this, "ty_ks": None,
        "change": change, "status": status, "headline": f"{change:+.0%}",
        "as_of": f"Sales to {end:%d %b %Y}",
        "stale": (run_time.date() - end).days > 1,
        "stale_rule": "daily", "stale_ref": end.isoformat(), "stale_lag": 1,  # overnight: data to yesterday
        "source": "Last year's accounts · sales estimate",
    }


# ---------------------------------------------------------------- metric 2: stock

def on_hand(data_dir=DATA):
    """Sum of qty_available per 3PL item_code (D07-01). qty_on_hand is not used.
    Rows earmarked with a HOLD- reference are left out (see earmarked())."""
    out = {}
    for r in table("tpl", "snapshot_ts", data_dir=data_dir):
        held = str(r["hold_ref"] or "").startswith(EXCLUDE_HOLD_PREFIX)
        out[r["item_code"]] = out.get(r["item_code"], 0.0) + (0.0 if held else num(r["qty_available"]))
    return out


def earmarked(data_dir=DATA):
    """3PL rows left out of on hand: [{item_code, hold_ref, qty}]."""
    return [{"item_code": r["item_code"], "hold_ref": r["hold_ref"], "qty": num(r["qty_available"])}
            for r in table("tpl", "snapshot_ts", data_dir=data_dir)
            if str(r["hold_ref"] or "").startswith(EXCLUDE_HOLD_PREFIX) and num(r["qty_available"]) > 0]


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
        "title": "Stock running low", "kind": "", "owner": "Marco",
        "refresh": "Daily, 06:00", "status": status,
        "headline": f"{red} red · {amber} amber",
        "sub": f"{gray} to check by hand" if gray else "",
        "as_of": snap.strftime("%d %b %Y, %H:%M"),
        "stale": run_time - snap > timedelta(days=1),
        "stale_rule": "daily", "stale_ref": snap.date().isoformat(), "stale_lag": 0,  # 06:00 export: today's
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
    card = {"title": "Ads: contribution after ads", "kind": "", "owner": "Priya",
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
        stale_rule="monthly", stale_ref=f"{y}-{m:02d}", stale_lag=0, data_date=f"{y}-{m:02d}-01",
        table=tbl, month=ym,
        note="Ad spend is estimated from BidWorks' budget split.")
    return card


# ---------------------------------------------------------------- metric 4: cash

def metric_cash(run_time, data_dir=DATA):
    return {"title": "Cash in the bank", "kind": "", "owner": "Marisa",
            "refresh": "-", "status": "gray", "headline": "No data", "as_of": "never",
            "note": "Waiting on a bank feed"}



# ---------------------------------------------------------------- page

S_CLASS = {"green": "good", "amber": "warn", "red": "crit", "gray": "gray"}
S_WORD = {"green": "Healthy", "amber": "Watch", "red": "Act now", "gray": "No data"}
S_ORDER = {"red": 0, "amber": 1, "gray": 2, "green": 3}


def esc(v):
    return html.escape(str(v))


def pill(status, text=None):
    return f'<span class="pill {S_CLASS[status]}">{esc(text or S_WORD[status])}</span>'


def money(v):
    return "–" if v is None else f"${v:,.0f}"


def pct(v):
    return "–" if v is None else f"{v:.0%}"


def n0(v):
    return "–" if v is None else f"{v:,.0f}"


def stale_tag(card):
    """STALE label, shown or hidden by the browser against simulated today."""
    if not card.get("stale_rule"):
        return ""
    return (f' <span class="stale" hidden data-rule="{card["stale_rule"]}" '
            f'data-ref="{card["stale_ref"]}" data-lag="{card["stale_lag"]}">STALE</span>')


def meta(card, last_run_label, last_run, source, demo_last_run=None):
    """Footer line. demo_last_run replaces the last-run time when DEMO_MODE is on (see JS)."""
    demo = f' data-demo="{esc(demo_last_run)}"' if demo_last_run else ""
    return (f'<div class="meta"><span>Owner <b>{esc(card["owner"])}</b></span>'
            f'<span>{esc(last_run_label)} <b{demo}>{esc(last_run)}</b>{stale_tag(card)}</span>'
            f'<span>Refresh <b>{esc(card["refresh"])}</b></span>'
            f'<span>Source: {esc(source)}</span></div>')


def panel_head(card, pill_html):
    """Collapsed row (<summary>): title, headline, owner, STALE, pill. Opens the panel body."""
    num = "–" if card["status"] == "gray" else card["headline"]
    return (f'<summary class="ph"><span class="arrow" aria-hidden="true"></span>'
            f'<h2>{esc(card["title"])}{f' <span class="tag">{esc(card["kind"])}</span>' if card["kind"] else ""}</h2>'
            f'<span class="sumnum">{esc(num)}</span>'
            f'<span class="sumowner">Owner <b>{esc(card["owner"])}</b>{stale_tag(card)}</span>'
            f'<span class="grow"></span>{pill_html}</summary><div class="pbody">')


def revenue_chart(chart):
    """Grouped bars per month: last year (Amazon + Shopify, Kickstarter stacked on top)
    and this year. Static SVG; hover text in data-t."""
    W, H, L, B, T = 560, 230, 52, 28, 10
    top = max([r["ly"] + r["ly_ks"] for r in chart] + [r["ty"] or 0 for r in chart] + [1])
    step = 50000
    vmax = (int(top // step) + 1) * step
    y = lambda v: T + (H - B - T) * (1 - v / vmax)
    s = []
    for g in range(0, vmax + 1, step):
        s.append(f'<line x1="{L}" x2="{W - 8}" y1="{y(g):.1f}" y2="{y(g):.1f}" stroke="var(--line)"/>'
                 f'<text x="{L - 6}" y="{y(g) + 4:.1f}" text-anchor="end">{"$%dk" % (g // 1000) if g else "0"}</text>')
    gw = (W - L - 8) / len(chart)
    bw = min(26, gw * .34)

    def bar(x, v0, v1, fill, tip, round_top):
        y0, y1 = y(v0), y(v1)
        h = y0 - y1
        if h <= 0:
            return ""
        if round_top and h > 4:
            d = f"M{x:.1f},{y0:.1f} V{y1 + 4:.1f} q0,-4 4,-4 h{bw - 8:.1f} q4,0 4,4 V{y0:.1f} Z"
        else:
            d = f"M{x:.1f},{y0:.1f} V{y1:.1f} h{bw:.1f} V{y0:.1f} Z"
        return (f'<path d="{d}" fill="{fill}" data-t="{esc(tip)}"/>')

    for i, r in enumerate(chart):
        cx = L + gw * i + gw / 2
        x1 = cx - bw - 1
        has_ks = r["ly_ks"] > 0
        s.append(bar(x1, 0, r["ly"], "var(--ly)", f'{r["m"]} 2025 Amazon + Shopify: ${r["ly"]:,.0f}', not has_ks))
        if has_ks:  # 2px surface gap between stacked segments
            s.append(bar(x1, r["ly"] + (vmax * 2 / (H - B - T)), r["ly"] + r["ly_ks"], "var(--ks)",
                         f'{r["m"]} 2025 Kickstarter: ${r["ly_ks"]:,.0f}', True))
        if r["ty"] is not None:
            s.append(bar(cx + 1, 0, r["ty"], "var(--accent)", f'{r["m"]} this year: ${r["ty"]:,.0f}', True))
        s.append(f'<text x="{cx:.1f}" y="{H - 8}" text-anchor="middle">{r["m"]}</text>')
    label = "Revenue by month, last year vs this year"
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{label}">{"".join(s)}</svg>'


def revenue_panel(rev):
    span = f"{rev['start']:%-d %b} – {rev['end']:%-d %b}"
    legend = ('<div class="legend"><span><span class="sw" style="background:var(--ly)"></span>Last year, Amazon + Shopify</span>'
              '<span><span class="sw" style="background:var(--ks)"></span>Last year, Kickstarter</span>'
              '<span><span class="sw" style="background:var(--accent)"></span>This year (estimate)</span></div>')
    return f"""
<details class="panel" data-s="{S_CLASS[rev['status']]}" id="rev"{date_attr(rev)}>
  {panel_head(rev, pill(rev['status']))}
  <div class="two">
    <div>{legend}{revenue_chart(rev['chart'])}</div>
    <div style="display:grid;gap:12px">
      <div><div class="lbl">Year to date, {span} · Estimate</div><div class="big">{money(rev['this_year'])}</div>
        <div class="note">{rev['change']:+.1%} vs {money(rev['last_year'])} last year</div></div>
      <table class="mini">
        <tr><th>Last year, {span}</th><th class="n"></th></tr>
        <tr><td>Amazon + Shopify</td><td class="n">{money(rev['ly_as'])}</td></tr>
        <tr><td>Kickstarter (pledges collected)</td><td class="n">{money(rev['ly_ks'])}</td></tr>
        <tr><td><b>Total</b></td><td class="n"><b>{money(rev['last_year'])}</b></td></tr>
        <tr><td>Kickstarter this year</td><td class="n">No source</td></tr>
      </table>
    </div>
  </div>
  <p class="bands">Green 25%+ above last year · Amber level with last year up to 25% above · Red below last year</p>
  {meta(rev, 'Last run', rev['as_of'], rev['source'], 'Today 05:00')}
</div></details>"""


def stock_panel(stock, unmatched):
    trs = []
    for r in stock["table"]:
        st = r["status"]
        tot = None if r["on_hand"] is None else r["on_hand"] + r["on_the_way"]
        rop = r["reorder_point"]
        scale = max(min(tot or 0, rop * 3), rop, 1) * 1.15
        fill = min(tot or 0, rop * 3) / scale * 100
        col = {"red": "var(--crit)", "amber": "var(--warn)", "green": "var(--good)", "gray": "var(--gray)"}[st]
        tip = f'{r["sku"]} {r["product"]}: {n0(tot)} vs reorder point {rop:,.0f}'
        bar = (f'<div class="bar" data-t="{esc(tip)}"><i style="width:{fill:.1f}%;background:{col}"></i>'
               f'<u style="left:{rop / scale * 100:.1f}%"></u></div>')
        check = f'<div class="note">{esc(r["check"])}</div>' if r["check"] else ""
        trs.append(
            f'<tr data-sales="{r["daily"]:.4f}" data-urgent="{S_ORDER[st]}" '
            f'data-ratio="{(tot / rop) if (tot is not None and rop) else 1e9:.4f}" data-sku="{esc(r["sku"])}">'
            f'<td class="sku">{esc(r["sku"])}</td><td>{esc(r["product"])}</td>'
            f'<td class="n">{r["daily"]:.1f}</td><td class="n">{n0(r["on_hand"])}</td>'
            f'<td class="n">{n0(r["on_the_way"]) if r["on_the_way"] else "–"}</td>'
            f'<td class="n">{rop:,.0f}</td><td class="n">{esc(r["lead_time"])}</td>'
            f'<td>{bar}</td><td>{pill(st)}{check}</td></tr>')
    still = sum(not u["mapped"] for u in unmatched)
    start, end = stock["window"]
    return f"""
<details class="panel" data-s="{S_CLASS[stock['status']]}" id="stock"{date_attr(stock)}>
  {panel_head(stock, pill(stock['status']))}
  <div><div class="big">{esc(stock['headline'])}</div><div class="note">of {len(stock['table'])} products{' · ' + esc(stock['sub']) if stock.get('sub') else ''}</div></div>
  <div class="sortbar" role="group" aria-label="Sort stock table" data-table="stockT">
    <span class="lbl">Sort</span>
    <button type="button" data-k="sales" aria-pressed="false">Best sellers</button>
    <button type="button" data-k="urgent" aria-pressed="true">Most urgent</button>
    <button type="button" data-k="sku" aria-pressed="false">SKU</button>
  </div>
  <div class="legend"><span><span class="sw" style="background:var(--fg);width:2px"></span>Reorder point (daily sales × {REORDER_DAYS} days)</span><span>Bar = on hand + on the way</span></div>
  <div class="tablewrap"><table id="stockT">
    <thead><tr><th>SKU</th><th>Product</th><th class="n">Sold / day</th><th class="n">On hand</th>
    <th class="n">On the way</th><th class="n">Reorder pt</th><th class="n">Lead time</th>
    <th style="min-width:130px">Stock vs reorder point</th><th>Status</th></tr></thead>
    <tbody>{''.join(trs)}</tbody></table></div>
  {f'<div class="note">{still} product code(s) do not match. See checks.md.</div>' if still else ''}
  <p class="bands">Green more than {BUFFER_DAYS} days of sales above the reorder point · Amber within {BUFFER_DAYS} days · Red at or below the reorder point</p>
  {meta(stock, 'Last run', stock['as_of'], '3PL stock export · Amazon and Shopify sales · supplier orders', 'Today 06:00')}
</div></details>"""


def ads_panel(ads):
    rows_ = sorted(ads.get("table", []),
                   key=lambda r: (S_ORDER[r["status"]], -(r["pct"] if r["pct"] is not None else 1e9)))
    trs = "".join(
        f'<tr data-worst="{r["pct"] if r["pct"] is not None else -1:.4f}" data-spend="{r["ad_spend"] or 0:.2f}" '
        f'data-contrib="{r["contribution"]:.2f}" data-name="{esc(r["product"])}" data-nounits="{int(r["units"] <= 0)}">'
        f'<td>{esc(r["product"])}<div class="sku">{esc(r["sku"])}</div></td>'
        f'<td class="n">{n0(r["units"])}</td><td class="n">{money(r["contribution"])}</td>'
        f'<td class="n">{money(r["ad_spend"])}</td><td class="n">{pct(r["pct"])}</td>'
        f'<td>{pill(r["status"])}'
        f'{"<div class=note>" + esc(r["check"]) + "</div>" if r["check"] else ""}</td></tr>'
        for r in rows_)
    return f"""
<details class="panel" data-s="{S_CLASS[ads['status']]}" id="ads"{date_attr(ads)}>
  {panel_head(ads, pill(ads['status']))}
  <div><div class="big">{esc(ads['headline'])} after ads</div><div class="note">{esc(ads.get('sub', ''))}</div></div>
  <div class="grayblock">{esc(ads['note'])}</div>
  <div class="sortbar" role="group" aria-label="Sort ads table" data-table="adsT">
    <span class="lbl">Sort</span>
    <button type="button" data-k="worst" aria-pressed="true">Worst first</button>
    <button type="button" data-k="spend" aria-pressed="false">Biggest ad spend</button>
    <button type="button" data-k="contrib" aria-pressed="false">Most contribution</button>
    <button type="button" data-k="name" aria-pressed="false">Product A–Z</button>
  </div>
  <div class="tablewrap"><table id="adsT">
    <thead><tr><th>Product</th><th class="n">Units</th><th class="n">Contribution</th>
    <th class="n">Ad spend (est.)</th><th class="n">Ad spend % of contribution</th><th>Status</th></tr></thead>
    <tbody>{trs}</tbody></table></div>
  <p class="bands">Green ad spend under 50% of contribution · Amber 50–100% · Red over 100% (losing money after ads)</p>
  {meta(ads, 'Covers', ads['as_of'].replace('Covers ', ''), 'BidWorks report · product margins')}
</div></details>"""


def cash_panel(cash):
    return f"""
<details class="panel" data-s="gray" id="cash">
  {panel_head(cash, pill('gray'))}
  <div class="grayblock">{esc(cash['note'])}</div>
  <p class="bands">Green covers 8+ weeks of payments due · Amber 4–8 weeks · Red under 4 weeks</p>
  {meta(cash, 'Last run', 'never', 'none')}
</div></details>"""


def date_attr(card):
    d = card.get("data_date") or (card.get("stale_ref") if card.get("stale_rule") == "daily" else None)
    return f' data-date="{d}"' if d else ""


def tile(label, big, note, status, card, target):
    return (f'<a class="tile" href="#{target}" data-s="{S_CLASS[status]}"{date_attr(card)}><div class="lbl">{esc(label)}</div>'
            f'<div class="big">{esc(big)}</div><div class="note">{esc(note)}{stale_tag(card)}</div>'
            f'{pill(status)}</a>')


CSS = """
:root{
  --bg:#f4f6f3; --panel:#ffffff; --fg:#1b211d; --muted:#5b665e; --line:#dfe4dd; --soft:#eef1ec;
  --accent:#2f5d46; --ly:#a9b3ab; --ks:#c98a2b;
  --good:#0ca30c; --warn:#fab219; --crit:#d03b3b; --gray:#8d958f;
  --good-ink:#0a6e0a; --warn-ink:#8a5a00; --crit-ink:#b02a2a;
  --body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#141815; --panel:#1c211e; --fg:#eef2ee; --muted:#a7b1a9; --line:#2e3631; --soft:#232a25;
  --accent:#7fbf9c; --ly:#56605a; --ks:#e0a54a; --gray:#79827c;
  --good-ink:#5fd35f; --warn-ink:#fab219; --crit-ink:#ff7b7b; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#141815; --panel:#1c211e; --fg:#eef2ee; --muted:#a7b1a9; --line:#2e3631; --soft:#232a25;
  --accent:#7fbf9c; --ly:#56605a; --ks:#e0a54a; --gray:#79827c;
  --good-ink:#5fd35f; --warn-ink:#fab219; --crit-ink:#ff7b7b; color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--body);font-size:14px;line-height:1.5}
.wrap{max-width:1120px;margin:0 auto;padding:16px 16px 32px;display:grid;gap:10px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:12px}
h1{font-size:26px;font-weight:700;margin:0;letter-spacing:-.01em}
.sub{color:var(--muted);margin:2px 0 0}
.sample{font-family:var(--mono);font-size:12px;color:var(--muted);border:1px dashed var(--line);border-radius:6px;padding:6px 10px;max-width:520px}
.strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
@media (max-width:860px){.strip{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:460px){.strip{grid-template-columns:1fr}}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;display:grid;gap:4px;border-top:4px solid var(--gray);align-content:start;color:inherit;text-decoration:none;cursor:pointer}
a.tile:hover{border-color:var(--accent)}a.tile:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tile[data-s="good"]{border-top-color:var(--good)}.tile[data-s="warn"]{border-top-color:var(--warn)}.tile[data-s="crit"]{border-top-color:var(--crit)}
.lbl{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.big{font-size:26px;font-weight:700;line-height:1.1}
.note{color:var(--muted);font-size:12.5px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:2px 9px;border-radius:99px;background:var(--soft);white-space:nowrap;width:fit-content}
.pill::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--gray)}
.pill.good{color:var(--good-ink)}.pill.good::before{background:var(--good)}
.pill.warn{color:var(--warn-ink)}.pill.warn::before{background:var(--warn)}
.pill.crit{color:var(--crit-ink)}.pill.crit::before{background:var(--crit)}
.pill.gray{color:var(--muted)}
.stale{font-family:var(--mono);font-size:10.5px;font-weight:600;color:var(--crit-ink);border:1px solid var(--crit);border-radius:4px;padding:0 5px;margin-left:4px;white-space:nowrap}
details.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;min-width:0;scroll-margin-top:8px}
.pbody{display:grid;gap:12px;padding:2px 16px 14px;min-width:0}
.pbody>*{min-width:0}
.ph{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;padding:9px 16px;cursor:pointer;list-style:none}
.ph::-webkit-details-marker{display:none}
.ph:focus-visible{outline:2px solid var(--accent);outline-offset:-2px;border-radius:8px}
.arrow::before{content:"▸";color:var(--muted);display:inline-block;width:10px}
details[open]>.ph .arrow::before{content:"▾"}
.sumnum{font-weight:700;font-variant-numeric:tabular-nums}
.sumowner{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.sumowner b{color:var(--fg);font-weight:500}
.grow{flex:1}
.toolbar{display:flex;justify-content:flex-end;margin:-2px 0}
.linkbtn{font:inherit;font-size:12.5px;color:var(--accent);background:none;border:none;padding:0;cursor:pointer;text-decoration:underline}
h2{font-size:17px;margin:0;font-weight:700}
.tag{font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:6px;font-weight:400}
.meta{display:flex;flex-wrap:wrap;gap:6px 16px;font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.meta b{color:var(--fg);font-weight:500}
.two{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:20px;align-items:start}
@media (max-width:760px){.two{grid-template-columns:1fr}}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13px}
th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
td.n,th.n{text-align:right;white-space:nowrap}
tr:last-child td{border-bottom:none}
table.mini th{text-transform:none;letter-spacing:0;font-size:12px}
.bar{position:relative;height:10px;background:var(--soft);border-radius:2px;min-width:110px}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:0 4px 4px 0}
.bar u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--fg)}
.sortbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.sortbar button{font:inherit;font-size:12.5px;padding:4px 11px;border-radius:99px;border:1px solid var(--line);background:var(--panel);color:var(--fg);cursor:pointer}
.sortbar button:hover{border-color:var(--accent)}
.sortbar button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--panel)}
.sortbar button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sku{font-family:var(--mono);font-size:12px;color:var(--muted);white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted)}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
svg text{fill:var(--muted);font-family:var(--body);font-size:11px}
.grayblock{border:1px dashed var(--line);border-radius:6px;padding:12px 14px;color:var(--muted);background:var(--soft)}
.tip{position:fixed;pointer-events:none;background:var(--fg);color:var(--bg);font-size:12px;padding:6px 9px;border-radius:5px;font-variant-numeric:tabular-nums;z-index:9}
.bands{font-size:12px;color:var(--muted);margin:0}
footer{color:var(--muted);font-size:13px}
footer ul{margin:6px 0 0;padding-left:20px}
"""

JS = """
// DEMO_MODE: pretend the data refreshes daily. No STALE labels, last-run times follow
// simulated today. Set to false to judge STALE against the real data dates.
const DEMO_MODE = true;
const D=(y,m,d)=>new Date(y,m,d);
const iso=s=>{const [y,m,d]=s.split('-').map(Number);return D(y,m-1,d||1)};
const now=new Date(), realDay=D(now.getFullYear(),now.getMonth(),now.getDate());
const SIM_START=iso('%(start)s'), SIM_ANCHOR=iso('%(anchor)s');
const shift=Math.round((realDay-SIM_ANCHOR)/864e5);
const today=D(SIM_START.getFullYear(),SIM_START.getMonth(),SIM_START.getDate()+shift);
const WD=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
document.getElementById('today').textContent=`${WD[today.getDay()]} ${String(today.getDate()).padStart(2,'0')} ${MO[today.getMonth()]} ${today.getFullYear()}`;
document.querySelectorAll('.demo-only').forEach(el=>el.hidden=!DEMO_MODE);
document.querySelectorAll('.real-only').forEach(el=>el.hidden=DEMO_MODE);
if(DEMO_MODE)document.querySelectorAll('[data-demo]').forEach(el=>el.textContent=el.dataset.demo);
document.querySelectorAll('.stale[data-rule]').forEach(el=>{
  if(DEMO_MODE){el.hidden=true;return}
  let stale;
  if(el.dataset.rule==='daily'){const need=D(today.getFullYear(),today.getMonth(),today.getDate()-Number(el.dataset.lag));stale=iso(el.dataset.ref)<need}
  else{const [y,m]=el.dataset.ref.split('-').map(Number);const prev=D(today.getFullYear(),today.getMonth()-1,1);stale=y*12+m<prev.getFullYear()*12+prev.getMonth()+1}
  el.hidden=!stale});
document.querySelectorAll('[data-date]').forEach(el=>{if(iso(el.dataset.date)>today)el.hidden=true});
const panels=[...document.querySelectorAll('details.panel')], toggleAll=document.getElementById('toggleAll');
const syncToggle=()=>{toggleAll.textContent=panels.every(d=>d.open)?'Collapse all':'Expand all'};
toggleAll.addEventListener('click',()=>{const open=!panels.every(d=>d.open);panels.forEach(d=>d.open=open);syncToggle()});
panels.forEach(d=>d.addEventListener('toggle',syncToggle));
function openPanel(id){const d=document.getElementById(id);if(!d)return;d.open=true;d.scrollIntoView({behavior:'smooth',block:'start'})}
document.querySelectorAll('a.tile').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();const id=a.getAttribute('href').slice(1);history.replaceState(null,'','#'+id);openPanel(id)}));
if(location.hash)openPanel(location.hash.slice(1));
const tip=document.getElementById('tip');
function showTip(e,t){tip.textContent=t;tip.hidden=false;tip.style.left=Math.min(e.clientX+12,innerWidth-220)+'px';tip.style.top=(e.clientY+12)+'px'}
document.querySelectorAll('[data-t]').forEach(el=>{el.addEventListener('mousemove',e=>showTip(e,el.dataset.t));el.addEventListener('mouseleave',()=>tip.hidden=true)});
const sorters={
  sales:(a,b)=>b.dataset.sales-a.dataset.sales,
  urgent:(a,b)=>(a.dataset.urgent-b.dataset.urgent)||(a.dataset.ratio-b.dataset.ratio),
  sku:(a,b)=>a.dataset.sku.localeCompare(b.dataset.sku),
  worst:(a,b)=>b.dataset.worst-a.dataset.worst,
  spend:(a,b)=>b.dataset.spend-a.dataset.spend,
  contrib:(a,b)=>b.dataset.contrib-a.dataset.contrib,
  name:(a,b)=>a.dataset.name.localeCompare(b.dataset.name)};
// rows with no units sink to the bottom of every ads sort except A-Z
const noUnitsLast=(k,f)=>k==='name'?f:(a,b)=>((a.dataset.nounits||0)-(b.dataset.nounits||0))||f(a,b);
function sortTable(bar,k){const tb=document.querySelector('#'+bar.dataset.table+' tbody');
  [...tb.rows].sort(noUnitsLast(k,sorters[k])).forEach(r=>tb.appendChild(r));
  bar.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.k===k?'true':'false'))}
document.querySelectorAll('.sortbar').forEach(bar=>{
  bar.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>sortTable(bar,b.dataset.k)));
  sortTable(bar,bar.querySelector('[aria-pressed="true"]').dataset.k)});
"""


def build_html(run_time, data_dir=DATA, feed_dir=FEED):
    rev = metric_revenue(run_time, data_dir, feed_dir)
    stock = metric_stock(run_time, data_dir)
    ads = metric_ads(run_time, data_dir)
    cash = metric_cash(run_time, data_dir)
    unmatched = unmatched_codes(data_dir)
    snap = snapshot_ts(data_dir)

    n_stock = len(stock["table"])
    n_ads = len(ads.get("table", []))
    tiles = "".join([
        tile("Revenue vs last year · Estimate", rev["headline"],
             f'{money(rev["this_year"])} vs {money(rev["last_year"])}', rev["status"], rev, "rev"),
        tile("Stock running low", stock["headline"],
             f'of {n_stock} products' + (f' · {stock["sub"]}' if stock.get("sub") else ""),
             stock["status"], stock, "stock"),
        tile("Ads: losing money after ads", f'{sum(r["status"] == "red" for r in ads.get("table", []))} of {n_ads}',
             f'products · {ads["as_of"].replace("Covers ", "")} · estimate', ads["status"], ads, "ads"),
        tile("Cash cover", "–", "Waiting on a bank feed", "gray", cash, "cash"),
    ])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Are We Okay</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head>
<body><div class="wrap">
<header>
  <div><h1>Are we okay?</h1>
  <p class="sub">Tannerhill Co. · Today <span id="today">{run_time:%a %d %b %Y}</span> <span class="real-only"> · Sales to {last_sales_date(data_dir):%-d %b} · Stock at {snap:%-d %b}</span><span class="demo-only" hidden> · Updated 06:00</span></p></div>
</header>
<div class="strip">{tiles}</div>
<div class="toolbar"><button type="button" class="linkbtn" id="toggleAll">Expand all</button></div>
{revenue_panel(rev)}
{stock_panel(stock, unmatched)}
{ads_panel(ads)}
{cash_panel(cash)}
</div>
<div class="tip" id="tip" hidden></div>
<script>{JS % {"start": SIM_START.isoformat(), "anchor": SIM_ANCHOR.isoformat()}}</script>
</body></html>
"""


def checks_md(data_dir=DATA):
    """Product-code checks (moved off the page): codes not in the SKU crosswalk."""
    lines = ["# Checks", "", f"Report date {REPORT_DATE:%a %-d %b %Y}.", "",
             "## SKU crosswalk: codes not in D07-06", "",
             "| Code | Where | Issue in D07-06 | Now |", "|---|---|---|---|"]
    for u in unmatched_codes(data_dir):
        lines.append(f"| `{u['code']}` | {u['where']} | {u['issue']} | {u['mapped'] or 'STILL UNMATCHED'} |")
    lines += ["", "## Earmarked stock left out of on hand", "", "| 3PL code | Hold | Units |", "|---|---|---|"]
    for e in earmarked(data_dir):
        lines.append(f"| {e['item_code']} | {e['hold_ref']} | {e['qty']:,.0f} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true",
                    help="replace test_index.html and checks.md if they exist (CLAUDE.md rule 3: ask first)")
    args = ap.parse_args()
    for path in (OUT,):
        if os.path.exists(path) and not args.overwrite:
            raise SystemExit(f"{path} exists. Not overwriting (CLAUDE.md rule 3). Use --overwrite if a person approved it.")
    with open(OUT, "w") as f:
        f.write(build_html(REPORT_DATE))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
