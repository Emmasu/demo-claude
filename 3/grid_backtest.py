#!/usr/bin/env python3
"""
Spot Grid Trading Backtest — core engine + CLI
Usage:
  python grid_backtest.py [--symbol BTC/USDT] [--timeframe 1h]
                          [--lower 70000] [--upper 76000] [--grids 10]
                          [--capital 10000] [--fee 0.1]
"""

import argparse
import sqlite3
from datetime import datetime
from config import DB_PATH

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def get_ohlcv(symbol, timeframe):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT ts, open, high, low, close FROM ohlcv "
        "WHERE symbol=? AND timeframe=? ORDER BY ts ASC",
        (symbol, timeframe),
    ).fetchall()
    conn.close()
    return rows  # [(ts, open, high, low, close), ...]


def ts_to_str(ts):
    return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _tf_to_ms(timeframe):
    """Convert timeframe string to milliseconds, e.g. '1h' → 3600000, '15m' → 900000."""
    import re
    m = re.match(r"(\d+)([mhd])", timeframe)
    num, unit = int(m.group(1)), m.group(2)
    return num * {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unit]


# ---------------------------------------------------------------------------
# Core engine  (used by both CLI and web app)
# ---------------------------------------------------------------------------

def backtest_engine(symbol, lower, upper, n_grids, capital, fee_rate=0.001, timeframe="1h"):
    """
    Run a spot grid backtest. Returns a rich result dict, or None if no data.

    Parameters
    ----------
    symbol        : e.g. "BTC/USDT"
    lower / upper : price range
    n_grids       : number of grid INTERVALS  (n_grids+1 lines)
    capital       : total USDT to deploy
    fee_rate      : per-trade fee as a fraction, e.g. 0.001 = 0.1%
    timeframe     : OHLCV timeframe
    """
    ohlcv = get_ohlcv(symbol, timeframe)
    if not ohlcv:
        return None

    step = (upper - lower) / n_grids
    grid_lines = [lower + i * step for i in range(n_grids + 1)]

    # ---- Initialise positions ----
    open_price = ohlcv[0][1]

    # Grid init logic:
    # 1. Find the "straddling slot" — whose range contains the entry price.
    # 2. Pre-fill slots whose buy_price is STRICTLY ABOVE the straddling slot's sell_price.
    #    This skips the slot immediately above the current interval (its buy price == straddling sell)
    #    to avoid a phantom trade at the same level where a sell is already pending.
    #
    # e.g. range 60k-70k, 5 grids (step 2k), entry=63,192:
    #   Straddling slot: [62k-64k]  → straddling sell = 64k
    #   buy@64k > 64k? NO  → skip (slot 2, no order)
    #   buy@66k > 64k? YES → fill at market  (slot 3 = BTC, sell at 68k)
    #   buy@68k > 64k? YES → fill at market  (slot 4 = BTC, sell at 70k)
    #   buy@62k and below  → USDT, pending buy orders

    # Find the upper bound of the straddling slot
    straddling_upper = upper  # default: if entry is outside range, no pre-fill
    for i in range(n_grids):
        if grid_lines[i] <= open_price < grid_lines[i + 1]:
            straddling_upper = grid_lines[i + 1]
            break

    # Equal-BTC grid: use open_price for pre-filled slots, grid_lines[i] for USDT slots
    effective_buy_prices = [
        open_price if grid_lines[i] > straddling_upper else grid_lines[i]
        for i in range(n_grids)
    ]
    btc_per_grid     = capital / sum(effective_buy_prices)
    capital_per_grid = capital / n_grids  # display reference only

    usdt = capital
    btc = 0.0
    total_fee = 0.0

    # slot_state[i] = True  → holding BTC (bought at market), sell order at grid_lines[i+1]
    # slot_state[i] = False → holding USDT, buy order at grid_lines[i]
    slot_state = {}
    for i in range(n_grids):
        if grid_lines[i] > straddling_upper:
            # Buy price strictly above straddling slot's sell → buy at market immediately
            usdt_cost = btc_per_grid * open_price
            fee       = usdt_cost * fee_rate
            usdt     -= usdt_cost + fee
            btc      += btc_per_grid
            total_fee += fee
            slot_state[i] = True
        else:
            slot_state[i] = False

    # snapshot initial state before simulation
    init_slot_state = dict(slot_state)
    init_usdt = usdt
    init_btc  = btc

    # ---- Record initial position market buys in trade log ----
    init_dt = ts_to_str(ohlcv[0][0])
    trades = []
    for i in range(n_grids):
        if init_slot_state[i]:
            usdt_cost = btc_per_grid * open_price
            fee       = usdt_cost * fee_rate
            trades.append({
                "time":        init_dt,
                "action":      "BUY",
                "grid":        i,
                "price":       round(open_price, 2),
                "amount":      round(btc_per_grid, 6),
                "value":       round(usdt_cost, 4),
                "fee":         round(fee, 4),
                "grid_profit": 0.0,
                "note":        "init",
            })
    portfolio_history = []
    total_grid_profit = 0.0
    half_tf_ms = _tf_to_ms(timeframe) // 2  # half candle duration for intra-candle time split
    price_hwm = open_price  # tracks highest price seen; gates above-market buy orders

    for ts, open_, high, low, close in ohlcv:
        bearish = open_ > close   # assume: bearish → high first, then low

        # Split the candle in two halves so events get distinct timestamps:
        # bearish:  sells in first half (high reached first), buys in second half
        # bullish:  buys in first half (low reached first), sells in second half
        dt_first  = ts_to_str(ts)
        dt_second = ts_to_str(ts + half_tf_ms)

        u, b, p, f = [usdt], [btc], [total_grid_profit], [total_fee]
        if bearish:
            _do_sells(dt_first,  high, grid_lines, slot_state, btc_per_grid, fee_rate, trades, u, b, p, f)
            _do_buys( dt_second, low, high, grid_lines, slot_state, btc_per_grid, fee_rate, trades, u, b, f, price_hwm, open_price)
        else:
            _do_buys( dt_first,  low, high, grid_lines, slot_state, btc_per_grid, fee_rate, trades, u, b, f, price_hwm, open_price)
            _do_sells(dt_second, high, grid_lines, slot_state, btc_per_grid, fee_rate, trades, u, b, p, f)
        usdt, btc, total_grid_profit, total_fee = u[0], b[0], p[0], f[0]

        # Update watermark AFTER processing current candle so a candle that first reaches
        # a sell level doesn't also unlock the buy in the same candle.
        price_hwm = max(price_hwm, high)

        portfolio_history.append({
            "ts": ts,
            "time": dt_first,
            "close": close,
            "usdt": usdt,
            "btc": btc,
            "portfolio_value": usdt + btc * close,
        })

    # ---- Max drawdown ----
    peak = capital
    max_dd = 0.0
    max_dd_pct = 0.0
    for h in portfolio_history:
        v = h["portfolio_value"]
        if v > peak:
            peak = v
        dd_pct = (peak - v) / peak * 100
        h["drawdown_pct"] = dd_pct
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = peak - v

    # ---- Number trades sequentially ----
    for idx, t in enumerate(trades, start=1):
        t["#"] = idx

    # ---- Final metrics ----
    final_price = ohlcv[-1][4]
    final_btc_value = btc * final_price
    final_total = usdt + final_btc_value

    return {
        # config
        "slot_state": slot_state,
        "init_slot_state": init_slot_state,
        "init_usdt": init_usdt,
        "init_btc":  init_btc,
        "symbol": symbol,
        "timeframe": timeframe,
        "lower": lower,
        "upper": upper,
        "n_grids": n_grids,
        "capital": capital,
        "fee_rate": fee_rate,
        "grid_lines": grid_lines,
        "step": step,
        "btc_per_grid": btc_per_grid,
        "capital_per_grid": capital_per_grid,
        # context
        "entry_price": open_price,
        "final_price": final_price,
        "n_candles": len(ohlcv),
        "date_start": ts_to_str(ohlcv[0][0]),
        "date_end": ts_to_str(ohlcv[-1][0]),
        # trades
        "trades": trades,
        "n_buys": sum(1 for t in trades if t["action"] == "BUY"),
        "n_sells": sum(1 for t in trades if t["action"] == "SELL"),
        # portfolio
        "portfolio_history": portfolio_history,
        # results
        "total_grid_profit": total_grid_profit,
        "total_fee": total_fee,
        "final_usdt": usdt,
        "final_btc": btc,
        "final_btc_value": final_btc_value,
        "final_total": final_total,
        "pnl": final_total - capital,
        "pnl_pct": (final_total - capital) / capital * 100,
        "hodl_pnl_pct": (final_price - open_price) / open_price * 100,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
    }


