"""SQLite persistence for finished summaries shown in the local UI."""

import json
from contextlib import closing

from db import connect


def initialize():
    with closing(connect()) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            source_url TEXT,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Rebuild old tables without the obsolete integration flag, retaining IDs,
        # original texts, results and dates. Works on Python 3.10's SQLite as well.
        columns = {row["name"] for row in db.execute("PRAGMA table_info(summaries)")}
        if "ostis_saved" in columns:
            db.executescript("""
            BEGIN;
            CREATE TABLE summaries_local (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                source_url TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO summaries_local(id, title, source_url, result_json, created_at)
                SELECT id, title, source_url, result_json, created_at FROM summaries;
            DROP TABLE summaries;
            ALTER TABLE summaries_local RENAME TO summaries;
            COMMIT;
            """)


def save(title, result, source_url=""):
    with closing(connect()) as db, db:
        cursor = db.execute(
            "INSERT INTO summaries(title, source_url, result_json) VALUES (?, ?, ?)",
            (title.strip() or "Документ без названия", source_url.strip(),
             json.dumps(result, ensure_ascii=False)),
        )
    return cursor.lastrowid


def get(summary_id):
    with closing(connect()) as db, db:
        row = db.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["result"] = json.loads(data.pop("result_json"))
    return data


def all_summaries():
    with closing(connect()) as db, db:
        return [dict(row) for row in db.execute(
            "SELECT id, title, source_url, created_at, "
            "COALESCE(json_extract(result_json, '$.method'), 'extractive') AS method "
            "FROM summaries ORDER BY id DESC")]


def delete(summary_id):
    with closing(connect()) as db, db:
        db.execute("DELETE FROM summaries WHERE id = ?", (summary_id,))
