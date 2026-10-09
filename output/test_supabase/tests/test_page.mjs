// Opens index.html in Chromium with a fake supabase-js that serves the load/ CSVs
// (max 1,000 rows per request, like Supabase). No connection to Supabase.
// Run:  NODE_PATH=$(npm root -g) node output/test_supabase/tests/test_page.mjs
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const HERE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows;
  return body.map(r => Object.fromEntries(head.map((h, i) => [h, r[i] === '' ? null : r[i]])));
}

const data = {};
for (const f of fs.readdirSync(path.join(HERE, 'load')).filter(f => f.endsWith('.csv')))
  data[f.replace('.csv', '')] = parseCsv(fs.readFileSync(path.join(HERE, 'load', f), 'utf8'));

function fakeSupabase(failTable) {
  return `window.__calls = {};
window.supabase = { createClient: (url, key) => ({ from: (name) => {
  const st = { name, from: 0, to: 0, count: null };
  const api = {
    select: (cols, opts) => { st.count = opts && opts.count; return api; },
    order: () => api,
    range: (a, b) => { st.from = a; st.to = b; return api; },
    then: (res, rej) => {
      window.__calls[name] = (window.__calls[name] || 0) + 1;
      if (name === ${JSON.stringify(failTable)}) return Promise.resolve({ data: null, error: { message: 'permission denied for table ' + name } }).then(res, rej);
      const all = window.__DATA[name] || [];
      const to = Math.min(st.to, st.from + 999);
      return Promise.resolve({ data: all.slice(st.from, to + 1), error: null, count: st.count ? all.length : null }).then(res, rej);
    } };
  return api; } }) };`;
}

async function open(browser, failTable = null) {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(d => { window.__DATA = d; }, data);
  await page.route('**/*', route => {
    const url = route.request().url();
    if (url.includes('cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/'))
      return route.fulfill({ contentType: 'application/javascript', body: fakeSupabase(failTable) });
    if (url.endsWith('/config.js'))
      return route.fulfill({ contentType: 'application/javascript',
        body: 'window.TANNERHILL_CONFIG={SUPABASE_URL:"https://test.supabase.co",SUPABASE_PUBLISHABLE_KEY:"sb_publishable_test"}' });
    if (url.startsWith('http://dash.test/'))
      return route.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(HERE, 'index.html'), 'utf8') });
    return route.abort();
  });
  await page.goto('http://dash.test/index.html');
  await page.waitForSelector('#panels details');
  return { page, errors };
}

const results = [];
function check(name, ok, expected, actual) {
  results.push(ok);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}\n      expected: ${expected}\n      actual:   ${actual}`);
}

const browser = await chromium.launch();
{
  const { page, errors } = await open(browser);
  await page.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true));
  const text = await page.evaluate(() => document.body.innerText);
  const calls = await page.evaluate(() => window.__calls);
  check('P1. No script errors', errors.length === 0, 'none', errors.join(' | ') || 'none');
  check('P2. Ledger read in pages of 1,000: 25,152 rows in 26 requests',
    /d10_01_order_ledger\s+25,152/.test(text) && calls.d10_01_order_ledger === 26,
    'd10_01_order_ledger 25,152 · 26 requests', `${(text.match(/d10_01_order_ledger\s+[\d,]+/) || ['not shown'])[0]} · ${calls.d10_01_order_ledger} requests`);
  const counts = Object.entries(data).map(([t, rows]) => [t, rows.length]);
  const missing = counts.filter(([t, n]) => !new RegExp(`${t}\\s+${n.toLocaleString('en-US')}`).test(text));
  check('P3. Rows read shown for all 16 tables', missing.length === 0, '16 of 16', missing.map(m => m[0]).join(', ') || '16 of 16');
  check('P4. Header line', text.includes('Data as of 3 April 2026. March is not closed.'), 'present', text.includes('Data as of 3 April 2026') ? 'present' : 'missing');
  const want = [
    ['Revenue headline', '+14%'], ['Revenue YTD', '$317,258'], ['Last year', '$278,210'],
    ['Kickstarter label', 'Kickstarter (recognized when rewards ship)'], ['Stock headline', '7 red · 1 amber'],
    ['Ads headline', '3 losing money after ads'], ['Ads month', 'Covers Feb 2026'],
    ['On the way PO-2602-011', '600'], ['Unmatched TNHC-5001', 'TNHC-5001'], ['Unmatched PRO-V2', 'TRAILHEAD-GRILL-PRO-V2'],
    ['Unmatched windshield', 'windshield-panel-set'],
  ];
  const miss = want.filter(([, s]) => !text.includes(s));
  check('P5. Page figures = build_dashboard.py figures', miss.length === 0, want.map(w => w[1]).join(' · '), miss.map(m => 'missing ' + m[1]).join(', ') || 'all present');
  const stockDate = await page.$eval('#stock', el => el.dataset.date);
  check('P5b. Stock read at the 19 Mar 2026 06:00 snapshot', stockDate === '2026-03-19', '2026-03-19', stockDate);
  const py = JSON.parse(execFileSync('python3', ['-c', `
