"""Canonical vs legacy AM4_* environment variables (app/env_compat.py)."""

from __future__ import annotations

import os

import pytest

from app import env_compat as ec


@pytest.fixture
def clean_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        ec.ENV_DB_CANONICAL,
        ec.ENV_DB_LEGACY,
        ec.ENV_TOKEN_CANONICAL,
        ec.ENV_TOKEN_LEGACY,
    ):
        monkeypatch.delenv(k, raising=False)


def test_resolved_env_db_prefers_canonical(clean_db_env, monkeypatch) -> None:
    monkeypatch.setenv(ec.ENV_DB_LEGACY, "/legacy.db")
    monkeypatch.setenv(ec.ENV_DB_CANONICAL, "/canonical.db")
    assert ec.resolved_env_db() == "/canonical.db"


def test_resolved_env_db_falls_back_to_legacy(clean_db_env, monkeypatch) -> None:
    monkeypatch.setenv(ec.ENV_DB_LEGACY, "/only-legacy.db")
    assert ec.resolved_env_db() == "/only-legacy.db"


def test_resolved_env_token_prefers_canonical(clean_db_env, monkeypatch) -> None:
    monkeypatch.setenv(ec.ENV_TOKEN_LEGACY, "legacy-secret")
    monkeypatch.setenv(ec.ENV_TOKEN_CANONICAL, "canonical-secret")
    assert ec.resolved_env_token() == "canonical-secret"


def test_resolved_env_token_falls_back_to_legacy(clean_db_env, monkeypatch) -> None:
    monkeypatch.setenv(ec.ENV_TOKEN_LEGACY, "legacy-only")
    assert ec.resolved_env_token() == "legacy-only"


def test_effective_db_path_uses_fallback_when_unset(clean_db_env) -> None:
    assert ec.effective_db_path("/fallback.db") == "/fallback.db"


def test_set_dashboard_db_from_cli_skips_when_env_set(clean_db_env, monkeypatch) -> None:
    monkeypatch.setenv(ec.ENV_DB_LEGACY, "/from-env.db")
    ec.set_dashboard_db_from_cli("/cli.db")
    assert ec.resolved_env_db() == "/from-env.db"
    assert os.environ.get(ec.ENV_DB_CANONICAL) is None


def test_set_dashboard_db_from_cli_sets_canonical(clean_db_env) -> None:
    ec.set_dashboard_db_from_cli("/cli.db")
    assert os.environ.get(ec.ENV_DB_CANONICAL) == "/cli.db"
    # Do not use monkeypatch.delenv here: its teardown would restore "/cli.db" and break later tests.
    os.environ.pop(ec.ENV_DB_CANONICAL, None)
