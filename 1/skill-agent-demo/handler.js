// Core skill matching and execution — shared by agent.js and server.js
const Anthropic = require("@anthropic-ai/sdk");

const client = new Anthropic();

function buildSystemPrompt(skills) {
  const skillDescriptions = skills
    .map((s) => {
      const inputs = Object.entries(s.meta.inputs || {})
        .map(([k, v]) => `  - ${k} (${v.type}, required): ${v.description}`)
        .join("\n");
      return `${s.meta.name}: ${s.meta.description}\nInputs:\n${inputs}`;
    })
    .join("\n\n");

  const skillNames = skills.map((s) => s.meta.name).join(", ");

  return `You are a crypto trading assistant that helps users create and manage bots.

Available skills:
${skillDescriptions}

Rules:
- If the user's intent matches a skill AND all required parameters are present, respond with:
  {"action": "execute", "skill": "<skill_name>", "params": {<all required params>}}
- If the intent matches a skill but parameters are missing, respond with:
  {"action": "ask", "question": "<friendly question asking for the missing info>"}
- If no skill matches, respond with:
  {"action": "unknown"}

Skill names must be exactly one of: ${skillNames}.
Respond with ONLY a raw JSON object — no markdown, no explanation.`;
}

// messages: array of {role, content} — full conversation history
async function handleMessage(skills, messages) {
  const response = await client.messages.create({
    model: process.env.MODEL || "claude-opus-4-6",
    max_tokens: 1024,
    system: buildSystemPrompt(skills),
    messages,
  });

  const raw = response.content[0].text
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();

  const parsed = JSON.parse(raw);

  if (parsed.action === "ask") {
    return { question: parsed.question };
  }

  if (parsed.action === "execute") {
    const skill = skills.find((s) => s.meta.name === parsed.skill);
    if (!skill) return { error: `Unknown skill: ${parsed.skill}` };
    const result = await skill.run(parsed.params);
    return { skill: parsed.skill, params: parsed.params, result };
  }

  return { error: "I'm not sure how to help with that. Try asking to create or cancel a grid bot." };
}

module.exports = { handleMessage };
