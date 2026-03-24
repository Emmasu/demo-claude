/**
 * Exchange API Client（Mock）
 * 模拟向交易所提交网格机器人的 API 调用
 * 实际部署时替换为真实交易所 SDK（如 Binance、OKX）
 */

import { randomUUID } from "crypto";

/**
 * @typedef {Object} BotResult
 * @property {string} botId
 * @property {string} symbol
 * @property {string} status  - "running" | "failed"
 * @property {string} message
 * @property {number} gridCount
 * @property {number} lowerPrice
 * @property {number} upperPrice
 * @property {number|null} investment
 */

/**
 * 提交网格机器人到交易所
 *
 * Mock 实现：随机生成 botId，模拟 95% 成功率
 * 真实实现示例（Binance）：
 *   client.createGridAlgoOrder({ symbol, gridType, upperPrice, lowerPrice, gridNum, totalInvestment })
 *
 * @param {import('../strategy/gridEngine.js').GridConfig} config
 * @returns {BotResult}
 */
export function createGridBot(config) {
  if (Math.random() < 0.05) {
    return {
      botId: "",
      symbol: config.symbol,
      status: "failed",
      message: "交易所连接超时，请稍后重试",
      gridCount: config.gridCount,
      lowerPrice: config.lowerPrice,
      upperPrice: config.upperPrice,
      investment: config.investment,
    };
  }

  const botId = `GRID-${config.symbol}-${randomUUID().replace(/-/g, "").slice(0, 8).toUpperCase()}`;

  return {
    botId,
    symbol: config.symbol,
    status: "running",
    message: "网格机器人创建成功，已开始运行",
    gridCount: config.gridCount,
    lowerPrice: config.lowerPrice,
    upperPrice: config.upperPrice,
    investment: config.investment,
  };
}
