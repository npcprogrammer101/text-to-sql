"""Filter-detection and SQL-generation agents."""
from __future__ import annotations

import re

from ..config import settings
from ..llm import Ollama, parse_list_output
from . import prompts

_filter_llm = Ollama(settings.agent_model)
_sql_llm = Ollama(settings.sql_model)


def detect_filters(question: str, columns: list[list[str]]) -> list:
    """Return the parsed filter spec: ['yes', [t,c,v], ...] or ['no']."""
    out = _filter_llm.complete(
        prompts.FILTER_SYSTEM,
        prompts.FILTER_USER.format(question=question, columns=str(columns)),
    )
    try:
        parsed = parse_list_output(out)
    except ValueError:
        return ["no"]
    return parsed if isinstance(parsed, list) and parsed else ["no"]


def _clean_sql(text_out: str) -> str:
    s = re.sub(r"```sql|```", "", text_out).strip()
    # strip a trailing semicolon so the guardrail sees one clean statement
    return s.rstrip(";").strip()


def generate_sql(question: str, columns: list[list[str]], filters: list,
                 error: str | None = None) -> str:
    user = prompts.SQL_USER.format(
        question=question, columns=str(columns), filters=str(filters)
    )
    if error:
        user += prompts.SQL_REPAIR_SUFFIX.format(error=error)
    out = _sql_llm.complete(prompts.SQL_SYSTEM, user)
    return _clean_sql(out)
