# Olist Text-to-SQL — a multi-agent pipeline with an AST guardrail

Ask questions in plain English against the [Olist Brazilian e-commerce
dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (9 tables,
~100k orders) and get read-only SQL back. A LangGraph multi-agent pipeline
narrows a large schema down to the columns a question needs, resolves fuzzy
filter values against real data, generates MySQL, and — critically — validates
every query with a real SQL parser and runs it under a read-only database role.

All models run **locally via Ollama**. No data or schema ever leaves the machine.

## Architecture

```
question
   │
   ▼
 route ──▶ retrieve ──▶ detect_filters ──┬─(filters)─▶ fuzzy_match ─┐
 (which     (subquestion   (are string     │                        │
  table-      → column       filters         └───(no filters)────────┤
  groups?)    selection)     needed?)                                 ▼
                                                                  generate
                                                                     │
                                                                     ▼
                                                                 guardrail ◀─┐
                                                             (sqlglot AST)   │ self-correct
                                                                     │       │ (feed error
                                                          pass ──────┤       │  back, retry)
                                                                     ▼       │
                                                                  execute ───┘
                                                            (read-only role)
                                                                     │
                                                                     ▼
                                                                  results
```

### The retrieval design

A large schema won't fit in a prompt, and dumping it hurts accuracy. So retrieval
is hierarchical:

1. **Router** picks which table-groups (customer / orders / product) are relevant.
2. **Subquestion agent** splits the question into parts and maps each to a single
   table.
3. **Column-selection agent** picks only the columns each part needs, from
   pre-generated descriptions in the knowledge base.

The model only ever sees **column descriptions**, never bulk table rows.

### Fuzzy value-matching

When a user writes "São Paulo" but the column stores "SP" or "sao paulo", a
literal filter misses. Before generation, requested filter values are resolved
against the actual `DISTINCT` values in the column using `rapidfuzz`, so the SQL
filters on a value that really exists.

## Security (the part worth reading)

This project is a from-scratch rebuild of an earlier prototype specifically to
get the safety architecture right. Four deliberate design decisions:

1. **AST guardrail, not an LLM check.** `guardrail.py` parses each generated
   query with `sqlglot` and rejects anything that isn't a single read-only
   `SELECT` over in-scope tables — no `DELETE`/`DROP`/`UPDATE`, no stacked
   statements, no out-of-scope tables (CTE names correctly excluded). Asking an
   LLM to "check the SQL" is not a security control; a parser is.

2. **Read-only database role.** Generated queries execute as `txt2sql_ro`, which
   holds `SELECT` and nothing else. Even if a write slipped past the guardrail,
   MySQL itself refuses it. Loading/admin work uses a separate elevated
   connection that the query path never touches.

3. **No `eval()` on model output.** Model responses are parsed with
   `ast.literal_eval` / `json` via `parse_list_output`, which only accepts
   literals — there is no code-execution path even on adversarial output.

4. **No committed secrets.** All credentials come from `.env` (git-ignored);
   `.env.example` documents them with placeholders.

The guardrail and the read-only role are independent layers — defense in depth.
The test suite (`tests/test_guardrail.py`) covers the guardrail against both
legitimate queries and attacks.

## Setup

### 1. Prerequisites
- Python 3.10+
- MySQL running locally
- [Ollama](https://ollama.com) with a model pulled: `ollama pull llama3.1:8b`

### 2. Install
```bash
pip install -e .            # add [data] for the loader, [dev] for tests
cp .env.example .env        # then edit .env with your DB passwords
```

### 3. Load data
```bash
python scripts/load_data.py            # downloads Olist + loads MySQL (admin role)
mysql -u root -p txt2sql < scripts/create_readonly_role.sql   # set a real password first
python scripts/build_kb.py             # builds data/kb.pkl via local model
```

### 4. Ask
```bash
python cli.py "How many orders were placed?"
python cli.py --trace "Average review score by state for credit-card orders"
```

`--trace` prints every stage's decision, including the guardrail's per-check
verdict — useful for demos and for understanding the flow.

## Testing
```bash
pytest            # guardrail tests, no DB or LLM required
```

## Project layout
```
src/txt2sql/
  config.py            settings from .env
  llm.py               Ollama client + safe list parser (no eval)
  guardrail.py         sqlglot AST validation
  db/engine.py         admin + read-only engines
  db/schema.py         table groups, KB loader
  agents/router.py     table-group routing
  agents/retrieval.py  subquestion + column selection
  agents/fuzzy.py      value matching
  agents/generate.py   filter detection + SQL generation
  agents/prompts.py    all prompt templates
  graph/pipeline.py    LangGraph wiring + self-correction
scripts/               load_data, build_kb, create_readonly_role.sql
tests/                 guardrail tests
cli.py
```

## Notes and limitations

- Local 8B models are weaker at hard SQL than frontier APIs; the pipeline is
  provider-pluggable (swap the `Ollama` class) if you want to compare.
- For real multi-tenant use you'd add per-user row-level security so the
  read-only role is further scoped by identity, plus audit logging of every
  generated query.
- The knowledge base uses sample rows at build time to write good descriptions;
  those descriptions (not bulk rows) are what the live pipeline sees.
```