# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where applicable.

## [Unreleased]

### Security

- **Dashboard mutating API:** all **`POST /api/*`** endpoints require **`Authorization: Bearer <token>`**; set **`AM4_ROUTEMINE_TOKEN`** or use the token printed at startup; **`hx-headers`** on **`base.html`** supplies HTMX requests (SEC-01 / SEC-06).
- **My Fleet buy/sell:** atomic SQLite **`UPDATE`** / **`BEGIN IMMEDIATE`** sell transaction to prevent concurrent quantity races (SEC-14).
- **Hub refresh:** non-blocking process lock so a second **`/api/hubs/refresh`** or **`/api/hubs/refresh-stale`** while extraction runs returns an **in progress** flash instead of stacking work (SEC-10).
- **Heatmap:** Leaflet marker popups built with DOM **`textContent`** instead of HTML string interpolation (SEC-04).
- **Dashboard API flash errors:** SQLite and other exception text shown in HTMX fragments is path-scrubbed and length-capped via **`dashboard/errors.py`** (SEC-18).
- **Dependencies:** **`requirements.in`** as the source of truth; **`requirements.lock`** with pip **`--require-hashes`** for Docker installs ( **`am4`** Git install remains a documented exception — commit pin); **`scripts/update_deps.sh`** and **`scripts/strip_vcs_from_lock.py`** (SEC-17).
- **Docker:** multi-stage build (compilers only in builder); runtime image runs as **`appuser`** (uid **1000**); **`docker-compose.yml`** publishes **`127.0.0.1:8000:8000`** by default (SEC-12 / SEC-13).

### Added

