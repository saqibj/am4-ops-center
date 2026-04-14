"""Dashboard UI settings: schema, defaults, validation, merge, and JSON helpers.

Persisted in the browser as JSON in localStorage (see static/js/settings-store.js).
Keep schema_version in sync with the JS store when the shape changes.
Airline name and logo are server-side (SQLite + uploads); not stored here.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SETTINGS_SCHEMA_VERSION = 2
SETTINGS_STORAGE_KEY = "am4-ops-center.ui-settings.v1"

ThemeMode = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]
UiDensity = Literal["comfortable", "compact"]
ResetSection = Literal["appearance", "preferences", "notifications"]

ALLOWED_THEME_MODES: frozenset[str] = frozenset({"light", "dark", "system"})
ALLOWED_DENSITIES: frozenset[str] = frozenset({"comfortable", "compact"})

ALLOWED_LANDING_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/hub-explorer",
        "/aircraft",
        "/route-analyzer",
        "/scenarios",
        "/fleet-planner",
        "/buy-next",
        "/buy-next/global",
        "/my-fleet",
        "/my-hubs",
        "/my-routes",
        "/routes/add",
        "/fleet-health",
        "/demand-utilization",
        "/extraction-deltas",
        "/hub-roi",
        "/contributions",
        "/heatmap",
    }
)


@dataclass
class AppearanceSettings:
    theme_mode: ThemeMode = "dark"
    ui_density: UiDensity = "comfortable"


@dataclass
class PreferencesSettings:
    default_landing_path: str = "/"


@dataclass
class NotificationSettings:
    route_change_alerts: bool = True
    maintenance_alerts: bool = False
    marketing_alerts: bool = False


@dataclass
class UiSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    preferences: PreferencesSettings = field(default_factory=PreferencesSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)


def default_ui_settings() -> UiSettings:
    return UiSettings()


def _coerce_theme_mode(value: Any) -> ThemeMode:
    if isinstance(value, str) and value in ALLOWED_THEME_MODES:
        return value  # type: ignore[return-value]
    return "dark"


def _coerce_density(value: Any) -> UiDensity:
    if isinstance(value, str) and value in ALLOWED_DENSITIES:
        return value  # type: ignore[return-value]
    return "comfortable"


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_landing_path(value: Any) -> str:
    if isinstance(value, str) and value in ALLOWED_LANDING_PATHS:
        return value
    return "/"


def ui_settings_from_dict(data: dict[str, Any] | None) -> UiSettings:
    """Build settings from a decoded JSON object; unknown keys ignored; invalid values coerced."""
    if not data or not isinstance(data, dict):
        return default_ui_settings()

    appearance = data.get("appearance") if isinstance(data.get("appearance"), dict) else {}
    preferences = data.get("preferences") if isinstance(data.get("preferences"), dict) else {}
    notifications = data.get("notifications") if isinstance(data.get("notifications"), dict) else {}

    schema_version = data.get("schema_version")
    sv = int(schema_version) if isinstance(schema_version, int) or isinstance(schema_version, str) and str(schema_version).isdigit() else SETTINGS_SCHEMA_VERSION
    if sv < 1:
        sv = 1

    return UiSettings(
        schema_version=min(sv, SETTINGS_SCHEMA_VERSION),
        appearance=AppearanceSettings(
            theme_mode=_coerce_theme_mode(appearance.get("theme_mode")),
            ui_density=_coerce_density(appearance.get("ui_density")),
        ),
        preferences=PreferencesSettings(
            default_landing_path=_coerce_landing_path(preferences.get("default_landing_path")),
        ),
        notifications=NotificationSettings(
            route_change_alerts=_coerce_bool(notifications.get("route_change_alerts"), True),
            maintenance_alerts=_coerce_bool(notifications.get("maintenance_alerts"), False),
            marketing_alerts=_coerce_bool(notifications.get("marketing_alerts"), False),
        ),
    )


def ui_settings_to_json_dict(settings: UiSettings) -> dict[str, Any]:
    """Serialize for localStorage / API; snake_case keys."""
    d = asdict(settings)
    d["schema_version"] = SETTINGS_SCHEMA_VERSION
    return d


def ui_settings_to_json(settings: UiSettings) -> str:
    return json.dumps(ui_settings_to_json_dict(settings), separators=(",", ":"))


def parse_stored_settings_json(raw: str | None) -> UiSettings:
    if raw is None or not str(raw).strip():
        return default_ui_settings()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return default_ui_settings()
    if not isinstance(data, dict):
        return default_ui_settings()
    return ui_settings_from_dict(data)


def merge_ui_settings(base: UiSettings, patch: dict[str, Any]) -> UiSettings:
    """Merge a partial patch dict onto base (e.g. form submit). Same coercion as from_dict."""
    merged = asdict(base)
    if not patch or not isinstance(patch, dict):
        return ui_settings_from_dict(merged)

    if "appearance" in patch and isinstance(patch["appearance"], dict):
        merged["appearance"] = {**merged["appearance"], **patch["appearance"]}
    if "preferences" in patch and isinstance(patch["preferences"], dict):
        merged["preferences"] = {**merged["preferences"], **patch["preferences"]}
    if "notifications" in patch and isinstance(patch["notifications"], dict):
        merged["notifications"] = {**merged["notifications"], **patch["notifications"]}

    return ui_settings_from_dict(merged)


def reset_section(settings: UiSettings, section: ResetSection) -> UiSettings:
    out = deepcopy(settings)
    if section == "appearance":
        out.appearance = AppearanceSettings()
    elif section == "preferences":
        out.preferences = PreferencesSettings()
    elif section == "notifications":
        out.notifications = NotificationSettings()
    return out


def reset_all_settings() -> UiSettings:
    return default_ui_settings()


def resolve_theme(theme_mode: ThemeMode, *, prefers_dark: bool | None) -> ResolvedTheme:
    """Resolve effective light/dark theme. For ``system``, use prefers_dark; default dark if unknown."""
    if theme_mode == "light":
        return "light"
    if theme_mode == "dark":
        return "dark"
    if prefers_dark is None:
        return "dark"
    return "dark" if prefers_dark else "light"
