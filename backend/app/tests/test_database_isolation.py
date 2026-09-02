"""Tests for database environment isolation and runtime selection."""

import os
from backend.app.db.connection import get_database_url, get_safe_database_name


def test_runtime_database_selection_strictly_prefers_database_url(monkeypatch):
    """Prove that default runtime selection strictly chooses DATABASE_URL and isolates DATABASE_URL_TEST."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/reconcilex_prod")
    monkeypatch.setenv("DATABASE_URL_TEST", "postgresql://user:pass@localhost:5432/reconcilex_test_db")

    # 1. Default runtime call (is_test=False) MUST strictly return DATABASE_URL
    runtime_url = get_database_url(is_test=False)
    assert runtime_url == "postgresql://user:pass@localhost:5432/reconcilex_prod"
    assert get_safe_database_name(runtime_url) == "reconcilex_prod"

    # 2. Test-specific call (is_test=True) MUST return DATABASE_URL_TEST
    test_url = get_database_url(is_test=True)
    assert test_url == "postgresql://user:pass@localhost:5432/reconcilex_test_db"
    assert get_safe_database_name(test_url) == "reconcilex_test_db"

    # 3. When DATABASE_URL is missing, runtime MUST NOT fall back to DATABASE_URL_TEST
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url(is_test=False) is None
    assert get_safe_database_name(get_database_url(is_test=False)) == "none"
