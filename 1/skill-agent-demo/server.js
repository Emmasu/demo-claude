require("dotenv").config();
const http = require("http");
const { loadSkills } = require("./skillLoader");
const { handleMessage } = require("./handler");

const PORT = 3000;

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Skill Agent Chat</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
    #app { width: 480px; background: #fff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); display: flex; flex-direction: column; height: 600px; }
    h2 { padding: 16px 20px; border-bottom: 1px solid #eee; font-size: 16px; color: #333; }
    #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
    .msg { max-width: 85%; padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    .msg.user { align-self: flex-end; background: #0084ff; color: #fff; border-bottom-right-radius: 2px; }
    .msg.agent { align-self: flex-start; background: #f1f0f0; color: #333; border-bottom-left-radius: 2px; }
    .msg.error { align-self: flex-start; background: #fdecea; color: #c62828; border-bottom-left-radius: 2px; }
    #input-row { display: flex; padding: 12px; border-top: 1px solid #eee; gap: 8px; }
    textarea { flex: 1; resize: none; border: 1px solid #ddd; border-radius: 8px; padding: 8px 12px; font-size: 14px; font-family: sans-serif; outline: none; }
    textarea:focus { border-color: #0084ff; }
    button { background: #0084ff; color: #fff; border: none; border-radius: 8px; padding: 0 18px; cursor: pointer; font-size: 14px; }
    button:hover { background: #006edc; }
  </style>
</head>
<body>
<div id="app">
  <h2>Skill Agent</h2>
  <div id="messages"></div>
  <div id="input-row">
    <textarea id="input" rows="3" placeholder="Type your message... (Shift+Enter for new line, Enter to send)"></textarea>
    <button id="send">Send</button>
  </div>
</div>
<script>
  const messagesEl = document.getElementById("messages");
  const inputEl = document.getElementById("input");
  const sendBtn = document.getElementById("send");

  // Full conversation history sent to the server each turn
  const history = [];

  function addMessage(text, type) {
    const el = document.createElement("div");
    el.className = "msg " + type;
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function formatResult(data) {
    if (data.error) return data.error;
    if (data.question) return data.question;
    const { skill, params, result } = data;
    let out = "Detected skill: " + skill + "\\n\\nParameters:\\n";
    for (const [k, v] of Object.entries(params)) out += "  " + k + ": " + v + "\\n";
    out += "\\nResult:\\n";
    if (result.status === "success") {
      if (skill === "cancel_grid_bot") {
        out += "  " + result.message;
      } else {
        out += "  Grid bot created\\n  bot_id: " + result.bot_id;
      }
    } else {
      out += JSON.stringify(result, null, 2);
    }
    return out;
  }

  async function send() {
    const message = inputEl.value.trim();
    if (!message) return;
    inputEl.value = "";
    addMessage(message, "user");

    // Append user turn to history
    history.push({ role: "user", content: message });

    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });
      const data = await res.json();
      const text = formatResult(data);
      const type = data.error ? "error" : "agent";
      addMessage(text, type);

      // Append assistant reply to history so next turn has full context
      if (!data.error) {
        history.push({ role: "assistant", content: text });
      }

      // Clear history after a successful execution so next task starts fresh
      if (data.result) {
        history.length = 0;
      }
    } catch (e) {
      addMessage("Request failed: " + e.message, "error");
    }
  }

  sendBtn.addEventListener("click", send);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
</script>
</body>
</html>`;

async function main() {
  const skills = await loadSkills();
  console.log("Loaded skills:", skills.map((s) => s.meta.name).join(", "));

  const server = http.createServer(async (req, res) => {
    if (req.method === "GET" && req.url === "/") {
      res.writeHead(200, { "Content-Type": "text/html" });
      return res.end(HTML);
    }

    if (req.method === "POST" && req.url === "/chat") {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", async () => {
        try {
          const { messages } = JSON.parse(body);
          const result = await handleMessage(skills, messages);
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(result));
        } catch (e) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }

    res.writeHead(404);
    res.end("Not found");
  });

  server.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
  });
}

main().catch(console.error);
