async function run(input) {
  const { bot_id } = input;

  return {
    status: "success",
    bot_id,
    message: `Grid bot ${bot_id} has been cancelled`,
  };
}

module.exports = { run };
