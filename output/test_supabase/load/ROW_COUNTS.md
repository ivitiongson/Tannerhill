# Row counts

Data rows = source rows after removing title lines, notes and total rows (the File Index "Data rows" column). D10-06a/b/c are unpivoted, so their load files hold one row per day per code.

| Table | Load file | Source file | Data rows (source) | File Index | Match | Rows in load file |
|---|---|---|---:|---:|---|---:|
| `d10_01_order_ledger` | `load/d10_01_order_ledger.csv` | D10-01 Order Ledger 2025-2026.csv | 25,152 | 25,152 | PASS | 25,152 |
| `d10_02_revenue_by_month` | `load/d10_02_revenue_by_month.csv` | D10-02 Revenue by Month 2025-2026.csv | 15 | 15 | PASS | 15 |
| `d10_03_amazon_business_report` | `load/d10_03_amazon_business_report.csv` | D10-03 Amazon Business Report Jan 2025-Mar 2026.csv | 180 | 180 | PASS | 180 |
| `d10_04_amazon_refunds_by_order_date` | `load/d10_04_amazon_refunds_by_order_date.csv` | D10-04 Amazon Refunds by Order Date Jan 2025-Mar 2026.csv | 180 | 180 | PASS | 180 |
| `d10_05_shopify_sales_by_product_weekly` | `load/d10_05_shopify_sales_by_product_weekly.csv` | D10-05 Shopify Sales by Product Weekly Jan 2025-Mar 2026.csv | 767 | 767 | PASS | 767 |
| `d10_06a_amazon_units_ordered` | `load/d10_06a_amazon_units_ordered.csv` | D10-06a Sales History - Amazon units ordered.csv | 455 | 455 | PASS | 5,460 |
| `d10_06b_amazon_units_refunded` | `load/d10_06b_amazon_units_refunded.csv` | D10-06b Sales History - Amazon units refunded.csv | 455 | 455 | PASS | 5,460 |
| `d10_06c_shopify_net_quantity` | `load/d10_06c_shopify_net_quantity.csv` | D10-06c Sales History - Shopify net quantity.csv | 455 | 455 | PASS | 5,915 |
| `d10_07_3pl_daily_stock` | `load/d10_07_3pl_daily_stock.csv` | D10-07 3PL Daily Stock Jan-Mar 2026.csv | 1,092 | 1,092 | PASS | 1,092 |
| `d10_08_bw_monthly_report` | `load/d10_08_bw_monthly_report.csv` | D10-08 BW Monthly Report Jan 2025-Mar 2026.csv | 15 | 15 | PASS | 15 |
| `d10_09_bw_agency_invoices` | `load/d10_09_bw_agency_invoices.csv` | D10-09 BW Agency Invoices 2026.csv | 3 | 3 | PASS | 3 |
| `d10_10_yuhang_po_history` | `load/d10_10_yuhang_po_history.csv` | D10-10 Yuhang PO History to 31 Mar 2026.xlsx | 38 | 38 | PASS | 38 |
| `d07_06_sku_crosswalk` | `load/d07_06_sku_crosswalk.csv` | dashboard-data/D07-06_SKU_Crosswalk.xlsx | 13 | 13 | PASS | 13 |
| `d04_01_supplier_terms` | `load/d04_01_supplier_terms.csv` | dashboard-data/D04-01_Stock_Position_and_Supplier_Terms.xlsx (tab Supplier terms) | 3 | 3 | PASS | 3 |
| `d04_03_bidworks_spend_by_product` | `load/d04_03_bidworks_spend_by_product.csv` | dashboard-data/D04-03_BidWorks_Spend_by_Product_FY2025.xlsx | 13 | 13 | PASS | 13 |
| `d04_04_product_margins` | `load/d04_04_product_margins.csv` | dashboard-data/D04-04_Product_Margins_FY2025.xlsx | 13 | 13 | PASS | 13 |
