# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where applicable.

## [Unreleased]

### Added

- **`my_hubs`** managed-hubs table, **`idx_my_hubs_airport`**, and **`v_my_hubs`** view; **`v_my_routes`** / **`v_best_routes`** expose **`hub_name`**, **`hub_country`**, **`dest_name`**, **`dest_fullname`** (and **`dest_country`** on `v_my_routes`; `v_best_routes` keeps existing **`dest_country`**).
- Hub-scoped extraction: **`refresh_single_hub`** / **`refresh_hubs`** in `extractors/routes.py` — delete and recompute **`route_aircraft`** / **`route_demands`** for selected origins only; upsert missing airports via AM4; update **`my_hubs`** extraction fields when rows exist; require existing **`aircraft`** master data (full extract if empty).
- **CLI:** `extract --refresh-hubs --hubs …` for hub-only refresh; **`fleet import`** / **`routes import`** default to **`--merge`** (add on duplicate) with **`--replace`** to overwrite counts.
- **Hub Manager** dashboard: **`/my-hubs`** with summary, add (single or comma-separated IATA), per-row refresh, **refresh stale**, and remove from `my_hubs` only; HTMX APIs under **`/api/hubs/*`**.
- **My Fleet** (`GET /my-fleet`): track fleet slots (hub, aircraft type, quantity, label) in SQLite and optionally assign slots to extracted `route_aircraft` rows; HTMX API under `/api/fleet/*` and JSON at `/api/fleet/json`.
- Schema tables **`fleet_aircraft`** and **`fleet_route_assignment`** (see `database/schema.py` and `PRD/am4-routemine-FLEET-SPEC.md`).
- **`CHANGELOG.md`** (this file).

### Changed

- **Dashboard** replaced **Streamlit** with **FastAPI**, **Jinja2**, **HTMX**, and **Tailwind** (CDN). Entry module: `dashboard.server:app`; dependencies in `pyproject.toml` / `requirements.txt` (`fastapi`, `uvicorn`, `jinja2`, `python-multipart`, etc.).
- `python main.py dashboard` now serves **uvicorn** on **`0.0.0.0:8000`** by default (was Streamlit on port **8501**). New flag **`--host`**.
- **`v_best_routes`** view is recreated on schema apply and includes **`income_per_ac_day`** (see `database/schema.py`).
- **README** updated for the new stack, PRD paths, dashboard routes, and `AM4_ROUTEMINE_DB`.

### Removed

- **`dashboard/app.py`** (Streamlit app).
