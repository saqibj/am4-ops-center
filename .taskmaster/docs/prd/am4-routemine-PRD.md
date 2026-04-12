# AM4 RouteMine — PRD & Technical Specification

> **Project:** am4-routemine
> **Repository:** https://github.com/saqibj/am4-routemine

> **Purpose:** A Python CLI tool that uses the `am4` pip package (v0.1.x) to extract ALL aircraft specs, ALL airport data, and compute route profitability for EVERY valid aircraft × airport combination — eliminating the need to query the Discord bot per-hub/per-aircraft.
>
> **Output:** SQLite database + CSV exports + optional local web dashboard for filtering/sorting.

---

## 1. Problem Statement

The AM4 Discord bot generates route reports one hub + one aircraft at a time. For competitive play, you need to compare profitability across ALL aircraft for ALL possible hubs/routes. Currently this means hundreds of individual bot queries. This tool does a single bulk extraction and stores everything locally for offline querying.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────┐
│                  am4 pip package                 │
│  (C++ core with pybind11 Python bindings)        │
│                                                  │
│  Aircraft.search()  Airport.search()             │
│  Route.create()     AircraftRoute.create()       │
│  RoutesSearch()     (exhaustive hub search)       │
│  Ticket prices      Demand data                  │
└──────────────────┬───────────────────────────────┘
                   │
          ┌────────▼────────┐
          │  AM4 RouteMine  │  ← Python CLI (this tool)
          │  (main.py)       │
          └────────┬────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
     ▼             ▼             ▼
  SQLite DB    CSV exports    Web UI
  (am4ops.db)  (exports/)   (FastAPI dashboard)
