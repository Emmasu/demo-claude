import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from grid_backtest import backtest_engine, get_ohlcv

st.set_page_config(page_title="Spot Grid Backtest", layout="wide")
st.title("Spot Grid Backtest")

# ---------------------------------------------------------------------------
# Sidebar — parameters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Parameters")

    symbol = st.selectbox("Symbol", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
    timeframe = st.selectbox("Timeframe", ["1h", "15m"])

    st.divider()

    # Derive price range hint from stored data
    ohlcv = get_ohlcv(symbol, timeframe)
    if ohlcv:
        prices = [row[3] for row in ohlcv] + [row[2] for row in ohlcv]  # lows + highs
        data_low = min(prices)
        data_high = max(prices)
        hint = f"Data range: ${data_low:,.0f} – ${data_high:,.0f}"
    else:
        data_low, data_high = 0.0, 100000.0
        hint = "No data loaded yet"

    st.caption(hint)

    lower = st.number_input("Lower Price ($)", value=60000.0, step=100.0, format="%.2f")
    upper = st.number_input("Upper Price ($)", value=70000.0, step=100.0, format="%.2f")
    n_grids = st.slider("Number of Grids", min_value=2, max_value=30, value=5)
    capital = st.number_input("Capital (USDT)", value=10000.0, step=100.0, format="%.2f")
    fee_pct = st.number_input("Trading Fee (%)", value=0.1, min_value=0.0, max_value=1.0, step=0.01, format="%.3f")

    st.divider()
    run = st.button("Run Backtest", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Run & display
# ---------------------------------------------------------------------------
if not ohlcv:
    st.warning("No OHLCV data found. Run the collector first: `python main.py ohlcv`")
    st.stop()

if lower >= upper:
    st.error("Lower price must be less than upper price.")
    st.stop()

r = backtest_engine(
    symbol=symbol,
    lower=lower,
    upper=upper,
    n_grids=n_grids,
    capital=capital,
    fee_rate=fee_pct / 100,
    timeframe=timeframe,
)

if r is None:
    st.error(f"No data found for {symbol} {timeframe}.")
    st.stop()

# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------
st.subheader("Summary")
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Final Portfolio", f"${r['final_total']:,.2f}",
          delta=f"{r['pnl_pct']:+.2f}%")
c2.metric("PnL", f"${r['pnl']:+,.2f}")
c3.metric("Grid Profit", f"${r['total_grid_profit']:,.2f}")
c4.metric("Fees Paid", f"${r['total_fee']:,.2f}")
c5.metric("Max Drawdown", f"{r['max_drawdown_pct']:.2f}%",
          delta=f"-${r['max_drawdown']:,.2f}", delta_color="inverse")
c6.metric("Total Trades", f"{len(r['trades'])}",
          delta=f"{r['n_buys']}B / {r['n_sells']}S")

st.caption(
    f"HODL return: **{r['hodl_pnl_pct']:+.2f}%**  |  "
    f"Entry: **${r['entry_price']:,.2f}**  →  Exit: **${r['final_price']:,.2f}**  |  "
    f"{r['n_candles']} candles  ({r['date_start']} – {r['date_end']})"
)

# ---------------------------------------------------------------------------
# Init Position module
# ---------------------------------------------------------------------------
st.subheader("Initial Position")

init_rows = []
init_total_btc  = 0.0
init_total_usdt = 0.0

for i in range(r["n_grids"]):
    buy_p  = r["grid_lines"][i]
    sell_p = r["grid_lines"][i + 1]
    holding = r["init_slot_state"][i]

    if holding:
        btc_qty  = r["btc_per_grid"]
        cost     = btc_qty * r["entry_price"] * (1 + r["fee_rate"])
        init_total_btc += btc_qty
        init_rows.append({
            "Grid":          i,
            "Buy price":     f"${buy_p:,.2f}",
            "Sell price":    f"${sell_p:,.2f}",
            "Status":        "🟢 Holding BTC",
            "Asset":         "BTC",
            "Qty":           f"{btc_qty:.6f}",
            "Cost basis":    f"${cost:,.4f}",
            "Value @ entry": f"${btc_qty * r['entry_price']:,.4f}",
        })
    else:
        usdt_reserved = r["btc_per_grid"] * buy_p * (1 + r["fee_rate"])
        init_total_usdt += usdt_reserved
        init_rows.append({
            "Grid":          i,
            "Buy price":     f"${buy_p:,.2f}",
            "Sell price":    f"${sell_p:,.2f}",
            "Status":        "🔵 Waiting (USDT)",
            "Asset":         "USDT",
            "Qty":           f"{usdt_reserved:,.4f}",
            "Cost basis":    f"${usdt_reserved:,.4f}",
            "Value @ entry": f"${usdt_reserved:,.4f}",
        })

# summary row
init_rows.append({
    "Grid":          "TOTAL",
    "Buy price":     "—",
    "Sell price":    "—",
    "Status":        f"{sum(1 for v in r['init_slot_state'].values() if v)} BTC slots  +  {sum(1 for v in r['init_slot_state'].values() if not v)} USDT slots",
    "Asset":         "BTC + USDT",
    "Qty":           f"{init_total_btc:.6f} BTC  +  ${init_total_usdt:,.4f} USDT",
    "Cost basis":    f"${r['capital']:,.2f}",
    "Value @ entry": f"${init_total_btc * r['entry_price'] + init_total_usdt:,.4f}",
})

col_left, col_right = st.columns([2, 1])

with col_left:
    st.dataframe(pd.DataFrame(init_rows), use_container_width=True, hide_index=True)

with col_right:
    # Visual grid bar
    n = r["n_grids"]
    entry = r["entry_price"]
    fig_init = go.Figure()

    for i in range(n):
        buy_p  = r["grid_lines"][i]
        sell_p = r["grid_lines"][i + 1]
        holding = r["init_slot_state"][i]
        color = "rgba(38,166,154,0.6)" if holding else "rgba(92,155,214,0.45)"
        label = f"BTC @ ${buy_p:,.0f}" if holding else f"USDT → buy @ ${buy_p:,.0f}"
        fig_init.add_trace(go.Bar(
            x=[label],
            y=[sell_p - buy_p],
            base=[buy_p],
            marker_color=color,
            marker_line_color="rgba(255,255,255,0.2)",
            marker_line_width=1,
            name=label,
            showlegend=False,
            hovertemplate=f"{'BTC' if holding else 'USDT'} slot {i}<br>${buy_p:,.0f} – ${sell_p:,.0f}<extra></extra>",
        ))

    # entry price line
    fig_init.add_hline(
        y=entry, line_color="#f7c948", line_dash="dash", line_width=2,
        annotation_text=f"Entry ${entry:,.0f}",
        annotation_font_color="#f7c948",
        annotation_position="top right",
    )

    fig_init.update_layout(
        template="plotly_dark",
        height=340,
        barmode="overlay",
        title="Grid slots at init  (🟢 BTC held  🔵 USDT waiting)",
        xaxis_visible=False,
        yaxis_title="Price (USDT)",
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig_init, use_container_width=True)

# ---------------------------------------------------------------------------
# Trade log
# ---------------------------------------------------------------------------
with st.expander("Trade Log"):
    if r["trades"]:
        df_log = pd.DataFrame(r["trades"])
        df_log["action"] = df_log["action"].apply(
            lambda x: "🟢 BUY" if x == "BUY" else "🔴 SELL"
        )
        cols = ["#"] + [c for c in df_log.columns if c != "#"]
        st.dataframe(df_log[cols], use_container_width=True, hide_index=True)
    else:
        st.info("No trades executed.")

# ---------------------------------------------------------------------------
# Chart 1 — Price + grid lines + trades
# ---------------------------------------------------------------------------
ph = r["portfolio_history"]
trades = r["trades"]
df = pd.DataFrame(ph)
df_trades = pd.DataFrame(trades) if trades else pd.DataFrame()

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.65, 0.35],
    vertical_spacing=0.04,
    subplot_titles=("Price Chart  (grid lines · buy/sell signals)", "Portfolio Value & Drawdown"),
)

