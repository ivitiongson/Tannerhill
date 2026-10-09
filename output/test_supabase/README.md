# "Are we okay?" dashboard on Supabase (test build)

Built in `output/test_supabase/` because CLAUDE.md only allows new files inside `output/`
and never overwriting existing files. Starts from v6 (`output/test_dashboard_v3/test_build_dashboard_6.py`
and `test_index_6.html`); those files are unchanged.

| File | What it is |
|---|---|
| `supabase/schema.sql` | 16 tables, one per source file. RLS on; anon may only SELECT. |
| `make_load.py` | Writes `load/<table>.csv` (clean, one per table) and `load/ROW_COUNTS.md` |
| `load/` | The CSVs to import. Header = table columns. `row_no` = primary key (source order), used to page. |
| `index.html` | The page. Reads every table from Supabase (pages of 1,000), works out the metrics in the browser. |
| `test_preview.html` | Preview only: same page, but reads the `load/` CSVs instead of Supabase. Works on GitHub Pages with no setup. |
| `config.js` | Project URL + publishable key. Placeholders: fill in before deploying. Never the secret key. |
| `build_dashboard.py` | Same metric functions in Python, reading `load/`. Used by the tests. |
| `tests/test_metrics.py` | Mapping "Checks" tab + dashboard logic, PASS/FAIL |
| `tests/test_page.mjs` | Opens the page with a fake Supabase serving `load/` (no connection), compares with Python |

## Set up

1. Supabase SQL editor: run `supabase/schema.sql`.
2. Import each `load/<table>.csv` into the table of the same name (Table editor > Import CSV,
   or `\copy public.<table> from 'load/<table>.csv' csv header`). Blank cells = NULL.
3. Put the Project URL and publishable key in `config.js`.
4. Deploy this folder to Vercel as a static site (no build step). `index.html` is the page.

## Run checks

```
python3 output/test_supabase/make_load.py
python3 output/test_supabase/tests/test_metrics.py
NODE_PATH=$(npm root -g) node output/test_supabase/tests/test_page.mjs
```
