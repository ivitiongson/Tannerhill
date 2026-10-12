"""Tannerhill "Are we okay?" dashboard - reference logic for the Supabase page.

Same metric functions as output/test_dashboard_v3/test_build_dashboard_6.py, but the
loaders read the clean load files in load/ (one per Supabase table, see make_load.py)
instead of the spreadsheets. index.html runs the same logic in the browser on the
Supabase rows; tests/test_metrics.py checks both give the expected figures.
"""

import csv
import os
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "load")
FEED = None

# Simulated "today" is worked out in the browser each time the page opens:
# SIM_START + (real days since SIM_ANCHOR). STALE labels and the hiding of data dated
# after today are done there too (see JS). The build uses SIM_START as its run date.
# Q4 decided 2026-10-09: the page date is fixed at Fri 3 Apr 2026 (the data date).
SIM_START = date(2026, 4, 3)     # page "today"
SIM_ANCHOR = None                # no longer moves with the real date
REPORT_DATE = datetime(SIM_START.year, SIM_START.month, SIM_START.day, 9, 0)

# Supabase table (= load/<table>.csv) per source file
FILES = {
    "ledger": "d10_01_order_ledger",
    "fin": "d10_02_revenue_by_month",
    "amz_report": "d10_03_amazon_business_report",
    "amz_refunds": "d10_04_amazon_refunds_by_order_date",
    "shopify": "d10_05_shopify_sales_by_product_weekly",
    "amz_ordered": "d10_06a_amazon_units_ordered",
    "amz_refunded": "d10_06b_amazon_units_refunded",
    "shp_net": "d10_06c_shopify_net_quantity",
    "tpl": "d10_07_3pl_daily_stock",
    "ads_monthly": "d10_08_bw_monthly_report",
    "invoices": "d10_09_bw_agency_invoices",
    "pos": "d10_10_yuhang_po_history",
    "crosswalk": "d07_06_sku_crosswalk",
    "stock_terms": "d04_01_supplier_terms",
    "ads_share": "d04_03_bidworks_spend_by_product",
    "margins": "d04_04_product_margins",
}

# Set by the prompt
INCLUDE_KICKSTARTER = True   # Kickstarter counted in the month rewards shipped (D10-02 recognized column)
SALES_WINDOW_DAYS = 90       # daily sales = average of the last 90 days of data in D10-06
REORDER_DAYS = 56            # reorder point = daily sales x 56 days
BUFFER_DAYS = 14             # green = more than 14 days of sales above the reorder point

# Code mappings missing from D07-06, confirmed by hand in chat on 2026-10-08.
# D07-06 itself is a source file and is not edited.
CONFIRMED_MAPPINGS = [
    {"sku": "TH-GRL-02", "field": "amazon", "code": "TRAILHEAD-GRILL-PRO-V2",
     "was": "TRAILHEAD-GRILL-PRO", "note": "same product, newer version; confirmed again 2026-10-09"},
    {"sku": "TH-ACC-WS", "field": "shopify", "code": "windshield-panel-set", "was": None},
]
CONFIRMED_ON = "2026-10-08"

# 3PL rows marked AVAILABLE but earmarked with a HOLD- reference (e.g. HOLD-KS26-CREATOR,
# HOLD-HS-GIVEAWAY) are taken out of on hand. Confirmed in chat on 2026-10-08.
EXCLUDE_HOLD_PREFIX = "HOLD-"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------------------------------------------------------- reading

_cache = {}


def table(key, data_dir=DATA):
    """All rows of one table (load/<table>.csv, same rows as Supabase) as dicts.
    Blank cells are None, like a NULL from Supabase."""
    k = (key, data_dir)
    if k not in _cache:
        with open(os.path.join(data_dir, FILES[key] + ".csv"), newline="", encoding="utf-8") as f:
            _cache[k] = [{h: (v if v != "" else None) for h, v in r.items()} for r in csv.DictReader(f)]
    return _cache[k]


def num(v):
    return 0.0 if v in (None, "", "-") else float(v)


