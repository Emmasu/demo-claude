#!/usr/bin/env python3
"""
Background data fetcher — polls Deribit (BTC) and Bybit (MNT) every 60s
and saves candles to Convex.

Usage:
    python3 fetcher.py

Config (env vars or .env.local):
    CONVEX_URL      e.g. https://small-bulldog-987.convex.cloud
    DERIBIT_CALL    e.g. BTC-27MAR26-74000-C  (optional, auto-detected if omitted)
    DERIBIT_PUT     e.g. BTC-27MAR26-74000-P
    MNT_CALL        e.g. MNT-27MAR26-0.76-C-USDT
"""

import os, time, json, urllib.request, urllib.parse, logging
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
def load_env():
    path = os.path.join(os.path.dirname(__file__), ".env.local")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

CONVEX_URL   = os.environ.get("CONVEX_URL", "https://small-bulldog-987.convex.cloud")
DERIBIT_BASE = "https://www.deribit.com"
BYBIT_BASE   = "https://api.bybit.com"

DERIBIT_BTC  = "BTC-PERPETUAL"
DERIBIT_CALL = os.environ.get("DERIBIT_CALL", "BTC-27MAR26-74000-C")
DERIBIT_PUT  = os.environ.get("DERIBIT_PUT",  "BTC-27MAR26-74000-P")
MNT_CALL     = os.environ.get("MNT_CALL",     "MNT-27MAR26-0.76-C-USDT")
MNT_SPOT     = "MNTUSDT"

INTERVAL_SEC = 60

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def post(url, body, timeout=10):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type": "application/json", "User-Agent": "fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# ── Deribit ───────────────────────────────────────────────────────────────────
def fetch_deribit_candles(instrument, resolution, start_ms, end_ms):
    url = (f"{DERIBIT_BASE}/api/v2/public/get_tradingview_chart_data"
           f"?instrument_name={urllib.parse.quote(instrument)}"
           f"&resolution={resolution}&start_timestamp={start_ms}&end_timestamp={end_ms}")
    d = get(url)
    r = d.get("result", {})
    if r.get("status") != "ok" or not r.get("ticks"):
        return None
    return {"ticks": r["ticks"], "closes": r["close"]}

def fetch_deribit_dvol(start_ms, end_ms):
    url = (f"{DERIBIT_BASE}/api/v2/public/get_volatility_index_data"
           f"?currency=BTC&start_timestamp={start_ms}&end_timestamp={end_ms}&resolution=3600")
    d = get(url)
    rows = d.get("result", {}).get("data", [])
    if not rows:
        return None
    return {"ticks": [r[0] for r in rows], "closes": [r[4] for r in rows]}

# ── Bybit ─────────────────────────────────────────────────────────────────────
def fetch_bybit_kline(symbol, interval, limit=200, end_ms=None):
    url = (f"{BYBIT_BASE}/v5/market/kline"
           f"?category=spot&symbol={symbol}&interval={interval}&limit={limit}")
    if end_ms:
        url += f"&end={end_ms}"
    d = get(url)
    if d.get("retCode") != 0:
        return None
    rows = list(reversed(d["result"]["list"]))  # oldest first
    return {"ticks": [int(r[0]) for r in rows], "closes": [float(r[4]) for r in rows]}

def fetch_bybit_ticker(symbol):
    url = (f"{BYBIT_BASE}/v5/market/tickers"
           f"?category=option&symbol={urllib.parse.quote(symbol)}")
    d = get(url)
    if d.get("retCode") != 0 or not d["result"]["list"]:
        return None
    return d["result"]["list"][0]

# ── SQLite storage ────────────────────────────────────────────────────────────
def save_to_convex(name, ticks, closes):
    if not ticks:
        return
    db.append(name, ticks, closes)
    log.info(f"  saved {len(ticks)} pts → {name}")

# ── State: last fetched timestamps ────────────────────────────────────────────
last_ts = {
    "btc_min": 0, "call_min": 0, "put_min": 0,
    "btc_hour": 0, "call_hour": 0, "put_hour": 0, "dvol_hour": 0,
    "mnt_min": 0, "mnt_hour": 0, "mnt_day": 0,
}

def now_ms():
    return int(time.time() * 1000)