```

---

## 3. Data Sources — What the `am4` Package Exposes

### 3.1 Aircraft Database

Install: `pip install "am4 @ git+https://github.com/abc8747/am4.git@master"` (requires GCC — use WSL on Windows)

The package embeds a compiled aircraft database. Each `Aircraft` object has:

| Property       | Type    | Description                              |
|----------------|---------|------------------------------------------|
| `id`           | int     | Internal numeric ID                      |
| `shortname`    | str     | Short code (e.g., "b738")                |
| `name`         | str     | Full name (e.g., "Boeing 737-800")       |
| `manufacturer` | str     | Manufacturer name                        |
| `type`         | enum    | PAX / CARGO / VIP                        |
| `speed`        | float   | Cruise speed (km/h)                      |
| `fuel`         | float   | Fuel consumption coefficient             |
| `co2`          | float   | CO₂ consumption coefficient              |
| `cost`         | int     | Purchase price ($)                       |
| `capacity`     | int     | Total seat/cargo capacity                |
| `range`        | int     | Max range (km)                           |
| `rwy`          | int     | Min runway length required (ft)          |
| `check_cost`   | int     | A-check cost ($)                         |
| `maint`        | int     | Maintenance cost                         |
| `ceil`         | int     | Service ceiling                          |
| `speed_mod`    | bool    | Has speed modification available         |
| `fuel_mod`     | bool    | Has fuel efficiency mod available        |
| `co2_mod`      | bool    | Has CO₂ efficiency mod available         |
| `fourx_mod`    | bool    | Has 4x speed mod available               |
| `pilots`       | int     | Required pilots                          |
| `crew`         | int     | Required crew                            |
| `engineers`    | int     | Required engineers                       |
| `technicians`  | int     | Required technicians                     |
| `wingspan`     | int     | Wingspan (m)                             |
| `length`       | int     | Length (m)                                |
| `valid`        | bool    | Whether aircraft is valid/active         |

**Seat configuration** is computed per-route via `Aircraft.PaxConfig` and `Aircraft.CargoConfig`:

- **PaxConfig:** `y` (economy), `j` (business), `f` (first) seats, `algorithm` (FJY, FYJ, JFY, JYF, YJF, YFJ, AUTO)
- **CargoConfig:** `l` (large), `h` (heavy), `algorithm` (L, H, AUTO)

### 3.2 Airport Database

Each `Airport` object has:

| Property    | Type   | Description                                |
|-------------|--------|--------------------------------------------|
| `id`        | int    | Internal ID                                |
| `iata`      | str    | 3-letter IATA code                         |
| `icao`      | str    | 4-letter ICAO code                         |
| `name`      | str    | Short name                                 |
| `fullname`  | str    | Full airport name                          |
| `country`   | str    | Country                                    |
| `continent` | str    | Continent code                             |
| `lat`       | float  | Latitude                                   |
| `lng`       | float  | Longitude                                  |
| `rwy`       | int    | Runway length (ft)                         |
| `rwy_codes` | str    | Runway code classification                 |
| `market`    | int    | Market tier (used in hub cost/demand calc)  |
| `hub_cost`  | int    | Cost to open as hub ($)                    |
| `valid`     | bool   | Whether airport is valid/active            |

### 3.3 Route Data (computed)

`Route.create(ap0, ap1)` returns:

| Property          | Type       | Description                      |
|-------------------|------------|----------------------------------|
| `direct_distance` | float      | Haversine distance (km)          |
| `pax_demand`      | PaxDemand  | Y/J/F demand for the route       |
| `valid`           | bool       | Whether route is valid           |

### 3.4 AircraftRoute (the main calculation object)

`AircraftRoute.create(ap0, ap1, ac, options, user)` returns:

| Property               | Type              | Description                           |
|------------------------|-------------------|---------------------------------------|
| `route`                | Route             | Underlying route                      |
| `config`               | PaxConfig/CargoConfig | Optimal seat configuration         |
| `ticket`               | PaxTicket/CargoTicket | Optimal ticket prices              |
| `fuel`                 | float             | Total fuel cost per trip              |
| `co2`                  | float             | Total CO₂ cost per trip               |
| `income`               | float             | Revenue per trip                      |
| `profit`               | float             | Profit per trip (income - costs)      |
| `max_income`           | float             | Max possible income                   |
| `contribution`         | float             | Alliance contribution per trip        |
| `ci`                   | int               | Cost Index used                       |
| `flight_time`          | float             | Flight time (hours)                   |
| `trips_per_day_per_ac` | int               | Max trips per day per aircraft        |
| `num_ac`               | int               | Aircraft needed to fill demand        |
| `needs_stopover`       | bool              | Whether route needs a stopover        |
| `stopover`             | Stopover          | Stopover airport details              |
| `acheck_cost`          | float             | A-check cost amortized                |
| `repair_cost`          | float             | Expected repair cost                  |
| `warnings`             | list[Warning]     | Any constraint violations             |
| `valid`                | bool              | Whether route is flyable              |

### 3.5 RoutesSearch (exhaustive hub-based search)

This is the **key class** for bulk extraction:

```python
from am4.utils.db import init
from am4.utils.route import RoutesSearch, AircraftRoute

init()  # MUST be called before any am4 lookups

# Search ALL destinations from a hub for a specific aircraft
search = RoutesSearch(
    ap0=[hub_airport],         # list of origin airports
    ac=aircraft,               # Aircraft object
    options=AircraftRoute.Options(
        sort_by=AircraftRoute.Options.SortBy.PER_AC_PER_DAY
    )
)

# Get all valid destinations, sorted by profitability
destinations = search.get()  # returns list[Destination]

for dest in destinations:
    print(dest.airport.iata, dest.ac_route.profit, dest.ac_route.config.to_dict())
```

---

## 4. Game Formulae Reference

All formulae from https://abc8747.github.io/am4/formulae/ — embed these as reference for verification/custom calculations.

### 4.1 Ticket Prices (Easy Mode)

```
Pax:   $Y = 0.4d + 170    $J = 0.8d + 560    $F = 1.2d + 1200
Optimal multipliers: Y × 1.10, J × 1.08, F × 1.06

VIP:   Same as Pax × 1.7489
Optimal multipliers: Y × 1.22, J × 1.195, F × 1.175

Cargo: $L = 0.0948d + 85.20    $H = 0.0690d + 28.30
Optimal multipliers: L × 1.10, H × 1.08
```

### 4.2 Ticket Prices (Realism Mode)

```
Pax:   $Y = 0.3d + 150    $J = 0.6d + 500    $F = 0.9d + 1000
Optimal multipliers: Y × 1.10, J × 1.08, F × 1.06

VIP:   Same as Pax × 1.7489
Optimal multipliers: Y × 1.22, J × 1.195, F × 1.175

