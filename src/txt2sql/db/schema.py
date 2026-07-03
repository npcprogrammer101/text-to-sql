"""
Schema catalog. Defines the table-group structure the router selects over, the
list of real tables (used by the guardrail to check scope), and a loader for
the pre-built knowledge base of table/column descriptions.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

# Table groups the router chooses among. Mirrors the original "agents".
TABLE_GROUPS: dict[str, list[str]] = {
    "customer": ["customer", "sellers"],
    "orders": ["order_items", "order_payments", "order_reviews", "orders"],
    "product": ["products", "category_translation"],
}

# Flat set of every real table — the guardrail's allowlist.
ALL_TABLES: list[str] = sorted({t for tables in TABLE_GROUPS.values() for t in tables})

# Human-readable one-liners for the router prompt.
GROUP_DESCRIPTIONS: dict[str, str] = {
    "customer": (
        "Customer and seller identifiers and their locations "
        "(city, state, zip)."
    ),
    "orders": (
        "Everything about orders: items and their prices/freight, payments and "
        "installments, reviews and scores, and order status/delivery timestamps."
    ),
    "product": (
        "Product details: category (Portuguese + English translation), "
        "description length, dimensions, weight."
    ),
}

_KB_PATH = Path(__file__).resolve().parents[3] / "data" / "kb.pkl"


def load_kb(path: Path | None = None) -> dict[str, Any]:
    """
    Load the knowledge base: {table_name: [description, [[col, col_desc], ...]]}.
    Built offline by scripts/build_kb.py so query-time never re-derives it.
    """
    p = path or _KB_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"Knowledge base not found at {p}. Run: python scripts/build_kb.py"
        )
    with open(p, "rb") as f:
        return pickle.load(f)