# Candlestick
ohlcv_df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close"])
ohlcv_df["time"] = pd.to_datetime(ohlcv_df["ts"], unit="ms")

fig.add_trace(go.Candlestick(
    x=ohlcv_df["time"],
    open=ohlcv_df["open"], high=ohlcv_df["high"],
    low=ohlcv_df["low"],  close=ohlcv_df["close"],
    name="Price", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    showlegend=False,
), row=1, col=1)

# Grid lines
for i, price in enumerate(r["grid_lines"]):
    fig.add_hline(
        y=price, line_dash="dot", line_color="rgba(180,180,180,0.5)", line_width=1,
        annotation_text=f"${price:,.0f}", annotation_position="left",
        annotation_font_size=9, row=1, col=1,
    )

# Buy / Sell markers
if not df_trades.empty:
    df_trades["time_dt"] = pd.to_datetime(
        df_trades["time"], format="%Y-%m-%d %H:%M:%S"
    )
    buys  = df_trades[df_trades["action"] == "BUY"]
    sells = df_trades[df_trades["action"] == "SELL"]

    if not buys.empty:
        fig.add_trace(go.Scatter(
            x=buys["time_dt"], y=buys["price"],
            mode="markers",
            marker=dict(symbol="triangle-up", size=10, color="#26a69a"),
            name="Buy", hovertemplate="BUY @ $%{y:,.2f}<br>%{x}<extra></extra>",
        ), row=1, col=1)

    if not sells.empty:
        fig.add_trace(go.Scatter(
            x=sells["time_dt"], y=sells["price"],
            mode="markers",
            marker=dict(symbol="triangle-down", size=10, color="#ef5350"),
            name="Sell", hovertemplate="SELL @ $%{y:,.2f}<br>%{x}<extra></extra>",
        ), row=1, col=1)

# Portfolio value line
df["time_dt"] = pd.to_datetime(df["time"], format="%Y-%m-%d %H:%M:%S")
fig.add_trace(go.Scatter(
    x=df["time_dt"], y=df["portfolio_value"],
    mode="lines", line=dict(color="#5c9bd6", width=2),
    name="Portfolio", fill="tozeroy", fillcolor="rgba(92,155,214,0.08)",
    hovertemplate="Portfolio: $%{y:,.2f}<br>%{x}<extra></extra>",
), row=2, col=1)

# Capital baseline
fig.add_hline(y=capital, line_dash="dash", line_color="rgba(255,255,255,0.3)",
              line_width=1, row=2, col=1)

# Drawdown shading
fig.add_trace(go.Scatter(
    x=df["time_dt"], y=df["drawdown_pct"],
    mode="lines", line=dict(color="rgba(239,83,80,0.7)", width=1),
    fill="tozeroy", fillcolor="rgba(239,83,80,0.15)",
    name="Drawdown %", yaxis="y3",
    hovertemplate="Drawdown: -%{y:.2f}%<br>%{x}<extra></extra>",
), row=2, col=1)

fig.update_layout(
    height=700,
    template="plotly_dark",
    xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=60, r=60, t=60, b=40),
)
fig.update_yaxes(title_text="Price (USDT)", row=1, col=1)
fig.update_yaxes(title_text="Portfolio (USDT)", row=2, col=1)

st.plotly_chart(fig, use_container_width=True)