Cargo: $L = 0.0776d + 85.06    $H = 0.0518d + 24.64
Optimal multipliers: L × 1.10, H × 1.08
```

### 4.3 Distance (Haversine)

```
d = 12742 × arcsin(√(sin²((φ₂-φ₁)/2) + cos(φ₁)·cos(φ₂)·sin²((λ₂-λ₁)/2)))
```

### 4.4 Fuel Consumption

```
fuel = (1 - t_f) × ceil(d, 2) × c_f × (CI/500 + 0.6)
```

Where `t_f` = fuel training (0-3), `c_f` = aircraft fuel coeff, `CI` = cost index (0-200).

### 4.5 CO₂ Consumption (Pax)

```
CO₂ = (1 - t_c/100) × ceil(d, 2) × c_c × (y_loaded + 2×j_loaded + 3×f_loaded + y_config + j_config + f_config) × (CI/2000 + 0.9)
```

### 4.6 CI / Speed

```
v = u × (0.0035 × CI + 0.3)
```

### 4.7 Best Seat Configuration Order (Easy Mode)

| Distance (km)     | Pax Priority  | Cargo Priority |
|--------------------|---------------|----------------|
| < 14,425           | F > J > Y     | L > H          |
| 14,425 – 14,812.5  | F > Y > J     | L > H          |
| 14,812.5 – 15,200  | Y > F > J     | L > H          |
| > 15,200            | Y > J > F     | L > H          |
| > 23,908            | —             | H > L          |

### 4.8 Alliance Contribution

```
$C = k_drop × min(k_gm × k × d × (3 - CI/100), 152)  ± 16%

k_gm = 1.5 (realism), 1 (easy)
k = 0.0064 (d < 6000), 0.0032 (6000 < d < 10000), 0.0048 (d > 10000)
k_drop = 1 (p=0.75) or 0.5 (p=0.25)
```

### 4.9 Aircraft Wear & Repair

```
wear ~ Uniform(0, 0.015 × (1 - 0.02 × t_r))     # Expected: 0.75% per departure
repair_cost = 0.001 × aircraft_cost × (1 - 0.02 × t_r) × wear
repair_time = 480000 × wear + 3600  (seconds)
```

### 4.10 Hub Cost

```
C_hub = k × planes_owned + k     (k = airport tier value)
```

### 4.11 Route Creation Cost (Easy, Pax)

```
C = 0.4 × (d + (y × floor(0.4d + 170)) + (j × floor(0.8d + 560)) + (f × floor(1.2d + 1200)))
```

---

## 5. Tool Specification

### 5.1 Project Structure

```
am4-routemine/
├── main.py                  # CLI entry point
├── config.py                # User settings (game mode, training, CI, etc.)
├── extractors/
│   ├── __init__.py
│   ├── aircraft.py          # Dump all aircraft to DB
│   ├── airports.py          # Dump all airports to DB
│   └── routes.py            # Bulk route calculations
├── database/
│   ├── __init__.py
│   ├── schema.py            # SQLite schema definitions
│   └── queries.py           # Predefined useful queries
├── exporters/
│   ├── __init__.py
│   ├── csv_export.py        # Export tables to CSV
│   └── excel_export.py      # Optional Excel export
├── dashboard/
│   ├── __init__.py
│   └── app.py               # Streamlit dashboard (optional)
├── requirements.txt
├── pyproject.toml
└── README.md
```

### 5.2 Configuration (config.py)

```python
from dataclasses import dataclass, field
from enum import Enum

class GameMode(Enum):
    EASY = "easy"
    REALISM = "realism"

@dataclass
class UserConfig:
    """Player-specific settings that affect calculations."""
    game_mode: GameMode = GameMode.EASY
    cost_index: int = 200              # CI: 0-200
    reputation: float = 87.0           # 0-100
    fuel_price: float = 700.0          # $/barrel (or current market)
    co2_price: float = 120.0           # $/quota
    total_planes_owned: int = 50       # Affects hub costs, route creation costs

    # Training levels (affect costs)
    fuel_training: int = 0             # 0-3
    co2_training: int = 0              # 0-5
    repair_training: int = 0           # 0-5

    # Filters
    min_runway: int = 0                # Filter airports by min runway
    min_profit_per_day: float = 0      # Skip unprofitable routes
    max_flight_time_hours: float = -1  # -1 = no limit
    include_stopovers: bool = True     # Calculate stopovers for out-of-range routes
    aircraft_filter: list[str] = field(default_factory=list)  # Empty = all aircraft
    hub_filter: list[str] = field(default_factory=list)       # Empty = use selected hubs

    # Selected hubs (IATA codes) — if empty, iterate ALL airports as potential hubs
    hubs: list[str] = field(default_factory=list)

    # Performance
    max_workers: int = 4               # Parallel processing threads
