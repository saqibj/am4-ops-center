"""Tests for dashboard UI settings schema and persistence helpers."""

from __future__ import annotations

import json

import pytest

from dashboard.ui_settings import (
    SETTINGS_SCHEMA_VERSION,
    default_ui_settings,
    merge_ui_settings,
    parse_stored_settings_json,
    reset_all_settings,
    reset_section,
    resolve_theme,
    sanitize_airline_name,
    sanitize_logo_data_url,
    ui_settings_from_dict,
    ui_settings_to_json,
    ui_settings_to_json_dict,
)


def test_default_settings_shape() -> None:
    s = default_ui_settings()
    d = ui_settings_to_json_dict(s)
    assert d["schema_version"] == SETTINGS_SCHEMA_VERSION
    assert d["appearance"]["theme_mode"] == "dark"
    assert d["appearance"]["ui_density"] == "comfortable"
    assert d["branding"]["airline_name"] == ""
    assert d["branding"]["airline_logo_data_url"] is None
    assert d["preferences"]["default_landing_path"] == "/"
    assert d["notifications"]["route_change_alerts"] is True


def test_parse_empty_and_malformed() -> None:
    assert parse_stored_settings_json(None) == default_ui_settings()
    assert parse_stored_settings_json("") == default_ui_settings()
    assert parse_stored_settings_json("not json") == default_ui_settings()
    assert parse_stored_settings_json("[]") == default_ui_settings()


def test_round_trip_json() -> None:
    s = default_ui_settings()
    s.branding.airline_name = "Test Airways"
    s.appearance.theme_mode = "system"
    raw = ui_settings_to_json(s)
    back = parse_stored_settings_json(raw)
    assert back.branding.airline_name == "Test Airways"
    assert back.appearance.theme_mode == "system"


def test_sanitize_airline_name() -> None:
    assert sanitize_airline_name("  Foo   Bar  ") == "Foo Bar"
    assert sanitize_airline_name("a" * 100) == "a" * 60
    assert sanitize_airline_name("x\x00y") == "xy"


def test_invalid_enums_coerced() -> None:
    s = ui_settings_from_dict(
        {
            "appearance": {"theme_mode": "neon", "ui_density": "ultra"},
            "preferences": {"default_landing_path": "/nope"},
        }
    )
    assert s.appearance.theme_mode == "dark"
    assert s.appearance.ui_density == "comfortable"
    assert s.preferences.default_landing_path == "/"


def test_logo_rejects_bad_payload() -> None:
    assert sanitize_logo_data_url("data:text/html;base64,abc") is None
    assert sanitize_logo_data_url("data:image/png;base64," + "x" * 800_000) is None
    good = "data:image/png;base64,iVBORw0KGgo="
    assert sanitize_logo_data_url(good) == good


def test_merge_partial() -> None:
    base = default_ui_settings()
    out = merge_ui_settings(
        base,
        {
            "appearance": {"theme_mode": "light"},
            "notifications": {"maintenance_alerts": True},
        },
    )
    assert out.appearance.theme_mode == "light"
    assert out.notifications.maintenance_alerts is True
    assert out.notifications.route_change_alerts is True


def test_reset_section_and_all() -> None:
    s = ui_settings_from_dict(
        {"branding": {"airline_name": "ACME", "airline_logo_data_url": None}}
    )
    s2 = reset_section(s, "branding")
    assert s2.branding.airline_name == ""
    assert s.branding.airline_name == "ACME"
    assert reset_all_settings() == default_ui_settings()


@pytest.mark.parametrize(
    ("mode", "prefers", "expected"),
    [
        ("light", None, "light"),
        ("dark", None, "dark"),
        ("system", True, "dark"),
        ("system", False, "light"),
        ("system", None, "dark"),
    ],
)
def test_resolve_theme(mode: str, prefers: bool | None, expected: str) -> None:
    assert resolve_theme(mode, prefers_dark=prefers) == expected  # type: ignore[arg-type]


def test_json_compact_roundtrip_matches_python_dict() -> None:
    """Ensure JS-style compact JSON still parses."""
    raw = '{"schema_version":1,"appearance":{"theme_mode":"light","ui_density":"compact"},"branding":{"airline_name":"","airline_logo_data_url":null},"preferences":{"default_landing_path":"/fleet-planner"},"notifications":{"route_change_alerts":false,"maintenance_alerts":true,"marketing_alerts":false}}'
    s = parse_stored_settings_json(raw)
    assert s.appearance.theme_mode == "light"
    assert s.appearance.ui_density == "compact"
    assert s.preferences.default_landing_path == "/fleet-planner"
    assert s.notifications.route_change_alerts is False
    back = json.loads(ui_settings_to_json(s))
    assert back["appearance"]["theme_mode"] == "light"
