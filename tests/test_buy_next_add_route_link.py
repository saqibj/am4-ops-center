"""Template tests: Buy Next per-row Add route deep-link column."""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "templates"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _row_base(**overrides: object) -> dict:
    r = {
        "destination": "DXB",
        "dest_country": "AE",
        "needs_stopover": False,
        "stopover_iata": None,
        "ac_name": "Test AC",
        "ac_shortname": "A333-800",
        "ac_type": "PAX",
        "ac_cost": 100_000_000,
        "config_y": 300,
        "config_j": 50,
        "config_f": 10,
        "distance_km": 5000.0,
        "profit_per_ac_day": 100_000.0,
        "profit_yield": 50.0,
        "qty_affordable": 1,
        "total_daily_profit": 100_000.0,
        "payback_days": 10.0,
        "match_tier": "none",
        "is_best_buy": False,
        "current_ac_shortname": None,
        "hub_iata": "LAX",
    }
    r.update(overrides)
    return r


def _first_add_route_href(page_html: str) -> str | None:
    m = re.search(r'href="(/routes/add\?[^"]+)"', page_html)
    return html.unescape(m.group(1)) if m else None


def test_per_hub_none_tier_renders_add_route_with_encoded_params() -> None:
    tmpl = _jinja_env().get_template("partials/buy_next_results.html")
    html = tmpl.render(
        rows=[_row_base(match_tier="none", ac_shortname="A333-800")],
        hub="LAX",
        budget=5_000_000,
        sort="price_desc",
        limit=15,
        truncated=False,
    )
    assert "➕" in html
    href = _first_add_route_href(html)
    assert href is not None
    q = parse_qs(urlparse(href).query)
    assert q["hub"] == ["LAX"]
    assert q["destination"] == ["DXB"]
    assert q["aircraft"] == ["A333-800"]
    assert 'title="Add route for A333-800 to DXB"' in html


def test_per_hub_match_tier_none_string_renders_link() -> None:
    """API sets match_tier to 'none' for non-flown rows."""
    tmpl = _jinja_env().get_template("partials/buy_next_results.html")
    html = tmpl.render(
        rows=[_row_base(match_tier="none")],
        hub="ORD",
        budget=1,
        sort="price_desc",
        limit=15,
        truncated=False,
    )
    assert _first_add_route_href(html) is not None


def test_per_hub_exact_tier_no_link() -> None:
    tmpl = _jinja_env().get_template("partials/buy_next_results.html")
    html = tmpl.render(
        rows=[_row_base(match_tier="exact")],
        hub="LAX",
        budget=5_000_000,
        sort="price_desc",
        limit=15,
        truncated=False,
    )
    assert "/routes/add" not in html
    assert "➕" not in html


def test_per_hub_route_tier_no_link() -> None:
    tmpl = _jinja_env().get_template("partials/buy_next_results.html")
    html = tmpl.render(
        rows=[_row_base(match_tier="route", current_ac_shortname="B744")],
        hub="LAX",
        budget=5_000_000,
        sort="price_desc",
        limit=15,
        truncated=False,
    )
    assert "/routes/add" not in html
    assert "➕" not in html


def test_empty_destination_no_link() -> None:
    tmpl = _jinja_env().get_template("partials/buy_next_results.html")
    html = tmpl.render(
        rows=[_row_base(match_tier="none", destination="")],
        hub="LAX",
        budget=5_000_000,
        sort="price_desc",
        limit=15,
        truncated=False,
    )
    assert "/routes/add" not in html


def test_global_uses_row_hub_iata_not_outer_hub() -> None:
    tmpl = _jinja_env().get_template("partials/buy_next_global_results.html")
    page_html = tmpl.render(
        rows=[
            _row_base(hub_iata="SEA", destination="NRT", ac_shortname="A21N"),
            _row_base(hub_iata="YVR", destination="LHR", ac_shortname="B789"),
        ],
        budget=9_000_000,
        sort="total_desc",
        limit=15,
        truncated=False,
    )
    hrefs = [html.unescape(h) for h in re.findall(r'href="(/routes/add\?[^"]+)"', page_html)]
    assert len(hrefs) == 2
    q0 = parse_qs(urlparse(hrefs[0]).query)
    q1 = parse_qs(urlparse(hrefs[1]).query)
    assert q0["hub"] == ["SEA"]
    assert q0["destination"] == ["NRT"]
    assert q1["hub"] == ["YVR"]
    assert q1["destination"] == ["LHR"]


def test_aircraft_shortname_with_hyphen_round_trips_in_query_string() -> None:
    tmpl = _jinja_env().get_template("partials/buy_next_results.html")
    html = tmpl.render(
        rows=[_row_base(match_tier="none", ac_shortname="A333-800")],
        hub="MIA",
        budget=3_000_000,
        sort="price_desc",
        limit=15,
        truncated=False,
    )
    href = _first_add_route_href(html)
    assert href is not None
    q = parse_qs(urlparse(href).query)
    assert q["aircraft"] == ["A333-800"]
    # Defensive: encoded form still parses back to the same shortname
    raw_q = urlparse(href).query
    for part in raw_q.split("&"):
        if part.startswith("aircraft="):
            assert unquote(part.split("=", 1)[1]) == "A333-800"
            break
    else:
        raise AssertionError("aircraft param missing")
