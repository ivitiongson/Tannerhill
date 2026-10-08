"""Break the dashboard on purpose, safely, and report whether each break fails safely.

Each case gets its own folder caseN/. Files a break changes are real copies; every
other data file is a read-only symlink to the real data, so the real data and the
real build are never written. The build used is the latest dashboard script,
reused as-is (its functions already take a data folder).

Run:  python3 output/dashboard/break_tests/run_breaks.py
Prints one line per break:  N · break · layer · what the page did · PASS/FAIL
PASS = fails safely (gray "No data", STALE, or a clear message naming the problem).
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DASH = os.path.join(REPO, "output", "test_dashboard_v3")
BUILD = os.path.join(DASH, "test_build_dashboard_6.py")   # latest dashboard build
PAGE = os.path.join(DASH, "test_index_6.html")            # latest built page
REAL_DATA = os.path.join(DASH, "data")
PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright/index.mjs"

F = {
    "tpl": "D07-01_3PL_Daily_Export.xlsx",
    "sales": "D07-07_Sales_History.xlsx",
    "margins": "D04-04_Product_Margins_FY2025.xlsx",
}


# ---------------------------------------------------------------- worker (runs one build)

def load_build(module_path, data_dir):
    """Import a build script and point every data_dir default at data_dir."""
    spec = importlib.util.spec_from_file_location("dash_build", module_path)
    bd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bd)
    real = bd.DATA
    for obj in vars(bd).values():
        if callable(obj) and getattr(obj, "__defaults__", None):
            obj.__defaults__ = tuple(data_dir if d == real else d for d in obj.__defaults__)
    bd.DATA = data_dir
    return bd


def worker(module_path, data_dir, out_dir):
    """Run the build's own entry point into out_dir; return what happened as JSON."""
    res = {"ok": False}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            bd = load_build(module_path, data_dir)
            bd.OUT = os.path.join(out_dir, "index.html")
            sys.argv = ["build", "--overwrite"]
            bd.main()
            rt = bd.REPORT_DATE
            rev, stock, ads = bd.metric_revenue(rt), bd.metric_stock(rt), bd.metric_ads(rt)
            cash = bd.metric_cash(rt)
            with open(os.path.join(out_dir, "checks.md"), "w") as f:
                f.write(bd.checks_md())
        res.update(ok=True,
                   status={"rev": rev["status"], "stock": stock["status"], "ads": ads["status"], "cash": cash["status"]},
                   rev_this=rev.get("this_year"), rev_months=[r["ty"] for r in rev["chart"]],
                   stock_head=stock["headline"], ads_head=ads["headline"],
                   stock_rows=[{k: r[k] for k in ("sku", "on_hand", "daily", "reorder_point", "status")}
                               for r in stock["table"]],
                   ads_rows=[{k: r[k] for k in ("sku", "units", "contribution", "status")} for r in ads.get("table", [])],
                   owners=[c["owner"] for c in (rev, stock, ads, cash)])
    except BaseException as e:  # noqa: BLE001 - we want to report any crash
        res["error"] = f"{type(e).__name__}: {e}"
    res["stdout"] = buf.getvalue()
    return res


def run_build(case, module_path=BUILD, data_dir=None):
    out = os.path.join(HERE, case)
    data_dir = data_dir if data_dir is not None else os.path.join(out, "data")
    p = subprocess.run([sys.executable, __file__, "--worker", module_path, data_dir, out],
                       capture_output=True, text=True)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": (p.stderr or p.stdout).strip().splitlines()[-1:], "stdout": p.stdout}


# ---------------------------------------------------------------- case setup helpers

def new_case(name, copy=(), link_rest=True):
    """caseN/data/: listed files copied (to be broken), everything else symlinked read-only."""
    d = os.path.join(HERE, name)
    if os.path.exists(d):
        raise SystemExit(f"{d} exists. Not overwriting (CLAUDE.md rule 3). Delete break_tests/case* to re-run.")
    data = os.path.join(d, "data")
    os.makedirs(data)
    for fn in sorted(os.listdir(REAL_DATA)):
        src = os.path.join(REAL_DATA, fn)
        if fn in copy:
            shutil.copy2(src, os.path.join(data, fn))
        elif link_rest:
            os.symlink(src, os.path.join(data, fn))
    return d, data


