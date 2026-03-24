/**
 * GridBot Skill Handler
 * OpenClaw Skill 入口：解析参数 → 调用 Strategy Service → 调用 Exchange API → 返回结果
 */

import { calculateGrid } from "../../strategy/gridEngine.js";
import { createGridBot } from "../../api/exchangeClient.js";

/**
 * OpenClaw Skill 标准入口函数
 *
 * @param {Object} params - 从 Claude Agent 解析出的参数，字段见 skill.yaml input_schema
 * @returns {Object} 字段见 skill.yaml output_schema
 */
export function handle(params) {
  let symbol = (params.symbol || "").toUpperCase();
  const lowerPrice = parseFloat(params.lower_price);
  const upperPrice = parseFloat(params.upper_price);
  const gridCount = parseInt(params.grid_count, 10);
  const investment = params.investment ? parseFloat(params.investment) : null;
  const gridType = params.grid_type || "geometric";

  if (!symbol.endsWith("USDT")) {
    symbol = symbol.replace(/USDT$/, "") + "USDT";
  }

  // Strategy Service：计算网格参数
  const config = calculateGrid(symbol, lowerPrice, upperPrice, gridCount, investment, gridType);

  // Exchange API：创建机器人
  const result = createGridBot(config);

  // 生成用户摘要
  const summary = buildSummary(config, result);

  return {
    bot_id: result.botId,
    symbol: result.symbol,
    grid_count: config.gridCount,
    grid_type: config.gridType,
    lower_price: config.lowerPrice,
    upper_price: config.upperPrice,
    price_levels: config.priceLevels,
    investment: config.investment,
    avg_profit_pct: config.avgProfitPct,
    est_profit_per_cycle: config.estProfitPerCycle,
    est_return_pct: config.estReturnPct,
    status: result.status,
    summary,
  };
}

function buildSummary(config, result) {
  const lines = [];

  if (result.status === "running") {
    lines.push("网格机器人创建成功！");
    lines.push(`机器人 ID：${result.botId}`);
  } else {
    lines.push(`创建失败：${result.message}`);
    return lines.join("\n");
  }

  lines.push(
    "",
    `交易对：${config.symbol}`,
    `网格类型：${config.gridType}`,
    `价格区间：${config.lowerPrice.toLocaleString()} ~ ${config.upperPrice.toLocaleString()} USDT`,
    `网格数量：${config.gridCount} 格`,
    `区间涨幅：${config.totalRangePct}%`,
    `每格平均收益：${config.avgProfitPct}%`
  );

  if (config.investment) {
    lines.push(
      `投入金额：${config.investment.toLocaleString()} USDT`,
      `每格资金：${config.capitalPerGrid} USDT`,
      `单次循环预估收益：${config.estProfitPerCycle} USDT（${config.estReturnPct}%）`
    );
  }

  lines.push(
    "",
    "网格价格节点（前5格）：",
    `${"格号".padEnd(5)} ${"买入价".padStart(12)} ${"卖出价".padStart(12)} ${"单格收益".padStart(10)}`,
    "-".repeat(44)
  );

  for (const lv of config.levels.slice(0, 5)) {
    const qtyStr = lv.qty ? `  数量:${lv.qty}` : "";
    lines.push(
      `${String(lv.gridNo).padEnd(5)} ${lv.buyPrice.toLocaleString("en-US", { minimumFractionDigits: 2 }).padStart(12)} ${lv.sellPrice.toLocaleString("en-US", { minimumFractionDigits: 2 }).padStart(12)} ${(lv.profitPct.toFixed(3) + "%").padStart(9)}${qtyStr}`
    );
  }

  if (config.gridCount > 5) {
    lines.push(`... 共 ${config.gridCount} 格，状态：运行中`);
  }

  return lines.join("\n");
}
