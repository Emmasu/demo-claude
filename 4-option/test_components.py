#!/usr/bin/env python3
"""
Health-check tool for crypto-greeks app.
Tests: web server, Deribit proxy, Bybit proxy, Convex data, fetcher freshness.

Usage:
    python3 test_components.py                              # test deployed app
    python3 test_components.py --url http://localhost:8080  # test local
    python3 test_components.py --from 2025-01-01 --to 2025-01-07
"""

import sys, json, time, argparse, urllib.request, urllib.parse
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
DEPLOYED_URL  = "https://crypto-greeks-m8vgj.ondigitalocean.app"
CONVEX_URL    = "https://small-bulldog-987.convex.cloud"
DERIBIT_CALL  = "BTC-27MAR26-74000-C"
DERIBIT_PUT   = "BTC-27MAR26-74000-P"
BYBIT_SYMBOL  = "MNTUSDT"

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"

# ── Helpers ───────────────────────────────────────────────────────────────────
def get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "test/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read())

def post(url, body, timeout=10):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type": "application/json", "User-Agent": "test/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read())

def date_to_ms(s):
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def ms_to_str(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def check(label, fn):
    try:
        result, detail = fn()
        icon = PASS if result else FAIL
        print(f"  {icon}  {label}")
        if detail:
            print(f"         {detail}")
        return result
    except Exception as e:
        print(f"  {FAIL}  {label}")
        print(f"         Error: {e}")
        return False

# ── Tests ─────────────────────────────────────────────────────────────────────
def test_web_server(base_url):
    print("\n[1] Web Server")
    def _check():
        req = urllib.request.Request(base_url + "/", headers={"User-Agent": "test/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = r.status == 200
            return ok, f"HTTP {r.status} — {base_url}/"
    check("Root URL responds", _check)


def test_deribit_proxy(base_url, from_ms, to_ms):
    print("\n[2] Deribit Proxy")

    def _btc():
        path = (f"/proxy/deribit/api/v2/public/get_tradingview_chart_data"
                f"?instrument_name=BTC-PERPETUAL&resolution=60"
                f"&start_timestamp={from_ms}&end_timestamp={to_ms}")
        status, body = get(base_url + path)
        r = body.get("result", {})
        pts = len(r.get("ticks", []))
        ok = status == 200 and r.get("status") == "ok" and pts > 0
        return ok, f"{pts} candles  [{ms_to_str(from_ms)} → {ms_to_str(to_ms)}]"

    def _call():
        inst = urllib.parse.quote(DERIBIT_CALL)
        path = (f"/proxy/deribit/api/v2/public/get_tradingview_chart_data"
                f"?instrument_name={inst}&resolution=60"
                f"&start_timestamp={from_ms}&end_timestamp={to_ms}")
        status, body = get(base_url + path)
        r = body.get("result", {})
        pts = len(r.get("ticks", []))
        ok = status == 200 and pts > 0
        return ok, f"{pts} candles for {DERIBIT_CALL}"

    def _put():
        inst = urllib.parse.quote(DERIBIT_PUT)
        path = (f"/proxy/deribit/api/v2/public/get_tradingview_chart_data"
                f"?instrument_name={inst}&resolution=60"
                f"&start_timestamp={from_ms}&end_timestamp={to_ms}")
        status, body = get(base_url + path)
        r = body.get("result", {})
        pts = len(r.get("ticks", []))
        ok = status == 200 and pts > 0
        return ok, f"{pts} candles for {DERIBIT_PUT}"

    check("BTC-PERPETUAL candles", _btc)
    check(f"Call option candles  ({DERIBIT_CALL})", _call)
    check(f"Put option candles   ({DERIBIT_PUT})", _put)


def test_bybit_proxy(base_url):
    print("\n[3] Bybit Proxy")

    def _spot():
        path = f"/proxy/bybit/v5/market/kline?category=spot&symbol={BYBIT_SYMBOL}&interval=60&limit=10"
        status, body = get(base_url + path)
        ok = status == 200 and body.get("retCode") == 0
        pts = len(body.get("result", {}).get("list", []))
        return ok, f"{pts} klines for {BYBIT_SYMBOL}"

    check(f"MNT spot klines ({BYBIT_SYMBOL})", _spot)


def test_convex(convex_url, from_ms, to_ms):
    print("\n[4] Convex Database")

    def _fetch_all():
        body = {"path": "candles:getAll", "args": {}, "format": "json"}
        status, resp = post(f"{convex_url}/api/query", body)
        if status != 200:
            return None, f"HTTP {status}"
        rows = resp.get("value") or resp.get("result") or []
        return {r["name"]: r for r in rows}, None

    def _all_series():
        rows, err = _fetch_all()
        if err:
            return False, err
        if not rows:
            return False, "no series in Convex yet — fetcher may not have run"
        return True, f"{len(rows)} series stored: {', '.join(sorted(rows.keys()))}"
    check("Convex reachable + has data", _all_series)

    rows, _ = _fetch_all()
    if not rows:
        return

    for name in ["btc_min", "call_min", "put_min", "btc_hour", "dvol_hour", "mnt_min"]:
        def _series(n=name):
            r = rows.get(n)
            if not r:
                return False, "not stored yet"
            ticks = r.get("ticks", [])
            in_range = [t for t in ticks if from_ms <= t <= to_ms]
            latest = ms_to_str(max(ticks))
            age_min = (time.time() * 1000 - max(ticks)) / 60000
            return True, f"{len(in_range)} pts in range  |  latest={latest}  age={age_min:.0f}m"
        check(f"candles:{name}", _series)


def test_fetcher_freshness(convex_url):
    print("\n[5] Fetcher Freshness  (data < 5 min old?)")
    stale_thresh = 5 * 60 * 1000
    now = time.time() * 1000

    body = {"path": "candles:getAll", "args": {}, "format": "json"}
    try:
        _, resp = post(f"{convex_url}/api/query", body)
        rows = {r["name"]: r for r in (resp.get("value") or resp.get("result") or [])}
    except Exception as e:
        print(f"  {FAIL}  Could not reach Convex: {e}")
        return

    for name in ["btc_min", "call_min", "mnt_min"]:
        def _fresh(n=name):
            r = rows.get(n)
            if not r or not r.get("ticks"):
                return False, "no data — fetcher hasn't written yet"
            age_ms = now - max(r["ticks"])
            age_min = age_ms / 60000
            ok = age_ms < stale_thresh
            hint = "fresh" if ok else "STALE — fetcher may be down"
            return ok, f"last candle {age_min:.1f}m ago — {hint}"
        check(f"{name}", _fresh)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="crypto-greeks component health check")
    parser.add_argument("--url",  default=DEPLOYED_URL, help="Base URL (default: deployed app)")
    parser.add_argument("--from", dest="date_from", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--to",   dest="date_to",   default=None, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    now_ms = int(time.time() * 1000)
    from_ms = date_to_ms(args.date_from) if args.date_from else now_ms - 3 * 3600 * 1000
    to_ms   = date_to_ms(args.date_to)   if args.date_to   else now_ms

    print("=" * 60)
    print(f"  crypto-greeks health check")
    print(f"  URL:  {args.url}")
    print(f"  From: {ms_to_str(from_ms)}")
    print(f"  To:   {ms_to_str(to_ms)}")
    print("=" * 60)

    test_web_server(args.url)
    test_deribit_proxy(args.url, from_ms, to_ms)
    test_bybit_proxy(args.url)
    test_convex(CONVEX_URL, from_ms, to_ms)
    test_fetcher_freshness(CONVEX_URL)

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
