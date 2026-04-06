"""SQLite schema definitions for AM4 RouteMine."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, fields
from pathlib import Path

from config import GameMode, UserConfig

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS aircraft (
    id              INTEGER PRIMARY KEY,
    shortname       TEXT NOT NULL UNIQUE,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_airports_iata_unique
    ON airports(iata) WHERE iata IS NOT NULL AND TRIM(iata) != '';

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
    fuel_price          REAL,
    co2_price           REAL,
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (origin_id)   REFERENCES airports(id),
    FOREIGN KEY (dest_id)     REFERENCES airports(id),
    FOREIGN KEY (aircraft_id) REFERENCES aircraft(id),
    UNIQUE(origin_id, dest_id, aircraft_id)
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

CREATE TABLE IF NOT EXISTS my_hubs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_id          INTEGER NOT NULL UNIQUE,
    notes               TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_extracted_at   TIMESTAMP,
    last_extract_status TEXT,
    last_extract_error  TEXT,
    FOREIGN KEY (airport_id) REFERENCES airports(id)
);

CREATE INDEX IF NOT EXISTS idx_my_hubs_airport ON my_hubs(airport_id);

CREATE TABLE IF NOT EXISTS extract_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

DROP VIEW IF EXISTS v_my_hubs;
CREATE VIEW v_my_hubs AS
SELECT
    mh.id,
    mh.airport_id,
    a.iata,
    a.icao,
    a.name,
    a.fullname,
    a.country,
    a.continent,
    a.market,
    a.hub_cost,
    mh.notes,
    mh.is_active,
    mh.last_extracted_at,
    mh.last_extract_status,
    mh.last_extract_error
FROM my_hubs mh
JOIN airports a ON mh.airport_id = a.id;

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
    ac.name AS ac_name,
    ho.name AS hub_name,
    ho.country AS hub_country,
    hd.name AS dest_name,
    hd.fullname AS dest_fullname,
    hd.country AS dest_country
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
    ra.warnings,
    a_orig.name AS hub_name,
    a_orig.country AS hub_country,
    a_dest.name AS dest_name,
    a_dest.fullname AS dest_fullname
FROM route_aircraft ra
JOIN airports a_orig ON ra.origin_id = a_orig.id
JOIN airports a_dest ON ra.dest_id = a_dest.id
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.is_valid = 1;
"""

# Recreate after migrations that DROP/rename master tables (views can become invalid).
DASHBOARD_VIEWS_SQL = """
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

DROP VIEW IF EXISTS v_my_hubs;
CREATE VIEW v_my_hubs AS
SELECT
    mh.id,
    mh.airport_id,
    a.iata,
    a.icao,
    a.name,
    a.fullname,
    a.country,
    a.continent,
    a.market,
    a.hub_cost,
    mh.notes,
    mh.is_active,
    mh.last_extracted_at,
    mh.last_extract_status,
    mh.last_extract_error
FROM my_hubs mh
JOIN airports a ON mh.airport_id = a.id;

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
    ac.name AS ac_name,
    ho.name AS hub_name,
    ho.country AS hub_country,
    hd.name AS dest_name,
    hd.fullname AS dest_fullname,
    hd.country AS dest_country
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
    ra.warnings,
    a_orig.name AS hub_name,
    a_orig.country AS hub_country,
    a_dest.name AS dest_name,
    a_dest.fullname AS dest_fullname
FROM route_aircraft ra
JOIN airports a_orig ON ra.origin_id = a_orig.id
JOIN airports a_dest ON ra.dest_id = a_dest.id
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.is_valid = 1;
"""


def _recreate_dashboard_views(conn: sqlite3.Connection) -> None:
    conn.executescript(DASHBOARD_VIEWS_SQL)


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


