/**
 * Strategy Service: 网格计算引擎
 * 负责根据参数生成网格价格区间和订单配置
 */

/**
 * @typedef {Object} GridLevel
 * @property {number} gridNo
 * @property {number} buyPrice
 * @property {number} sellPrice
 * @property {number} profitPct
 * @property {number|null} capital
 * @property {number|null} qty
 * @property {number|null} profitPerGrid
 */

/**
 * @typedef {Object} GridConfig
 * @property {string} symbol
 * @property {string} gridType
 * @property {number} lowerPrice
 * @property {number} upperPrice
 * @property {number} gridCount
 * @property {number|null} investment
 * @property {number[]} priceLevels
 * @property {GridLevel[]} levels
 * @property {number} avgProfitPct
 * @property {number} totalRangePct
 * @property {number|null} capitalPerGrid
 * @property {number|null} estProfitPerCycle
 * @property {number|null} estReturnPct
 */

/**
 * 计算网格价格节点和每格订单参数
 *
 * @param {string} symbol       交易对，如 BTCUSDT
 * @param {number} lowerPrice   网格下限价格
 * @param {number} upperPrice   网格上限价格
 * @param {number} gridCount    网格数量
 * @param {number|null} investment  投入 USDT（可选）
 * @param {string} gridType     geometric(等比) 或 arithmetic(等差)
 * @returns {GridConfig}
 */
export function calculateGrid(
  symbol,
  lowerPrice,
  upperPrice,
  gridCount,
  investment = null,
  gridType = "geometric"
) {
  if (lowerPrice >= upperPrice) throw new Error("upperPrice 必须大于 lowerPrice");
  if (gridCount < 2) throw new Error("网格数量至少为 2");

  // 计算价格节点
  let priceLevels = [];
  if (gridType === "arithmetic") {
    const interval = (upperPrice - lowerPrice) / gridCount;
    for (let i = 0; i <= gridCount; i++) {
      priceLevels.push(lowerPrice + i * interval);
    }
  } else {
    const ratio = Math.pow(upperPrice / lowerPrice, 1 / gridCount);
    for (let i = 0; i <= gridCount; i++) {
      priceLevels.push(lowerPrice * Math.pow(ratio, i));
    }
  }
  priceLevels = priceLevels.map((p) => parseFloat(p.toFixed(6)));

  const capitalPerGrid = investment ? investment / gridCount : null;
  const levels = [];

  for (let i = 0; i < gridCount; i++) {
    const buyPrice = priceLevels[i];
    const sellPrice = priceLevels[i + 1];
    const profitPct = parseFloat(((( sellPrice - buyPrice) / buyPrice) * 100).toFixed(4));

    let qty = null;
    let profitPerGrid = null;
    if (capitalPerGrid) {
      qty = parseFloat((capitalPerGrid / buyPrice).toFixed(6));
      profitPerGrid = parseFloat((qty * (sellPrice - buyPrice)).toFixed(4));
    }

    levels.push({
      gridNo: i + 1,
      buyPrice: parseFloat(buyPrice.toFixed(4)),
      sellPrice: parseFloat(sellPrice.toFixed(4)),
      profitPct,
      capital: capitalPerGrid ? parseFloat(capitalPerGrid.toFixed(2)) : null,
      qty,
      profitPerGrid,
    });
  }

  const avgProfitPct = parseFloat(
    (levels.reduce((s, lv) => s + lv.profitPct, 0) / gridCount).toFixed(4)
  );
  const totalRangePct = parseFloat(
    (((upperPrice - lowerPrice) / lowerPrice) * 100).toFixed(2)
  );

  let estProfitPerCycle = null;
  let estReturnPct = null;
  if (investment) {
    estProfitPerCycle = parseFloat(
      levels.reduce((s, lv) => s + lv.profitPerGrid, 0).toFixed(4)
    );
    estReturnPct = parseFloat(((estProfitPerCycle / investment) * 100).toFixed(4));
  }

  return {
    symbol: symbol.toUpperCase(),
    gridType: gridType === "geometric" ? "等比" : "等差",
    lowerPrice,
    upperPrice,
    gridCount,
    investment,
    priceLevels,
    levels,
    avgProfitPct,
    totalRangePct,
    capitalPerGrid: capitalPerGrid ? parseFloat(capitalPerGrid.toFixed(2)) : null,
    estProfitPerCycle,
    estReturnPct,
  };
}
