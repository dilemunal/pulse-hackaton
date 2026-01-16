# DOSYA: src/db/connection.py
"""
PostgreSQL connection helpers for Pulse (demo).

Purpose:
- Single place for DB connection config (env via config/settings.py)
- Safe-ish, simple psycopg2 connection creation for scripts & pipelines

AI concept note:
- DB is the "source of truth" for structured entities (products, customers, history).
- RAG vector store is a derived index from this truth source (for semantic retrieval).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg2
from psycopg2.extensions import connection as PgConnection

from config.settings import SETTINGS


def get_db_connection(*, autocommit: bool = False) -> PgConnection:
    """
    Create and return a psycopg2 connection.

    Demo notes:
- Keep it simple: one connection per script/pipeline run.
- Production would use pooling (psycopg_pool / pgbouncer), but out of scope.
    """
    conn = psycopg2.connect(
        host=SETTINGS.DB_HOST,
        port=SETTINGS.DB_PORT,
        database=SETTINGS.DB_NAME,
        user=SETTINGS.DB_USER,
        password=SETTINGS.DB_PASS,
    )
    conn.autocommit = autocommit
    return conn


@contextmanager
def db_cursor(*, autocommit: bool = False) -> Iterator[tuple[PgConnection, any]]:
    """
    Context manager yielding (conn, cursor). Commits on success, rollbacks on error.

    Usage:
        with db_cursor() as (conn, cur):
            cur.execute("SELECT 1")
    """
    conn: Optional[PgConnection] = None
    try:
        conn = get_db_connection(autocommit=autocommit)
        cur = conn.cursor()
        yield conn, cur
        if not autocommit:
            conn.commit()
    except Exception:
        if conn and not autocommit:
            conn.rollback()
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
