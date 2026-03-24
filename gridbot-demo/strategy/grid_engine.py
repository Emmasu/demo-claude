"""
Strategy Service: 网格计算引擎
负责根据参数生成网格价格区间和订单配置
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GridLevel:
    grid_no: int
    buy_price: float
    sell_price: float
    profit_pct: float
    capital: Optional[float] = None
    qty: Optional[float] = None
    profit_per_grid: Optional[float] = None


@dataclass
class GridConfig:
    symbol: str
    grid_type: str
    lower_price: float
    upper_price: float
    grid_count: int
    investment: Optional[float]
    price_levels: list[float]
    levels: list[GridLevel]
    avg_profit_pct: float
    total_range_pct: float
    capital_per_grid: Optional[float] = None
    est_profit_per_cycle: Optional[float] = None
    est_return_pct: Optional[float] = None


def calculate_grid(
    symbol: str,
    lower_price: float,
    upper_price: float,
    grid_count: int,
    investment: Optional[float] = None,
    grid_type: str = "geometric",
) -> GridConfig:
    """
    计算网格价格节点和每格订单参数

    Args:
        symbol:       交易对，如 BTCUSDT
        lower_price:  网格下限价格
        upper_price:  网格上限价格
        grid_count:   网格数量
        investment:   投入 USDT（可选，用于计算每格资金和数量）
        grid_type:    geometric(等比) 或 arithmetic(等差)
    """
    if lower_price >= upper_price:
        raise ValueError("upper_price 必须大于 lower_price")
    if grid_count < 2:
        raise ValueError("网格数量至少为 2")

    # 计算价格节点
    if grid_type == "arithmetic":
        interval = (upper_price - lower_price) / grid_count
        price_levels = [lower_price + i * interval for i in range(grid_count + 1)]
    else:  # geometric
        ratio = (upper_price / lower_price) ** (1 / grid_count)
        price_levels = [lower_price * (ratio ** i) for i in range(grid_count + 1)]

    price_levels = [round(p, 6) for p in price_levels]

    # 计算每格参数
    capital_per_grid = investment / grid_count if investment else None
    levels: list[GridLevel] = []

    for i in range(grid_count):
        buy_price = price_levels[i]
        sell_price = price_levels[i + 1]
        profit_pct = round((sell_price - buy_price) / buy_price * 100, 4)

        qty = None
        profit_per_grid = None
        if capital_per_grid:
            qty = round(capital_per_grid / buy_price, 6)
            profit_per_grid = round(qty * (sell_price - buy_price), 4)

        levels.append(GridLevel(
            grid_no=i + 1,
            buy_price=round(buy_price, 4),
            sell_price=round(sell_price, 4),
            profit_pct=profit_pct,
            capital=round(capital_per_grid, 2) if capital_per_grid else None,
            qty=qty,
            profit_per_grid=profit_per_grid,
        ))

    avg_profit_pct = round(sum(lv.profit_pct for lv in levels) / grid_count, 4)
    total_range_pct = round((upper_price - lower_price) / lower_price * 100, 2)

    est_profit_per_cycle = None
    est_return_pct = None
    if investment:
        est_profit_per_cycle = round(sum(lv.profit_per_grid for lv in levels), 4)
        est_return_pct = round(est_profit_per_cycle / investment * 100, 4)

    return GridConfig(
        symbol=symbol.upper(),
        grid_type="等比" if grid_type == "geometric" else "等差",
        lower_price=lower_price,
        upper_price=upper_price,
        grid_count=grid_count,
        investment=investment,
        price_levels=price_levels,
        levels=levels,
        avg_profit_pct=avg_profit_pct,
        total_range_pct=total_range_pct,
        capital_per_grid=round(capital_per_grid, 2) if capital_per_grid else None,
        est_profit_per_cycle=est_profit_per_cycle,
        est_return_pct=est_return_pct,
    )
