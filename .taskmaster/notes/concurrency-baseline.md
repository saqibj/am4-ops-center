# SQLite Concurrency Overhaul Baseline

## Branch

- Branch created: `feature/sqlite-concurrency-overhaul`
- Branched from commit: `ab963311ef8f1560978fc760407e20fc05cf0a0e`

## Test Suite Baseline

- Command: `pytest`
- Result: `173 passed`
- Runtime: `38.51s`

## SQLite PRAGMA Baseline

Source DB used for snapshot: `am4_data_backup.db`

- `journal_mode=wal`
- `synchronous=2`
- `busy_timeout=5000`
- `wal_autocheckpoint=1000`

## Shared Connection Pattern Inventory

Connection import/access pattern used across the codebase:

- Import path: `from database.schema import ... get_connection`
- Call pattern: `get_connection(...)`

Files matched by grep for `get_connection(`:

- `commands/airline.py`
- `dashboard/routes/setup.py`
- `dashboard/setup_flow.py`
- `database/schema.py`
- `extractors/routes.py`
- `main.py`
- `tests/test_add_route_page.py`
- `tests/test_airports_extract.py`
- `tests/test_app_state.py`
- `tests/test_backup_cmd.py`
- `tests/test_dashboard_auth.py`
- `tests/test_eligible_aircraft_api.py`
- `tests/test_fleet_atomic.py`
- `tests/test_fleet_recommend.py`
- `tests/test_fleet_service.py`
- `tests/test_heatmap_popup.py`
- `tests/test_hub_extraction_lock.py`
- `tests/test_hubs_service.py`
- `tests/test_route_validator.py`
- `tests/test_routes_add_transactional.py`
- `tests/test_schema.py`
- `tests/test_settings_dao.py`

Files matched by grep for `from ... import ... get_connection`:

- `commands/airline.py`
- `dashboard/routes/setup.py`
- `dashboard/setup_flow.py`
- `database/__init__.py`
- `main.py`
- `tests/test_add_route_page.py`
- `tests/test_airports_extract.py`
- `tests/test_app_state.py`
- `tests/test_backup_cmd.py`
- `tests/test_dashboard_auth.py`
- `tests/test_eligible_aircraft_api.py`
- `tests/test_fleet_atomic.py`
- `tests/test_fleet_recommend.py`
- `tests/test_fleet_service.py`
- `tests/test_heatmap_popup.py`
- `tests/test_hub_extraction_lock.py`
- `tests/test_hubs_service.py`
- `tests/test_route_validator.py`
- `tests/test_routes_add_transactional.py`
- `tests/test_settings_dao.py`
