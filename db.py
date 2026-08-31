"""SQLite schema and read/write helpers for the price drop tracker."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "prices.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    threshold REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    timestamp TEXT NOT NULL
);
"""


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def add_product(name: str, url: str, threshold: float) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO products (name, url, threshold) VALUES (?, ?, ?)",
            (name, url, threshold),
        )
        return cursor.lastrowid


def product_exists(url: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM products WHERE url = ?", (url,)).fetchone()
        return row is not None


def remove_product(product_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))


def list_products() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM products ORDER BY created_at").fetchall()


def get_product(product_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def insert_price(product_id: int, price: float, timestamp: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO price_history (product_id, price, timestamp) VALUES (?, ?, ?)",
            (product_id, price, timestamp),
        )


def get_history(product_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM price_history WHERE product_id = ? ORDER BY timestamp",
            (product_id,),
        ).fetchall()


def get_latest_price(product_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM price_history WHERE product_id = ? ORDER BY timestamp DESC LIMIT 1",
            (product_id,),
        ).fetchone()