```

### 5.3 Database Schema (schema.py)

```sql
-- Aircraft master data
CREATE TABLE aircraft (
    id              INTEGER PRIMARY KEY,
    shortname       TEXT NOT NULL,
    name            TEXT NOT NULL,
    manufacturer    TEXT,
    type            TEXT NOT NULL,  -- PAX, CARGO, VIP
    speed           REAL,
    fuel            REAL,
    co2             REAL,
    cost            INTEGER,
    capacity        INTEGER,
    range_km        INTEGER,
    rwy             INTEGER,
    check_cost      INTEGER,
    maint           INTEGER,
    speed_mod       BOOLEAN,
    fuel_mod        BOOLEAN,
    co2_mod         BOOLEAN,
    fourx_mod       BOOLEAN,
    pilots          INTEGER,
    crew            INTEGER,
    engineers       INTEGER,
    technicians     INTEGER,
    wingspan        INTEGER,
    length          INTEGER
);

-- Airport master data
CREATE TABLE airports (
    id              INTEGER PRIMARY KEY,
    iata            TEXT,
    icao            TEXT,
    name            TEXT,
    fullname        TEXT,
    country         TEXT,
    continent       TEXT,
    lat             REAL,
    lng             REAL,
    rwy             INTEGER,
    rwy_codes       TEXT,
    market          INTEGER,
    hub_cost        INTEGER
);

-- Pre-computed route demands (airport pair → demand)
CREATE TABLE route_demands (
    origin_id       INTEGER NOT NULL,
    dest_id         INTEGER NOT NULL,
    distance_km     REAL,
    demand_y        INTEGER,  -- Economy demand
    demand_j        INTEGER,  -- Business demand
    demand_f        INTEGER,  -- First class demand
    PRIMARY KEY (origin_id, dest_id),
    FOREIGN KEY (origin_id) REFERENCES airports(id),
    FOREIGN KEY (dest_id)   REFERENCES airports(id)
);

-- The big table: route profitability per aircraft
CREATE TABLE route_aircraft (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_id           INTEGER NOT NULL,
    dest_id             INTEGER NOT NULL,
    aircraft_id         INTEGER NOT NULL,

    -- Configuration
    config_y            INTEGER,  -- Economy seats (pax) or large_pct (cargo)
    config_j            INTEGER,  -- Business seats (pax) or heavy_pct (cargo)
    config_f            INTEGER,  -- First seats (pax) or NULL (cargo)
    config_algorithm    TEXT,     -- e.g. "FJY", "AUTO"

    -- Ticket prices (optimal)
    ticket_y            REAL,
    ticket_j            REAL,
    ticket_f            REAL,

    -- Economics per trip
    income              REAL,
    fuel_cost           REAL,
    co2_cost            REAL,
    repair_cost         REAL,
    acheck_cost         REAL,
    profit_per_trip     REAL,

    -- Scheduling
    flight_time_hrs     REAL,
    trips_per_day       INTEGER,
    num_aircraft        INTEGER,

    -- Daily economics (the key metric)
    profit_per_ac_day   REAL,     -- profit_per_trip × trips_per_day
    income_per_ac_day   REAL,

    -- Alliance
    contribution        REAL,

    -- Stopover
    needs_stopover      BOOLEAN,
    stopover_iata       TEXT,
    total_distance      REAL,     -- With stopover if applicable

    -- Constraints
    ci                  INTEGER,
    warnings            TEXT,     -- JSON array of warning strings
    is_valid            BOOLEAN,

    -- Metadata
    game_mode           TEXT,
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (origin_id)   REFERENCES airports(id),
    FOREIGN KEY (dest_id)     REFERENCES airports(id),
    FOREIGN KEY (aircraft_id) REFERENCES aircraft(id)
);

