const fs = require("fs");
const path = require("path");
const YAML = require("yaml");

async function loadSkills() {
  const skillsDir = path.join(__dirname, "skills");
  const entries = fs.readdirSync(skillsDir, { withFileTypes: true });
  const skills = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const skillDir = path.join(skillsDir, entry.name);
    const yamlPath = path.join(skillDir, "skill.yaml");
    const implPath = path.join(skillDir, "index.js");

    if (!fs.existsSync(yamlPath) || !fs.existsSync(implPath)) continue;

    const yamlText = fs.readFileSync(yamlPath, "utf8");
    const meta = YAML.parse(yamlText);
    const impl = require(implPath);

    skills.push({ meta, run: impl.run });
  }

  return skills;
}

module.exports = { loadSkills };