def _do_buys(dt, low, high, grid_lines, slot_state, btc_per_grid, fee_rate, trades, u, b, f, price_hwm, initial_open):
    for i in range(len(grid_lines) - 1):
        # Above-market slots: only allow buy after price has previously reached their sell level.
        # This prevents the "nearest grid above market" slot from buying on the first upward touch.
        if grid_lines[i] >= initial_open and price_hwm < grid_lines[i + 1]:
            continue
        usdt_cost = btc_per_grid * grid_lines[i]
        total_out = usdt_cost * (1 + fee_rate)
        # Buy fires only when price passed THROUGH the buy level: low <= price <= high
        if not slot_state[i] and low <= grid_lines[i] <= high and u[0] >= total_out:
            fee = usdt_cost * fee_rate
            u[0] -= total_out
            b[0] += btc_per_grid
            f[0] += fee
            slot_state[i] = True
            trades.append({
                "time": dt, "action": "BUY", "grid": i,
                "price": round(grid_lines[i], 2),
                "amount": round(btc_per_grid, 6),
                "value": round(usdt_cost, 4),
                "fee": round(fee, 4),
                "grid_profit": 0.0,
            })


def _do_sells(dt, high, grid_lines, slot_state, btc_per_grid, fee_rate, trades, u, b, p, f):
    for i in range(len(grid_lines) - 1):
        if slot_state[i] and high >= grid_lines[i + 1]:
            gross       = btc_per_grid * grid_lines[i + 1]
            fee         = gross * fee_rate
            proceeds    = gross - fee
            buy_cost    = btc_per_grid * grid_lines[i] * (1 + fee_rate)
            grid_profit = proceeds - buy_cost
            u[0] += proceeds
            b[0] -= btc_per_grid
            p[0] += grid_profit
            f[0] += fee
            slot_state[i] = False
            trades.append({
                "time": dt, "action": "SELL", "grid": i,
                "price": round(grid_lines[i + 1], 2),
                "amount": round(btc_per_grid, 6),
                "value": round(proceeds, 4),
                "fee": round(fee, 4),
                "grid_profit": round(grid_profit, 4),
            })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_table(rows, headers="keys"):
    if not rows:
        print("  (no data)")
        return
    if HAS_TABULATE:
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline", floatfmt=".4f"))
    else:
        keys = list(rows[0].keys())
        print("  " + " | ".join(keys))
        print("  " + "-" * 80)
        for r in rows:
            print("  " + " | ".join(str(r[k]) for k in keys))


