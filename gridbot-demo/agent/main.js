/**
 * Claude Agent 主入口
 * 负责：接收用户自然语言 → 调用 Skill Router → GridBot Skill → 返回结果
 *
 * 调用链：
 *   用户 (Lark / Web / Claude)
 *        |
 *        v
 *   Claude Agent  (本文件)
 *        |
 *        v
 *   GridBot Skill  (skills/create_spot_grid_bot/handler.js)
 *        |
 *        v
 *   Strategy Service  (strategy/gridEngine.js)
 *        |
 *        v
 *   Exchange API  (api/exchangeClient.js)
 *        |
 *        v
 *   返回机器人信息
 */

import Anthropic from "@anthropic-ai/sdk";
import { handle as gridbotHandler } from "../skills/create_spot_grid_bot/handler.js";

const client = new Anthropic();

// ── Skill 注册表（Skill Router）──────────────────────────────────────────────
const SKILL_TOOLS = [
  {
    name: "create_spot_grid_bot",
    description:
      "创建现货网格交易机器人。" +
      "当用户想要创建网格机器人、网格交易、现货网格时调用此工具。" +
      "Claude 负责从用户输入中提取参数后调用。",
    input_schema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "交易对，如 BTCUSDT。若用户只说 BTC，自动补全为 BTCUSDT。",
        },
        lower_price: {
          type: "number",
          description: "网格价格下限",
        },
        upper_price: {
          type: "number",
          description: "网格价格上限",
        },
        grid_count: {
          type: "integer",
          description: "网格数量，建议 5-200",
        },
        investment: {
          type: "number",
          description: "投入的 USDT 金额（可选）",
        },
        grid_type: {
          type: "string",
          enum: ["arithmetic", "geometric"],
          description: "网格类型：等差 arithmetic 或 等比 geometric，默认 geometric",
        },
      },
      required: ["symbol", "lower_price", "upper_price", "grid_count"],
    },
  },
];

// Skill 路由表：tool name → handler 函数
const SKILL_REGISTRY = {
  create_spot_grid_bot: gridbotHandler,
};

const SYSTEM_PROMPT = `你是一个专业的量化交易助手，接入了 OpenClaw Skill 平台。

你可以帮助用户创建现货网格交易机器人。

工作方式：
1. 理解用户的自然语言意图
2. 提取关键参数（交易对、价格区间、网格数、投入金额等）
3. 调用对应的 Skill 工具执行
4. 将工具返回的 summary 直接展示给用户，不要改写或省略

参数识别规则：
- "BTC/ETH/SOL" → 自动补全为 BTCUSDT/ETHUSDT/SOLUSDT
- "60000-70000" / "6万到7万" → lower=60000, upper=70000
- "20格" / "网格数20" → grid_count=20
- "投入1000U" / "1000USDT" → investment=1000
- 未指定 grid_type 时默认使用 geometric（等比）

如果缺少必填参数（交易对、价格区间、网格数），直接询问用户补充。`;

/**
 * Agent 主循环：处理用户消息，支持多轮 tool_use
 * @param {string} userMessage
 * @returns {Promise<string>}
 */
async function runAgent(userMessage) {
  console.log(`\n[Agent] 收到消息：${userMessage}`);

  const messages = [{ role: "user", content: userMessage }];

  while (true) {
    const response = await client.messages.create({
      model: "claude-sonnet-4-6",
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      tools: SKILL_TOOLS,
      messages,
    });

    console.log(`[Agent] stop_reason: ${response.stop_reason}`);

    // 没有工具调用，直接返回文本
    if (response.stop_reason === "end_turn") {
      for (const block of response.content) {
        if (block.type === "text") return block.text;
      }
      return "";
    }

    // 处理工具调用（Skill Router 分发）
    if (response.stop_reason === "tool_use") {
      const toolResults = [];

      for (const block of response.content) {
        if (block.type !== "tool_use") continue;

        const skillName = block.name;
        const skillInput = block.input;
        console.log(`[Skill Router] 路由到 Skill: ${skillName}`);
        console.log(`[Skill Router] 参数: ${JSON.stringify(skillInput, null, 2)}`);

        const handler = SKILL_REGISTRY[skillName];
        let skillOutput;
        if (!handler) {
          skillOutput = { error: `未找到 Skill: ${skillName}` };
        } else {
          try {
            skillOutput = handler(skillInput);
            console.log(
              `[Skill] 执行完成，bot_id: ${skillOutput.bot_id}, status: ${skillOutput.status}`
            );
          } catch (e) {
            skillOutput = { error: e.message };
          }
        }

        toolResults.push({
          type: "tool_result",
          tool_use_id: block.id,
          content: JSON.stringify(skillOutput),
        });
      }

      // 将工具结果送回 Claude
      messages.push({ role: "assistant", content: response.content });
      messages.push({ role: "user", content: toolResults });
    } else {
      break;
    }
  }

  return "处理完成";
}

// ── 测试入口 ──────────────────────────────────────────────────────────────────
const testCases = [
  "创建一个btc现货机器人，网格区间为60000-70000，网格数为20",
  "帮我做ETH网格，3000到3500，30格，投入5000USDT",
  "SOL现货网格，100-150，15格，等差",
];

for (const msg of testCases) {
  console.log("\n" + "=".repeat(60));
  console.log(`用户输入：${msg}`);
  console.log("=".repeat(60));
  const result = await runAgent(msg);
  console.log("\n[最终回复]");
  console.log(result);
}