-- Indexes for fast querying
CREATE INDEX idx_ra_origin ON route_aircraft(origin_id);
CREATE INDEX idx_ra_dest ON route_aircraft(dest_id);
CREATE INDEX idx_ra_aircraft ON route_aircraft(aircraft_id);
CREATE INDEX idx_ra_profit ON route_aircraft(profit_per_ac_day DESC);
CREATE INDEX idx_ra_origin_ac ON route_aircraft(origin_id, aircraft_id);
CREATE INDEX idx_ra_valid_profit ON route_aircraft(is_valid, profit_per_ac_day DESC);

-- View: Top routes per hub (most useful query)
CREATE VIEW v_best_routes AS
SELECT
    a_orig.iata AS hub,
    a_dest.iata AS destination,
    a_dest.country AS dest_country,
    ac.shortname AS aircraft,
    ac.type AS ac_type,
    ra.distance_km,
    ra.config_y, ra.config_j, ra.config_f,
    ra.profit_per_trip,
    ra.trips_per_day,
    ra.profit_per_ac_day,
    ra.contribution,
    ra.flight_time_hrs,
    ra.needs_stopover,
    ra.stopover_iata,
    ra.warnings
FROM route_aircraft ra
JOIN airports a_orig ON ra.origin_id = a_orig.id
JOIN airports a_dest ON ra.dest_id = a_dest.id
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.is_valid = 1
ORDER BY ra.profit_per_ac_day DESC;
```

### 5.4 Core Extraction Logic (extractors/routes.py)

```python
"""
Pseudocode for the bulk extraction engine.
Uses the am4 package's RoutesSearch for exhaustive per-hub searches.
"""

import json
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from am4.utils.db import init
from am4.utils.aircraft import Aircraft
from am4.utils.airport import Airport
from am4.utils.route import RoutesSearch, AircraftRoute, Route

# CRITICAL: must be called before any am4 lookups
init()

def extract_all_aircraft(db: sqlite3.Connection):
    """Iterate all aircraft IDs and dump to DB."""
    aircraft_list = []
    for ac_id in range(0, 500):  # Iterate a safe range of IDs
        try:
            result = Aircraft.search(str(ac_id))
            ac = result.ac
            if ac.valid:
                aircraft_list.append(ac.to_dict())
                # INSERT into aircraft table
        except:
            continue
    return aircraft_list

def extract_all_airports(db: sqlite3.Connection):
    """Iterate all airport IDs and dump to DB."""
    airport_list = []
    for ap_id in range(0, 4500):  # ~3900+ airports in the game
        try:
            result = Airport.search(str(ap_id))
            ap = result.ap
            if ap.valid:
                airport_list.append(ap.to_dict())
                # INSERT into airports table
        except:
            continue
    return airport_list