def save_extract_config(conn: sqlite3.Connection, cfg: UserConfig) -> None:
    """Persist the UserConfig used for an extraction or hub refresh."""
    payload = asdict(cfg)
    payload["game_mode"] = cfg.game_mode.value
    for k, v in payload.items():
        conn.execute(
            """
            INSERT INTO extract_metadata (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (k, json.dumps(v)),
        )
    conn.commit()


def load_extract_config(conn: sqlite3.Connection) -> UserConfig | None:
    """Load UserConfig from the last save. Returns None if no rows."""
    rows = conn.execute("SELECT key, value FROM extract_metadata").fetchall()
    if not rows:
        return None
    data: dict = {r[0]: json.loads(r[1]) for r in rows}
    if "game_mode" in data:
        data["game_mode"] = GameMode(data["game_mode"])
    known = {f.name for f in fields(UserConfig)}
    data = {k: v for k, v in data.items() if k in known}
    return UserConfig(**data)


def derived_total_planes(conn: sqlite3.Connection) -> int | None:
    """Return SUM(quantity) from my_fleet, or None if empty or table missing."""
    try:
        row = conn.execute("SELECT COALESCE(SUM(quantity), 0) FROM my_fleet").fetchone()
    except sqlite3.OperationalError:
        return None
    n = int(row[0] or 0) if row else 0
    return n if n > 0 else None


def clear_route_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM route_aircraft")
    conn.execute("DELETE FROM route_demands")
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'route_aircraft'")
    conn.commit()


def replace_master_tables(conn: sqlite3.Connection) -> None:
    """Clear aircraft and airports master tables in FK-safe order.

    Delete route_aircraft and route_demands first so removing aircraft/airports
    does not leave dangling references. User tables (my_fleet, my_routes, my_hubs)
    still reference aircraft/airports by ID; am4 repopulates deterministic IDs on
    the next extract.

    Foreign keys are always re-enabled in ``finally`` so a failed delete cannot
    leave the connection with enforcement permanently off.
    """
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        conn.execute("DELETE FROM route_aircraft")
        conn.execute("DELETE FROM route_demands")
        conn.execute("DELETE FROM aircraft")
        conn.execute("DELETE FROM airports")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('route_aircraft', 'aircraft', 'airports')"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _reassign_airport_id(conn: sqlite3.Connection, old_id: int, new_id: int) -> None:
    if old_id == new_id:
        return
    conn.execute("UPDATE route_aircraft SET origin_id = ? WHERE origin_id = ?", (new_id, old_id))
    conn.execute("UPDATE route_aircraft SET dest_id = ? WHERE dest_id = ?", (new_id, old_id))
    conn.execute("UPDATE my_routes SET origin_id = ? WHERE origin_id = ?", (new_id, old_id))
    conn.execute("UPDATE my_routes SET dest_id = ? WHERE dest_id = ?", (new_id, old_id))
    old_hub = conn.execute("SELECT id FROM my_hubs WHERE airport_id = ?", (old_id,)).fetchone()
    new_hub = conn.execute("SELECT id FROM my_hubs WHERE airport_id = ?", (new_id,)).fetchone()
    if old_hub and new_hub:
        conn.execute("DELETE FROM my_hubs WHERE airport_id = ?", (old_id,))
    elif old_hub:
        conn.execute("UPDATE my_hubs SET airport_id = ? WHERE airport_id = ?", (new_id, old_id))


def _dedupe_airports_for_iata_index(conn: sqlite3.Connection) -> None:
    while True:
        row = conn.execute(
            """
            SELECT UPPER(TRIM(iata)) FROM airports
            WHERE iata IS NOT NULL AND TRIM(iata) != ''
            GROUP BY UPPER(TRIM(iata))
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if not row:
            break
        u = row[0]
        ids = [
            int(r[0])
            for r in conn.execute(
                """
                SELECT id FROM airports
                WHERE iata IS NOT NULL AND TRIM(iata) != ''
                  AND UPPER(TRIM(iata)) = ?
                ORDER BY id
                """,
                (u,),
            ).fetchall()
        ]
        keep = ids[0]
        for oid in ids[1:]:
            _reassign_airport_id(conn, oid, keep)
            conn.execute("DELETE FROM airports WHERE id = ?", (oid,))


def _migrate_airports_iata_unique(conn: sqlite3.Connection) -> None:
    has_idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_airports_iata_unique'"
    ).fetchone()
    if has_idx:
        return
    _dedupe_airports_for_iata_index(conn)
    conn.execute(
        """
        CREATE UNIQUE INDEX idx_airports_iata_unique
            ON airports(iata) WHERE iata IS NOT NULL AND TRIM(iata) != ''
        """
    )


def _reassign_aircraft_id(conn: sqlite3.Connection, old_id: int, new_id: int) -> None:
    if old_id == new_id:
        return
    conn.execute("UPDATE route_aircraft SET aircraft_id = ? WHERE aircraft_id = ?", (new_id, old_id))
    conn.execute("UPDATE my_routes SET aircraft_id = ? WHERE aircraft_id = ?", (new_id, old_id))
    row_old = conn.execute("SELECT quantity FROM my_fleet WHERE aircraft_id = ?", (old_id,)).fetchone()
    row_new = conn.execute("SELECT quantity FROM my_fleet WHERE aircraft_id = ?", (new_id,)).fetchone()
    if row_old and row_new:
        q = min(999, int(row_new[0]) + int(row_old[0]))
        conn.execute("UPDATE my_fleet SET quantity = ? WHERE aircraft_id = ?", (q, new_id))
        conn.execute("DELETE FROM my_fleet WHERE aircraft_id = ?", (old_id,))
    elif row_old:
        conn.execute("UPDATE my_fleet SET aircraft_id = ? WHERE aircraft_id = ?", (new_id, old_id))


