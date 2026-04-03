# Baseline audit — guard rails (Task 1)

Use this when changing extraction, imports, or dashboard routes so later work stays predictable and non-destructive by intent.

## Verified CLI entrypoints

- `python main.py --help` — top-level commands: `extract`, `export`, `query`, `dashboard`, `fleet`, `routes`, `recommend`.
- `python main.py dashboard --help` — options: `--db`, `--port`, `--host`.

## Dashboard page routes vs left nav

FastAPI page routes are defined in `dashboard/routes/pages.py` and mounted at the app root (`dashboard/server.py`). Left nav links in `dashboard/templates/base.html` match these paths.

| Path | Page handler | Nav label |
|------|----------------|----------|
| `/` | `page_index` | Overview |
| `/hub-explorer` | `page_hub_explorer` | Hub Explorer |
| `/aircraft` | `page_aircraft` | Aircraft |
| `/route-analyzer` | `page_route_analyzer` | Route Analyzer |
| `/fleet-planner` | `page_fleet_planner` | Fleet Planner |
| `/my-fleet` | `page_my_fleet` | My Fleet |
| `/my-routes` | `page_my_routes` | My Routes |
| `/contributions` | `page_contributions` | Contributions |
| `/heatmap` | `page_heatmap` | Heatmap |

**There is no `/buy-next` route or handler** in the application. `README.md` still lists Buy Next at `/buy-next`; treat that as documentation ahead of implementation until a page exists.

## `my_fleet` / `my_routes` upsert semantics (overwrite, not merge)

Duplicate keys **replace** counts; they do **not** increment.

- **CLI CSV import:** `commands/airline.py` — `ON CONFLICT(aircraft_id) DO UPDATE SET quantity = excluded.quantity` and `ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET num_assigned = excluded.num_assigned`.
- **Dashboard HTMX:** `dashboard/routes/api_routes.py` — same `ON CONFLICT` patterns for fleet and routes add endpoints.

Later “merge vs replace” work should treat this baseline as **replace-on-conflict** unless explicitly redesigned.

## Full bulk extraction is destructive

`extractors/routes.py` → `run_bulk_extraction`:

1. `database.schema.create_schema` — applies full schema script.
2. `clear_route_tables` — `DELETE FROM route_aircraft` and `DELETE FROM route_demands`.
3. `replace_master_tables` — deletes **all** rows in `aircraft` and `airports` (FK pragma off for the operation).
4. Re-extracts aircraft, airports, then all hub×aircraft routes and inserts demand data.

Any “hub-only refresh” or non-destructive modes must **not** reuse this path blindly; they need a separate orchestration (see downstream tasks).

## Working branch

Baseline audit work: branch `chore/task-1-baseline-audit`.