def extract_routes_for_hub(hub_iata: str, aircraft_list: list, config: UserConfig):
    """
    For a given hub, run RoutesSearch against EVERY aircraft
    and collect all valid routes.
    """
    hub_result = Airport.search(hub_iata)
    hub = hub_result.ap

    results = []

    for ac_dict in aircraft_list:
        ac_result = Aircraft.search(ac_dict['shortname'])
        ac = ac_result.ac

        # Skip if aircraft runway > hub runway
        if ac.rwy > hub.rwy:
            continue

        options = AircraftRoute.Options(
            sort_by=AircraftRoute.Options.SortBy.PER_AC_PER_DAY,
            tpd_mode=AircraftRoute.Options.TPDMode.AUTO,
        )

        try:
            search = RoutesSearch(ap0=[hub], ac=ac, options=options)
            destinations = search.get()

            for dest in destinations:
                acr = dest.ac_route
                if not acr.valid:
                    continue

                route_data = {
                    'origin_id': hub.id,
                    'dest_id': dest.airport.id,
                    'aircraft_id': ac.id,
                    'distance_km': acr.route.direct_distance,
                    'income': acr.income,
                    'fuel_cost': acr.fuel,
                    'co2_cost': acr.co2,
                    'repair_cost': acr.repair_cost,
                    'acheck_cost': acr.acheck_cost,
                    'profit_per_trip': acr.profit,
                    'flight_time_hrs': acr.flight_time,
                    'trips_per_day': acr.trips_per_day_per_ac,
                    'num_aircraft': acr.num_ac,
                    'profit_per_ac_day': acr.profit * acr.trips_per_day_per_ac,
                    'income_per_ac_day': acr.income * acr.trips_per_day_per_ac,
                    'contribution': acr.contribution,
                    'ci': acr.ci,
                    'needs_stopover': acr.needs_stopover,
                    'is_valid': acr.valid,
                    'warnings': json.dumps([w.to_str() for w in acr.warnings]),
                }

                # Extract config
                cfg = acr.config.to_dict()
                if ac.type.name == 'CARGO':
                    route_data['config_y'] = cfg.get('l', 0)
                    route_data['config_j'] = cfg.get('h', 0)
                    route_data['config_f'] = None
                else:
                    route_data['config_y'] = cfg.get('y', 0)
                    route_data['config_j'] = cfg.get('j', 0)
                    route_data['config_f'] = cfg.get('f', 0)

                # Extract ticket prices
                ticket = acr.ticket
                # ticket object will have price attributes
                # (exact attribute names depend on type - PaxTicket vs CargoTicket)

                # Stopover info
                if acr.needs_stopover and acr.stopover.exists:
                    route_data['stopover_iata'] = acr.stopover.airport.iata
                    route_data['total_distance'] = acr.stopover.full_distance

                results.append(route_data)

        except Exception as e:
            print(f"  Error: {hub_iata} × {ac.shortname}: {e}")
            continue

    return results

def run_bulk_extraction(config: UserConfig):
    """Main orchestrator."""
    # Step 1: Extract aircraft
    print("[1/3] Extracting aircraft database...")
    aircraft_list = extract_all_aircraft(db)

    # Step 2: Extract airports
    print("[2/3] Extracting airport database...")
    airport_list = extract_all_airports(db)

    # Step 3: For each hub × each aircraft, compute all routes
    hubs = config.hubs if config.hubs else [ap['iata'] for ap in airport_list]
    total = len(hubs)

    print(f"[3/3] Computing routes for {total} hubs × {len(aircraft_list)} aircraft...")

    # Can parallelize across hubs
    for i, hub_iata in enumerate(hubs):
        print(f"  [{i+1}/{total}] Processing hub: {hub_iata}")
        routes = extract_routes_for_hub(hub_iata, aircraft_list, config)
        # Bulk INSERT into route_aircraft table
        print(f"    → {len(routes)} valid routes found")
```

### 5.5 CLI Interface (main.py)

```python
"""
Usage:
    python main.py extract --hubs KHI,DXB,LHR --mode easy --ci 200
    python main.py extract --all-hubs --mode easy
    python main.py export --format csv --output ./exports/
    python main.py query --hub KHI --aircraft b738 --top 20
    python main.py dashboard
"""
import argparse

def main():
    from app.paths import db_path

    DEFAULT_DB_PATH = str(db_path())
    parser = argparse.ArgumentParser(description="AM4 RouteMine — Bulk Route Data Extractor")
    subparsers = parser.add_subparsers(dest="command")

    # Extract command
    extract = subparsers.add_parser("extract", help="Run bulk extraction")
    extract.add_argument("--hubs", type=str, help="Comma-separated IATA codes (e.g. KHI,DXB)")
    extract.add_argument("--all-hubs", action="store_true", help="Process ALL airports as hubs")
    extract.add_argument("--mode", choices=["easy", "realism"], default="easy")
    extract.add_argument("--ci", type=int, default=200, help="Cost Index (0-200)")
    extract.add_argument("--reputation", type=float, default=87.0)
    extract.add_argument("--aircraft", type=str, help="Filter aircraft (e.g. b738,a388)")
    extract.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="SQLite database path")
    extract.add_argument("--workers", type=int, default=4)

    # Export command
    export = subparsers.add_parser("export", help="Export DB to CSV/Excel")
    export.add_argument("--format", choices=["csv", "excel"], default="csv")
    export.add_argument("--output", type=str, default="./exports/")
    export.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    # Query command (quick CLI queries)
    query = subparsers.add_parser("query", help="Quick query against extracted data")
    query.add_argument("--hub", type=str, required=True)
    query.add_argument("--aircraft", type=str)
    query.add_argument("--type", choices=["pax", "cargo", "vip"])
    query.add_argument("--top", type=int, default=20)
    query.add_argument("--sort", choices=["profit", "contribution", "income"], default="profit")
    query.add_argument("--db", type=str, default=DEFAULT_DB_PATH)

    # Dashboard command
    dash = subparsers.add_parser("dashboard", help="Launch FastAPI dashboard")
    dash.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    dash.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    # Route to appropriate handler
