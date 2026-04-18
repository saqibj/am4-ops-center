"""VIP ticket and profit from stored PAX ``route_aircraft`` figures (AM4 formulae)."""

from __future__ import annotations

VIP_BASE_MULT = 1.7489
VIP_OPT_Y = 1.22
VIP_OPT_J = 1.195
VIP_OPT_F = 1.175
PAX_OPT_Y = 1.10
PAX_OPT_J = 1.08
PAX_OPT_F = 1.06


def _pax_base_prices(distance_km: float, realism: bool) -> tuple[float, float, float]:
    d = float(distance_km)
    if realism:
        return (0.3 * d + 150.0, 0.6 * d + 500.0, 0.9 * d + 1000.0)
    return (0.4 * d + 170.0, 0.8 * d + 560.0, 1.2 * d + 1200.0)


def vip_ticket_prices(distance_km: float, realism: bool) -> tuple[float, float, float]:
    """Return ``(ticket_y, ticket_j, ticket_f)`` for VIP pricing (per seat, before config)."""
    by, bj, bf = _pax_base_prices(distance_km, realism)
    return (
        by * VIP_BASE_MULT * VIP_OPT_Y,
        bj * VIP_BASE_MULT * VIP_OPT_J,
        bf * VIP_BASE_MULT * VIP_OPT_F,
    )


def compute_vip_profit(
    distance_km: float,
    config_y: int,
    config_j: int,
    config_f: int,
    pax_profit_per_trip: float,
    pax_income_per_trip: float | None,
    trips_per_day: int,
    realism: bool,
) -> dict[str, float]:
    """Return ``vip_income_per_trip``, ``vip_profit_per_trip``, ``vip_profit_per_ac_day``."""
    by, bj, bf = _pax_base_prices(distance_km, realism)
    pax_ty = by * PAX_OPT_Y
    pax_tj = bj * PAX_OPT_J
    pax_tf = bf * PAX_OPT_F

    cy, cj, cf = int(config_y), int(config_j), int(config_f)

    if pax_income_per_trip is None:
        pax_income_per_trip = cy * pax_ty + cj * pax_tj + cf * pax_tf

    costs_per_trip = float(pax_income_per_trip) - float(pax_profit_per_trip)

    v_ty, v_tj, v_tf = vip_ticket_prices(distance_km, realism)
    vip_income_per_trip = cy * v_ty + cj * v_tj + cf * v_tf
    vip_profit_per_trip = vip_income_per_trip - costs_per_trip
    vip_profit_per_ac_day = vip_profit_per_trip * int(trips_per_day)

    return {
        "vip_income_per_trip": float(vip_income_per_trip),
        "vip_profit_per_trip": float(vip_profit_per_trip),
        "vip_profit_per_ac_day": float(vip_profit_per_ac_day),
    }


def adjust_rows_for_route_type(
    rows: list[dict],
    route_type: str,
    realism: bool,
) -> list[dict]:
    """Return adjusted copies of ``route_aircraft``-style row dicts.

    - ``pax``, ``charter``, ``cargo``: unchanged numbers (shallow-copied rows).
    - ``vip``: recompute ``profit_per_trip`` and ``profit_per_ac_day`` from VIP pricing.
    """
    rt = (route_type or "").strip().lower()
    if rt != "vip":
        return [dict(r) for r in rows]

    out: list[dict] = []
    for r in rows:
        nr = dict(r)
        d = float(nr.get("distance_km") or 0.0)
        pax_profit = float(nr.get("profit_per_trip") or 0.0)
        tpd = int(nr.get("trips_per_day") or 0)
        raw_inc = nr.get("income_per_trip")
        pax_inc: float | None
        if raw_inc is None or raw_inc == "":
            pax_inc = None
        else:
            pax_inc = float(raw_inc)

        res = compute_vip_profit(
            d,
            int(nr.get("config_y") or 0),
            int(nr.get("config_j") or 0),
            int(nr.get("config_f") or 0),
            pax_profit,
            pax_inc,
            tpd,
            realism,
        )
        nr["profit_per_trip"] = res["vip_profit_per_trip"]
        nr["profit_per_ac_day"] = res["vip_profit_per_ac_day"]
        out.append(nr)
    return out
