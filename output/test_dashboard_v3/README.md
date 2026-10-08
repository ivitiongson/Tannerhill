# "Are we okay?" dashboard (v3)

One page for Lena: summary strip, 4 metric panels, "Not answered yet". Sandbox data only.
Layout follows `layout-reference.html` (style only; every number and band comes from the prompt).

Built in `output/test_dashboard_v3/` because v1 (`output/dashboard/`) and v2
(`output/test_dashboard_v3/`) already exist and CLAUDE.md rule 3 says existing files are never overwritten.

## Confirmed in chat, 2026-10-08

- `TRAILHEAD-GRILL-PRO-V2` (Amazon, D07-07) = TH-GRL-02 Trailhead Grill Pro
- `windshield-panel-set` (Shopify, D07-07) = TH-ACC-WS Windshield Panel Set
- Ads panel covers Dec 2025 (latest month in both D07-07 and D04-02)
- 3PL rows earmarked with a `HOLD-` reference are taken out of on hand

The two mappings live in `CONFIRMED_MAPPINGS` in `build_dashboard.py`. D07-06 itself is not edited.
They still show on the page, marked "Mapped", so nothing is dropped silently.

## Files

| File | What it is |
|---|---|
| `data/` | Copies of the 13 spreadsheets (originals stay in `dashboard-data/`) |
| `build_dashboard.py` | All the logic. Reads `data/`, writes `index.html` |
| `tests/test_metrics.py` | Checks 1–8, each prints PASS/FAIL with expected vs actual |
| `index.html` | The page (static, inline CSS, no login) |
| `feed/` (not created yet) | Drop live revenue exports here to light up the revenue panel |

## Run

```
pip install openpyxl
python3 output/test_dashboard_v3/tests/test_metrics.py
python3 output/test_dashboard_v3/build_dashboard.py            # run time = now
python3 output/test_dashboard_v3/build_dashboard.py --as-of "2026-10-08 09:00"
```

## Live revenue feed

Put three files in `feed/`, same layout as the Q2 samples:

- `amazon_business_report.xlsx` (like D09-01)
- `amazon_payments_summary.xlsx` (like D09-02, with the "Refunds by order date" tab)
- `shopify_sales_by_product.xlsx` (like D09-03)

They should cover 1 Jan to the end of last month. "Last run" = the oldest file's save time.