- **Buy Next global (`/buy-next/global`):** same flat **route × aircraft × config** table as hub **Buy next**, but every hub; **Hub** column in results; **`GET /api/buy-next-global`** for HTMX; default sort **total daily profit** at budget; **limit** capped at **100**; saved-filter page key **`buy-next-global`**.
- **Extraction freshness:** `hub_freshness_context` in **`dashboard/db.py`** (merged into **`base_context`** with a single DB round-trip) exposes **`hub_freshness_by_iata`**, **`hub_freshness_list`**, and **`stale_hub_banner`**. Overview shows a **Data freshness** card (green ≤7d, yellow 8–14d, red &gt;14d). Hub / origin dropdowns and datalists append age suffixes like **`(3d)`** or **`(21d, stale)`**. When **`?hub=`** or **`?origin=`** is stale (&gt;14d), **`base.html`** shows a refresh banner with **`extract --refresh-hubs`** and Hub Manager link.
- **Demand utilization (`/demand-utilization`):** compares **My Routes** seat supply (Y/J/F config × trips × assigned copies) to **`route_demands`** per cabin; classifies each cabin as Underserved / Saturated / Wasted (±10% band); hub, aircraft type, and “any cabin matches” filters; per-route cards with mini bars (demand fill + offered marker) and AM4 demand caveat in the header. **`GET /api/demand-utilization`** returns the HTMX fragment.
- **Extraction deltas (`/extraction-deltas`):** each successful full or hub extract records an **`extraction_runs`** row and copies **`route_aircraft`** into **`route_aircraft_snapshot`**. The page compares two runs (auto-pick latest pair or choose runs) for new/removed routes, large profit movers, validity flips, and per-hub average delta; optional hub filter and min |Δ%|. **`GET /api/extraction-deltas`** returns the HTMX fragment.
- **Saved filters (task 17):** SQLite **`saved_filters`** stores named URL query strings per dashboard page. **Buy Next**, **Fleet Planner**, **Fleet Health**, **Scenarios**, **Demand utilization**, and **Extraction deltas** show a **Saved filters** bar: apply reloads the page with that query string; **Save** persists the current filter form (serialized like **`URLSearchParams`**); **Delete** removes the selected preset. **`POST /api/saved-filters/save`** and **`POST /api/saved-filters/delete`** require the dashboard bearer token; duplicate names on the same page return a friendly inline error.
- **Aircraft page:** **`GET /api/aircraft-cost-breakdown`** returns a horizontal stacked bar (Chart.js) of average fuel, CO₂, A-check, repair, other, and profit as a percentage of average trip revenue per aircraft (valid **`route_aircraft`** rows only), with sort (margin %, fuel %, name) and PAX / cargo / VIP filters; tooltips show segment **$** averages and avg trip revenue.
- **Scenarios (`/scenarios`):** fuel and CO₂ price sliders vs extraction baselines stored on **`route_aircraft`** (`fuel_price`, `co2_price` columns, backfilled on dashboard connect / migrate); **`GET /api/scenarios`** recomputes daily profit from stored costs, with **My Routes** (default) or full-database scope, optional hub filter, totals / flip counts, and top-10 gain/loss assignments.
- **Hub ROI (`/hub-roi`):** per-hub cards for hubs you operate (**My Routes**), with capital deployed, daily profit, payback days, route and copy counts, and average profit per assigned copy; hubs sorted by lowest avg $/copy first with the worst hub highlighted; totals row with blended payback; footnote on capital accounting.
- **Fleet Health (`/fleet-health`):** compares each **My Routes** assignment to the best **`route_aircraft`** alternative on the same origin–destination (by profit per aircraft per day), with hub / minimum gap / “hide optimal” / reconfig-only filters; HTMX loads **`/api/fleet-health`** and shows swap vs reconfigure suggestions plus a summary of estimated daily profit left on the table.
- **Buy Next** hub view: see **Changed** for the current flat-table behavior; HTMX loads **`/api/buy-next`**.
- **Buy Next multi-hub allocate:** per recommendation, **Calculate** runs a greedy assignment of 1–50 copies across selected hubs (**`GET /api/buy-next/allocate`**) using each hub’s route queue (profit/day descending); shows total marginal $/day, payback on placed capital, per-hub copy counts and route list, and warns when fewer copies are placed than requested.
- **CLI `backup`:** **`python main.py backup --db …`** copies the SQLite file via the online backup API to **`./backups/<stem>_UTCtimestamp.db`** ( **`--output`** / **`-o`** for another directory) (SEC-15).
- **Recommend / Fleet Planner / Buy Next:** **`days_to_breakeven_avg`** and **`days_to_breakeven_best`** (CLI columns **`days_be_avg`**, **`days_be_best`**); primary **`days_to_breakeven`** follows the **best-route** case.
- **Extract:** **`--aircraft-id-max`** and **`--airport-id-max`** (**`UserConfig`**, persisted via **`extract_metadata`**).
- **`scripts/verify_aircraft_map.py`** — validate **`convert_csv`** **`AIRCRAFT_MAP`** entries against am4.
- **Tests:** `test_my_inventory_pages_form_after_request_elt_guard` in **`tests/test_dashboard_http.py`** (HTMX elt guard on **`/my-routes`**, **`/my-hubs`**, **`/my-fleet`** add forms); **`tests/test_buy_next_api.py`** for Buy Next budget parsing, missing DB, and **`limit`** validation; plus dashboard auth, fleet buy/sell concurrency, hub extraction lock, heatmap popup script shape, fleet recommend breakeven, airport extract vs **`min_runway`**, and related coverage.

### Changed

- **SQLite defaults & documentation:** canonical database file **`am4ops.db`** with CLI/dashboard default path from **`app.paths.db_path()`** (and optional **`AM4OPS_DATA_DIR`** / **`AM4_ROUTEMINE_DB`**). **`.taskmaster/docs/prd/`**, **`PRD/perf-flamegraphs-phase2.md`**, and related spec snippets were updated from legacy **`am4_data.db`** wording; diagram and sample **`argparse`** blocks now use **`DEFAULT_DB_PATH = str(db_path())`** where appropriate. **README** and **SETUP-GUIDE:** **Direct SQLite Queries** spell out **`sqlite3`** with **`db_path()`** on Bash, PowerShell, **`cmd.exe`**, and Docker. **README** project tree lists **`.taskmaster/docs/prd/`** and PRD naming conventions; **Contributing** references both spec locations. **Docker** uses **`/app/data/am4ops.db`** (migration note there for volumes still named **`am4_data.db`**). Test fixtures use a nonexistent **`no_am4ops.db`** path for absent-DB cases.

- **Buy Next (`/buy-next`, `/api/buy-next`):** flat sortable **route × aircraft × seat config** table with required hub and budget; columns for qty affordable, total daily profit, profit yield ($/d per $1M), and payback days; six sort options (A/C price asc/desc, profit/day asc/desc, yield, total daily profit at budget); default sort A/C price high→low; default row limit **15** with **Show all matches** (up to **500**); **`my_routes`** highlights — blue tint when you fly the route with another aircraft, dim with **✓ same** when hub+dest+aircraft already assigned; toggle to hide routes you already operate; 🏆 marks the row with the highest total daily profit at your budget regardless of sort. Implementation in **`dashboard/routes/api/recommendations.py`** and **`dashboard/templates/partials/buy_next_results.html`**.

