"""Router agent — picks the table-groups relevant to a question."""
from __future__ import annotations

from ..config import settings
from ..llm import Ollama, parse_list_output
from ..db.schema import GROUP_DESCRIPTIONS, TABLE_GROUPS
from . import prompts

_llm = Ollama(settings.router_model)


def route(question: str) -> list[str]:
    desc = "\n".join(f"- {g}: {d}" for g, d in GROUP_DESCRIPTIONS.items())
    out = _llm.complete(
        prompts.ROUTER_SYSTEM,
        prompts.ROUTER_USER.format(group_descriptions=desc, question=question),
    )
    groups = parse_list_output(out)
    # keep only valid group names; default to all groups if the model whiffs
    valid = [g for g in groups if g in TABLE_GROUPS]
    return valid or list(TABLE_GROUPS.keys())
