# "Are we OK?" dashboard

One page for Lena: 4 metrics + "Not answered yet". Sandbox data only.

## Files

| File | What it is |
|---|---|
| `build_dashboard.py` | All the logic. Reads `dashboard-data/*.xlsx` (read-only), writes `index.html` |
| `tests/test_metrics.py` | 6 checks, each prints PASS/FAIL with expected vs actual |
| `index.html` | The page (static, inline CSS, no login) |
| `feed/` (not created yet) | Drop live revenue exports here to light up card 1 |

## Run

```
pip install openpyxl
python3 output/dashboard/tests/test_metrics.py
python3 output/dashboard/build_dashboard.py            # run time = now
python3 output/dashboard/build_dashboard.py --as-of "2026-10-08 09:00"
```

## Live revenue feed (card 1)

Put three files in `output/dashboard/feed/`, same layout as the Q2 samples:

- `amazon_business_report.xlsx` (like D09-01)
- `amazon_payments_summary.xlsx` (like D09-02, needs the "Refunds by order date" tab)
- `shopify_sales_by_product.xlsx` (like D09-03)

They should cover 1 Jan to the end of last month. The card compares them with the same months of 2025 from D02-02. "As of" = the oldest file's save time.

## Choices made

- Kickstarter pledges are **included** in revenue (Lena: treat as shipped).
- Daily sales = average of the **last 28 days** in D07-07.
