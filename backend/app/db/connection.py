"""Database connection and transaction management for ReconcileX."""

import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Generator, Optional

import psycopg
from psycopg.rows import dict_row


def jsonify(obj: Any) -> Any:
    """Recursively convert Decimal, datetime, date, and Enum to JSON-serializable primitives."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonify(item) for item in obj]
    return obj



def load_env_file(env_path: Optional[Path] = None) -> None:
    """Minimal stdlib-based environment loader for .env / .env.test files."""
    if env_path is None:
        # Check .env in project root
        root_dir = Path(__file__).resolve().parent.parent.parent.parent
        env_path = root_dir / ".env"
        if not env_path.exists():
            test_env = root_dir / ".env.test"
            if test_env.exists():
                env_path = test_env

    if env_path and env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v


# Load environment variables on module import if available
load_env_file()


def get_database_url(is_test: bool = False) -> Optional[str]:
    """Retrieve database URL from environment."""
    if is_test:
        return os.environ.get("DATABASE_URL_TEST")
    return os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")


def get_connection(db_url: Optional[str] = None) -> psycopg.Connection:
    """Create a raw psycopg connection with dict_row row factory."""
    url = db_url or get_database_url()
    if not url:
        raise ValueError("Database URL is not configured. Set DATABASE_URL or DATABASE_URL_TEST.")
    return psycopg.connect(url, row_factory=dict_row)


@contextmanager
def get_db_cursor(conn: Optional[psycopg.Connection] = None, db_url: Optional[str] = None) -> Generator[psycopg.Cursor, None, None]:
    """Context manager yielding a cursor within a transaction."""
    owned_conn = False
    if conn is None:
        conn = get_connection(db_url)
        owned_conn = True

    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        if owned_conn:
            conn.close()
