"""SQLite persistence for finished summaries shown in the local UI."""

import json

from db import connect


def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            source_url TEXT,
            result_json TEXT NOT NULL,
            ostis_saved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)


def save(title, result, source_url=""):
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO summaries(title, source_url, result_json) VALUES (?, ?, ?)",
            (title.strip() or "Документ без названия", source_url.strip(),
             json.dumps(result, ensure_ascii=False)),
        )
    return cursor.lastrowid


def get(summary_id):
    with connect() as db:
        row = db.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["result"] = json.loads(data.pop("result_json"))
    return data


def all_summaries():
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT id, title, source_url, created_at, ostis_saved "
            "FROM summaries ORDER BY id DESC")]


def mark_ostis_saved(summary_id):
    with connect() as db:
        db.execute("UPDATE summaries SET ostis_saved = 1 WHERE id = ?", (summary_id,))


def delete(summary_id):
    with connect() as db:
        db.execute("DELETE FROM summaries WHERE id = ?", (summary_id,))