# ── Fetch cycle ───────────────────────────────────────────────────────────────
def fetch_deribit():
    end = now_ms()

    # ── Minute data (BTC + options) ──
    for key, instrument in [("btc_min", DERIBIT_BTC),
                             ("call_min", DERIBIT_CALL),
                             ("put_min",  DERIBIT_PUT)]:
        start = last_ts[key] if last_ts[key] else end - 2 * 3600 * 1000
        try:
            data = fetch_deribit_candles(instrument, 1, start, end)
            if data:
                save_to_convex(key, data["ticks"], data["closes"])
                last_ts[key] = data["ticks"][-1]
        except Exception as e:
            log.warning(f"deribit {key}: {e}")

    # ── Hourly data (BTC + options) ──
    for key, instrument in [("btc_hour",  DERIBIT_BTC),
                             ("call_hour", DERIBIT_CALL),
                             ("put_hour",  DERIBIT_PUT)]:
        start = last_ts[key] if last_ts[key] else end - 90 * 86400 * 1000
        try:
            data = fetch_deribit_candles(instrument, 60, start, end)
            if data:
                save_to_convex(key, data["ticks"], data["closes"])
                last_ts[key] = data["ticks"][-1]
        except Exception as e:
            log.warning(f"deribit {key}: {e}")

    # ── DVOL hourly ──
    start = last_ts["dvol_hour"] if last_ts["dvol_hour"] else end - 90 * 86400 * 1000
    try:
        data = fetch_deribit_dvol(start, end)
        if data:
            save_to_convex("dvol_hour", data["ticks"], data["closes"])
            last_ts["dvol_hour"] = data["ticks"][-1]
    except Exception as e:
        log.warning(f"deribit dvol_hour: {e}")


def fetch_bybit():
    # ── MNT spot minute ──
    try:
        data = fetch_bybit_kline(MNT_SPOT, 1, limit=200)
        if data:
            # Only send candles newer than last saved
            cutoff = last_ts["mnt_min"]
            new_ticks  = [t for t in data["ticks"]  if t > cutoff]
            new_closes = [c for t, c in zip(data["ticks"], data["closes"]) if t > cutoff]
            if new_ticks:
                save_to_convex("mnt_min", new_ticks, new_closes)
                last_ts["mnt_min"] = new_ticks[-1]
    except Exception as e:
        log.warning(f"bybit mnt_min: {e}")

    # ── MNT spot hourly ──
    try:
        data = fetch_bybit_kline(MNT_SPOT, 60, limit=500)
        if data:
            cutoff = last_ts["mnt_hour"]
            new_ticks  = [t for t in data["ticks"]  if t > cutoff]
            new_closes = [c for t, c in zip(data["ticks"], data["closes"]) if t > cutoff]
            if new_ticks:
                save_to_convex("mnt_hour", new_ticks, new_closes)
                last_ts["mnt_hour"] = new_ticks[-1]
    except Exception as e:
        log.warning(f"bybit mnt_hour: {e}")

    # ── MNT spot daily ──
    try:
        data = fetch_bybit_kline(MNT_SPOT, "D", limit=500)
        if data:
            cutoff = last_ts["mnt_day"]
            new_ticks  = [t for t in data["ticks"]  if t > cutoff]
            new_closes = [c for t, c in zip(data["ticks"], data["closes"]) if t > cutoff]
            if new_ticks:
                save_to_convex("mnt_day", new_ticks, new_closes)
                last_ts["mnt_day"] = new_ticks[-1]
    except Exception as e:
        log.warning(f"bybit mnt_day: {e}")

    # ── MNT live IV (ticker) ──
    try:
        ticker = fetch_bybit_ticker(MNT_CALL)
        if ticker and ticker.get("markIv"):
            ts = now_ms()
            save_to_convex("mnt_iv", [ts], [float(ticker["markIv"])])
    except Exception as e:
        log.warning(f"bybit mnt_iv: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log.info(f"Fetcher started — Convex: {CONVEX_URL}")
    log.info(f"Deribit: {DERIBIT_BTC} / {DERIBIT_CALL} / {DERIBIT_PUT}")
    log.info(f"Bybit:   {MNT_SPOT} / {MNT_CALL}")
    log.info(f"Interval: {INTERVAL_SEC}s")

    while True:
        cycle_start = time.time()
        log.info("── fetch cycle ──")
        fetch_deribit()
        fetch_bybit()
        elapsed = time.time() - cycle_start
        sleep = max(0, INTERVAL_SEC - elapsed)
        log.info(f"cycle done in {elapsed:.1f}s, sleeping {sleep:.0f}s")
        time.sleep(sleep)


if __name__ == "__main__":
    main()
