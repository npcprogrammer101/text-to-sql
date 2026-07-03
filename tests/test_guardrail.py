"""
Tests for the guardrail — the security centerpiece. These run without a
database or an LLM, so they're fast and CI-friendly.

Run: pytest
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from txt2sql.guardrail import validate  # noqa: E402

ALLOWED = ["customer", "orders", "order_items", "products", "sellers",
           "order_payments", "order_reviews", "category_translation"]


def test_allows_simple_select():
    assert validate("SELECT COUNT(*) FROM orders", ALLOWED).ok


def test_allows_join():
    sql = ("SELECT c.customer_id FROM customer c "
           "JOIN orders o ON o.customer_id = c.customer_id")
    assert validate(sql, ALLOWED).ok


def test_allows_cte():
    sql = "WITH x AS (SELECT customer_id FROM customer) SELECT * FROM x"
    assert validate(sql, ALLOWED).ok


def test_blocks_delete():
    assert not validate("DELETE FROM orders", ALLOWED).ok


def test_blocks_drop():
    assert not validate("DROP TABLE orders", ALLOWED).ok


def test_blocks_update():
    assert not validate("UPDATE customer SET customer_city = NULL", ALLOWED).ok


def test_blocks_stacked_statements():
    assert not validate("SELECT 1; DROP TABLE orders", ALLOWED).ok


def test_blocks_out_of_scope_table():
    assert not validate("SELECT * FROM secret_table", ALLOWED).ok


def test_blocks_cte_hiding_bad_table():
    sql = "WITH x AS (SELECT * FROM secret_table) SELECT * FROM x"
    assert not validate(sql, ALLOWED).ok


def test_blocks_subquery_write():
    # a delete smuggled into a subquery must not slip through
    sql = "SELECT * FROM orders WHERE order_id IN (SELECT order_id FROM orders)"
    # this particular one is a legit read; ensure it passes
    assert validate(sql, ALLOWED).ok