```

### 5.6 Predefined Queries (queries.py)

```sql
-- Best routes from a specific hub
SELECT * FROM v_best_routes WHERE hub = ? ORDER BY profit_per_ac_day DESC LIMIT ?;

-- Best aircraft for a specific route
SELECT ac.shortname, ac.name, ra.profit_per_ac_day, ra.trips_per_day,
       ra.config_y, ra.config_j, ra.config_f, ra.flight_time_hrs
FROM route_aircraft ra
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.origin_id = ? AND ra.dest_id = ? AND ra.is_valid = 1
ORDER BY ra.profit_per_ac_day DESC;

-- Top 10 most profitable hubs overall
SELECT a.iata, a.name, a.country,
       COUNT(*) AS total_routes,
       AVG(ra.profit_per_ac_day) AS avg_profit,
       MAX(ra.profit_per_ac_day) AS max_profit
FROM route_aircraft ra
JOIN airports a ON ra.origin_id = a.id
WHERE ra.is_valid = 1
GROUP BY ra.origin_id
ORDER BY avg_profit DESC
LIMIT 10;

-- Routes ranked by alliance contribution
SELECT * FROM v_best_routes ORDER BY contribution DESC LIMIT ?;

-- Aircraft comparison for a hub (avg profit across all routes)
SELECT ac.shortname, ac.type, ac.cost,
       COUNT(*) AS viable_routes,
       AVG(ra.profit_per_ac_day) AS avg_daily_profit,
       SUM(ra.profit_per_ac_day) AS total_daily_profit_potential
FROM route_aircraft ra
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.origin_id = ? AND ra.is_valid = 1
GROUP BY ra.aircraft_id
ORDER BY avg_daily_profit DESC;

-- Routes needing stopovers (for fleet planning)
SELECT * FROM v_best_routes WHERE needs_stopover = 1 ORDER BY profit_per_ac_day DESC;

-- Routes by distance band (short/medium/long haul)
SELECT
    CASE
        WHEN distance_km < 3000 THEN 'short_haul'
        WHEN distance_km < 7000 THEN 'medium_haul'
        ELSE 'long_haul'
    END AS haul_type,
    aircraft, hub, destination,
    profit_per_ac_day, contribution
