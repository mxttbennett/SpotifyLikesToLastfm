import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    spotify_id TEXT NOT NULL,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    clean_title TEXT,
    loved_at TEXT,
    unloved_at TEXT
);
CREATE UNIQUE INDEX tracks_active ON tracks (spotify_id) WHERE unloved_at IS NULL;
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_log_line(line):
    artist, rest = line.split(" - ", 1)
    title, track_id = rest.rsplit(" - ", 1)
    return artist, title, track_id


def open_store(db_path, log_path):
    conn = sqlite3.connect(db_path)
    if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
        with conn:
            conn.executescript(SCHEMA)
            if os.path.exists(log_path):
                with open(log_path, encoding="utf-8") as f:
                    rows = [parse_log_line(line.strip()) for line in f if line.strip()]
                # The log never recorded times, so imported rows keep loved_at NULL.
                conn.executemany(
                    "INSERT OR IGNORE INTO tracks (artist, title, spotify_id) VALUES (?, ?, ?)", rows)
            conn.execute("PRAGMA user_version = 1")
    return conn


def active_tracks(conn):
    return conn.execute(
        "SELECT artist, title, spotify_id FROM tracks WHERE unloved_at IS NULL ORDER BY id").fetchall()


def record_love(conn, artist, title, clean_title, spotify_id):
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO tracks (spotify_id, artist, title, clean_title, loved_at) VALUES (?, ?, ?, ?, ?)",
            (spotify_id, artist, title, clean_title, now()))


def record_unlove(conn, spotify_ids):
    with conn:
        conn.executemany(
            "UPDATE tracks SET unloved_at = ? WHERE spotify_id = ? AND unloved_at IS NULL",
            [(now(), i) for i in spotify_ids])