def run_cli(args):
    r = backtest_engine(
        symbol=args.symbol,
        lower=args.lower,
        upper=args.upper,
        n_grids=args.grids,
        capital=args.capital,
        fee_rate=args.fee / 100,
        timeframe=args.timeframe,
    )
    if r is None:
        print(f"No data found for {args.symbol} {args.timeframe}. Run collector first.")
        return

    print(f"\n{'='*62}")
    print(f"  Spot Grid Backtest — {r['symbol']} ({r['timeframe']})")
    print(f"{'='*62}")
    print(f"  Price range  : ${r['lower']:,.0f} – ${r['upper']:,.0f}  (step ${r['step']:,.2f})")
    print(f"  Grids        : {r['n_grids']} intervals  ({r['n_grids']+1} lines)")
    print(f"  Capital      : ${r['capital']:,.2f}  |  Per grid: ${r['capital_per_grid']:,.2f}")
    print(f"  Fee          : {r['fee_rate']*100:.3f}% per trade")
    print(f"  Candles      : {r['n_candles']} x {r['timeframe']}  ({r['date_start']} → {r['date_end']})")
    print(f"  Entry price  : ${r['entry_price']:,.2f}")
    print(f"{'='*62}\n")

    print("  Grid lines:")
    for i, price in enumerate(r["grid_lines"]):
        next_p = r["grid_lines"][i + 1] if i + 1 < len(r["grid_lines"]) else price + 1
        marker = " <-- entry" if price <= r["entry_price"] < next_p else ""
        print(f"    [{i:2d}] ${price:>10,.2f}{marker}")
    print()

    print(f"  Last 20 trades:")
    _print_table(r["trades"][-20:])

    print(f"\n{'='*62}")
    print(f"  RESULTS")
    print(f"{'='*62}")
    print(f"  Total trades     : {len(r['trades'])}  ({r['n_buys']} buys / {r['n_sells']} sells)")
    print(f"  Grid profit      : ${r['total_grid_profit']:>+10,.4f}")
    print(f"  Total fees paid  : ${r['total_fee']:>10,.4f}")
    print(f"  Net grid profit  : ${r['total_grid_profit'] - r['total_fee']:>+10,.4f}")
    print(f"  Final USDT       : ${r['final_usdt']:>10,.4f}")
    print(f"  Final BTC        : {r['final_btc']:.6f}  (${r['final_btc_value']:,.4f})")
    print(f"  Final portfolio  : ${r['final_total']:>10,.4f}")
    print(f"  PnL              : ${r['pnl']:>+10,.4f}  ({r['pnl_pct']:+.2f}%)")
    print(f"  Max drawdown     : ${r['max_drawdown']:>10,.4f}  ({r['max_drawdown_pct']:.2f}%)")
    print(f"  HODL return      : {r['hodl_pnl_pct']:>+10.2f}%  (${r['entry_price']:,.2f} → ${r['final_price']:,.2f})")
    print(f"{'='*62}\n")


def main():
    parser = argparse.ArgumentParser(description="Spot Grid Backtest")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--lower", type=float, default=70000)
    parser.add_argument("--upper", type=float, default=76000)
    parser.add_argument("--grids", type=int, default=10)
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--fee", type=float, default=0.1, help="Fee in percent, e.g. 0.1 = 0.1%%")
    run_cli(parser.parse_args())


if __name__ == "__main__":
    main()
