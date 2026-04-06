"""Airport extraction stores all valid rows (no extract-time min_runway filter)."""

from __future__ import annotations

from config import UserConfig
from database.schema import create_schema, get_connection
from extractors.airports import extract_all_airports


def test_extract_all_airports_inserts_short_runway_despite_min_runway(
    tmp_path, monkeypatch
) -> None:
    """Previously rwy < min_runway skipped insert; short strips must exist in DB."""
    db = tmp_path / "apx.db"
    conn = get_connection(db)
    create_schema(conn)

    cfg = UserConfig(min_runway=50_000, airport_id_max=6)

    class _Ap:
        valid = True
        id = 3
        iata = "SHT"
        icao = ""
        name = "Short"
        fullname = ""
        country = "T"
        continent = ""
        lat = 1.0
        lng = 2.0
        rwy = 1200
        rwy_codes = ""
        market = 1
        hub_cost = 0

    class _Bad:
        valid = False

    class _Res:
        def __init__(self, ap) -> None:
            self.ap = ap

    def fake_search(s: str) -> _Res:
        if s == "3":
            return _Res(_Ap())
        return _Res(_Bad())

    monkeypatch.setattr("am4.utils.airport.Airport.search", fake_search)

    rows = extract_all_airports(conn, cfg)
    conn.close()

    assert any(r.get("iata") == "SHT" for r in rows)
    c2 = get_connection(db)
    rwy = c2.execute("SELECT rwy FROM airports WHERE iata = 'SHT'").fetchone()
    c2.close()
    assert rwy is not None
    assert int(rwy[0]) == 1200


def test_upsert_airport_from_am4_still_respects_min_runway(tmp_path, monkeypatch) -> None:
    """Hub add path keeps min_runway guard (query/add-time policy)."""
    from extractors.routes import upsert_airport_from_am4

    db = tmp_path / "up.db"
    conn = get_connection(db)
    create_schema(conn)

    cfg = UserConfig(min_runway=10_000)

    class _Ap:
        valid = True
        id = 9
        iata = "ZZZ"
        icao = ""
        name = "Z"
        fullname = ""
        country = ""
        continent = ""
        lat = 0.0
        lng = 0.0
        rwy = 2000
        rwy_codes = ""
        market = 0
        hub_cost = 0

    class _Res:
        ap = _Ap()

    monkeypatch.setattr("am4.utils.airport.Airport.search", lambda _iata: _Res())
    ap_id, err = upsert_airport_from_am4(conn, cfg, "ZZZ")
    conn.close()

    assert ap_id is None
    assert err is not None
    assert "min_runway" in (err or "").lower() or "below" in (err or "").lower()
