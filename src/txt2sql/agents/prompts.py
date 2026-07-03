"""
Prompt templates for every agent, kept in one place so they're easy to read,
tune, and review. These preserve the strong retrieval design from the original
project (router -> subquestion -> column selection -> filter -> SQL) while
trimming verbosity.

Each template is a (system, user) pair. `{placeholders}` are filled by the
agent functions.
"""

OLIST_CONTEXT = (
    "This dataset is from Olist, the largest department store on Brazilian "
    "marketplaces. A customer buys a product from a seller; the seller fulfills "
    "and ships it; after delivery (or the estimated date) the customer receives "
    "a satisfaction survey and may leave a review score and comment. An order "
    "can contain multiple items, each possibly from a different seller."
)

# --- Router ----------------------------------------------------------------
ROUTER_SYSTEM = (
    "You route a user's question to the table-groups that can help answer it. "
    "Multiple groups may apply. Output ONLY a JSON list of group-name strings, "
    "no prose."
)

ROUTER_USER = """Table-groups and what they contain:
{group_descriptions}

Rules:
- Split the question into parts and decide which group answers each part.
- Return every group that contributes, as a JSON list of strings.
- Examples: ["customer", "orders"]  or  ["product"]

User question:
{question}"""

# --- Subquestion / table selection -----------------------------------------
SUBQUESTION_SYSTEM = (
    "You are a subquestion generator inside a text-to-SQL system. You break a "
    "question into minimal parts and map each to the single most relevant table."
)

SUBQUESTION_USER = (
    OLIST_CONTEXT
    + """

Given a user question and a set of tables (with descriptions), do this:
1. Break the question into minimal, specific subquestions.
2. For each, pick the SINGLE most appropriate table by its description.
3. Drop any subquestion no table can answer.
4. A table may be included only to act as a JOIN link to another needed table.
5. If several subquestions map to one table, group them into one entry.

Output ONLY a JSON list of lists. Each inner list ends with the table name:
[["subquestion", "table"], ["subq a", "subq b", "table"]]
If nothing applies: []

Tables:
{tables}

User question:
{question}"""
)

# --- Column selection ------------------------------------------------------
COLUMN_SYSTEM = (
    "You select the minimal set of columns needed to answer a subquestion, for "
    "a downstream SQL generator. Choose only columns that help build the query."
)

COLUMN_USER = """For the subquestion (and with the main question in mind), pick the columns
from the list that the SQL will need.

Guidance:
- Always include identifier columns needed for joins/grouping (order_id,
  product_id, customer_id) when relevant.
- NEVER select customer_unique_id.
- When a metric needs several columns (e.g. quantity AND unit price for a
  total), include all of them.

Output ONLY a JSON list of lists, each: ["column_name", "why it's needed + sample values"].
If none: []

Columns available:
{columns}

Subquestion:
{subquestion}

Main question:
{main_question}"""

# --- Filter detection ------------------------------------------------------
FILTER_SYSTEM = (
    "You decide whether a text-to-SQL query needs WHERE-clause filters on "
    "STRING columns, and if so which columns and values."
)

FILTER_USER = """Analyze the question. Identify string-column filters it implies
(e.g. city='Campinas', payment_type='credit_card').

Rules:
- Only STRING columns that narrow the dataset (city, state, status, payment
  type, category). For numeric/date columns, do not emit a filter.
- Give the value(s) as the user stated them.
- Output ONLY a JSON list:
  ["yes", ["table", "column", "value(s)"], ...]  or  ["no"]

Question:
{question}

Available tables/columns (with sample values):
{columns}"""

# --- SQL generation --------------------------------------------------------
SQL_SYSTEM = (
    "You generate a single, syntactically correct, read-only MySQL SELECT query "
    "from the provided columns and filters. Output ONLY the SQL — no prose, no "
    "markdown fences, no trailing commentary."
)

SQL_USER = """Write ONE MySQL SELECT query answering the question.

Rules:
- Use the selected columns; they were chosen deliberately upstream.
- Apply the filters (already resolved to real DB values) as WHERE conditions.
- Use explicit JOINs and clear table aliases (never reserved words like or/and/as).
- Use a CTE if the query is complex.
- It must be a read-only SELECT. Never write, update, or delete.

User question:
{question}

Selected tables/columns:
{columns}

Resolved filters:
{filters}"""

# Repair suffix appended on a self-correction retry.
SQL_REPAIR_SUFFIX = """

Your previous query failed with this database error:
{error}

Return a corrected single SELECT query."""
