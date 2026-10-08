# "Are we okay?" dashboard (v2)

One page for Lena: summary strip, 4 metric panels, "Not answered yet". Sandbox data only.
Layout follows `layout-reference.html` (style only; every number and band comes from the prompt).

Built in `output/test_dashboard/` because `output/dashboard/` already holds v1 and
CLAUDE.md rule 3 says existing files are never overwritten.

## Files

| File | What it is |
|---|---|
| `data/` | Copies of the 13 spreadsheets (originals stay in `dashboard-data/`) |
| `build_dashboard.py` | All the logic. Reads `data/`, writes `index.html` |
| `tests/test_metrics.py` | Checks 1–6, each prints PASS/FAIL with expected vs actual |
| `index.html` | The page (static, inline CSS, no login) |
| `feed/` (not created yet) | Drop live revenue exports here to light up the revenue panel |

## Run

```
pip install openpyxl
python3 output/test_dashboard/tests/test_metrics.py
python3 output/test_dashboard/build_dashboard.py            # run time = now
python3 output/test_dashboard/build_dashboard.py --as-of "2026-10-08 09:00"
```

## Live revenue feed

Put three files in `feed/`, same layout as the Q2 samples:

- `amazon_business_report.xlsx` (like D09-01)
- `amazon_payments_summary.xlsx` (like D09-02, with the "Refunds by order date" tab)
- `shopify_sales_by_product.xlsx` (like D09-03)

They should cover 1 Jan to the end of last month. "Last run" = the oldest file's save time.
