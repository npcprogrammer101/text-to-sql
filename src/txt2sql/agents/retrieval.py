"""
Retrieval agents — the strongest idea carried over from the original project.

Two stages narrow a large schema down to just the columns a question needs:
  1. subquestion: break the question into parts, map each to one table.
  2. column selection: for each (subquestion, table), pick the needed columns
     from that table's KB description.

All model outputs are parsed with parse_list_output (safe), never eval().
"""
from __future__ import annotations

from ..config import settings
from ..llm import Ollama, parse_list_output
from ..db.schema import TABLE_GROUPS, load_kb
from . import prompts

_llm = Ollama(settings.agent_model)
_kb = None


def _kb_cached():
    global _kb
    if _kb is None:
        _kb = load_kb()
    return _kb


def subquestions_for_group(question: str, group: str) -> list[list[str]]:
    """Return [[subquestion..., table], ...] for one table-group."""
    kb = _kb_cached()
    tables = TABLE_GROUPS[group]
    table_descs = {t: kb[t][0] for t in tables if t in kb}
    out = _llm.complete(
        prompts.SUBQUESTION_SYSTEM,
        prompts.SUBQUESTION_USER.format(tables=str(table_descs), question=question),
    )
    parsed = parse_list_output(out)
    # filter to well-formed non-empty entries
    return [entry for entry in parsed if isinstance(entry, list) and len(entry) >= 2]


def columns_for_subquestions(main_question: str, entries: list[list[str]]) -> list[list[str]]:
    """
    For each [subq..., table] entry, ask which columns are needed.
    Returns rows like ["name of table:<t>", "<column>", "<why + samples>"].
    """
    kb = _kb_cached()
    selected: list[list[str]] = []
    for entry in entries:
        table = entry[-1]
        subq = " ".join(entry[:-1])
        if table not in kb:
            continue
        columns = kb[table][1]  # [[col, desc], ...]
        out = _llm.complete(
            prompts.COLUMN_SYSTEM,
            prompts.COLUMN_USER.format(
                columns=str(columns), subquestion=subq, main_question=main_question
            ),
        )
        try:
            picked = parse_list_output(out)
        except ValueError:
            continue
        for col in picked:
            if isinstance(col, list) and col:
                selected.append([f"name of table:{table}", *col])
    return selected


def retrieve_columns(question: str, groups: list[str]) -> list[list[str]]:
    """Full retrieval across all routed groups, de-duplicated."""
    all_entries: list[list[str]] = []
    for group in groups:
        all_entries.extend(subquestions_for_group(question, group))

    selected = columns_for_subquestions(question, all_entries)

    # de-duplicate identical rows, preserving order
    seen = set()
    deduped = []
    for row in selected:
        key = tuple(row)
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped
