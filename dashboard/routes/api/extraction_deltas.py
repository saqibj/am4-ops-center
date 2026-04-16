"""Compare route snapshots between two extraction runs."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.db import fetch_all, get_read_db
from dashboard.extraction_delta_diff import SnapshotMap, compute_extraction_delta_view
from dashboard.server import templates

router = APIRouter()

_SNAPSHOT_ROWS_SQL = """
    SELECT s.origin_id, s.dest_id, s.aircraft_id,
           s.profit_per_ac_day, s.is_valid, s.income,
           ho.iata AS hub_iata, hd.iata AS dest_iata, ac.shortname AS ac_short
    FROM route_aircraft_snapshot s
    JOIN airports ho ON s.origin_id = ho.id
    JOIN airports hd ON s.dest_id = hd.id
    JOIN aircraft ac ON s.aircraft_id = ac.id
    WHERE s.run_id = ?
"""


def _snapshot_map(
    conn, run_id: int, hub_filter: str | None
) -> SnapshotMap:
    rows = fetch_all(conn, _SNAPSHOT_ROWS_SQL, [run_id])
    out: SnapshotMap = {}
    hf = hub_filter.strip().upper() if hub_filter and hub_filter.strip() else None
    for r in rows:
        if hf and str(r.get("hub_iata") or "").strip().upper() != hf:
            continue
        k = (int(r["origin_id"]), int(r["dest_id"]), int(r["aircraft_id"]))
        out[k] = dict(r)
    return out


@router.get("/extraction-deltas", response_class=HTMLResponse)
def api_extraction_deltas(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    run_a: int = Query(0, ge=0),
    run_b: int = Query(0, ge=0),
    hub: str = Query(""),
    min_pct: float = Query(5.0, ge=0.0, le=1000.0),
    limit: int = Query(75, ge=10, le=500),
):
    if conn is None:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found.</p>"
        )

    runs = fetch_all(
        conn,
        """
        SELECT id, started_at, finished_at, scope, hubs, route_count, snapshot_count, status
        FROM extraction_runs
        WHERE status = 'ok' AND finished_at IS NOT NULL
        ORDER BY id DESC
        LIMIT 100
        """,
    )
    if len(runs) < 2:
        return templates.TemplateResponse(
            request,
            "partials/extraction_deltas_results.html",
            {
                "runs": runs,
                "need_more_runs": True,
                "run_a": run_a,
                "run_b": run_b,
            },
        )

    ids = [int(r["id"]) for r in runs]
    if run_a <= 0 or run_b <= 0 or run_a not in ids or run_b not in ids:
        run_b = int(ids[0])
        run_a = int(ids[1]) if len(ids) > 1 else int(ids[0])

    older, newer = sorted((int(run_a), int(run_b)))
    if older == newer and len(ids) >= 2:
        newer = int(ids[0])
        older = int(ids[-1])

    ma = _snapshot_map(conn, older, hub)
    mb = _snapshot_map(conn, newer, hub)
    delta = compute_extraction_delta_view(ma, mb, min_pct, limit)

    return templates.TemplateResponse(
        request,
        "partials/extraction_deltas_results.html",
        {
            "runs": runs,
            "need_more_runs": False,
            "run_a": older,
            "run_b": newer,
            "min_pct": min_pct,
            "hub_filter": hub.strip(),
            **delta,
        },
    )
