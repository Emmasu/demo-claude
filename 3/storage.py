import sqlite3
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS tickers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange    TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            bid         REAL,
            ask         REAL,
            last        REAL,
            volume_24h  REAL,
            change_pct  REAL,
            fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ohlcv (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange    TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            timeframe   TEXT NOT NULL,
            ts          INTEGER NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      REAL,
            UNIQUE(exchange, symbol, timeframe, ts)
        );

        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange    TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            side        TEXT NOT NULL,
            price       REAL NOT NULL,
            amount      REAL NOT NULL,
            depth_rank  INTEGER NOT NULL,
            fetched_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def insert_ticker(exchange, symbol, data):
    conn = get_conn()
    conn.execute(
        """INSERT INTO tickers (exchange, symbol, bid, ask, last, volume_24h, change_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            exchange,
            symbol,
            data.get("bid"),
            data.get("ask"),
            data.get("last"),
            data.get("baseVolume"),
            data.get("percentage"),
        ),
    )
    conn.commit()
    conn.close()


def insert_ohlcv(exchange, symbol, timeframe, rows):
    conn = get_conn()
    conn.executemany(
        """INSERT OR IGNORE INTO ohlcv (exchange, symbol, timeframe, ts, open, high, low, close, volume)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(exchange, symbol, timeframe, r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows],
    )
    conn.commit()
    conn.close()


def insert_orderbook(exchange, symbol, bids, asks):
    conn = get_conn()
    rows = []
    for i, (price, amount) in enumerate(bids[:10]):
        rows.append((exchange, symbol, "bid", price, amount, i + 1))
    for i, (price, amount) in enumerate(asks[:10]):
        rows.append((exchange, symbol, "ask", price, amount, i + 1))
    conn.executemany(
        """INSERT INTO orderbook_snapshots (exchange, symbol, side, price, amount, depth_rank)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


def query(sql, params=()):
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
