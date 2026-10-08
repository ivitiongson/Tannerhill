"""DEMO ONLY: shows how the dashboard looks once revenue and cash have a source.

Revenue (this year) and cash are FAKE numbers made up for the demo. Stock and ads
still come from the sandbox spreadsheets in data/. The real page is index.html;
this writes test_demo_index.html and never touches index.html.

Run:  python3 output/test_dashboard_v3/test_build_demo.py
"""

import os
from datetime import datetime

import build_dashboard as bd

OUT = os.path.join(bd.HERE, "test_demo_index.html")
RUN_TIME = datetime(2026, 10, 8, 6, 30)

# FAKE: this year's Amazon + Shopify by month = last year x these made-up growth factors
FAKE_GROWTH = {"Jan": 1.22, "Feb": 1.18, "Mar": 1.31, "Apr": 1.27, "May": 1.15,
               "Jun": 1.24, "Jul": 1.19, "Aug": 1.28, "Sep": 1.33}
FAKE_KS_THIS_YEAR = {"May": 120000, "Jun": 85000}   # FAKE Kickstarter pledges collected

# FAKE cash: one bank balance and the payments due in the next 8 weeks
FAKE_BALANCE = 186000
FAKE_PAYMENTS = [("PO deposits and balances (D07-08 style)", 98000),
                 ("Agency fees (BidWorks + social)", 44800),
                 ("3PL fixed fee + pick and pack", 15000)]

real_metric_revenue = bd.metric_revenue


def demo_revenue(run_time, data_dir=bd.DATA, feed_dir=bd.FEED):
    card = real_metric_revenue(run_time, data_dir, feed_dir)
    for row in card["chart"]:
        row["ty"] = round(row["ly"] * FAKE_GROWTH.get(row["m"], 1.0))
    ty_as = sum(r["ty"] for r in card["chart"])
    ty_ks = sum(FAKE_KS_THIS_YEAR.get(m, 0) for m in card["months"])
    this = ty_as + ty_ks
    status, change = bd.revenue_status(this, card["last_year"])
    card.update(status=status, headline=f"{change:+.0%}", this_year=this, ty_ks=ty_ks,
                change=change, as_of=run_time.strftime("%Y-%m-%d %H:%M"), stale=False,
                source="DEMO: fake feed · last year D02-02 Revenue by Month")
    return card


def demo_cash(run_time, data_dir=bd.DATA):
    due = sum(v for _, v in FAKE_PAYMENTS)
    weeks = FAKE_BALANCE / (due / 8)
    status = "green" if weeks >= 8 else "amber" if weeks >= 4 else "red"
    return {"title": "Cash in the bank", "kind": "LEADING", "owner": "Marisa",
            "refresh": "Weekly", "status": status, "headline": f"{weeks:.1f} weeks",
            "as_of": run_time.strftime("%Y-%m-%d %H:%M"), "weeks": weeks, "due": due,
            "note": "DEMO: fake balance and payments."}


def demo_cash_panel(cash):
    rows = "".join(f'<tr><td>{bd.esc(k)}</td><td class="n">{bd.money(v)}</td></tr>' for k, v in FAKE_PAYMENTS)
    fill = min(cash["weeks"], 12) / 12 * 100
    col = {"green": "var(--good)", "amber": "var(--warn)", "red": "var(--crit)"}[cash["status"]]
    return f"""
<section class="panel" data-s="{bd.S_CLASS[cash['status']]}" id="cash">
  {bd.panel_head(cash, bd.pill(cash['status']))}
  <div class="two">
    <div style="display:grid;gap:10px">
      <div><div class="lbl">Bank balance</div><div class="big">{bd.money(FAKE_BALANCE)}</div></div>
      <div><div class="lbl">Covers</div><div class="big">{cash['weeks']:.1f} weeks</div>
        <div class="note">of payments due in the next 8 weeks</div></div>
      <div class="bar" data-t="Covers {cash['weeks']:.1f} weeks"><i style="width:{fill:.1f}%;background:{col}"></i>
        <u style="left:{4 / 12 * 100:.1f}%"></u><u style="left:{8 / 12 * 100:.1f}%"></u></div>
      <div class="legend"><span>Markers at 4 and 8 weeks</span></div>
    </div>
    <table class="mini">
      <tr><th>Due in the next 8 weeks</th><th class="n"></th></tr>{rows}
      <tr><td><b>Total</b></td><td class="n"><b>{bd.money(cash['due'])}</b></td></tr>
    </table>
  </div>
  <p class="bands">Bank balance vs payments due in the next 8 weeks (PO deposits and balances, agency fees, 3PL).
  Green covers 8+ weeks · Amber 4–8 weeks · Red under 4 weeks</p>
  {bd.meta(cash, 'Last run', cash['as_of'], 'DEMO: fake bank balance')}
</section>"""


bd.metric_revenue = demo_revenue
bd.metric_cash = demo_cash
bd.cash_panel = demo_cash_panel

page = bd.build_html(RUN_TIME)
banner = ('<div class="sample" style="max-width:none;border-color:var(--crit);color:var(--crit-ink);'
          'font-size:13px;padding:10px 14px"><b>DEMO WITH FAKE DATA.</b> Revenue this year and cash are made up '
          'to show how the page looks once they have a source. Stock and ads use the sandbox files. '
          'Do not use these numbers.</div>')
cash = demo_cash(RUN_TIME)
old_tile = bd.tile("Cash cover", "–", "No source yet", "gray", cash)
new_tile = bd.tile("Cash cover", f"{cash['weeks']:.1f} weeks", "DEMO · fake balance", cash["status"], cash)
assert old_tile in page
page = (page.replace("<title>Are We Okay</title>", "<title>Are We Okay Demo</title>")
            .replace('<div class="wrap">', '<div class="wrap">' + banner, 1)
            .replace(old_tile, new_tile))
with open(OUT, "w") as f:
    f.write(page)
print(f"Wrote {OUT}")
