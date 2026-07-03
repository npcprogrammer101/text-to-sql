"""
Central configuration. Every secret and connection detail comes from the
environment (loaded from a local .env that is never committed). This is the
first fix over the original project, which hardcoded the MySQL root password
in source files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


@dataclass(frozen=True)
class Settings:
    # --- Admin DB connection (schema creation + data loading ONLY) ---------
    admin_db_url: str
    # --- Read-only DB connection (ALL generated-query execution) -----------
    readonly_db_url: str
    # --- Ollama (local models) ---------------------------------------------
    ollama_host: str
    router_model: str
    agent_model: str
    sql_model: str
    # --- Execution guardrails ----------------------------------------------
    max_rows: int
    statement_timeout_s: int
    max_repairs: int


def load_settings() -> Settings:
    return Settings(
        admin_db_url=os.getenv(
            "ADMIN_DATABASE_URL",
            # default points at localhost; password still comes from env in prod
            "mysql+mysqlconnector://root:@localhost/txt2sql",
        ),
        readonly_db_url=os.getenv(
            "READONLY_DATABASE_URL",
            "mysql+mysqlconnector://txt2sql_ro:@localhost/txt2sql",
        ),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        router_model=os.getenv("ROUTER_MODEL", "llama3.1:8b"),
        agent_model=os.getenv("AGENT_MODEL", "llama3.1:8b"),
        sql_model=os.getenv("SQL_MODEL", "llama3.1:8b"),
        max_rows=int(os.getenv("MAX_ROWS", "200")),
        statement_timeout_s=int(os.getenv("STATEMENT_TIMEOUT_S", "10")),
        max_repairs=int(os.getenv("MAX_REPAIRS", "2")),
    )


settings = load_settings()