def iso(s):
    """YYYY-MM-DD (or the date part of a timestamp) -> date."""
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date() if s else None


def ts(s):
    """D10-07 snapshot_ts 'YYYY-MM-DD HH:MM' (Supabase sends 'YYYY-MM-DDTHH:MM:SS')."""
    return datetime.strptime(str(s).replace("T", " ")[:16], "%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- crosswalk

def load_crosswalk(data_dir=DATA, apply_confirmed=True):
    """Our SKU <-> 3PL item code <-> Shopify handle <-> Amazon seller SKU (D07-06),
    with CONFIRMED_MAPPINGS applied on top unless apply_confirmed=False."""
    cw = []
    for r in table("crosswalk", data_dir):
        notes = (r.get("notes") or "").lower()
        cw.append({
            "sku": r["our_sku"],
            "product": r["product"],
            "tpl": r["3pl_item_code"],
            "shopify": r["shopify_handle"],
            "amazon": r["amazon_seller_sku"],
            "notes": r.get("notes") or "",
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
            extra = f"; {m['note']}" if m.get("note") else ""
            return f"Mapped by hand to {m['sku']} {m['field']} code {m['code']} (confirmed {CONFIRMED_ON}{extra})"
    return ""


def sales_columns(data_dir=DATA):
    """Codes (the wide files' column headers) in each D10-06 table, in file order."""
    def codes(key):
        return list(dict.fromkeys(r["code"] for r in table(key, data_dir)))
    return {
        "amz_ordered": codes("amz_ordered"),
        "amz_refunded": codes("amz_refunded"),
        "shopify": codes("shp_net"),
    }


def unmatched_codes(data_dir=DATA):
    """Every code in D10-07 and D10-06 with no row in D07-06, plus crosswalk gaps.
    Checked against D07-06 as it is; codes fixed by CONFIRMED_MAPPINGS stay listed,
    marked "mapped", so nothing disappears silently."""
    cw = load_crosswalk(data_dir, apply_confirmed=False)
    tpl_codes = {c["tpl"] for c in cw if c["tpl"]}
    amz_codes = {c["amazon"] for c in cw if c["amazon"]}
    shp_codes = {c["shopify"] for c in cw if c["shopify"]}
    out = []
    stock_codes = set()
    for r in table("tpl", data_dir):
        stock_codes.add(r["item_code"])
        if r["item_code"] not in tpl_codes and not any(u["code"] == r["item_code"] for u in out):
            out.append({"code": r["item_code"], "where": "D10-07 3PL item_code",
                        "issue": "not in D07-06 3PL item code column"})
    cols = sales_columns(data_dir)
    for tab, known, label in [("amz_ordered", amz_codes, "D10-06a Amazon units ordered"),
                              ("amz_refunded", amz_codes, "D10-06b Amazon units refunded"),
                              ("shopify", shp_codes, "D10-06c Shopify net quantity")]:
        for code in cols[tab]:
            if code and code not in known:
                out.append({"code": code, "where": label,
                            "issue": "not in D07-06"})
    # crosswalk entries that point at nothing in the sales history
    for c in cw:
        if c["tpl"] and c["tpl"] not in stock_codes:
            out.append({"code": c["tpl"], "where": f"D07-06 ({c['sku']} 3PL item code)",
                        "issue": "no rows in D10-07"})
        if c["amazon"] and c["amazon"] not in cols["amz_ordered"]:
            out.append({"code": c["amazon"], "where": f"D07-06 ({c['sku']} Amazon seller SKU)",
                        "issue": "no matching column in D10-06a"})
        if not c["amazon"] and not c["not_on_amazon"]:
            out.append({"code": "(blank)", "where": f"D07-06 ({c['sku']} Amazon seller SKU)",
                        "issue": "blank in crosswalk"})
        if c["shopify"] and c["shopify"] not in cols["shopify"]:
            out.append({"code": c["shopify"], "where": f"D07-06 ({c['sku']} Shopify handle)",
                        "issue": "no matching column in D10-06c"})
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
    """Our SKUs whose sales can't be fully read from D10-06 because a code doesn't match."""
    cols = sales_columns(data_dir)
    bad = {}
    for c in load_crosswalk(data_dir):
        reasons = []
        if not c["not_on_amazon"] and (not c["amazon"] or c["amazon"] not in cols["amz_ordered"]):
            reasons.append(f"Amazon code '{c['amazon'] or 'blank'}' not found in D10-06a")
        if not c["not_on_shopify"] and (not c["shopify"] or c["shopify"] not in cols["shopify"]):
            reasons.append(f"Shopify handle '{c['shopify'] or 'blank'}' not found in D10-06c")
        if reasons:
            bad[c["sku"]] = "; ".join(reasons)
    return bad


# ---------------------------------------------------------------- sales history (D10-06a/b/c)

def daily_units(data_dir=DATA):
    """{our_sku: {date: net units}} = Amazon ordered - Amazon refunded + Shopify net.
    Unmatched columns are left out here and reported by unmatched_codes()."""
    cw = load_crosswalk(data_dir)
    by_amz = {c["amazon"]: c["sku"] for c in cw if c["amazon"]}
    by_shp = {c["shopify"]: c["sku"] for c in cw if c["shopify"]}
    out = {c["sku"]: {} for c in cw}

    def add(key, mapping, sign):
        for r in table(key, data_dir):
            d = iso(r["date"])
            if d > REPORT_DATE.date():
                continue
            if r["code"] in mapping:
                sku = mapping[r["code"]]
                out[sku][d] = out[sku].get(d, 0.0) + sign * num(r["units"])

    add("amz_ordered", by_amz, +1)
    add("amz_refunded", by_amz, -1)
    add("shp_net", by_shp, +1)
    return out


def last_sales_date(data_dir=DATA):
    last = max(iso(r["date"]) for r in table("amz_ordered", data_dir))
    return min(last, REPORT_DATE.date())


# ---------------------------------------------------------------- metric 1: revenue

def last_year_by_month(data_dir=DATA, year=2025):
    """D10-02 'Revenue by Month' for one year: {month: {amazon, shopify, kickstarter, books}}.
    Kickstarter = 'Kickstarter (recognized when rewards ship)'. The 'pledges collected'
    column is cash, not revenue, and is never read."""
    out = {}
    for r in table("fin", data_dir):
        d = iso(r["month"])
        if d.year != year:
            continue
        out[MONTHS[d.month - 1]] = {
            "amazon": num(r["amazon_net_of_refunds"]),
            "shopify": num(r["shopify_net_of_discounts_and_returns"]),
            "kickstarter": num(r["kickstarter_recognized_when_rewards_ship"]),
            "books": r["books"],
        }
    return out


def kickstarter_by_month(data_dir=DATA):
    """D10-01 channel = kickstarter, net_revenue summed by month of recognized_date
    (when rewards shipped), not order_date. {(year, month): $}."""
    out = {}
    for r in table("ledger", data_dir):
        if r["channel"] == "kickstarter":
            d = iso(r["recognized_date"])
            out[(d.year, d.month)] = out.get((d.year, d.month), 0.0) + num(r["net_revenue"])
    return out


def last_year_total(months, include_kickstarter=INCLUDE_KICKSTARTER, data_dir=DATA):
    by_month = last_year_by_month(data_dir)
    return sum(by_month[m]["amazon"] + by_month[m]["shopify"]
               + (by_month[m]["kickstarter"] if include_kickstarter else 0) for m in months)


def ytd_months(yesterday):
    """Full calendar months from Jan up to the month before `yesterday`'s month.
    D10-02 is monthly, so a part month can't be compared."""
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
    return {r["sku"]: num(r["net_revenue_fy25"]) / num(r["units_sold_fy25"])
            for r in table("margins", data_dir)}


def revenue_estimate(start, end, data_dir=DATA):
    """Estimated revenue between two dates (inclusive): D10-06 net units per SKU
    (D10-06: Amazon ordered - Amazon refunded + Shopify net) x FY25 net revenue per unit.
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


def metric_revenue(run_time, data_dir=DATA):
    """Q1 decided 2026-10-09: actual revenue. Year to date = D10-02 Amazon + Shopify for every
    full month from January to the last day of sales data, vs the same months last year.
    Kickstarter is its own line, counted in the month rewards shipped (D10-02 recognized
    column). A month whose Books is not "Closed" is labelled Draft."""
    end = last_sales_date(data_dir)
    last_full = end.month if end.day == days_in_month(end.year, end.month) else end.month - 1
    start = date(end.year, 1, 1)
    ly = last_year_by_month(data_dir, end.year - 1)
    ty = last_year_by_month(data_dir, end.year)
    chart, ly_as, ly_ks, ty_as, ty_ks, drafts = [], 0.0, 0.0, 0.0, 0.0, []
    for mo in range(1, last_full + 1):
        name = MONTHS[mo - 1]
        a, k = ly[name]["amazon"] + ly[name]["shopify"], ly[name]["kickstarter"]
        t = ty[name]["amazon"] + ty[name]["shopify"]
        ly_as, ly_ks, ty_as, ty_ks = ly_as + a, ly_ks + k, ty_as + t, ty_ks + ty[name]["kickstarter"]
        draft = ty[name]["books"] != "Closed"
        if draft:
            drafts.append(name)
        chart.append({"m": f"{name} (draft)" if draft else name, "ly": a, "ly_ks": k, "ty": t})
    period_end = date(end.year, last_full, days_in_month(end.year, last_full))
    last = ly_as + (ly_ks if INCLUDE_KICKSTARTER else 0)
    this = ty_as + (ty_ks if INCLUDE_KICKSTARTER else 0)
    status, change = revenue_status(this, last)
    return {
        "title": "Revenue vs last year", "kind": "", "owner": "Marisa",
        "refresh": "Daily, overnight", "chart": chart, "start": start, "end": period_end,
        "ly_as": ly_as, "ly_ks": ly_ks, "last_year": last, "this_year": this, "ty_ks": ty_ks,
        "drafts": drafts, "change": change, "status": status, "headline": f"{change:+.0%}",
        "as_of": f"Sales to {end:%d %b %Y}",
        "stale": (run_time.date() - end).days > 1,
        "stale_rule": "daily", "stale_ref": end.isoformat(), "stale_lag": 1,  # overnight: data to yesterday
        "source": "QuickBooks revenue by month (D10-02)",
    }


# ---------------------------------------------------------------- metric 2: stock

def snapshot_ts(data_dir=DATA):
    """Latest D10-07 snapshot on or before the report date."""
    return max(t for t in (ts(r["snapshot_ts"]) for r in table("tpl", data_dir)) if t <= REPORT_DATE)


def snapshot_rows(data_dir=DATA):
    snap = snapshot_ts(data_dir)
    return [r for r in table("tpl", data_dir) if ts(r["snapshot_ts"]) == snap]


def on_hand(data_dir=DATA):
    """Sum of qty_available per 3PL item_code at the latest snapshot (D10-07).
    qty_on_hand is not used. Rows earmarked with a HOLD- reference are left out."""
    out = {}
    for r in snapshot_rows(data_dir):
        held = str(r["po_ref"] or "").startswith(EXCLUDE_HOLD_PREFIX)
        out[r["item_code"]] = out.get(r["item_code"], 0.0) + (0.0 if held else num(r["qty_available"]))
    return out


def earmarked(data_dir=DATA):
    """3PL rows left out of on hand: [{item_code, hold_ref, qty}]."""
    return [{"item_code": r["item_code"], "hold_ref": r["po_ref"], "qty": num(r["qty_available"])}
            for r in snapshot_rows(data_dir)
            if str(r["po_ref"] or "").startswith(EXCLUDE_HOLD_PREFIX) and num(r["qty_available"]) > 0]


def open_pos(data_dir=DATA):
    """D10-10 POs signed by Lena and not fully arrived: {po: {sku, open_qty}}.
    Part shipments share a PO number, so arrived qty is summed per PO."""
    pos = {}
    for r in table("pos", data_dir):
        po = r["po_no"]
        p = pos.setdefault(po, {"sku": r["our_sku"], "qty": 0.0, "arrived": 0.0, "signed": None})
        p["qty"] += num(r["qty"])
        p["arrived"] += num(r["qty_arrived"])
        if r["po_signed_lena"]:
            p["signed"] = iso(r["po_signed_lena"])
    return {po: {"sku": p["sku"], "open_qty": p["qty"] - p["arrived"]}
            for po, p in pos.items() if p["signed"] and p["qty"] - p["arrived"] > 0}


def on_the_way(data_dir=DATA):
    """{our_sku: units} from D10-07 qty_expected, cross-checked with D10-10 open POs.
    A PO in both is counted once (3PL figure). Returns (totals, detail lines)."""
    cw = load_crosswalk(data_dir)
    tpl_to_sku = {c["tpl"]: c["sku"] for c in cw if c["tpl"]}
    totals, detail, seen_pos = {}, [], set()
    for r in snapshot_rows(data_dir):
        q = num(r["qty_expected"])
        if q <= 0:
            continue
        sku = tpl_to_sku.get(r["item_code"])
        po = r["po_ref"]
        totals[sku] = totals.get(sku, 0.0) + q
        seen_pos.add(po)
        detail.append({"sku": sku, "po": po, "qty": q, "source": "D10-07 qty_expected"})
    pos = open_pos(data_dir)
    for po, p in pos.items():
        if po in seen_pos:
            line = next(d for d in detail if d["po"] == po)
            line["source"] += " + D10-10 (counted once)"
            if line["qty"] != p["open_qty"]:
                line["source"] += f" - MISMATCH: D10-10 says {p['open_qty']:.0f}"
        else:
            totals[p["sku"]] = totals.get(p["sku"], 0.0) + p["open_qty"]
            detail.append({"sku": p["sku"], "po": po, "qty": p["open_qty"],
                           "source": "D10-10 only (not on 3PL ASN yet)"})
    return totals, detail


def lead_times(data_dir=DATA):
    """Lead time per our SKU from D04-01 'Supplier terms' (the only D04-01 tab loaded).
    Supplier per SKU: Castellan where the D07-06 notes say so; Yuhang where the SKU has a
    PO in D10-10 (Yuhang PO history); otherwise UNSURE."""
    terms = {r["supplier"].split()[0]: r["lead_time"] for r in table("stock_terms", data_dir)}
    yuhang = {r["our_sku"] for r in table("pos", data_dir)}
    out = {}
    for c in load_crosswalk(data_dir):
        sup = ("Castellan" if "castellan" in c["notes"].lower()
               else "Yuhang" if c["sku"] in yuhang else None)
        out[c["sku"]] = (terms[sup].split(" (")[0] if sup in terms
                         else "UNSURE: supplier not in terms")
    return out


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
                f"{start:%d %b} to {end:%d %b %Y} (D10-06). Reorder point = daily sales x {REORDER_DAYS}.",
    }


# ---------------------------------------------------------------- metric 3: ads

def contribution_per_unit(data_dir=DATA):
    return {r["sku"]: {"product": r["product"],
                       "per_unit": num(r["contribution_fy25"]) / num(r["units_sold_fy25"]),
                       "contribution": num(r["contribution_fy25"]), "units": num(r["units_sold_fy25"])}
            for r in table("margins", data_dir)}


def monthly_spend(data_dir=DATA):
    """{(year, month): spend} from D10-08."""
    return {(iso(r["month"]).year, iso(r["month"]).month): num(r["spend"])
            for r in table("ads_monthly", data_dir)}


def budget_share(data_dir=DATA):
    return {r["sku"]: num(r["share_of_budget"]) for r in table("ads_share", data_dir)}


def ads_month(data_dir=DATA):
    """Latest full calendar month present in both D10-06 (units) and D10-08 (spend)."""
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
                    note="No full month in both D10-06 and D10-08.")
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
