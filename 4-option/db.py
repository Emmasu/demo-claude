#!/usr/bin/env python3
"""SQLite storage layer — drop-in replacement for Convex candle_series."""

import os, json, sqlite3, threading

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "candles.db"))
_lock = threading.Lock()

def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candle_series (
            name   TEXT PRIMARY KEY,
            ticks  TEXT NOT NULL,
            closes TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def get_all():
    """Return list of {name, ticks, closes} — mirrors Convex candles:getAll."""
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT name, ticks, closes FROM candle_series").fetchall()
        conn.close()
    return [{"name": r[0], "ticks": json.loads(r[1]), "closes": json.loads(r[2])} for r in rows]

def append(name, new_ticks, new_closes):
    """Append new candles to a named series, dedup by timestamp, trim old data."""
    max_days = 90 if name.endswith("_hour") else (365 if name.endswith("_day") else 7)
    cutoff = (__import__("time").time() * 1000) - max_days * 86400 * 1000

    with _lock:
        conn = _connect()
        row = conn.execute("SELECT ticks, closes FROM candle_series WHERE name=?", (name,)).fetchone()
        if row:
            ticks  = json.loads(row[0])
            closes = json.loads(row[1])
        else:
            ticks, closes = [], []

        # Append only candles newer than what's stored
        last_ts = ticks[-1] if ticks else 0
        for t, c in zip(new_ticks, new_closes):
            if t > last_ts:
                ticks.append(t)
                closes.append(c)

        # Trim to rolling window
        cut = next((i for i, t in enumerate(ticks) if t >= cutoff), 0)
        ticks  = ticks[cut:]
        closes = closes[cut:]

        conn.execute(
            "INSERT INTO candle_series(name,ticks,closes) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET ticks=excluded.ticks, closes=excluded.closes",
            (name, json.dumps(ticks), json.dumps(closes))
        )
        conn.commit()
        conn.close()
