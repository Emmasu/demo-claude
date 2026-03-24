async function run(input) {
  const { symbol, lower_price, upper_price, grid_number, capital } = input;

  return {
    status: "success",
    bot_id: "grid_123456",
    config: {
      symbol,
      lower_price,
      upper_price,
      grid_number,
      capital,
    },
  };
}

module.exports = { run };
