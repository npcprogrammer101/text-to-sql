"""
Database access. Two distinct engines, on purpose:

  * admin_engine    — full privileges. Used ONLY by loading/KB scripts.
  * readonly_engine — the txt2sql_ro role (SELECT only). Used for ALL
                      generated-query execution.

The original project ran everything as root, including executing model-written
SQL. Splitting the connections means a bad generation cannot write even if it
somehow slipped past the guardrail — the database itself refuses it.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..config import settings

_admin: Engine | None = None
_readonly: Engine | None = None


def admin_engine() -> Engine:
    global _admin
    if _admin is None:
        _admin = create_engine(settings.admin_db_url, pool_pre_ping=True)
    return _admin


def readonly_engine() -> Engine:
    global _readonly
    if _readonly is None:
        _readonly = create_engine(settings.readonly_db_url, pool_pre_ping=True)
    return _readonly


def run_readonly(sql: str) -> tuple[list[str], list[list]]:
    """
    Execute a SELECT under the read-only role and return (columns, rows).
    A per-statement timeout caps runaway queries. Raises on any DB error, which
    the pipeline uses to drive the self-correction loop.
    """
    eng = readonly_engine()
    with eng.connect() as conn:
        # MySQL: cap execution time (milliseconds) for this statement
        timeout_ms = settings.statement_timeout_s * 1000
        try:
            conn.execute(text(f"SET SESSION max_execution_time = {timeout_ms}"))
        except Exception:
            pass  # not fatal if the server doesn't support it
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchmany(settings.max_rows)]
    return columns, rows
