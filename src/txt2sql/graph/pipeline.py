"""
The LangGraph pipeline.

Flow:
  route -> retrieve -> detect_filters -> [fuzzy?] -> generate -> guardrail
        -> (blocked? -> regenerate up to N times) -> execute
        -> (exec error? -> regenerate with error up to N times) -> done

The guardrail is a DEDICATED node before execution (per the chosen design).
A query only reaches the database if the guardrail passed; execution runs on
the read-only role.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from ..config import settings
from ..db.engine import run_readonly
from ..db.schema import ALL_TABLES
from ..guardrail import validate
from ..agents.router import route
from ..agents.retrieval import retrieve_columns
from ..agents.generate import detect_filters, generate_sql
from ..agents.fuzzy import resolve_filters


class State(TypedDict, total=False):
    question: str
    groups: list[str]
    columns: list[list[str]]
    filter_spec: list
    resolved_filters: list[list[str]]
    sql: str
    guard_ok: bool
    guard_reason: str
    attempts: int
    last_error: str
    columns_in_scope: list[str]
    result_columns: list[str]
    result_rows: list[list]
    status: str
    trace: list[dict]


def _log(state: State, stage: str, **data):
    state.setdefault("trace", []).append({"stage": stage, **data})


def n_route(state: State) -> State:
    groups = route(state["question"])
    _log(state, "route", groups=groups)
    return {"groups": groups, "trace": state["trace"]}


def n_retrieve(state: State) -> State:
    cols = retrieve_columns(state["question"], state["groups"])
    tables = sorted({
        c[0].split("name of table:")[-1].strip()
        for c in cols if c and str(c[0]).startswith("name of table:")
    })
    _log(state, "retrieve", num_columns=len(cols), tables=tables)
    return {"columns": cols, "columns_in_scope": tables or ALL_TABLES,
            "trace": state["trace"]}


def n_filters(state: State) -> State:
    spec = detect_filters(state["question"], state["columns"])
    needs = isinstance(spec, list) and spec and spec[0] == "yes"
    _log(state, "detect_filters", needs_filters=bool(needs), spec=spec)
    return {"filter_spec": spec, "trace": state["trace"]}


def n_fuzzy(state: State) -> State:
    resolved = resolve_filters(state["filter_spec"])
    _log(state, "fuzzy_match", resolved=resolved)
    return {"resolved_filters": resolved, "trace": state["trace"]}


def n_generate(state: State) -> State:
    attempts = state.get("attempts", 0) + 1
    sql = generate_sql(
        state["question"], state["columns"],
        state.get("resolved_filters") or state.get("filter_spec") or [],
        error=state.get("last_error"),
    )
    _log(state, "generate", attempt=attempts, sql=sql)
    # clear the error once consumed, so a later clean pass doesn't see stale text
    return {"sql": sql, "attempts": attempts, "last_error": "",
            "trace": state["trace"]}


def n_guardrail(state: State) -> State:
    # scope = tables the retrieval actually pulled (fall back to all)
    scope = state.get("columns_in_scope") or ALL_TABLES
    result = validate(state["sql"], scope)
    _log(state, "guardrail", ok=result.ok,
         checks=[{"name": c.name, "passed": c.passed, "detail": c.detail}
                 for c in result.checks])
    out = {"guard_ok": result.ok, "guard_reason": result.failure_summary(),
           "trace": state["trace"]}
    # If blocked, persist the reason as the error so the next generate() sees it.
    # (Node return values are merged into state; edge-function mutations are not.)
    if not result.ok:
        out["last_error"] = f"Rejected by guardrail: {result.failure_summary()}"
    return out


def n_execute(state: State) -> State:
    try:
        cols, rows = run_readonly(state["sql"])
        _log(state, "execute", ok=True, num_rows=len(rows))
        return {"result_columns": cols, "result_rows": rows, "status": "ok",
                "trace": state["trace"]}
    except Exception as e:
        _log(state, "execute", ok=False, error=str(e))
        return {"last_error": str(e), "status": "exec_error", "trace": state["trace"]}


# --- conditional edges ------------------------------------------------------
def after_filters(state: State) -> str:
    spec = state.get("filter_spec") or ["no"]
    return "fuzzy" if (spec and spec[0] == "yes") else "generate"


def after_guardrail(state: State) -> str:
    if state["guard_ok"]:
        return "execute"
    # last_error was already set by the guardrail node so generate() sees it.
    if state.get("attempts", 0) <= settings.max_repairs:
        return "generate"
    return "blocked"


def after_execute(state: State) -> str:
    if state.get("status") == "ok":
        return "done"
    if state.get("attempts", 0) <= settings.max_repairs:
        return "generate"
    return "failed"


def n_blocked(state: State) -> State:
    return {"status": "blocked", "trace": state["trace"]}


def n_failed(state: State) -> State:
    return {"status": "failed", "trace": state["trace"]}


def build_graph():
    g = StateGraph(State)
    g.add_node("route", n_route)
    g.add_node("retrieve", n_retrieve)
    g.add_node("detect_filters", n_filters)
    g.add_node("fuzzy", n_fuzzy)
    g.add_node("generate", n_generate)
    g.add_node("guardrail", n_guardrail)
    g.add_node("execute", n_execute)
    g.add_node("blocked", n_blocked)
    g.add_node("failed", n_failed)

    g.add_edge(START, "route")
    g.add_edge("route", "retrieve")
    g.add_edge("retrieve", "detect_filters")
    g.add_conditional_edges("detect_filters", after_filters,
                            {"fuzzy": "fuzzy", "generate": "generate"})
    g.add_edge("fuzzy", "generate")
    g.add_edge("generate", "guardrail")
    g.add_conditional_edges("guardrail", after_guardrail,
                            {"execute": "execute", "generate": "generate",
                             "blocked": "blocked"})
    g.add_conditional_edges("execute", after_execute,
                            {"done": END, "generate": "generate", "failed": "failed"})
    g.add_edge("blocked", END)
    g.add_edge("failed", END)
    return g.compile()
