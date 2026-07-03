"""
The guardrail — a real AST gate, not an LLM "please check this" prompt.

The original project's only validation was another LLM call asking the model to
review its own SQL. That is not a security control: nothing stopped a generated
DELETE/DROP/UPDATE, and the query ran as root. This module is the replacement.

Every generated query must pass ALL checks before execution:
  1. Parses as valid MySQL.
  2. Exactly one statement (no stacked queries).
  3. Top-level node is a SELECT (a WITH ... SELECT counts).
  4. No DML/DDL nodes anywhere in the tree.
  5. Every referenced physical table is in the allowlist (CTE names excluded).

This is defense-in-depth: the read-only DB role is the second line, so even a
guardrail miss cannot write. But the guardrail catches problems early and gives
a clear reason, which the pipeline can feed back into self-correction.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.TruncateTable, exp.Merge, exp.Grant, exp.Command,
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class GuardResult:
    ok: bool
    checks: list[Check]
    referenced_tables: list[str]

    def failure_summary(self) -> str:
        return "; ".join(c.detail for c in self.checks if not c.passed)


def validate(sql: str, allowed_tables: list[str]) -> GuardResult:
    checks: list[Check] = []
    referenced: list[str] = []

    # 1 + 2: parse into exactly one statement
    try:
        statements = [s for s in sqlglot.parse(sql, read="mysql") if s is not None]
    except Exception as e:
        return GuardResult(False, [Check("parse", False, f"Could not parse: {e}")], [])

    checks.append(Check("parse", True, "Parsed as valid MySQL"))
    if len(statements) != 1:
        checks.append(Check("single_statement", False,
                            f"Expected 1 statement, found {len(statements)}"))
        return GuardResult(False, checks, referenced)
    checks.append(Check("single_statement", True, "Single statement"))

    tree = statements[0]

    # 3: read-only root
    is_read = isinstance(tree, exp.Select) or (
        isinstance(tree, exp.With) and isinstance(tree.this, exp.Select)
    )
    checks.append(Check(
        "read_only_root", is_read,
        "Top-level statement is SELECT" if is_read
        else f"Top-level statement is {tree.key.upper()}, not SELECT"))

    # 4: no forbidden nodes anywhere in the tree
    bad = next((n for n in tree.walk() if isinstance(n, _FORBIDDEN_NODES)), None)
    checks.append(Check(
        "no_write_nodes", bad is None,
        "No write/DDL nodes" if bad is None else f"Contains a {bad.key.upper()} node"))

    # 5: referenced tables in scope (CTE names are query-local, not physical)
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE) if c.alias_or_name}
    referenced = sorted({
        t.name.lower() for t in tree.find_all(exp.Table)
        if t.name and t.name.lower() not in cte_names
    })
    unknown = [t for t in referenced if t not in allowed_tables]
    checks.append(Check(
        "tables_in_scope", not unknown,
        "All referenced tables in scope" if not unknown
        else f"Out-of-scope table(s): {', '.join(unknown)}"))

    ok = all(c.passed for c in checks)
    return GuardResult(ok, checks, referenced)