- **Dashboard API:** monolithic **`dashboard/routes/api_routes.py`** split into **`dashboard/routes/api/`** (`shared`, `meta`, `analytics`, `recommendations`, `fleet`, `my_routes`, `hubs`); **`api_routes.py`** re-exports **`router`** for compatibility.

- **`scripts/convert_csv.py`:** **`AIRCRAFT_MAP`** shortnames aligned with am4 **`Aircraft.search`** canonical ids.
- **Airport bulk extract:** stores **every** valid am4 airport; **`min_runway`** applies only when adding a hub through **`upsert_airport_from_am4`**, not during full **`extract_all_airports`**.
- **Dashboard default bind:** **`python main.py dashboard`** uses **`127.0.0.1`** unless **`--host 0.0.0.0`** (see README).
- **README:** Docker section, auth / token documentation, extract option table (id max, runway note), breakeven and troubleshooting updates; **Windows (native)** install with **Visual Studio Build Tools** / MSVC (pinned **saqibj/am4** fork), PowerShell quick start, and **WSL** as optional.

### Fixed

- **My Routes** (`/my-routes`): HTMX **`after-request`** on the add-route form was listening to **bubbled** events from child requests (airport/aircraft search), so successful search responses triggered **`form.reset()`** and cleared the hub; shared **`hx-indicator`** also showed **“Saving…”** for those searches. **Guard** `event.detail.elt !== event.currentTarget` on the form handler; **`hx-indicator="false"`** on search inputs; separate **“Loading routes…”** indicator for the inventory panel vs save.
- **Hub Manager** (`/my-hubs`) and **My Fleet** (`/my-fleet`): same **`after-request`** guard on add forms (and on **Refresh stale hubs**) so bubbled child HTMX cannot run the wrong handler.

---

## [0.1.1] — 2026-04-04

### Added

- **Settings** page **`/settings`**: **light / dark / system** theme, **comfortable / compact** UI density, **default landing page** (redirect from `/` once per browser tab session when a non-root default is chosen), **notification** toggles (for future in-app use), **airline name** and **logo** (data URL) in the nav shell and Overview welcome line. Persistence in **`localStorage`** (`dashboard/static/js/settings-store.js`); Python mirror **`dashboard/ui_settings.py`** (schema version, allowlists, sanitization).
- **Theming:** **`dashboard/static/css/theme.css`** (semantic CSS variables, **`am4-*`** surfaces, banded **`am4-table`** rows, compact-density overrides, sticky table headers in horizontal scroll, **`:focus-visible`** rings, **`am4-text-negative`** / danger links).
- **Boot / UI scripts:** **`theme-boot.js`**, **`branding.js`**, **`shell-branding.js`**, **`settings-page.js`**, **`settings.css`**; landing redirect and **`Am4Notifications.enabled()`** stub in **`app.js`**.
- **Tests:** **`tests/test_ui_settings.py`**, **`tests/test_dashboard_http.py`**. Optional **`pip install -e ".[dev]"`** for **`pytest`**.
- **Docs:** **`docs/UIPRO_DESIGN_BRIEF.md`**, **`docs/UIPRO_VISUAL_SPEC.md`**.

### Changed

- **README:** **12** dashboard pages (adds **Settings**), theme / **`localStorage`** behavior, **Tests** section, **`docs/`** and **`tests/`** in project tree, troubleshooting for settings storage.

---

## [0.1.0] — 2026-03-28

### Added

