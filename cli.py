"""
Command-line interface for the Olist text-to-SQL pipeline.

Usage:
  python cli.py "How many orders were placed?"
  python cli.py --trace "Average review score by state"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from txt2sql.graph.pipeline import build_graph  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Olist text-to-SQL")
    parser.add_argument("question", help="Natural-language question")
    parser.add_argument("--trace", action="store_true", help="Print full pipeline trace")
    args = parser.parse_args()

    graph = build_graph()
    final = graph.invoke({"question": args.question})

    if args.trace:
        print("\n=== PIPELINE TRACE ===")
        for step in final.get("trace", []):
            stage = step.pop("stage")
            print(f"\n[{stage}]")
            for k, v in step.items():
                print(f"  {k}: {v}")
        print("\n=== RESULT ===")

    status = final.get("status")
    if status == "ok":
        print("\nSQL:")
        print(final["sql"])
        print(f"\n{len(final['result_rows'])} row(s):")
        print("  " + " | ".join(final["result_columns"]))
        for row in final["result_rows"][:50]:
            print("  " + " | ".join(str(c) for c in row))
    elif status == "blocked":
        print("\nBLOCKED by guardrail:")
        print(f"  {final.get('guard_reason')}")
        print(f"\nLast generated SQL (not executed):\n{final.get('sql')}")
    else:
        print(f"\nFAILED after retries: {final.get('last_error')}")
        print(f"\nLast generated SQL:\n{final.get('sql')}")


if __name__ == "__main__":
    main()
