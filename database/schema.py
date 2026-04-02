"""SQLite schema definitions for AM4 RouteMine."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS aircraft (
    id              INTEGER PRIMARY KEY,
    shortname       TEXT NOT NULL,
    name            TEXT NOT NULL,
    manufacturer    TEXT,
    type            TEXT NOT NULL,
    speed           REAL,
    fuel            REAL,
    co2             REAL,
    cost            INTEGER,
    capacity        INTEGER,
    range_km        INTEGER,
    rwy             INTEGER,
    check_cost      INTEGER,
    maint           INTEGER,
    speed_mod       INTEGER,
    fuel_mod        INTEGER,
    co2_mod         INTEGER,
    fourx_mod       INTEGER,
    pilots          INTEGER,
    crew            INTEGER,
    engineers       INTEGER,
    technicians     INTEGER,
    wingspan        INTEGER,
    length          INTEGER
);

CREATE TABLE IF NOT EXISTS airports (
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

CREATE TABLE IF NOT EXISTS route_demands (
    origin_id       INTEGER NOT NULL,
    dest_id         INTEGER NOT NULL,
    distance_km     REAL,
    demand_y        INTEGER,
    demand_j        INTEGER,
    demand_f        INTEGER,
    PRIMARY KEY (origin_id, dest_id),
    FOREIGN KEY (origin_id) REFERENCES airports(id),
    FOREIGN KEY (dest_id)   REFERENCES airports(id)
);

CREATE TABLE IF NOT EXISTS route_aircraft (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_id           INTEGER NOT NULL,
    dest_id             INTEGER NOT NULL,
    aircraft_id         INTEGER NOT NULL,
    distance_km         REAL,

    config_y            INTEGER,
    config_j            INTEGER,
    config_f            INTEGER,
    config_algorithm    TEXT,

    ticket_y            REAL,
    ticket_j            REAL,
    ticket_f            REAL,

    income              REAL,
    fuel_cost           REAL,
    co2_cost            REAL,
    repair_cost         REAL,
    acheck_cost         REAL,
    profit_per_trip     REAL,

    flight_time_hrs     REAL,
    trips_per_day       INTEGER,
    num_aircraft        INTEGER,

    profit_per_ac_day   REAL,
    income_per_ac_day   REAL,

    contribution        REAL,

    needs_stopover      INTEGER,
    stopover_iata       TEXT,
    total_distance      REAL,

    ci                  INTEGER,
    warnings            TEXT,
    is_valid            INTEGER,

    game_mode           TEXT,
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (origin_id)   REFERENCES airports(id),
    FOREIGN KEY (dest_id)     REFERENCES airports(id),
    FOREIGN KEY (aircraft_id) REFERENCES aircraft(id)
);

CREATE INDEX IF NOT EXISTS idx_ra_origin ON route_aircraft(origin_id);
CREATE INDEX IF NOT EXISTS idx_ra_dest ON route_aircraft(dest_id);
CREATE INDEX IF NOT EXISTS idx_ra_aircraft ON route_aircraft(aircraft_id);
CREATE INDEX IF NOT EXISTS idx_ra_profit ON route_aircraft(profit_per_ac_day DESC);
CREATE INDEX IF NOT EXISTS idx_ra_origin_ac ON route_aircraft(origin_id, aircraft_id);
CREATE INDEX IF NOT EXISTS idx_ra_valid_profit ON route_aircraft(is_valid, profit_per_ac_day DESC);

DROP TABLE IF EXISTS fleet_route_assignment;
DROP TABLE IF EXISTS fleet_aircraft;

CREATE TABLE IF NOT EXISTS my_fleet (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    aircraft_id     INTEGER NOT NULL UNIQUE,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1 AND quantity <= 999),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (aircraft_id) REFERENCES aircraft(id)
);

CREATE INDEX IF NOT EXISTS idx_my_fleet_ac ON my_fleet(aircraft_id);

CREATE TABLE IF NOT EXISTS my_routes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_id       INTEGER NOT NULL,
    dest_id         INTEGER NOT NULL,
    aircraft_id     INTEGER NOT NULL,
    num_assigned    INTEGER NOT NULL DEFAULT 1 CHECK (num_assigned >= 1 AND num_assigned <= 999),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (origin_id) REFERENCES airports(id),
    FOREIGN KEY (dest_id) REFERENCES airports(id),
    FOREIGN KEY (aircraft_id) REFERENCES aircraft(id),
    UNIQUE(origin_id, dest_id, aircraft_id)
);

CREATE INDEX IF NOT EXISTS idx_my_routes_origin ON my_routes(origin_id);
CREATE INDEX IF NOT EXISTS idx_my_routes_dest ON my_routes(dest_id);
CREATE INDEX IF NOT EXISTS idx_my_routes_ac ON my_routes(aircraft_id);

DROP VIEW IF EXISTS v_my_fleet;
CREATE VIEW v_my_fleet AS
SELECT
    mf.id,
    mf.aircraft_id,
    mf.quantity,
    mf.notes,
    mf.created_at,
    mf.updated_at,
    ac.shortname,
    ac.name AS ac_name,
    ac.type AS ac_type,
    ac.cost
FROM my_fleet mf
JOIN aircraft ac ON mf.aircraft_id = ac.id;

DROP VIEW IF EXISTS v_my_routes;
CREATE VIEW v_my_routes AS
SELECT
    mr.id,
    mr.origin_id,
    mr.dest_id,
    mr.aircraft_id,
    mr.num_assigned,
    mr.notes,
    mr.created_at,
    mr.updated_at,
    ho.iata AS hub,
    hd.iata AS destination,
    ac.shortname AS aircraft,
    ac.name AS ac_name
FROM my_routes mr
JOIN airports ho ON mr.origin_id = ho.id
JOIN airports hd ON mr.dest_id = hd.id
JOIN aircraft ac ON mr.aircraft_id = ac.id;

DROP VIEW IF EXISTS v_best_routes;
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
    ra.income_per_ac_day,
    ra.contribution,
    ra.flight_time_hrs,
    ra.needs_stopover,
    ra.stopover_iata,
    ra.warnings
FROM route_aircraft ra
JOIN airports a_orig ON ra.origin_id = a_orig.id
JOIN airports a_dest ON ra.dest_id = a_dest.id
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.is_valid = 1;
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def clear_route_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM route_aircraft")
    conn.execute("DELETE FROM route_demands")
    conn.commit()


def replace_master_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM aircraft")
    conn.execute("DELETE FROM airports")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
