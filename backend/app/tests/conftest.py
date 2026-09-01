"""Pytest configuration and database fixtures for ReconcileX."""

import os
from typing import Generator
import pytest

from backend.app.db.connection import get_connection, get_database_url
from backend.app.db.migrations import reset_db


def is_test_db_available() -> bool:
    """Check if DATABASE_URL_TEST is set and reachable."""
    test_url = get_database_url(is_test=True)
    if not test_url:
        return False
    try:
        with get_connection(test_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def setup_test_database():
    """Reset and initialize test database schema if DATABASE_URL_TEST is available."""
    if not is_test_db_available():
        pytest.skip("DATABASE_URL_TEST is not configured or database is unreachable.")
    test_url = get_database_url(is_test=True)
    reset_db(test_url)
    yield test_url


@pytest.fixture
def db_conn(setup_test_database) -> Generator:
    """Provide a dedicated test connection with automatic cleanup."""
    test_url = setup_test_database
    conn = get_connection(test_url)
    try:
        yield conn
    finally:
        conn.close()
