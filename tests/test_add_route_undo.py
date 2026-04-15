"""Tests for persisted add-route undo (``route_add_undos``)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from database.schema import create_schema
from dashboard.db import fetch_one
from dashboard.services.add_route_undo import (
    create_undo_token,
    consume_undo_token,
    ensure_route_add_undos_schema,
)


def _conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "undo.db"
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    create_schema(c)
    c.execute("INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')")
    c.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    c.commit()
    return c


def test_create_undo_token_60s_expiry(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, rid, None)
        conn.commit()
        row = fetch_one(conn, "SELECT * FROM route_add_undos WHERE token = ?", (tok,))
        assert row is not None
        left = fetch_one(
            conn,
            """
            SELECT CAST(
                (julianday(expires_at) - julianday('now')) * 86400
            AS INTEGER) AS secs
            FROM route_add_undos WHERE token = ?
            """,
            (tok,),
        )
        assert left is not None
        assert 55 <= int(left["secs"]) <= 60
    finally:
        conn.close()


def test_expired_undo_row_not_removed_by_create_token(tmp_path: Path) -> None:
    """Expired log rows are no longer opportunistically deleted (Task 9)."""
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute(
            """
            INSERT INTO route_add_undos (token, route_id, fleet_id, expires_at)
            VALUES ('stale', ?, NULL, datetime('now', '-1 day'))
            """,
            (rid,),
        )
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, rid, None)
        conn.commit()
        assert fetch_one(conn, "SELECT 1 FROM route_add_undos WHERE token = 'stale'") is not None
        assert fetch_one(conn, "SELECT 1 FROM route_add_undos WHERE token = ?", (tok,)) is not None
    finally:
        conn.close()


def test_create_undo_token_trims_to_20_rows(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        for d in range(4, 25):
            conn.execute("INSERT INTO airports (id, iata) VALUES (?, ?)", (d, f"D{d}"))
        conn.commit()
        for d in range(4, 25):
            conn.execute(
                """
                INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned)
                VALUES (1, ?, 1, 1)
                """,
                (d,),
            )
        conn.commit()
        rids = [
            int(x[0])
            for x in conn.execute("SELECT id FROM my_routes ORDER BY id ASC").fetchall()
        ]
        tokens: list[str] = []
        for rid in rids:
            conn.execute("BEGIN IMMEDIATE")
            tokens.append(create_undo_token(conn, rid, None))
            conn.commit()
        n = int(conn.execute("SELECT COUNT(*) FROM route_add_undos").fetchone()[0])
        assert n == 20
        assert fetch_one(conn, "SELECT 1 FROM route_add_undos WHERE token = ?", (tokens[0],)) is None
        assert fetch_one(conn, "SELECT 1 FROM route_add_undos WHERE token = ?", (tokens[-1],)) is not None
    finally:
        conn.close()


def test_consume_valid_deletes_route_fleet_and_link(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 2)"
        )
        fid = int(conn.execute("SELECT id FROM my_fleet").fetchone()[0])
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.execute(
            "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, distance_km, is_valid) "
            "VALUES (1, 2, 1, 100.0, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, rid, fid)
        conn.commit()
        out = consume_undo_token(conn, tok)
        assert out is not None
        assert out["origin"] == "KHI"
        assert out["dest"] == "DXB"
        assert fetch_one(conn, "SELECT 1 FROM my_routes WHERE id = ?", (rid,)) is None
        assert fetch_one(conn, "SELECT 1 FROM my_fleet WHERE id = ?", (fid,)) is None
        assert fetch_one(conn, "SELECT 1 FROM route_aircraft WHERE origin_id=1 AND dest_id=2 AND aircraft_id=1") is None
        assert fetch_one(conn, "SELECT 1 FROM route_add_undos WHERE token = ?", (tok,)) is None
    finally:
        conn.close()


def test_consume_valid_no_fleet_id_deletes_route_and_link_only(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.execute(
            "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, distance_km, is_valid) "
            "VALUES (1, 2, 1, 100.0, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, rid, None)
        conn.commit()
        out = consume_undo_token(conn, tok)
        assert out is not None
        assert fetch_one(conn, "SELECT 1 FROM my_routes WHERE id = ?", (rid,)) is None
        assert fetch_one(conn, "SELECT 1 FROM route_aircraft WHERE origin_id=1 AND dest_id=2 AND aircraft_id=1") is None
    finally:
        conn.close()


def test_consume_expired_returns_none_intact(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute(
            """
            INSERT INTO route_add_undos (token, route_id, fleet_id, expires_at)
            VALUES ('exp', ?, NULL, datetime('now', '-10 seconds'))
            """,
            (rid,),
        )
        conn.commit()
        assert consume_undo_token(conn, "exp") is None
        assert fetch_one(conn, "SELECT 1 FROM my_routes WHERE id = ?", (rid,)) is not None
    finally:
        conn.close()


def test_consume_unknown_returns_none(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        assert consume_undo_token(conn, "00000000-0000-4000-8000-000000000000") is None
    finally:
        conn.close()


def test_consume_preserves_fleet_when_other_route_uses_aircraft(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 5)")
        fid = int(conn.execute("SELECT id FROM my_fleet").fetchone()[0])
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (2, 1, 1, 1)"
        )
        conn.commit()
        r1 = int(
            conn.execute(
                "SELECT id FROM my_routes WHERE origin_id=1 AND dest_id=2"
            ).fetchone()[0]
        )
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, r1, fid)
        conn.commit()
        out = consume_undo_token(conn, tok)
        assert out is not None
        assert fetch_one(conn, "SELECT 1 FROM my_routes WHERE id = ?", (r1,)) is None
        assert fetch_one(conn, "SELECT 1 FROM my_fleet WHERE id = ?", (fid,)) is not None
    finally:
        conn.close()


def test_consume_idempotent(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, rid, None)
        conn.commit()
        assert consume_undo_token(conn, tok) is not None
        assert consume_undo_token(conn, tok) is None
    finally:
        conn.close()


def test_consume_concurrency_one_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
    )
    conn.commit()
    rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
    ensure_route_add_undos_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    tok = create_undo_token(conn, rid, None)
    conn.commit()
    conn.close()

    results: list[dict | None] = []

    def run() -> None:
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        try:
            results.append(consume_undo_token(c, tok))
        finally:
            c.close()

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    wins = [r for r in results if r is not None]
    assert len(wins) == 1
    assert wins[0] is not None
    assert wins[0]["origin"] == "KHI"
