# Agent Skills with Anthropic (Claude) — Course Summary

**Platform:** deeplearning.ai
**Instructor:** Elie Schoppik (Head of Technical Education, Anthropic)
**Duration:** ~2h 19min | 10 video lessons + 1 quiz | Beginner

---

## Lesson 1: Introduction (2 min)

A quick overview: **Skills are folders of instructions** that extend an agent's capabilities with specialized knowledge. They follow an **open standard format** — build once, deploy across Claude AI, Claude Code, Gemini CLI, Codex, and more.

---

## Lesson 2: Course Materials (1 min — Reading)

Platform guide: how to use the deeplearning.ai environment — resetting workspace, downloading notebooks, video features, etc. No technical content.

---

## Lesson 3: Why Use Skills — Part I (11 min)

- Skills package repeated workflows and specialized knowledge into reusable assets
- **SKILL.md file structure:** YAML metadata (name + description) + Markdown instructions + optional References folder
- Without skills, you'd have to paste long prompts/docs into every conversation, wasting the context window
- Demo: marketing campaign analysis (funnel analysis, ROI, budget reallocation)
- Naming convention: lowercase, dash-separated, verb+ing format (e.g., `analyzing-campaigns`)

---

## Lesson 4: Why Use Skills — Part II (8 min)

- Skills are an **open standard** — not Anthropic-specific
- Skills include executable scripts + referenced resources, not just text
- **Progressive disclosure:** only skill name/description loads at first; full SKILL.md loads on activation; additional files load as needed — protects context window
- Best for company-specific/domain-specific knowledge Claude doesn't inherently have (brand guidelines, financial workflows, legal processes)
- Philosophy: simpler agents + composable skills > separate domain-specific agents

---

## Lesson 5: Skills vs Tools, MCP, and Subagents (7 min)

- **Tools** = low-level capabilities (hammer, saw) — bash, filesystem, APIs
- **Skills** = higher-level knowledge (how to build a bookshelf) — instructions + workflows
- **MCP (Model Context Protocol)** = connects agents to external systems (databases, Google Drive)
- **Subagents** = spawned by a main agent for specialized tasks; each has its own context window and permissions
- Demo: "Customer Insight Analyzer" — main agent orchestrates, subagents parallelize analysis, skills handle predictable workflows

---

## Lesson 6: Exploring Pre-Built Skills (18 min)

- Claude AI/Desktop has **always-on built-in skills**: Excel, PowerPoint, Word, PDF
- Additional example skills live on GitHub (`github.com/anthropic/skills`), toggleable
- **Skill-Creator** skill: automates the file/folder structure creation for new skills
- Demo: combined marketing analysis (BigQuery) + brand guidelines skill + PowerPoint skill → generates a branded presentation automatically
- Key insight: skill-creator handles structure, but **you still need a good prompt and good data**

---

## Lesson 7: Creating Custom Skills (16 min)

- Every skill needs SKILL.md with YAML frontmatter (`name`, `description`)
- Keep skill content **under 500 lines**; reference external files beyond that
- Use forward slashes for cross-platform path compatibility
- Optional directories:
  - `scripts/` — executable code with error handling
  - `references/` — additional documentation
  - `assets/` — templates, images, schemas, data files
- **Two example skills:** "Generating Practice Questions" (Markdown/LaTeX/PDF output) and "Analyzing Time Series Data" (deterministic Python script pipeline)
- Both scored 9–10/10 when evaluated by the skill-creator tool
- **Test skills like software:** unit test correct input handling, workflow execution, and output format

---

## Lesson 8: Skills with the Claude API (17 min)

- Skills in Claude AI/Desktop are **NOT automatically available** in the Messages API — you must set them up manually
- Two required components:
  - **Code Execution Tool** — sandboxed container for running bash/managing files
  - **Files API** — upload/download files to/from the execution environment
- Workflow: upload skills via Files API → reference in API call via `container` parameter → process → download results via file ID
- **Key limitation:** API sandbox has no internet connection (can't `pip install` freely)
- Skill format is identical across environments; only the plumbing differs

---

## Lesson 9: Skills with Claude Code (24 min)

- Skills stored in `.claude/skills/` — can be project-level or user-level
- Demo: building a CLI task manager app with 3 custom skills:
  1. **adding-cli-commands** — enforces consistent command patterns
  2. **generating-cli-tests** — creates pytest tests with fixtures and edge cases
  3. **reviewing-cli-commands** — validates quality, security, best practices
- **Subagents in Claude Code:** each runs in its own context window for efficiency
  - `code-reviewer` subagent + `test-generator-runner` subagent
- **Important:** subagents do NOT inherit skills from the parent — you must explicitly pass skills to each subagent

---

## Lesson 10: Skills with the Claude Agent SDK (20 min)

- Demo: building a general-purpose **research agent** with 3 specialized subagents:
  - Documentation researcher (WebSearch + WebFetch)
  - Repository analyzer (Bash + file ops)
  - Web researcher (community content)
- Uses a `learning-a-tool` skill to guide the main agent with structured, predictable research workflows
- **MCP integration:** Notion MCP server writes research outputs for team sharing
- Tools must be **explicitly enabled** per subagent (Write, Bash, WebSearch, WebFetch, Skill tool)
- Demo output: comprehensive learning guide for a PDF library (MinerU), with progressive difficulty levels, written to Notion
- **Security note:** current implementations lack user confirmation before destructive actions (file writes, bash) — important for production

---

## Lesson 11: Conclusion (1 min)

Recap: Skills are reusable, portable, and composable. Combine them with MCP and subagents to build powerful, reliable agentic systems across any platform.

---

## Key Takeaway

The course teaches a layered agentic architecture:

| Component | Purpose |
|-----------|---------|
| **Skills** | Reusable, portable knowledge and workflows (SKILL.md) |
| **Tools / MCP** | Low-level capabilities and external system access |
| **Subagents** | Parallelism, specialization, isolated context windows |

All centered around a portable open standard (SKILL.md) that works across Claude AI, Claude Code, Claude API, Claude Agent SDK, and third-party platforms.
