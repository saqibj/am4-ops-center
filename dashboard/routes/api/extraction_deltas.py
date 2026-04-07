"""Compare route snapshots between two extraction runs."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.db import fetch_all, get_db
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
) -> dict[tuple[int, int, int], dict]:
    rows = fetch_all(conn, _SNAPSHOT_ROWS_SQL, [run_id])
    out: dict[tuple[int, int, int], dict] = {}
    hf = hub_filter.strip().upper() if hub_filter and hub_filter.strip() else None
    for r in rows:
        if hf and str(r.get("hub_iata") or "").strip().upper() != hf:
            continue
        k = (int(r["origin_id"]), int(r["dest_id"]), int(r["aircraft_id"]))
        out[k] = dict(r)
    return out


def _pct_change(pa: float | None, pb: float | None) -> float:
    a = float(pa or 0)
    b = float(pb or 0)
    if abs(a) < 1e-9:
        return float("inf") if abs(b) > 1e-9 else 0.0
    return (b - a) / abs(a) * 100.0


@router.get("/extraction-deltas", response_class=HTMLResponse)
def api_extraction_deltas(
    request: Request,
    run_a: int = Query(0, ge=0),
    run_b: int = Query(0, ge=0),
    hub: str = Query(""),
    min_pct: float = Query(5.0, ge=0.0, le=1000.0),
    limit: int = Query(75, ge=10, le=500),
):
    try:
        conn = get_db()
    except FileNotFoundError:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found.</p>"
        )

    try:
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

        keys_a = set(ma.keys())
        keys_b = set(mb.keys())

        appeared = [mb[k] for k in sorted(keys_b - keys_a)]
        disappeared = [ma[k] for k in sorted(keys_a - keys_b)]

        movers: list[dict] = []
        flip_to_profit = 0
        flip_to_loss = 0
        for k in keys_a & keys_b:
            ra, rb = ma[k], mb[k]
            pa = float(ra.get("profit_per_ac_day") or 0)
            pb = float(rb.get("profit_per_ac_day") or 0)
            va = int(ra.get("is_valid") or 0)
            vb = int(rb.get("is_valid") or 0)
            if va == 0 and vb == 1 and pb > 0:
                flip_to_profit += 1
            if va == 1 and vb == 0:
                flip_to_loss += 1
            pct = _pct_change(pa, pb)
            if pct == float("inf") or abs(pct) >= min_pct:
                movers.append(
                    {
                        "hub": ra["hub_iata"],
                        "dest": ra["dest_iata"],
                        "ac": ra["ac_short"],
                        "profit_a": pa,
                        "profit_b": pb,
                        "pct": pct,
                        "pct_display": "∞" if pct == float("inf") else f"{pct:+.1f}%",
                        "valid_a": va,
                        "valid_b": vb,
                    }
                )
        movers.sort(key=lambda x: abs(x["profit_b"] - x["profit_a"]), reverse=True)

        hub_deltas: dict[str, list[float]] = {}
        for k in keys_a & keys_b:
            ra, rb = ma[k], mb[k]
            h = str(ra.get("hub_iata") or "")
            pa = float(ra.get("profit_per_ac_day") or 0)
            pb = float(rb.get("profit_per_ac_day") or 0)
            hub_deltas.setdefault(h, []).append(pb - pa)

        hub_avg = [
            {
                "hub": h,
                "avg_delta": sum(v) / len(v) if v else 0.0,
                "n": len(v),
            }
            for h, v in sorted(hub_deltas.items(), key=lambda x: -abs(sum(x[1]) / len(x[1]) if x[1] else 0))
        ][:20]

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
                "appeared": appeared[:limit],
                "disappeared": disappeared[:limit],
                "movers": movers[:limit],
                "n_appeared": len(appeared),
                "n_disappeared": len(disappeared),
                "n_movers": len(movers),
                "flip_to_profit": flip_to_profit,
                "flip_to_loss": flip_to_loss,
                "hub_avg": hub_avg,
            },
        )
    finally:
        conn.close()
