-- Tannerhill dashboard: one table per source file. Sources are not merged.
-- Column names = source column names in snake_case (see "Dashboard Data Mapping D10").
-- row_no = line order in the clean load file (load/<table>.csv); primary key, used to page.
-- Every table: row level security on, anon may SELECT all rows, nothing else.

-- ---------------------------------------------------------------- D10 files

create table if not exists public.d10_01_order_ledger (
  row_no integer primary key,
  order_id text,
  order_date date,
  recognized_date date,
  channel text,
  customer_id text,
  sku text,
  product text,
  qty integer,
  net_revenue numeric(12,2),
  gross_sales numeric(12,2),
  discounts numeric(12,2),
  refunds numeric(12,2),
  refunded_qty integer,
  refund_date date,
  kickstarter_fee numeric(12,2)
);

create table if not exists public.d10_02_revenue_by_month (
  row_no integer primary key,
  month date,                                              -- "Jan 2025" -> 2025-01-01
  amazon_net_of_refunds numeric(12,2),
  shopify_net_of_discounts_and_returns numeric(12,2),
  kickstarter_recognized_when_rewards_ship numeric(12,2),
  total_revenue numeric(12,2),
  kickstarter_pledges_collected_net_of_fees_cash_not_revenue numeric(12,2),  -- cash, not revenue: never used on the page
  books text
);

create table if not exists public.d10_03_amazon_business_report (
  row_no integer primary key,
  month date,
  child_asin text,
  sku text,
  title text,
  units_ordered integer,
  ordered_product_sales numeric(12,2)
);

create table if not exists public.d10_04_amazon_refunds_by_order_date (
  row_no integer primary key,
  order_month date,
  sku text,
  asin text,
  title text,
  units_refunded integer,
  refund_amount numeric(12,2)
);

create table if not exists public.d10_05_shopify_sales_by_product_weekly (
  row_no integer primary key,
  week date,
  product_title text,
  product_variant_sku text,
  net_items_sold integer,
  gross_sales numeric(12,2),
  discounts numeric(12,2),
  returns numeric(12,2),
  net_sales numeric(12,2)
);

-- D10-06a/b/c unpivoted from wide (one column per code) to long
create table if not exists public.d10_06a_amazon_units_ordered (
  row_no integer primary key,
  date date,          -- order_date
  code text,          -- Amazon seller SKU (column header)
  units integer
);

create table if not exists public.d10_06b_amazon_units_refunded (
  row_no integer primary key,
  date date,          -- refund_date
  code text,          -- Amazon seller SKU (column header)
  units integer
);

create table if not exists public.d10_06c_shopify_net_quantity (
  row_no integer primary key,
  date date,          -- Day (MM/DD/YYYY in the source)
  code text,          -- Shopify handle (column header)
  units integer
);

create table if not exists public.d10_07_3pl_daily_stock (
  row_no integer primary key,
  snapshot_ts timestamp,
  client text,
  item_code text,
  item_desc text,
  qty_on_hand integer,
  qty_allocated integer,
  qty_hold integer,
  qty_available integer,
  qty_expected integer,
  expected_date date,
  po_ref text
);

create table if not exists public.d10_08_bw_monthly_report (
  row_no integer primary key,
  month date,
  spend numeric(12,2),
  impressions integer,
  clicks integer,
  ctr numeric(8,4),   -- fraction: 1.77% -> 0.0177
  cpc numeric(8,2),
  quality_score numeric(4,1)
);

create table if not exists public.d10_09_bw_agency_invoices (
  row_no integer primary key,
  invoice_no text,    -- "Invoice #"
  month text,
  date_issued date,
  description text,
  amount numeric(12,2),
  deliverables_listed text,
  paid text
);

create table if not exists public.d10_10_yuhang_po_history (
  row_no integer primary key,
  po_no text,         -- "PO #"; PO-2506-029 has 2 rows (split shipment)
  our_sku text,
  product text,
  qty integer,
  unit_price_ddp_to_3pl numeric(12,2),
  po_value numeric(12,2),
  marco_asked_lena date,
  po_signed_lena date,
  deposit_paid date,
  left_factory date,
  arrived_3pl date,
  qty_arrived integer,
  balance_paid date,
  notes text
);

-- ---------------------------------------------------------------- earlier files still needed

create table if not exists public.d07_06_sku_crosswalk (
  row_no integer primary key,
  our_sku text,
  product text,
  "3pl_item_code" text,
  shopify_handle text,
  amazon_seller_sku text,
  asin text,
  notes text
);

create table if not exists public.d04_01_supplier_terms (
  row_no integer primary key,
  supplier text,
  country text,
  supplies text,
  lead_time text,
  payment_terms text,
  minimum_order text,
  notes text
);

create table if not exists public.d04_03_bidworks_spend_by_product (
  row_no integer primary key,
  sku text,
  product text,
  annual_ad_spend numeric(12,2),
  share_of_budget numeric(6,4)   -- fraction: 0.225 = 22.5%
);

create table if not exists public.d04_04_product_margins (
  row_no integer primary key,
  sku text,
  product text,
  retail_price numeric(12,2),
  landed_unit_cost numeric(12,2),
  product_margin_pct numeric(6,4),   -- "Product margin %", as a fraction
  units_sold_fy25 integer,
  net_revenue_fy25 numeric(12,2),
  contribution_fy25 numeric(12,2)
);

-- ---------------------------------------------------------------- read-only access for anon

do $$
declare t text;
begin
  foreach t in array array[
    'd10_01_order_ledger', 'd10_02_revenue_by_month', 'd10_03_amazon_business_report',
    'd10_04_amazon_refunds_by_order_date', 'd10_05_shopify_sales_by_product_weekly',
    'd10_06a_amazon_units_ordered', 'd10_06b_amazon_units_refunded', 'd10_06c_shopify_net_quantity',
    'd10_07_3pl_daily_stock', 'd10_08_bw_monthly_report', 'd10_09_bw_agency_invoices',
    'd10_10_yuhang_po_history', 'd07_06_sku_crosswalk', 'd04_01_supplier_terms',
    'd04_03_bidworks_spend_by_product', 'd04_04_product_margins'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select on public.%I to anon', t);
    execute format('drop policy if exists "anon can read" on public.%I', t);
    execute format('create policy "anon can read" on public.%I for select to anon using (true)', t);
  end loop;
end $$;
