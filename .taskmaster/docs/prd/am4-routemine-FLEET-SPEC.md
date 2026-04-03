# AM4 RouteMine — Fleet Management Specification

> **Purpose:** Track player-owned aircraft by type (`my_fleet`) and operational assignments hub→destination→aircraft (`my_routes`), with CSV/CLI and dashboard parity.
> **UI:** FastAPI + Jinja2 + HTMX (same patterns as `am4-routemine-DASHBOARD-SPEC.md`).
> **Data:** SQLite tables alongside extraction data in `am4_data.db`.

---

## 1. Schema

### 1.1 `my_fleet`

One row per **aircraft type** in your hangar (no hub on this table).

| Column        | Type      | Notes |
|---------------|-----------|--------|
| `id`          | INTEGER PK AUTOINCREMENT | |
| `aircraft_id` | INTEGER NOT NULL UNIQUE | FK → `aircraft(id)` |
| `quantity`    | INTEGER NOT NULL DEFAULT 1 | CHECK 1–999 |
| `notes`       | TEXT NULL | |
| `created_at`  | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| `updated_at`  | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

Index: `idx_my_fleet_ac (aircraft_id)`.

### 1.2 `my_routes`

Assignments of **N aircraft** of a type on a **hub → destination** pair.

| Column         | Type      | Notes |
|----------------|-----------|--------|
| `id`           | INTEGER PK AUTOINCREMENT | |
| `origin_id`    | INTEGER NOT NULL | FK → `airports(id)` (hub IATA) |
| `dest_id`      | INTEGER NOT NULL | FK → `airports(id)` (destination IATA) |
| `aircraft_id`  | INTEGER NOT NULL | FK → `aircraft(id)` (shortname) |
| `num_assigned` | INTEGER NOT NULL DEFAULT 1 | CHECK 1–999 |
| `notes`        | TEXT NULL | |
| `created_at`   | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| `updated_at`   | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**UNIQUE** `(origin_id, dest_id, aircraft_id)`.

Indexes: `idx_my_routes_origin`, `idx_my_routes_dest`, `idx_my_routes_ac`.

### 1.3 Views

- **`v_my_fleet`** — `my_fleet` joined to `aircraft` (`shortname`, `ac_name`, `ac_type`, `cost`, …).
- **`v_my_routes`** — `my_routes` joined to `airports` (hub/destination IATA) and `aircraft` (`shortname`, `ac_name`).

Legacy tables **`fleet_aircraft`** / **`fleet_route_assignment`** are **dropped** when `create_schema()` runs; use `my_fleet` / `my_routes` only.

---

## 2. Fleet API (`/api/fleet/…`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/fleet/inventory` | HTML partial: `my_fleet` table + delete |
| GET | `/api/fleet/summary` | HTML partial: type count, total qty, `my_routes` row count, est. daily profit |
| POST | `/api/fleet/add` | Form: `aircraft` (shortname), `quantity`, `notes` → upsert by `aircraft_id`, return inventory |
| POST | `/api/fleet/delete` | Form: `fleet_id` (`my_fleet.id`) → delete row, return inventory |
| GET | `/api/fleet/json` | JSON list of fleet rows |

**Est. profit** (summary): `SUM(my_routes.num_assigned × best_profit_per_ac_day)` where “best” is `MAX(profit_per_ac_day)` per `(origin_id, dest_id, aircraft_id)` among `route_aircraft` with `is_valid = 1`.

---

## 3. Routes API (`/api/routes/…`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/routes/inventory` | HTML partial: `my_routes` with optional joined economics |
| GET | `/api/routes/summary` | HTML partial: row count, sum `num_assigned`, est. profit |
| POST | `/api/routes/add` | Form: `hub_iata`, `destination_iata`, `aircraft`, `num_assigned`, `notes` |
| POST | `/api/routes/delete` | Form: `my_route_id` |
| GET | `/api/routes/json` | JSON list |

---

## 4. Dashboard & navigation

- **`GET /my-fleet`** — `my_fleet.html`: summary + add form + inventory (HTMX).
- **`GET /my-routes`** — `my_routes.html`: summary + add form + inventory (HTMX).
- **Sidebar:** group **My Airline** with links **My Fleet**, **My Routes** (after Fleet Planner).
- **Overview (`/`):** subsection **My Airline** with the same two quick links.

---

## 5. CSV formats

| File | Columns |
|------|---------|
| `fleet.csv` | `shortname`, `count`, `notes` (header row). Resolves `shortname` → `aircraft.id`. |
| `my_routes.csv` | `hub`, `destination`, `aircraft`, `num_assigned`, `notes`. Resolves IATA → `airports.id`, `aircraft` → `aircraft.id`. |

Import **upserts**: same aircraft in `fleet.csv` replaces quantity/notes for that type; same triple hub/dest/aircraft in routes CSV replaces `num_assigned`/notes.

---

## 7. CLI (`main.py`)

```bash
python main.py fleet import --file fleet.csv [--db am4_data.db]
python main.py fleet export --output fleet.csv [--db am4_data.db]
python main.py fleet list [--db am4_data.db]

python main.py routes import --file my_routes.csv [--db am4_data.db]
python main.py routes export --output my_routes.csv [--db am4_data.db]

python main.py recommend --hub KHI --budget 500000000 [--db am4_data.db] [--top 25]
```

- **`recommend`** prints TSV of aircraft types flyable from `--hub` with `cost <= budget`, ranked by average `profit_per_ac_day` over valid extracted routes (same logic as dashboard fleet planner).

All CSV/CLI paths call `create_schema()` so `my_fleet` / `my_routes` exist after a fresh DB or upgrade.
