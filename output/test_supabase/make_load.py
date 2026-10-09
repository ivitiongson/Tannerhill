"""Write one clean CSV per Supabase table into load/, plus load/ROW_COUNTS.md.

Follows the "READ FILE" column of docs: Tannerhill Dashboard Data Mapping D10.xlsx.
Source files are read-only. Every load file starts with row_no (source order), used
as the primary key so the page can page through rows in a fixed order.

Run:  python3 output/test_supabase/make_load.py
"""

import csv
import os
import re
from datetime import datetime

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OLD = os.path.join(ROOT, "dashboard-data")
LOAD = os.path.join(HERE, "load")

MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def src(name):
    return os.path.join(ROOT, name)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def plain(v):
    """Number as plain text: no $, commas or %. Blank stays blank."""
    v = (v or "").strip().replace("$", "").replace(",", "")
    return v


def mon_yyyy(s):
    """'Jan 2025' -> '2025-01-01'."""
    m, y = s.split()
    return f"{int(y):04d}-{MON[m]:02d}-01"


def xl_date(v):
    return v.strftime("%Y-%m-%d") if isinstance(v, datetime) else ("" if v is None else str(v))


def xl_val(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(round(v, 10))
    return str(v)


def snake(h):
    h = h.replace("%", " pct").replace("#", " no")
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


# ---------------------------------------------------------------- one function per file

def d10_01():
    rs = read_csv(src("D10-01 Order Ledger 2025-2026.csv"))
    return rs[0], rs[1:]


def d10_02():
    rs = read_csv(src("D10-02 Revenue by Month 2025-2026.csv"))
    head = rs[3]  # header is line 4
    out = [r for r in rs[4:] if r and re.fullmatch(r"[A-Z][a-z]{2} \d{4}", r[0])]
    out = [[mon_yyyy(r[0])] + [plain(v) for v in r[1:6]] + [r[6]] for r in out]
    header = ["month", "amazon_net_of_refunds", "shopify_net_of_discounts_and_returns",
              "kickstarter_recognized_when_rewards_ship", "total_revenue",
              "kickstarter_pledges_collected_net_of_fees_cash_not_revenue", "books"]
    assert len(head) == len(header)
    return header, out


def d10_03():
    rs = read_csv(src("D10-03 Amazon Business Report Jan 2025-Mar 2026.csv"))
    header = ["month", "child_asin", "sku", "title", "units_ordered", "ordered_product_sales"]
    return header, [[mon_yyyy(r[0]), r[1], r[2], r[3], plain(r[4]), plain(r[5])] for r in rs[1:] if r]


def d10_04():
    rs = read_csv(src("D10-04 Amazon Refunds by Order Date Jan 2025-Mar 2026.csv"))
    header = ["order_month", "sku", "asin", "title", "units_refunded", "refund_amount"]
    return header, [[mon_yyyy(r[0]), r[1], r[2], r[3], plain(r[4]), plain(r[5])] for r in rs[1:] if r]


def d10_05():
    rs = read_csv(src("D10-05 Shopify Sales by Product Weekly Jan 2025-Mar 2026.csv"))
    header = [snake(h) for h in rs[0]]
    return header, [[r[0], r[1], r[2]] + [plain(v) for v in r[3:]] for r in rs[1:] if r]


def unpivot(name, parse_date):
    """Wide (one column per code) -> long (date, code, units)."""
    rs = read_csv(src(name))
    codes = rs[0][1:]
    out = []
    for r in rs[1:]:
        if not r:
            continue
        d = parse_date(r[0])
        for code, v in zip(codes, r[1:]):
            out.append([d, code, plain(v)])
    return ["date", "code", "units"], out, len([r for r in rs[1:] if r])


def mdy(s):
    return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")


def d10_07():
    rs = read_csv(src("D10-07 3PL Daily Stock Jan-Mar 2026.csv"))
    return rs[0], [r for r in rs[1:] if r]


def d10_08():
    rs = read_csv(src("D10-08 BW Monthly Report Jan 2025-Mar 2026.csv"))
    header = [snake(h) for h in rs[3]]  # header is line 4
    out = []
    for r in rs[4:]:
        if not r or not re.fullmatch(r"[A-Z][a-z]{2} \d{4}", r[0]):
            continue
        ctr = float(plain(r[4]).replace("%", "")) / 100
        out.append([mon_yyyy(r[0]), plain(r[1]), plain(r[2]), plain(r[3]),
                    f"{ctr:.4f}", plain(r[5]), plain(r[6])])
    return header, out


def d10_09():
    rs = read_csv(src("D10-09 BW Agency Invoices 2026.csv"))
    header = ["invoice_no", "month", "date_issued", "description", "amount",
              "deliverables_listed", "paid"]
    out = [[r[0], r[1], datetime.strptime(r[2], "%b %d, %Y").strftime("%Y-%m-%d"),
            r[3], plain(r[4]), r[5], r[6]] for r in rs[1:] if r]
    return header, out


def d10_10():
    ws = openpyxl.load_workbook(src("D10-10 Yuhang PO History to 31 Mar 2026.xlsx"), data_only=True).worksheets[0]
    rs = [r for r in ws.iter_rows(values_only=True)]
    hi = next(i for i, r in enumerate(rs) if r[0] == "PO #")
    header = ["po_no", "our_sku", "product", "qty", "unit_price_ddp_to_3pl", "po_value",
              "marco_asked_lena", "po_signed_lena", "deposit_paid", "left_factory",
              "arrived_3pl", "qty_arrived", "balance_paid", "notes"]
    assert len([h for h in rs[hi] if h]) == len(header)
    # keep every row, including the second (blank Qty) row of the split PO-2506-029
    out = [[xl_val(v) for v in r[:len(header)]] for r in rs[hi + 1:] if r[0]]
    return header, out


def xl_table(path, tab, first_cell, header, ncols):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[tab] if tab else wb.worksheets[0]
    rs = [r for r in ws.iter_rows(values_only=True)]
    hi = next(i for i, r in enumerate(rs) if r[0] == first_cell)
    out = []
    for r in rs[hi + 1:]:
        if r[0] is None or str(r[0]).strip() == "Total":
            break
        out.append([xl_val(v) for v in r[:ncols]])
    return header, out


def d07_06():
    return xl_table(os.path.join(OLD, "D07-06_SKU_Crosswalk.xlsx"), None, "Our SKU",
                    ["our_sku", "product", "3pl_item_code", "shopify_handle",
                     "amazon_seller_sku", "asin", "notes"], 7)


def d04_01():
    return xl_table(os.path.join(OLD, "D04-01_Stock_Position_and_Supplier_Terms.xlsx"),
                    "Supplier terms", "Supplier",
                    ["supplier", "country", "supplies", "lead_time", "payment_terms",
                     "minimum_order", "notes"], 7)


def d04_03():
    return xl_table(os.path.join(OLD, "D04-03_BidWorks_Spend_by_Product_FY2025.xlsx"), None, "SKU",
                    ["sku", "product", "annual_ad_spend", "share_of_budget"], 4)


def d04_04():
    return xl_table(os.path.join(OLD, "D04-04_Product_Margins_FY2025.xlsx"), None, "SKU",
                    ["sku", "product", "retail_price", "landed_unit_cost", "product_margin_pct",
                     "units_sold_fy25", "net_revenue_fy25", "contribution_fy25"], 8)


# table name, source file, expected "Data rows" (File Index), loader
TABLES = [
    ("d10_01_order_ledger", "D10-01 Order Ledger 2025-2026.csv", 25152, d10_01),
    ("d10_02_revenue_by_month", "D10-02 Revenue by Month 2025-2026.csv", 15, d10_02),
    ("d10_03_amazon_business_report", "D10-03 Amazon Business Report Jan 2025-Mar 2026.csv", 180, d10_03),
    ("d10_04_amazon_refunds_by_order_date", "D10-04 Amazon Refunds by Order Date Jan 2025-Mar 2026.csv", 180, d10_04),
    ("d10_05_shopify_sales_by_product_weekly", "D10-05 Shopify Sales by Product Weekly Jan 2025-Mar 2026.csv", 767, d10_05),
    ("d10_06a_amazon_units_ordered", "D10-06a Sales History - Amazon units ordered.csv", 455,
     lambda: unpivot("D10-06a Sales History - Amazon units ordered.csv", lambda s: s)),
    ("d10_06b_amazon_units_refunded", "D10-06b Sales History - Amazon units refunded.csv", 455,
     lambda: unpivot("D10-06b Sales History - Amazon units refunded.csv", lambda s: s)),
    ("d10_06c_shopify_net_quantity", "D10-06c Sales History - Shopify net quantity.csv", 455,
     lambda: unpivot("D10-06c Sales History - Shopify net quantity.csv", mdy)),
    ("d10_07_3pl_daily_stock", "D10-07 3PL Daily Stock Jan-Mar 2026.csv", 1092, d10_07),
    ("d10_08_bw_monthly_report", "D10-08 BW Monthly Report Jan 2025-Mar 2026.csv", 15, d10_08),
    ("d10_09_bw_agency_invoices", "D10-09 BW Agency Invoices 2026.csv", 3, d10_09),
    ("d10_10_yuhang_po_history", "D10-10 Yuhang PO History to 31 Mar 2026.xlsx", 38, d10_10),
    ("d07_06_sku_crosswalk", "dashboard-data/D07-06_SKU_Crosswalk.xlsx", 13, d07_06),
    ("d04_01_supplier_terms", "dashboard-data/D04-01_Stock_Position_and_Supplier_Terms.xlsx (tab Supplier terms)", 3, d04_01),
    ("d04_03_bidworks_spend_by_product", "dashboard-data/D04-03_BidWorks_Spend_by_Product_FY2025.xlsx", 13, d04_03),
    ("d04_04_product_margins", "dashboard-data/D04-04_Product_Margins_FY2025.xlsx", 13, d04_04),
]


def main():
    os.makedirs(LOAD, exist_ok=True)
    lines = ["# Row counts", "",
             "Data rows = source rows after removing title lines, notes and total rows "
             "(the File Index \"Data rows\" column). D10-06a/b/c are unpivoted, so their load "
             "files hold one row per day per code.", "",
             "| Table | Load file | Source file | Data rows (source) | File Index | Match | Rows in load file |",
             "|---|---|---|---:|---:|---|---:|"]
    for name, source, expected, fn in TABLES:
        res = fn()
        header, out = res[0], res[1]
        source_rows = res[2] if len(res) == 3 else len(out)
        path = os.path.join(LOAD, name + ".csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["row_no"] + header)
            for i, r in enumerate(out, 1):
                assert len(r) == len(header), (name, r)
                w.writerow([i] + r)
        ok = "PASS" if source_rows == expected else "FAIL"
        lines.append(f"| `{name}` | `load/{name}.csv` | {source} | {source_rows:,} | {expected:,} | {ok} | {len(out):,} |")
        print(f"{ok}  {name}: {source_rows} source rows (expected {expected}), {len(out)} load rows")
    with open(os.path.join(LOAD, "ROW_COUNTS.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
