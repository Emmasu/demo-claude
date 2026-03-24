#!/usr/bin/env python3
"""
Crypto Data Collector
Usage:
  python main.py ticker   [--exchange binance] [--symbols BTC/USDT ETH/USDT]
  python main.py ohlcv    [--exchange binance] [--symbol BTC/USDT] [--timeframe 1h] [--limit 100]
  python main.py orderbook [--exchange binance] [--symbol BTC/USDT]
  python main.py watch    [--exchange binance] [--symbols BTC/USDT ETH/USDT] [--interval 10]
  python main.py show     ticker|ohlcv|orderbook [--limit 20]
  python main.py exchanges
"""

import argparse
import sys

import ccxt
import storage
from collector import fetch_tickers, fetch_ohlcv, fetch_orderbook, watch_tickers
from config import DEFAULT_EXCHANGE, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAME

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


def print_table(rows, headers="keys"):
    if not rows:
        print("  (no data)")
        return
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline", floatfmt=".4f"))
    else:
        if rows:
            keys = list(rows[0].keys())
            print("  " + " | ".join(keys))
            print("  " + "-" * 60)
            for r in rows:
                print("  " + " | ".join(str(r[k]) for k in keys))


def cmd_ticker(args):
    symbols = args.symbols or DEFAULT_SYMBOLS
    print(f"\nFetching tickers from {args.exchange}...")
    results = fetch_tickers(args.exchange, symbols)
    print()
    print_table(results)


def cmd_ohlcv(args):
    print(f"\nFetching OHLCV ({args.timeframe}) for {args.symbol} from {args.exchange}...")
    ohlcv = fetch_ohlcv(args.exchange, args.symbol, args.timeframe, args.limit)
    if ohlcv:
        rows = [
            {"timestamp": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in ohlcv[-5:]
        ]
        print("\nLast 5 candles:")
        print_table(rows)


def cmd_orderbook(args):
    print(f"\nFetching order book for {args.symbol} from {args.exchange}...")
    ob = fetch_orderbook(args.exchange, args.symbol)
    if ob:
        bids = [{"side": "bid", "price": p, "amount": a} for p, a in ob.get("bids", [])[:5]]
        asks = [{"side": "ask", "price": p, "amount": a} for p, a in ob.get("asks", [])[:5]]
        print("\nTop 5 bids & asks:")
        print_table(bids + asks)


def cmd_watch(args):
    symbols = args.symbols or DEFAULT_SYMBOLS
    print(f"\nWatching {', '.join(symbols)} on {args.exchange} every {args.interval}s... (Ctrl+C to stop)")
    watch_tickers(args.exchange, symbols, interval=args.interval)


def cmd_show(args):
    storage.init_db()
    limit = args.limit
    if args.table == "ticker":
        rows = storage.query(
            "SELECT exchange, symbol, last, bid, ask, volume_24h, change_pct, fetched_at "
            "FROM tickers ORDER BY fetched_at DESC LIMIT ?", (limit,)
        )
    elif args.table == "ohlcv":
        rows = storage.query(
            "SELECT exchange, symbol, timeframe, datetime(ts/1000, 'unixepoch') as time, open, high, low, close, volume "
            "FROM ohlcv ORDER BY ts DESC LIMIT ?", (limit,)
        )
    elif args.table == "orderbook":
        rows = storage.query(
            "SELECT exchange, symbol, side, price, amount, depth_rank, fetched_at "
            "FROM orderbook_snapshots ORDER BY fetched_at DESC, side, depth_rank LIMIT ?", (limit,)
        )
    else:
        print(f"Unknown table: {args.table}")
        sys.exit(1)
    print(f"\n{args.table} (last {limit} rows):")
    print_table(rows)


def cmd_exchanges(_args):
    names = sorted(ccxt.exchanges)
    print(f"\n{len(names)} supported exchanges:")
    cols = 6
    for i in range(0, len(names), cols):
        print("  " + "  ".join(f"{n:<18}" for n in names[i:i+cols]))


def main():
    storage.init_db()

    parser = argparse.ArgumentParser(description="Crypto Data Collector")
    sub = parser.add_subparsers(dest="command")

    # ticker
    p = sub.add_parser("ticker", help="Fetch current ticker prices")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--symbols", nargs="+", default=None)

    # ohlcv
    p = sub.add_parser("ohlcv", help="Fetch OHLCV candlestick data")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    p.add_argument("--limit", type=int, default=100)

    # orderbook
    p = sub.add_parser("orderbook", help="Fetch order book snapshot")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--symbol", default="BTC/USDT")

    # watch
    p = sub.add_parser("watch", help="Continuously poll ticker prices")
    p.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    p.add_argument("--symbols", nargs="+", default=None)
    p.add_argument("--interval", type=int, default=10)

    # show
    p = sub.add_parser("show", help="Show stored data")
    p.add_argument("table", choices=["ticker", "ohlcv", "orderbook"])
    p.add_argument("--limit", type=int, default=20)

    # exchanges
    sub.add_parser("exchanges", help="List all supported exchanges")

    args = parser.parse_args()

    commands = {
        "ticker": cmd_ticker,
        "ohlcv": cmd_ohlcv,
        "orderbook": cmd_orderbook,
        "watch": cmd_watch,
        "show": cmd_show,
        "exchanges": cmd_exchanges,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
