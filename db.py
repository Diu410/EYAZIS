"""SQLite storage shared by the three laboratory modules."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("eyazis.sqlite3")


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_url TEXT,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS terms (
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            term TEXT NOT NULL,
            frequency INTEGER NOT NULL,
            PRIMARY KEY (document_id, term)
        );
        CREATE INDEX IF NOT EXISTS terms_term_idx ON terms(term);
        """)