import json, sys; sys.path.insert(0, ${JSON.stringify(HERE)})
import build_dashboard as bd
n0 = lambda v: '–' if v is None else f'{v:,.0f}'
st, _ = bd.stock_table()
ads, _ = bd.ads_table()
print(json.dumps({
 'stock': sorted([r['sku'], f"{r['daily']:.1f}", n0(r['on_hand']), n0(r['on_the_way']) if r['on_the_way'] else '–', f"{r['reorder_point']:,.0f}", r['lead_time'], r['status']] for r in st),
 'ads': sorted([r['sku'], n0(r['units']), '–' if r['contribution'] is None else f"\${r['contribution']:,.0f}", '–' if r['ad_spend'] is None else f"\${r['ad_spend']:,.0f}", '–' if r['pct'] is None else f"{r['pct']:.0%}", r['status']] for r in ads)}))
`]).toString());
  const word = { 'Act now': 'red', Watch: 'amber', Healthy: 'green', 'No data': 'gray' };
  const pageStock = (await page.$$eval('#stockT tbody tr', trs => trs.map(tr => [...tr.cells].map(td => td.innerText.trim()))))
    .map(c => [c[0], c[2], c[3], c[4], c[5], c[6], c[8].split('\n')[0]]).map(r => (r[6] = word[r[6]], r)).sort();
  const pageAds = (await page.$$eval('#adsT tbody tr', trs => trs.map(tr => [...tr.cells].map(td => td.innerText.trim()))))
    .map(c => [c[0].split('\n')[1], c[1], c[2], c[3], c[4], c[5].split('\n')[0]]).map(r => (r[5] = word[r[5]], r)).sort();
  const diff = (a, b) => a.filter((r, i) => JSON.stringify(r) !== JSON.stringify(b[i])).map(r => r.join(' '));
  const ds = diff(pageStock, py.stock), da = diff(pageAds, py.ads);
  check('P5c. Stock and ads tables on the page = build_dashboard.py, row by row',
    !ds.length && !da.length && pageStock.length === 13 && pageAds.length === 13,
    '13 + 13 rows equal', ds.concat(da).join(' | ') || `${pageStock.length} + ${pageAds.length} rows equal`);
  const unmatchedRows = await page.$$eval('#codesT tbody tr', trs => trs.length);
  check('P6. Every unmatched code listed on the page', unmatchedRows === 6, '6 rows', `${unmatchedRows} rows`);
  await page.screenshot({ path: path.join(HERE, 'tests', 'test_page.png'), fullPage: true });
  await page.close();
}
{
  const { page, errors } = await open(browser, 'd10_07_3pl_daily_stock');
  await page.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true));
  const text = await page.evaluate(() => document.body.innerText);
  const stockTile = await page.$eval('a.tile[href="#stock"]', el => el.innerText);
  check('P7. Failed table: name and error shown, stock card shows no numbers',
    errors.length === 0 && text.includes('d10_07_3pl_daily_stock: failed – permission denied') &&
    text.includes('Missing data: d10_07_3pl_daily_stock') && !/\d/.test(stockTile.replace('Stock running low', '')),
    'error shown; stock tile "–"', `tile: ${stockTile.replace(/\n/g, ' / ')}`);
  check('P8. Other cards still load', text.includes('$317,258') && text.includes('3 losing money after ads'), 'revenue and ads shown', text.includes('$317,258') ? 'shown' : 'missing');
  await page.close();
}
await browser.close();
console.log(`\n${results.filter(Boolean).length}/${results.length} passed`);
process.exit(results.every(Boolean) ? 0 : 1);
