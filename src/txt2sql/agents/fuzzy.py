"""
Fuzzy value-matching — the other strong idea from the original.

When a user says "Sao Paulo" but the column stores "SP" or "sao paulo", a
literal WHERE clause misses. This resolves each requested filter value against
the actual DISTINCT values in that column using rapidfuzz, so the generated SQL
filters on a value that really exists.

Reads distinct values through the READ-ONLY engine — this is a lookup, not a
mutation, and it keeps even this helper on the least-privileged connection.
"""
from __future__ import annotations

from rapidfuzz import fuzz, process
from sqlalchemy import text

from ..db.engine import readonly_engine


def _distinct_values(table: str, column: str) -> list[str]:
    eng = readonly_engine()
    with eng.connect() as conn:
        # identifiers come from the KB/agents (our own schema), not user free-text
        rows = conn.execute(text(f"SELECT DISTINCT `{column}` FROM `{table}`")).fetchall()
    return [str(r[0]) for r in rows if r[0] is not None]


def _best_match(value: str, choices: list[str]) -> tuple[str, float]:
    match, score, _ = process.extractOne(value, choices, scorer=fuzz.token_set_ratio)
    return match, score


def resolve_filters(filter_spec: list) -> list[list[str]]:
    """
    filter_spec is the parsed filter agent output:
        ["yes", ["table", "column", "v1, v2"], ...]  or  ["no"]
    Returns resolved rows: [["table name:<t>", "column_name:<c>", "filter_value:<real>"], ...]
    """
    if not filter_spec or filter_spec[0] != "yes":
        return []

    resolved: list[list[str]] = []
    for entry in filter_spec[1:]:
        if not (isinstance(entry, list) and len(entry) == 3):
            continue
        table, column, raw_values = entry
        wanted = [v.strip() for v in str(raw_values).split(",") if v.strip()]
        try:
            choices = _distinct_values(table, column)
        except Exception:
            continue
        if not choices:
            continue
        for w in wanted:
            best, _score = _best_match(w, choices)
            resolved.append([f"table name:{table}", f"column_name:{column}",
                             f"filter_value:{best}"])
    return resolved
