"""CLI: my_fleet / my_routes CSV and recommend (see PRD/am4-routemine-FLEET-SPEC.md)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from commands.fleet_recommend import fleet_recommend_rows
from database.schema import create_schema, get_connection


def _norm_keys(row: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in row.items():
        if k is None:
            continue
        key = str(k).strip().lower()
        out[key] = ("" if v is None else str(v)).strip()
    return out


def _aircraft_id(conn, shortname: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
        [shortname],
    ).fetchone()
    return int(row[0]) if row else None


def _airport_id(conn, iata: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
        [iata],
    ).fetchone()
    return int(row[0]) if row else None


def fleet_import(db_path: str, file_path: str, *, mode: str = "merge") -> None:
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    conn = get_connection(db_path)
    create_schema(conn)
    errors: list[str] = []
    n_ok = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("Error: empty CSV", file=sys.stderr)
            sys.exit(2)
        for lineno, raw in enumerate(reader, start=2):
            row = _norm_keys(raw)
            sn = row.get("shortname", "")
            if not sn:
                errors.append(f"line {lineno}: missing shortname")
                continue
            try:
                cnt = int(row.get("count", "0") or 0)
            except ValueError:
                errors.append(f"line {lineno}: invalid count")
                continue
            if cnt < 1 or cnt > 999:
                errors.append(f"line {lineno}: count must be 1–999")
                continue
            aid = _aircraft_id(conn, sn)
            if aid is None:
                errors.append(f"line {lineno}: unknown aircraft shortname {sn!r}")
                continue
            notes = row.get("notes") or None
            if mode == "replace":
                conn.execute(
                    """
                    INSERT INTO my_fleet (aircraft_id, quantity, notes, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(aircraft_id) DO UPDATE SET
                        quantity = excluded.quantity,
                        notes = COALESCE(excluded.notes, my_fleet.notes),
                        updated_at = datetime('now')
                    """,
                    (aid, cnt, notes),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO my_fleet (aircraft_id, quantity, notes, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(aircraft_id) DO UPDATE SET
                        quantity = MIN(999, my_fleet.quantity + excluded.quantity),
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_fleet.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (aid, cnt, notes),
                )
            n_ok += 1
    conn.commit()
    conn.close()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"Imported {n_ok} fleet row(s).")
    if errors:
        sys.exit(1)


def fleet_export(db_path: str, output_path: str) -> None:
    conn = get_connection(db_path)
    create_schema(conn)
    rows = conn.execute(
        "SELECT shortname, quantity, COALESCE(notes, '') AS notes FROM v_my_fleet ORDER BY shortname COLLATE NOCASE"
    ).fetchall()
    conn.close()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["shortname", "count", "notes"])
        for r in rows:
            w.writerow([r[0], r[1], r[2]])
    print(f"Wrote {len(rows)} row(s) to {out}")


def fleet_list(db_path: str) -> None:
    conn = get_connection(db_path)
    create_schema(conn)
    rows = conn.execute(
        """
        SELECT shortname, quantity, COALESCE(notes, ''), ac_name
        FROM v_my_fleet
        ORDER BY shortname COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    if not rows:
        print("No fleet rows.")
        return
    print("shortname\tquantity\tnotes\tname")
    for r in rows:
        print(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}")


def routes_import(db_path: str, file_path: str, *, mode: str = "merge") -> None:
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    conn = get_connection(db_path)
    create_schema(conn)
    errors: list[str] = []
    n_ok = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("Error: empty CSV", file=sys.stderr)
            sys.exit(2)
        for lineno, raw in enumerate(reader, start=2):
            row = _norm_keys(raw)
            hub = row.get("hub", "")
            dest = row.get("destination", "")
            ac = row.get("aircraft", "")
            if not hub or not dest or not ac:
                errors.append(f"line {lineno}: hub, destination, and aircraft required")
                continue
            try:
                n = int(row.get("num_assigned", "1") or 1)
            except ValueError:
                errors.append(f"line {lineno}: invalid num_assigned")
                continue
            if n < 1 or n > 999:
                errors.append(f"line {lineno}: num_assigned must be 1–999")
                continue
            oid = _airport_id(conn, hub)
            did = _airport_id(conn, dest)
            aid = _aircraft_id(conn, ac)
            if oid is None:
                errors.append(f"line {lineno}: unknown hub IATA {hub!r}")
                continue
            if did is None:
                errors.append(f"line {lineno}: unknown destination IATA {dest!r}")
                continue
            if aid is None:
                errors.append(f"line {lineno}: unknown aircraft {ac!r}")
                continue
            notes = row.get("notes") or None
            if mode == "replace":
                conn.execute(
                    """
                    INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                        num_assigned = excluded.num_assigned,
                        notes = COALESCE(excluded.notes, my_routes.notes),
                        updated_at = datetime('now')
                    """,
                    (oid, did, aid, n, notes),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                        num_assigned = MIN(999, my_routes.num_assigned + excluded.num_assigned),
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_routes.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (oid, did, aid, n, notes),
                )
            n_ok += 1
    conn.commit()
    conn.close()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"Imported {n_ok} route row(s).")
    if errors:
        sys.exit(1)


def routes_export(db_path: str, output_path: str) -> None:
    conn = get_connection(db_path)
    create_schema(conn)
    rows = conn.execute(
        """
        SELECT hub, destination, aircraft, num_assigned, COALESCE(notes, '') AS notes
        FROM v_my_routes
        ORDER BY hub COLLATE NOCASE, destination COLLATE NOCASE, aircraft COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hub", "destination", "aircraft", "num_assigned", "notes"])
        for r in rows:
            w.writerow([r[0], r[1], r[2], r[3], r[4]])
    print(f"Wrote {len(rows)} row(s) to {out}")


def recommend(
    db_path: str,
    hub: str,
    budget: int,
    top_n: int,
    *,
    hide_owned: bool = False,
) -> None:
    conn = get_connection(db_path)
    try:
        rows, err = fleet_recommend_rows(
            conn, hub, int(budget), int(top_n), hide_owned=hide_owned
        )
    finally:
        conn.close()
    if err == "unknown_hub":
        print(f"Unknown hub IATA: {hub}", file=sys.stderr)
        sys.exit(2)
    if not rows:
        print("No aircraft match this hub and budget (or no extraction data).")
        return
    print(
        "shortname\tname\ttype\tcost\towned\troutes\tavg_profit_day\tbest_profit_day\t"
        "days_be_avg\tdays_be_best"
    )
    for r in rows:
        avg = float(r.get("avg_daily_profit") or 0)
        owned = int(r.get("owned_qty") or 0)
        be_avg = r.get("days_to_breakeven_avg")
        be_best = r.get("days_to_breakeven_best")
        be_avg_out = "" if be_avg is None else be_avg
        be_best_out = "" if be_best is None else be_best
        print(
            f"{r['shortname']}\t{r['name']}\t{r['type']}\t{int(r.get('cost') or 0)}\t{owned}\t{r['routes']}\t"
            f"{round(avg, 2)}\t{round(float(r.get('best_daily_profit') or 0), 2)}\t"
            f"{be_avg_out}\t{be_best_out}"
        )
