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

- **Buy Next page (`/buy-next`):** recommends aircraft to purchase next by payback period (cost ÷ average daily profit), with optional budget, hub, aircraft type, Top N, and “exclude owned” filters; HTMX loads **`/api/buy-next`** and shows top three routes with Y/J/F configuration per result.
- **CLI `backup`:** **`python main.py backup --db …`** copies the SQLite file via the online backup API to **`./backups/<stem>_UTCtimestamp.db`** ( **`--output`** / **`-o`** for another directory) (SEC-15).
- **Recommend / Fleet Planner / Buy Next:** **`days_to_breakeven_avg`** and **`days_to_breakeven_best`** (CLI columns **`days_be_avg`**, **`days_be_best`**); primary **`days_to_breakeven`** follows the **best-route** case.
- **Extract:** **`--aircraft-id-max`** and **`--airport-id-max`** (**`UserConfig`**, persisted via **`extract_metadata`**).
- **`scripts/verify_aircraft_map.py`** — validate **`convert_csv`** **`AIRCRAFT_MAP`** entries against am4.
- **Tests:** `test_my_inventory_pages_form_after_request_elt_guard` in **`tests/test_dashboard_http.py`** (HTMX elt guard on **`/my-routes`**, **`/my-hubs`**, **`/my-fleet`** add forms); plus dashboard auth, fleet buy/sell concurrency, hub extraction lock, heatmap popup script shape, fleet recommend breakeven, airport extract vs **`min_runway`**, and related coverage.

### Changed

- **Dashboard API:** monolithic **`dashboard/routes/api_routes.py`** split into **`dashboard/routes/api/`** (`shared`, `meta`, `analytics`, `recommendations`, `fleet`, `my_routes`, `hubs`); **`api_routes.py`** re-exports **`router`** for compatibility.

- **`convert_csv.py`:** **`AIRCRAFT_MAP`** shortnames aligned with am4 **`Aircraft.search`** canonical ids.
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
