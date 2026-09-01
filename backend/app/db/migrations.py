"""Database migration and schema initialization utility."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .connection import get_connection, get_database_url


def get_schema_sql() -> str:
    """Read schema.sql contents."""
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        return f.read()


def init_db(db_url: Optional[str] = None) -> None:
    """Apply schema.sql to the target database."""
    sql = get_schema_sql()
    with get_connection(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def reset_db(db_url: Optional[str] = None) -> None:
    """Drop and recreate all tables for clean test initialization."""
    drop_sql = """
    DROP TABLE IF EXISTS audit_events CASCADE;
    DROP TABLE IF EXISTS exceptions CASCADE;
    DROP TABLE IF EXISTS reconciliation_results CASCADE;
    DROP TABLE IF EXISTS refunds CASCADE;
    DROP TABLE IF EXISTS bank_credits CASCADE;
    DROP TABLE IF EXISTS settlements CASCADE;
    DROP TABLE IF EXISTS payments CASCADE;
    DROP TABLE IF EXISTS raw_source_records CASCADE;
    DROP TABLE IF EXISTS reconciliation_batches CASCADE;
    DROP FUNCTION IF EXISTS prevent_audit_event_mutation() CASCADE;
    """
    with get_connection(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(drop_sql)
            cur.execute(get_schema_sql())
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="ReconcileX Database Schema Initializer")
    parser.add_argument("--test-db", action="store_true", help="Initialize the test database (DATABASE_URL_TEST)")
    parser.add_argument("--reset", action="store_true", help="Drop existing tables before recreating schema")
    args = parser.parse_args()

    url = get_database_url(is_test=args.test_db)
    if not url:
        db_name = "DATABASE_URL_TEST" if args.test_db else "DATABASE_URL"
        print(f"Error: {db_name} is not set in environment or .env", file=sys.stderr)
        sys.exit(1)

    print(f"Initializing database schema on: {url.split('@')[-1] if '@' in url else url}")
    try:
        if args.reset:
            reset_db(url)
            print("Successfully reset and initialized schema.")
        else:
            init_db(url)
            print("Successfully applied schema.")
    except Exception as e:
        print(f"Failed to initialize schema: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
