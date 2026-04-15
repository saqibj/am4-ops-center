"""Recent adds strip (``route_add_undos`` log + ``delete_recent_add``)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from database.schema import create_schema
from dashboard.db import fetch_one
from dashboard.services.add_route_undo import (
    create_undo_token,
    delete_recent_add,
    ensure_route_add_undos_schema,
    list_recent_adds,
)


def _conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "ra.db"
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    create_schema(c)
    c.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'a333', 'A330-300', 'PAX')"
    )
    for iid, code in [(1, "KHI"), (2, "DXB"), (3, "JFK")]:
        c.execute("INSERT INTO airports (id, iata) VALUES (?, ?)", (iid, code))
    c.commit()
    return c


def test_list_recent_adds_join_and_order(tmp_path: Path) -> None:
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
        rows = list_recent_adds(conn, limit=5)
        assert len(rows) == 1
        assert rows[0]["token"] == tok
        assert rows[0]["origin_iata"] == "KHI"
        assert rows[0]["dest_iata"] == "DXB"
        assert rows[0]["aircraft_short"] == "a333"
        r2 = list_recent_adds(conn, limit=1)
        assert len(r2) == 1
    finally:
        conn.close()


def test_list_recent_adds_respects_limit(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        for d in range(4, 9):
            conn.execute("INSERT INTO airports (id, iata) VALUES (?, ?)", (d, f"X{d}"))
        conn.commit()
        for d in range(4, 9):
            conn.execute(
                "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, ?, 1, 1)",
                (d,),
            )
        conn.commit()
        rids = [int(r[0]) for r in conn.execute("SELECT id FROM my_routes ORDER BY id").fetchall()]
        for rid in rids:
            conn.execute("BEGIN IMMEDIATE")
            create_undo_token(conn, rid, None)
            conn.commit()
        rows = list_recent_adds(conn, limit=2)
        assert len(rows) == 2
    finally:
        conn.close()


def test_list_recent_adds_filters_missing_route(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        create_undo_token(conn, rid, None)
        conn.commit()
        conn.execute("DELETE FROM my_routes WHERE id = ?", (rid,))
        conn.commit()
        assert list_recent_adds(conn, limit=5) == []
    finally:
        conn.close()


def test_fleet_safe_to_remove(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 3)")
        fid = int(conn.execute("SELECT id FROM my_fleet").fetchone()[0])
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 3, 1, 1)"
        )
        conn.commit()
        r1 = int(
            conn.execute("SELECT id FROM my_routes WHERE dest_id = 2").fetchone()[0]
        )
        conn.execute("BEGIN IMMEDIATE")
        create_undo_token(conn, r1, fid)
        conn.commit()
        row = list_recent_adds(conn, limit=5)[0]
        assert row["fleet_safe_to_remove"] is False
    finally:
        conn.close()


def test_delete_recent_add_no_fleet(tmp_path: Path) -> None:
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
        out = delete_recent_add(conn, tok, remove_fleet=False)
        assert out is not None
        assert out["fleet_removed"] is False
        assert fetch_one(conn, "SELECT 1 FROM my_routes WHERE id = ?", (rid,)) is None
        assert fetch_one(conn, "SELECT 1 FROM route_add_undos WHERE token = ?", (tok,)) is None
    finally:
        conn.close()


def test_delete_recent_add_with_fleet_safe(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 2)")
        fid = int(conn.execute("SELECT id FROM my_fleet").fetchone()[0])
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.commit()
        rid = int(conn.execute("SELECT id FROM my_routes").fetchone()[0])
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, rid, fid)
        conn.commit()
        out = delete_recent_add(conn, tok, remove_fleet=True)
        assert out is not None
        assert out["fleet_removed"] is True
        assert fetch_one(conn, "SELECT 1 FROM my_fleet WHERE id = ?", (fid,)) is None
    finally:
        conn.close()


def test_delete_recent_add_fleet_override_when_unsafe(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 3)")
        fid = int(conn.execute("SELECT id FROM my_fleet").fetchone()[0])
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
        )
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 3, 1, 1)"
        )
        conn.commit()
        r1 = int(
            conn.execute("SELECT id FROM my_routes WHERE dest_id = 2").fetchone()[0]
        )
        conn.execute("BEGIN IMMEDIATE")
        tok = create_undo_token(conn, r1, fid)
        conn.commit()
        out = delete_recent_add(conn, tok, remove_fleet=True)
        assert out is not None
        assert out["fleet_removed"] is False
        assert fetch_one(conn, "SELECT 1 FROM my_fleet WHERE id = ?", (fid,)) is not None
    finally:
        conn.close()


def test_delete_recent_add_unknown_token(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    try:
        ensure_route_add_undos_schema(conn)
        assert delete_recent_add(conn, "00000000-0000-4000-8000-000000000000", False) is None
    finally:
        conn.close()


def test_delete_recent_add_idempotent(tmp_path: Path) -> None:
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
        assert delete_recent_add(conn, tok, False) is not None
        assert delete_recent_add(conn, tok, False) is None
    finally:
        conn.close()
