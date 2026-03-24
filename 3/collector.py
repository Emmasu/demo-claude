import ccxt
import time
import storage
from config import DEFAULT_EXCHANGE, DEFAULT_SYMBOLS, DEFAULT_TIMEFRAME


def get_exchange(exchange_id):
    cls = getattr(ccxt, exchange_id, None)
    if cls is None:
        raise ValueError(f"Unknown exchange: {exchange_id}")
    ex = cls({"enableRateLimit": True})
    return ex


def fetch_tickers(exchange_id=DEFAULT_EXCHANGE, symbols=None):
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    ex = get_exchange(exchange_id)
    results = []
    for symbol in symbols:
        try:
            ticker = ex.fetch_ticker(symbol)
            storage.insert_ticker(exchange_id, symbol, ticker)
            results.append(
                {
                    "symbol": symbol,
                    "last": ticker.get("last"),
                    "bid": ticker.get("bid"),
                    "ask": ticker.get("ask"),
                    "volume_24h": ticker.get("baseVolume"),
                    "change_pct": ticker.get("percentage"),
                }
            )
            print(f"  [{exchange_id}] {symbol}: ${ticker.get('last'):,.4f}")
        except Exception as e:
            print(f"  Error fetching ticker for {symbol}: {e}")
    return results


def fetch_ohlcv(exchange_id=DEFAULT_EXCHANGE, symbol="BTC/USDT", timeframe=DEFAULT_TIMEFRAME, limit=100):
    ex = get_exchange(exchange_id)
    try:
        if not ex.has["fetchOHLCV"]:
            print(f"  {exchange_id} does not support OHLCV")
            return []
        ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        storage.insert_ohlcv(exchange_id, symbol, timeframe, ohlcv)
        print(f"  [{exchange_id}] {symbol} {timeframe}: {len(ohlcv)} candles saved")
        return ohlcv
    except Exception as e:
        print(f"  Error fetching OHLCV for {symbol}: {e}")
        return []


def fetch_orderbook(exchange_id=DEFAULT_EXCHANGE, symbol="BTC/USDT"):
    ex = get_exchange(exchange_id)
    try:
        ob = ex.fetch_order_book(symbol, limit=10)
        storage.insert_orderbook(exchange_id, symbol, ob["bids"], ob["asks"])
        spread = ob["asks"][0][0] - ob["bids"][0][0] if ob["asks"] and ob["bids"] else None
        print(f"  [{exchange_id}] {symbol} order book: spread=${spread:.2f}" if spread else f"  [{exchange_id}] {symbol} order book saved")
        return ob
    except Exception as e:
        print(f"  Error fetching order book for {symbol}: {e}")
        return {}


def watch_tickers(exchange_id=DEFAULT_EXCHANGE, symbols=None, interval=10, rounds=None):
    """Poll tickers repeatedly at `interval` seconds."""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    count = 0
    try:
        while rounds is None or count < rounds:
            count += 1
            print(f"\n--- Round {count} ({time.strftime('%H:%M:%S')}) ---")
            fetch_tickers(exchange_id, symbols)
            if rounds is None or count < rounds:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
