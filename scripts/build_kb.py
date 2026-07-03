"""
Build the knowledge base: LLM-generated descriptions of each table and its
columns, cached to data/kb.pkl so query-time never re-derives them.

Sample rows are used ONLY here, at build time, to help the local model write
good descriptions — and the resulting descriptions are what the query-time
agents see. This keeps bulk real data out of the live pipeline.

Usage:
  python scripts/build_kb.py
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from txt2sql.db.engine import admin_engine  # noqa: E402
from txt2sql.llm import Ollama, parse_list_output  # noqa: E402
from txt2sql.config import settings  # noqa: E402

TABLE_DESCRIPTIONS = {
    "order_items": "Items within orders: item count, product and seller ids, "
                   "price and freight per item, seller shipping-limit date.",
    "customer": "Customer id and location (city, state, zip prefix).",
    "order_payments": "Payments per order: sequential index, installments, "
                      "payment type, and value per transaction.",
    "order_reviews": "Reviews per order: score and optional comment.",
    "orders": "Order lifecycle: status and purchase/approval/delivery timestamps.",
    "products": "Product details: category (Portuguese), description length, "
                "dimensions, weight.",
    "sellers": "Seller id and location.",
    "category_translation": "Maps product category name Portuguese -> English.",
}

KB_SYSTEM = (
    "You annotate a SQL table for a text-to-SQL system. Given a table "
    "description and sample rows, produce a concise table description plus a "
    "description and 1-2 sample values for each column. Output ONLY the "
    "specified list format, no prose."
)

KB_USER = """Produce output as a JSON list of exactly two elements:
[
  "<one-paragraph table description>",
  [["col1: description, datatype, sample values: a, b (and more)"], ["col2: ..."]]
]

Base description: {description}

Sample rows:
{sample}"""


def sample_rows(table: str, n: int = 5) -> pd.DataFrame:
    with admin_engine().connect() as conn:
        return pd.read_sql(text(f"SELECT * FROM `{table}` ORDER BY RAND() LIMIT {n}"), conn)


def build() -> None:
    llm = Ollama(settings.agent_model, temperature=0.3)
    kb: dict = {}
    for table, base_desc in TABLE_DESCRIPTIONS.items():
        print(f"Annotating {table}...")
        df = sample_rows(table)
        out = llm.complete(
            KB_SYSTEM,
            KB_USER.format(description=base_desc, sample=df.to_string(index=False)),
        )
        try:
            parsed = parse_list_output(out)
            if isinstance(parsed, list) and len(parsed) == 2:
                kb[table] = parsed
            else:
                raise ValueError("unexpected shape")
        except ValueError:
            # fall back to base description + raw column names
            kb[table] = [base_desc, [[c] for c in df.columns]]
            print(f"  ! used fallback for {table}")

    out_path = Path(__file__).resolve().parents[1] / "data" / "kb.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(kb, f)
    print(f"Knowledge base written to {out_path}")


if __name__ == "__main__":
    build()
