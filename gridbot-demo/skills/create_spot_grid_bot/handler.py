"""
GridBot Skill Handler
OpenClaw Skill 入口：解析参数 → 调用 Strategy Service → 调用 Exchange API → 返回结果
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from strategy.grid_engine import calculate_grid
from api.exchange_client import create_grid_bot


def handle(params: dict) -> dict:
    """
    OpenClaw Skill 标准入口函数

    Args:
        params: 从 Claude Agent 解析出的参数，字段见 skill.yaml input_schema

    Returns:
        dict，字段见 skill.yaml output_schema
    """
    # 1. 参数校验
    symbol = params.get("symbol", "").upper()
    lower_price = float(params["lower_price"])
    upper_price = float(params["upper_price"])
    grid_count = int(params["grid_count"])
    investment = float(params["investment"]) if params.get("investment") else None
    grid_type = params.get("grid_type", "geometric")

    if not symbol.endswith("USDT"):
        symbol = symbol.rstrip("USDT") + "USDT"

    # 2. Strategy Service：计算网格参数
    config = calculate_grid(
        symbol=symbol,
        lower_price=lower_price,
        upper_price=upper_price,
        grid_count=grid_count,
        investment=investment,
        grid_type=grid_type,
    )

    # 3. Exchange API：创建机器人
    result = create_grid_bot(config)

    # 4. 生成用户摘要
    summary = _build_summary(config, result)

    return {
        "bot_id": result.bot_id,
        "symbol": result.symbol,
        "grid_count": config.grid_count,
        "grid_type": config.grid_type,
        "lower_price": config.lower_price,
        "upper_price": config.upper_price,
        "price_levels": config.price_levels,
        "investment": config.investment,
        "avg_profit_pct": config.avg_profit_pct,
        "est_profit_per_cycle": config.est_profit_per_cycle,
        "est_return_pct": config.est_return_pct,
        "status": result.status,
        "summary": summary,
    }


def _build_summary(config, result) -> str:
    lines = []

    if result.status == "running":
        lines.append(f"网格机器人创建成功！")
        lines.append(f"机器人 ID：{result.bot_id}")
    else:
        lines.append(f"创建失败：{result.message}")
        return "\n".join(lines)

    lines += [
        f"",
        f"交易对：{config.symbol}",
        f"网格类型：{config.grid_type}",
        f"价格区间：{config.lower_price:,} ~ {config.upper_price:,} USDT",
        f"网格数量：{config.grid_count} 格",
        f"区间涨幅：{config.total_range_pct}%",
        f"每格平均收益：{config.avg_profit_pct}%",
    ]

    if config.investment:
        lines += [
            f"投入金额：{config.investment:,} USDT",
            f"每格资金：{config.capital_per_grid} USDT",
            f"单次循环预估收益：{config.est_profit_per_cycle} USDT（{config.est_return_pct}%）",
        ]

    lines += [
        f"",
        f"网格价格节点（前5格）：",
        f"{'格号':<5} {'买入价':>12} {'卖出价':>12} {'单格收益':>10}",
        "-" * 44,
    ]

    for lv in config.levels[:5]:
        qty_str = f"  数量:{lv.qty}" if lv.qty else ""
        lines.append(f"{lv.grid_no:<5} {lv.buy_price:>12,.2f} {lv.sell_price:>12,.2f} {lv.profit_pct:>9.3f}%{qty_str}")

    if config.grid_count > 5:
        lines.append(f"... 共 {config.grid_count} 格，状态：运行中")

    return "\n".join(lines)
