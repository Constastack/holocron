import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "web.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            published_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            location TEXT,
            format TEXT,
            link TEXT
        );
    """)
    conn.commit()
    conn.close()


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "clanek"


def _unique_slug(conn, base_slug: str, exclude_id: int | None = None) -> str:
    slug = base_slug
    suffix = 2
    while True:
        row = conn.execute(
            "SELECT id FROM articles WHERE slug = ? AND (? IS NULL OR id != ?)",
            (slug, exclude_id, exclude_id),
        ).fetchone()
        if row is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


# ---------- Articles ----------

def create_article(title: str, body: str) -> str:
    conn = _connect()
    slug = _unique_slug(conn, slugify(title))
    conn.execute(
        "INSERT INTO articles (slug, title, body, published_at) VALUES (?, ?, ?, ?)",
        (slug, title, body, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return slug


def update_article(article_id: int, title: str, body: str):
    conn = _connect()
    conn.execute("UPDATE articles SET title = ?, body = ? WHERE id = ?", (title, body, article_id))
    conn.commit()
    conn.close()


def delete_article(article_id: int):
    conn = _connect()
    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()


def get_article_by_id(article_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_article_by_slug(slug: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM articles WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_articles(limit: int | None = None) -> list[dict]:
    conn = _connect()
    query = "SELECT * FROM articles ORDER BY published_at DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------- Calendar ----------

def create_event(name: str, event_date: str, location: str, format_: str, link: str) -> int:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO calendar_events (name, event_date, location, format, link) VALUES (?, ?, ?, ?, ?)",
        (name, event_date, location, format_, link),
    )
    conn.commit()
    event_id = cur.lastrowid
    conn.close()
    return event_id


def update_event(event_id: int, name: str, event_date: str, location: str, format_: str, link: str):
    conn = _connect()
    conn.execute(
        "UPDATE calendar_events SET name = ?, event_date = ?, location = ?, format = ?, link = ? WHERE id = ?",
        (name, event_date, location, format_, link, event_id),
    )
    conn.commit()
    conn.close()


def delete_event(event_id: int):
    conn = _connect()
    conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def get_event(event_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_events(upcoming_only: bool = False) -> list[dict]:
    conn = _connect()
    query = "SELECT * FROM calendar_events"
    params = ()
    if upcoming_only:
        query += " WHERE event_date >= ?"
        params = (datetime.now().date().isoformat(),)
    query += " ORDER BY event_date ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]