FROM v_best_routes
ORDER BY haul_type, profit_per_ac_day DESC;
```

---

## 6. Dashboard Specification (Streamlit)

### 6.1 Pages

1. **Hub Explorer** — Select a hub → see all routes sorted by profit, filterable by aircraft type, distance, profit threshold
2. **Aircraft Comparison** — Select an aircraft → see best routes across all hubs
3. **Route Analyzer** — Select origin + destination → see all aircraft ranked for that route
4. **Fleet Planner** — Given a hub + budget, recommend which aircraft to buy and which routes to fly
5. **Contribution Optimizer** — Sort all routes by alliance contribution/profit ratio
6. **Global Heatmap** — Choropleth map showing most profitable destinations from a hub

### 6.2 Key Filters (all pages)

- Hub (IATA dropdown)
- Aircraft (searchable dropdown)
- Aircraft type (PAX/CARGO/VIP)
- Min/Max distance
- Min profit/day
- Show/hide stopover routes
- Sort by: profit/trip, profit/day, contribution, income

---

## 7. Performance Considerations

### 7.1 Scale Estimate

- ~450 aircraft × ~3900 airports = ~1.75M combinations per hub
- Most will be filtered out (range, runway constraints)
- Realistic: ~50-200 viable routes per aircraft per hub
- For 10 hubs × 450 aircraft: ~100K-900K route_aircraft rows
- For ALL hubs (3900): ~200M+ rows — use selective hub mode

### 7.2 Recommendations

- **Start with specific hubs** (your actual hubs in-game) — takes minutes
- **ALL hubs** mode should use `--workers 4+` and expect hours
- SQLite handles 200M rows fine with proper indexes
- Consider WAL mode for concurrent reads during extraction
- Batch INSERTs (1000 rows per transaction)

### 7.3 Incremental Updates

- Store `extracted_at` timestamp on every row
- Re-extract only specific hubs or aircraft when game updates happen
- The `am4` pip package updates when the game changes aircraft/airports

---

## 8. Dependencies

```
# requirements.txt
am4 @ git+https://github.com/abc8747/am4.git@master  # Core game calculations (C++ with pybind11)
streamlit>=1.30.0      # Dashboard (optional)
pandas>=2.0.0          # Data manipulation
openpyxl>=3.1.0        # Excel export (optional)
tqdm>=4.65.0           # Progress bars
rich>=13.0.0           # Pretty CLI output
```

> **Platform Note:** The `am4` package has no prebuilt wheels — it compiles C++ source via
> pybind11 on install. The code uses a lambda pattern that fails under MSVC (Windows) but
> compiles cleanly under GCC (Linux). **Use WSL Ubuntu on Windows.** Requires Python 3.10–3.12,
> `build-essential`, `cmake`, and `python3-dev`.

---

## 9. Getting Started (for Cursor)

> **Important:** Run this in **WSL Ubuntu** on Windows (or native Linux/macOS).
> The `am4` C++ source does not compile under MSVC. See the Setup Guide for details.

```bash
# 1. Install system dependencies (WSL Ubuntu)
sudo apt install -y build-essential cmake python3-dev python3-venv git

# 2. Clone the repo
cd ~ && git clone https://github.com/saqibj/am4-routemine.git && cd am4-routemine

# 3. Set up venv
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip

# 4. Install am4 from GitHub (PyPI version is outdated)
pip install "am4 @ git+https://github.com/abc8747/am4.git@master"

# 5. Install remaining dependencies
pip install pandas tqdm rich streamlit openpyxl

# 6. Verify am4 works (init() MUST be called before any am4 module)
python -c "from am4.utils.db import init; init(); from am4.utils.aircraft import Aircraft; print(Aircraft.search('b738').ac.name)"
# Should print: B737-800

# 7. Run extraction for your hubs
python main.py extract --hubs KHI,DXB --mode easy --ci 200

# 8. Quick query
python main.py query --hub KHI --top 20

# 9. Launch dashboard
python main.py dashboard
```

---

## 10. Important Notes

1. **The `am4` package must be installed from GitHub** — the PyPI version (0.1.8a1) is outdated and has C++ compilation errors on MSVC. Always install from master: `pip install "am4 @ git+https://github.com/abc8747/am4.git@master"`. The installed version will be 0.1.11+.

2. **You MUST call `init()` before using any `am4` module** — `from am4.utils.db import init; init()` loads the aircraft, airport, and route databases into memory. Without it, all lookups will fail. On first call, `init()` auto-downloads parquet data files from GitHub releases.

3. **Use WSL Ubuntu on Windows** — the C++ source uses a lambda ternary that GCC handles but MSVC rejects (error C2446). Linux/macOS work natively. Python 3.10–3.12 required.

4. **`RoutesSearch` is the powerhouse** — it does the exhaustive search from hub(s) to all destinations for a given aircraft in C++. Much faster than Python loops over `AircraftRoute.create()`.

5. **User object** — Some methods accept a `User` object from `am4.utils.game`. This contains game mode, training levels, etc. Check `Game` API docs if the default doesn't match your settings.

6. **Demand data is baked into the package** — stored as a hashtable. The `Route.create()` method returns demand via `pax_demand`. No external API calls needed.

7. **The `to_dict()` methods** on Aircraft, Airport, Route, AircraftRoute all return clean Python dicts — perfect for DB insertion.

8. **Stopover calculation** can be expensive — `Stopover.find_by_efficiency()` searches all airports to find the best intermediate stop. Consider disabling for initial bulk runs.

9. **Game updates** — The AM4 game occasionally rebalances. When this happens, update the `am4` package (`pip install --upgrade "am4 @ git+https://github.com/abc8747/am4.git@master"`) and re-run extraction.