- **`my_hubs`** managed-hubs table, **`idx_my_hubs_airport`**, and **`v_my_hubs`** view; **`v_my_routes`** / **`v_best_routes`** expose **`hub_name`**, **`hub_country`**, **`dest_name`**, **`dest_fullname`** (and **`dest_country`** on `v_my_routes`; `v_best_routes` keeps existing **`dest_country`**).
- Hub-scoped extraction: **`refresh_single_hub`** / **`refresh_hubs`** in `extractors/routes.py` — delete and recompute **`route_aircraft`** / **`route_demands`** for selected origins only; upsert missing airports via AM4; update **`my_hubs`** extraction fields when rows exist; require existing **`aircraft`** master data (full extract if empty).
- **CLI:** `extract --refresh-hubs --hubs …` for hub-only refresh; **`fleet import`** / **`routes import`** default to **`--merge`** (add on duplicate) with **`--replace`** to overwrite counts.
- **Hub Manager** dashboard: **`/my-hubs`** with summary, add (single or comma-separated IATA), per-row refresh, **time-based refresh stale** (last **OK** extract older than **7** days only — use per-row **Refresh** for errors / never-extracted), freshness badges, and remove from **`my_hubs`** only; HTMX APIs under **`/api/hubs/*`**.
- **My Fleet:** GUI add **merges** quantities; **`POST /api/fleet/{id}/buy`** and **`POST /api/fleet/{id}/sell`** (sell only up to **free** = owned − assigned on routes); table shows type, owned, assigned, free, unit/total value; summary adds assigned, free, fleet value.
- **My Routes:** GUI add **merges** `num_assigned`; **`GET /api/route-exists`** duplicate hint and **`GET /api/routes/pair-coverage`** (saved rows + top extracted profit) on the form via HTMX.
- **Airport search UX:** **`GET /api/search/airports`** and **`GET /api/search/aircraft`** (HTMX autocomplete); **`partials/airport_badge.html`**; richer destination labels in Hub Explorer, My Routes, Route Analyzer.
- **Buy Next** (`/buy-next`): budget-ranked aircraft at a hub via **`GET /api/fleet-plan`** (shared **`fleet_recommend_rows`** with CLI **`recommend`** and **Fleet Planner**). Nav + overview link.
- **Fleet recommendations:** **`my_fleet`** join for **Owned** in the table; **`hide_owned`** on **`/api/fleet-plan`**, Fleet Planner / Buy Next checkbox, and **`python main.py recommend --hide-owned`**.
- **`CHANGELOG.md`** (this file).

### Fixed

- **Hub Manager:** `POST /api/hubs/add`, `POST /api/hubs/refresh`, and `POST /api/hubs/refresh-stale` return an HTML flash error when the **`am4`** package is unavailable (`ImportError` / `ModuleNotFoundError`) instead of HTTP 500.

### Changed

- **Dashboard** replaced **Streamlit** with **FastAPI**, **Jinja2**, **HTMX**, and **Tailwind** (CDN). Entry module: `dashboard.server:app`; dependencies in `pyproject.toml` / `requirements.txt` (`fastapi`, `uvicorn`, `jinja2`, `python-multipart`, etc.).
- `python main.py dashboard` now serves **uvicorn** on **`0.0.0.0:8000`** by default (was Streamlit on port **8501**). New flag **`--host`**.
- **`v_best_routes`** view is recreated on schema apply and includes **`income_per_ac_day`** (see `database/schema.py`).
- **README** updated for the new stack, PRD paths, dashboard routes, and `AM4_ROUTEMINE_DB`.
- **README:** **10** dashboard pages including **Hub Manager**; documented **`extract --refresh-hubs`**, **merge vs replace** imports, **`recommend`** CLI, **`--workers`** default **4**, and **`requirements.txt` / `pyproject.toml`** alignment for **`am4`** (`saqibj/am4` **`msvc-fix`**).
- **`pyproject.toml`**: **`am4`** dependency URL aligned with **`requirements.txt`**.
- **`create_schema()`** applies **`DROP TABLE IF EXISTS`** for legacy **`fleet_aircraft`** / **`fleet_route_assignment`** before **`my_fleet`** / **`my_routes`**; airline state lives in those tables only (see `database/schema.py`).

### Removed

- **`dashboard/app.py`** (Streamlit app).

---

## Git tags

- **`v0.1.0`** — annotated tag on the last commit before the Settings / theme bundle on branch **`ui-update`** (FastAPI dashboard + Hub Manager + fleet/routes + Buy Next baseline).
- **`v0.1.1`** — annotated tag for Settings / theme release (**`git tag -a v0.1.1 -m "Release 0.1.1: Settings, themes, tests, docs"`**). **`[Unreleased]`** compares **`v0.1.1...HEAD`**.

[Unreleased]: https://github.com/saqibj/am4-ops-center/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/saqibj/am4-ops-center/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/saqibj/am4-ops-center/releases/tag/v0.1.0
