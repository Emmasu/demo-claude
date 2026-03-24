require("dotenv").config();
const readline = require("readline");
const { loadSkills } = require("./skillLoader");
const { handleMessage } = require("./handler");

// --- Main ---

async function main() {
  const skills = await loadSkills();

  console.log("Available skills:\n");
  for (const skill of skills) {
    console.log(`  * ${skill.meta.name}`);
  }
  console.log();

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  // Collect multi-line input until empty line
  console.log("Enter message (press Enter twice to submit):\n");

  const lines = [];

  rl.on("line", async (line) => {
    if (line.trim() === "" && lines.length > 0) {
      rl.close();
      const message = lines.join("\n");
      await printResult(skills, message);
    } else if (line.trim() !== "" || lines.length > 0) {
      lines.push(line);
    }
  });

  rl.on("close", () => {});
}

async function printResult(skills, message) {
  const data = await handleMessage(skills, message);

  if (data.error) {
    console.log("\n" + data.error);
    return;
  }

  const { skill, params, result } = data;

  console.log(`\nDetected skill: ${skill}\n`);
  console.log("Parameters:\n");
  for (const [key, value] of Object.entries(params)) {
    console.log(`  ${key}: ${value}`);
  }

  console.log("\nExecuting skill...\n");
  console.log("Skill result:\n");
  if (result.status === "success") {
    if (skill === "cancel_grid_bot") {
      console.log(`  ${result.message}`);
    } else {
      console.log("  Grid bot created");
      console.log(`  bot_id: ${result.bot_id}`);
    }
  } else {
    console.log(JSON.stringify(result, null, 2));
  }
}

main().catch(console.error);