def wb(path):
    import openpyxl
    return openpyxl.load_workbook(path)


def sha_tree(path):
    h = hashlib.sha256()
    for fn in sorted(os.listdir(path)):
        with open(os.path.join(path, fn), "rb") as f:
            h.update(fn.encode() + f.read())
    return h.hexdigest()


def browser(page_path, js_check, block_net=False):
    """Open a page in headless Chromium (Node Playwright) at real date 8 Oct 2026."""
    if not os.path.exists(PLAYWRIGHT):
        return {"skip": "no browser"}
    script = f"""
import {{ chromium }} from '{PLAYWRIGHT}';
const b = await chromium.launch(); const p = await b.newPage();
await p.clock.setFixedTime(new Date('2026-10-08T10:00:00'));
const errs=[]; p.on('pageerror',e=>errs.push(e.message));
{"await p.route(u=>!u.href.startsWith('file:'),r=>r.abort());" if block_net else ""}
await p.goto('file://{page_path}', {{waitUntil:'load'}});
const r = await p.evaluate(() => {{ {js_check} }});
r.errors = errs; console.log(JSON.stringify(r)); await b.close();
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(script)
    try:
        p = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=60)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"skip": f"browser failed: {e}"}
    finally:
        os.unlink(f.name)


def crashed(r):
    return "" if r.get("ok") else f"build crashed ({r.get('error')})"


# ---------------------------------------------------------------- the breaks

def main():
    real_before = sha_tree(REAL_DATA)
    if os.path.exists(os.path.join(HERE, "case0_baseline")):
        raise SystemExit("case0_baseline exists. Delete break_tests/case* to re-run.")
    os.makedirs(os.path.join(HERE, "case0_baseline"))
    base = run_build("case0_baseline", data_dir=REAL_DATA)   # real data, for comparison
    if not base.get("ok"):
        raise SystemExit(f"Baseline build failed: {base.get('error')}")
    lines = []

    def report(n, name, layer, did, ok):
        lines.append((n, name, layer, did, "PASS" if ok else "FAIL"))

    # 1. Source: delete D07-01
    d, data = new_case("case1")
    os.unlink(os.path.join(data, F["tpl"]))
    r = run_build("case1")
    ok = r.get("ok") and r["status"]["stock"] == "gray" and r["status"]["rev"] != "gray"
    report(1, "Delete 3PL stock export", "Source", crashed(r) or f"stock card {r['status']['stock']}", ok)

    # 2. Source: blank qty_available
    d, data = new_case("case2", copy=[F["tpl"]])
    w = wb(os.path.join(data, F["tpl"]))
    ws = w.active
    col = [c.value for c in ws[1]].index("qty_available") + 1
    for row in range(2, ws.max_row + 1):
        ws.cell(row, col).value = None
    w.save(os.path.join(data, F["tpl"]))
    r = run_build("case2")
    if r.get("ok"):
        zeros = [x["sku"] for x in r["stock_rows"] if x["on_hand"] == 0 and x["status"] != "gray"]
        ok = r["status"]["stock"] == "gray" and not zeros
        did = f"stock card {r['status']['stock']}; {len(zeros)} products shown with 0 on hand"
    else:
        ok, did = False, crashed(r)
    report(2, "Blank qty_available", "Source", did, ok)

    # 3. Source: new product code in sales, not in crosswalk
    d, data = new_case("case3", copy=[F["sales"]])
    w = wb(os.path.join(data, F["sales"]))
    ws = w["Amazon units ordered"]
    newc = ws.max_column + 1
    ws.cell(1, newc).value = "TRAILHEAD-GRILL-MINI"
    for row in range(2, ws.max_row + 1):
        ws.cell(row, newc).value = 3
    w.save(os.path.join(data, F["sales"]))
    r = run_build("case3")
    if r.get("ok"):
        listed = "TRAILHEAD-GRILL-MINI" in open(os.path.join(d, "checks.md")).read()
        same = (r["rev_this"], r["stock_head"], r["ads_head"]) == (base["rev_this"], base["stock_head"], base["ads_head"])
        ok = listed and same
        did = f"{'listed' if listed else 'NOT listed'} in checks.md; other numbers {'unchanged' if same else 'CHANGED'}"
    else:
        ok, did = False, crashed(r)
    report(3, "New sales code not in crosswalk", "Source", did, ok)

    # 4. Source: renamed file
    d, data = new_case("case4")
    os.unlink(os.path.join(data, F["sales"]))
    os.symlink(os.path.join(REAL_DATA, F["sales"]), os.path.join(data, "D07-07 Sales History (1).xlsx"))
    r = run_build("case4")
    ok = r.get("ok") and "D07-07" in r["stdout"] and "gray" in r["status"].values()
    report(4, "Renamed sales file", "Source", crashed(r) or "built; see stdout", ok)

    # 5. Logic: duplicate one week of sales rows
    d, data = new_case("case5", copy=[F["sales"]])
    w = wb(os.path.join(data, F["sales"]))
    for tab in ("Amazon units ordered", "Amazon units refunded", "Shopify net quantity"):
        ws = w[tab]
        week = [[c.value for c in row] for row in ws.iter_rows(min_row=2)
                if str(row[0].value) in ("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05",
                                         "2026-03-06", "2026-03-07", "2026-03-08",
                                         "03/02/2026", "03/03/2026", "03/04/2026", "03/05/2026",
                                         "03/06/2026", "03/07/2026", "03/08/2026")]
        for vals in week:
            ws.append(vals)
    w.save(os.path.join(data, F["sales"]))
    r = run_build("case5")
    if r.get("ok"):
        extra = r["rev_this"] - base["rev_this"]
        flagged = "duplicate" in (r["stdout"] + open(os.path.join(d, "index.html")).read()).lower()
        ok = abs(extra) < 1 and flagged
        did = f"revenue {'+' if extra >= 0 else ''}${extra:,.0f} vs real; {'flagged' if flagged else 'not flagged'}"
    else:
        ok, did = False, crashed(r)
    report(5, "Duplicate week of sales", "Logic", did, ok)

    # 6. Logic: refunds bigger than orders (Windshield, 10 Mar 2026)
    d, data = new_case("case6", copy=[F["sales"]])
    w = wb(os.path.join(data, F["sales"]))
    ordered, refunded = w["Amazon units ordered"], w["Amazon units refunded"]
    col = [c.value for c in ordered[1]].index("ACC-WINDSHIELD-SET") + 1
    for row in range(2, ordered.max_row + 1):
        if str(ordered.cell(row, 1).value) == "2026-03-10":
            refunded.cell(row, col).value = (ordered.cell(row, col).value or 0) + 500
    w.save(os.path.join(data, F["sales"]))
    r = run_build("case6")
    if r.get("ok"):
        neg = [x["sku"] for x in r["stock_rows"] if x["daily"] < 0] + \
              [x["sku"] for x in r["ads_rows"] if x["units"] < 0] + \
              (["revenue"] if any(v < 0 for v in r["rev_months"]) else [])
        flagged = "refund" in r["stdout"].lower()
        ok = not neg and flagged
        did = (f"negative values: {', '.join(sorted(set(neg)))}" if neg else "no negatives") + \
              f"; {'flagged' if flagged else 'not flagged'}"
    else:
        ok, did = False, crashed(r)
    report(6, "Refunds > orders one day", "Logic", did, ok)

    # 7. Logic: units sold FY25 = 0 for one product (Windshield)
    d, data = new_case("case7", copy=[F["margins"]])
    w = wb(os.path.join(data, F["margins"]))
    ws = w.active
    hdr = next(i for i in range(1, 10) if ws.cell(i, 1).value == "SKU")
    col = [c.value for c in ws[hdr]].index("Units sold FY25") + 1
    for row in range(hdr + 1, ws.max_row + 1):
        if ws.cell(row, 1).value == "TH-ACC-WS":
            ws.cell(row, col).value = 0
    w.save(os.path.join(data, F["margins"]))
    r = run_build("case7")
    if r.get("ok"):
        ws_row = next((x for x in r["ads_rows"] if x["sku"] == "TH-ACC-WS"), None)
        ok = ws_row is not None and ws_row["status"] == "gray"
        did = f"Windshield ads row {ws_row['status'] if ws_row else 'missing'}"
    else:
        ok, did = False, crashed(r)
    report(7, "Units sold FY25 = 0", "Logic", did, ok)

    # 8. Trigger: DEMO_MODE = false
    d = os.path.join(HERE, "case8")
    os.makedirs(d)
    html = open(PAGE).read().replace("const DEMO_MODE = true;", "const DEMO_MODE = false;")
    open(os.path.join(d, "index.html"), "w").write(html)
    b = browser(os.path.join(d, "index.html"),
                "const v=id=>[...document.querySelectorAll('#'+id+' .stale')].some(e=>!e.hidden);"
                "return {rev:v('rev'),stock:v('stock'),ads:v('ads')};")
    if "skip" in b:
        report(8, "DEMO_MODE = false", "Trigger", b["skip"], False)
    else:
        ok = b["rev"] and b["stock"] and b["ads"] and not b["errors"]
        report(8, "DEMO_MODE = false", "Trigger",
               ("STALE on " + ", ".join(k for k in ("rev", "stock", "ads") if b[k])) if ok else
               f"STALE shown: {b}", ok)

    # 9. Trigger: DEMO_MODE = true left on -> build should warn
    has_demo = "const DEMO_MODE = true;" in open(PAGE).read()
    warned = "demo mode is on" in base["stdout"].lower()
    report(9, "DEMO_MODE left on", "Trigger",
           f"page has DEMO_MODE = true; build {'warned' if warned else 'printed no warning'}", has_demo and warned)

    # 10. Home: whole data folder missing
    d = os.path.join(HERE, "case10")
    os.makedirs(d)
    r = run_build("case10", data_dir=os.path.join(d, "data"))
    ok = r.get("ok") and all(s == "gray" for s in r["status"].values())
    report(10, "data/ folder missing", "Home", crashed(r) or f"cards {r['status']}", ok)

    # 11. View: no internet (fonts blocked)
    d = os.path.join(HERE, "case11")
    os.makedirs(d)
    shutil.copy2(PAGE, os.path.join(d, "index.html"))
    b = browser(os.path.join(d, "index.html"),
                "const h=document.querySelector('h1').getBoundingClientRect();"
                "return {font:getComputedStyle(document.body).fontFamily,h1:h.height,"
                "text:document.body.innerText.length,tiles:document.querySelectorAll('.tile').length,"
                "loaded:[...document.fonts].filter(f=>f.status==='loaded').length};", block_net=True)
    if "skip" in b:
        report(11, "No internet (fonts fail)", "View", b["skip"], False)
    else:
        ok = b["h1"] > 0 and b["text"] > 300 and b["tiles"] == 4 and not b["errors"]
        report(11, "No internet (fonts fail)", "View",
               f"readable with fallback fonts ({b['loaded']} web fonts loaded, {b['tiles']} tiles shown)", ok)

    # 12. Owner: remove one metric's owner (stock) in a copy of the build
    d = os.path.join(HERE, "case12")
    os.makedirs(d)
    src = open(BUILD).read()
    needle = '"title": "Stock running low", "kind": "", "owner": "Marco",'
    assert needle in src
    open(os.path.join(d, "build_dashboard.py"), "w").write(src.replace(needle, needle.replace('"Marco"', '""')))
    r = run_build("case12", module_path=os.path.join(d, "build_dashboard.py"), data_dir=REAL_DATA)
    refused = (not r.get("ok")) and "Every metric needs one named owner" in str(r.get("error"))
    did = "build refused" if refused else (crashed(r) or f"built with owners {r['owners']}")
    report(12, "Metric owner removed", "Owner", did, refused)

    # ---- report
    print(f"{'#':>2} · {'Break':<32} · {'Layer':<7} · {'What the page did':<70} · Result")
    for n, name, layer, did, res in lines:
        print(f"{n:>2} · {name:<32} · {layer:<7} · {did[:70]:<70} · {res}")
    print(f"\n{sum(l[4] == 'PASS' for l in lines)}/{len(lines)} PASS")
    print("Real data unchanged:", sha_tree(REAL_DATA) == real_before)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        print(json.dumps(worker(*sys.argv[2:5]), default=str))
    else:
        main()
