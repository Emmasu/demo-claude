"""
Exchange API Client（Mock）
模拟向交易所提交网格机器人的 API 调用
实际部署时替换为真实交易所 SDK（如 Binance、OKX）
"""

import uuid
import random
from dataclasses import dataclass
from typing import Optional

from strategy.grid_engine import GridConfig


@dataclass
class BotResult:
    bot_id: str
    symbol: str
    status: str          # running / failed
    message: str
    grid_count: int
    lower_price: float
    upper_price: float
    investment: Optional[float]


def create_grid_bot(config: GridConfig) -> BotResult:
    """
    提交网格机器人到交易所

    Mock 实现：随机生成 bot_id，模拟 95% 成功率
    真实实现示例（Binance）：
        client.create_grid_algo_order(
            symbol=config.symbol,
            side="BOTH",
            gridType="GEOMETRIC",
            upperPrice=config.upper_price,
            lowerPrice=config.lower_price,
            gridNum=config.grid_count,
            totalInvestment=config.investment,
        )
    """
    if random.random() < 0.05:  # 模拟 5% 失败
        return BotResult(
            bot_id="",
            symbol=config.symbol,
            status="failed",
            message="交易所连接超时，请稍后重试",
            grid_count=config.grid_count,
            lower_price=config.lower_price,
            upper_price=config.upper_price,
            investment=config.investment,
        )

    bot_id = f"GRID-{config.symbol}-{uuid.uuid4().hex[:8].upper()}"

    return BotResult(
        bot_id=bot_id,
        symbol=config.symbol,
        status="running",
        message="网格机器人创建成功，已开始运行",
        grid_count=config.grid_count,
        lower_price=config.lower_price,
        upper_price=config.upper_price,
        investment=config.investment,
    )