def _dedupe_aircraft_by_shortname(conn: sqlite3.Connection) -> None:
    while True:
        row = conn.execute(
            """
            SELECT LOWER(shortname) FROM aircraft
            GROUP BY LOWER(shortname)
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if not row:
            break
        sn = row[0]
        ids = [
            int(r[0])
            for r in conn.execute(
                "SELECT id FROM aircraft WHERE LOWER(shortname) = ? ORDER BY id",
                (sn,),
            ).fetchall()
        ]
        keep = ids[0]
        for rid in ids[1:]:
            _reassign_aircraft_id(conn, rid, keep)
            conn.execute("DELETE FROM aircraft WHERE id = ?", (rid,))


ROUTE_AIRCRAFT_NEW_TABLE_SQL = """
CREATE TABLE route_aircraft__m (
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
    fuel_price          REAL,
    co2_price           REAL,
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (origin_id)   REFERENCES airports(id),
    FOREIGN KEY (dest_id)     REFERENCES airports(id),
    FOREIGN KEY (aircraft_id) REFERENCES aircraft(id),
    UNIQUE(origin_id, dest_id, aircraft_id)
);
"""

ROUTE_AIRCRAFT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_ra_origin ON route_aircraft(origin_id);
CREATE INDEX IF NOT EXISTS idx_ra_dest ON route_aircraft(dest_id);
CREATE INDEX IF NOT EXISTS idx_ra_aircraft ON route_aircraft(aircraft_id);
CREATE INDEX IF NOT EXISTS idx_ra_profit ON route_aircraft(profit_per_ac_day DESC);
CREATE INDEX IF NOT EXISTS idx_ra_origin_ac ON route_aircraft(origin_id, aircraft_id);
CREATE INDEX IF NOT EXISTS idx_ra_valid_profit ON route_aircraft(is_valid, profit_per_ac_day DESC);
"""

AIRCRAFT_NEW_TABLE_SQL = """
CREATE TABLE aircraft__m (
    id              INTEGER PRIMARY KEY,
    shortname       TEXT NOT NULL UNIQUE,
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
"""


def _aircraft_table_has_shortname_unique(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='aircraft'"
    ).fetchone()
    if not row or not row[0]:
        return False
    return bool(re.search(r"shortname\s+TEXT\s+NOT\s+NULL\s+UNIQUE", row[0], re.IGNORECASE))


def _migrate_aircraft_shortname_unique(conn: sqlite3.Connection) -> None:
    if _aircraft_table_has_shortname_unique(conn):
        return
    _dedupe_aircraft_by_shortname(conn)
    conn.executescript(
        "DROP TABLE IF EXISTS aircraft__m;\n"
        + AIRCRAFT_NEW_TABLE_SQL
        + "INSERT INTO aircraft__m SELECT * FROM aircraft;\n"
        "DROP TABLE aircraft;\n"
        "ALTER TABLE aircraft__m RENAME TO aircraft;\n"
    )


def _route_aircraft_table_has_unique(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='route_aircraft'"
    ).fetchone()
    if not row or not row[0]:
        return False
    return "UNIQUE(origin_id, dest_id, aircraft_id)" in row[0]


def _migrate_route_aircraft_unique(conn: sqlite3.Connection) -> None:
    if _route_aircraft_table_has_unique(conn):
        return
    conn.execute(
        """
        DELETE FROM route_aircraft
        WHERE id NOT IN (
            SELECT MAX(id) FROM route_aircraft
            GROUP BY origin_id, dest_id, aircraft_id
        )
        """
    )
    conn.executescript(
        "DROP TABLE IF EXISTS route_aircraft__m;\n"
        + ROUTE_AIRCRAFT_NEW_TABLE_SQL
        + "INSERT INTO route_aircraft__m SELECT * FROM route_aircraft;\n"
        "DROP TABLE route_aircraft;\n"
        "ALTER TABLE route_aircraft__m RENAME TO route_aircraft;\n"
    )
    conn.executescript(ROUTE_AIRCRAFT_INDEX_SQL)


def _route_aircraft_has_column(conn: sqlite3.Connection, col: str) -> bool:
    cur = conn.execute("PRAGMA table_info(route_aircraft)")
    return any(row[1] == col for row in cur.fetchall())


def ensure_route_aircraft_baseline_prices(conn: sqlite3.Connection) -> None:
    """Add ``fuel_price`` / ``co2_price`` (extraction baselines) and backfill NULLs.

    Safe to call on every dashboard DB open; idempotent.
    """
    if not _route_aircraft_has_column(conn, "fuel_price"):
        conn.execute("ALTER TABLE route_aircraft ADD COLUMN fuel_price REAL")
    if not _route_aircraft_has_column(conn, "co2_price"):
        conn.execute("ALTER TABLE route_aircraft ADD COLUMN co2_price REAL")
    cfg = load_extract_config(conn)
    fp = float(cfg.fuel_price) if cfg else UserConfig().fuel_price
    cp = float(cfg.co2_price) if cfg else UserConfig().co2_price
    conn.execute("UPDATE route_aircraft SET fuel_price = ? WHERE fuel_price IS NULL", (fp,))
    conn.execute("UPDATE route_aircraft SET co2_price = ? WHERE co2_price IS NULL", (cp,))
    conn.commit()


def migrate_add_unique_constraints(conn: sqlite3.Connection) -> None:
    """Apply unique constraints to DBs created before the schema update. Safe to run multiple times."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        _migrate_airports_iata_unique(conn)
        _migrate_aircraft_shortname_unique(conn)
        ensure_route_aircraft_baseline_prices(conn)
        _migrate_route_aircraft_unique(conn)
        _recreate_dashboard_views(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
