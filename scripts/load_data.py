"""
Load the Olist dataset into MySQL.

Downloads the Kaggle dataset, then writes each CSV to a table using the ADMIN
engine (this is the one place elevated privileges are needed — creating tables).
Query execution later uses the read-only role instead.

Usage:
  python scripts/load_data.py
Requires ADMIN_DATABASE_URL in .env and `kagglehub` installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from txt2sql.db.engine import admin_engine  # noqa: E402

# CSV filename -> table name
TABLES = {
    "olist_customers_dataset.csv": "customer",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_orders_dataset.csv": "orders",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "category_translation",
}

INDEXES = [
    "CREATE INDEX idx_orders_customer ON orders (customer_id(20))",
    "CREATE INDEX idx_orders_id ON orders (order_id(20))",
    "CREATE INDEX idx_customer_id ON customer (customer_id(20))",
    "CREATE INDEX idx_oi_order ON order_items (order_id(20))",
    "CREATE INDEX idx_oi_product ON order_items (product_id(20))",
    "CREATE INDEX idx_oi_seller ON order_items (seller_id(20))",
    "CREATE INDEX idx_sellers_id ON sellers (seller_id(20))",
    "CREATE INDEX idx_products_id ON products (product_id(20))",
    "CREATE INDEX idx_reviews_order ON order_reviews (order_id(20))",
    "CREATE INDEX idx_payments_order ON order_payments (order_id(20))",
]


def download() -> Path:
    import kagglehub
    path = kagglehub.dataset_download("olistbr/brazilian-ecommerce")
    print(f"Dataset downloaded to: {path}")
    return Path(path)


def load(data_dir: Path) -> None:
    engine = admin_engine()
    for csv_name, table in TABLES.items():
        csv_path = data_dir / csv_name
        if not csv_path.exists():
            print(f"  ! missing {csv_name}, skipping")
            continue
        df = pd.read_csv(csv_path)
        df.to_sql(name=table, con=engine, index=False, if_exists="replace")
        print(f"  loaded {table}  ({len(df):,} rows)")

    print("Creating indexes...")
    with engine.begin() as conn:
        for stmt in INDEXES:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                print(f"  ! index skipped: {str(e)[:60]}")
    print("Done.")


if __name__ == "__main__":
    data_dir = download()
    load(data_dir)
