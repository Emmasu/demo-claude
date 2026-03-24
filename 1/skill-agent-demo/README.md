# skill-agent-demo

A minimal Node.js demo showing how an LLM-based agent discovers and executes Skills using a standard Skill format.

## Setup

```bash
npm install
```

## Run

```bash
npm start
```

## Example interaction

When prompted, type a multi-line message and press **Enter twice** to submit:

```
创建BTC网格
区间60000-70000
网格20
资金10000
```

Expected output:

```
Detected skill: create_grid_bot

Parameters:

  symbol: BTC
  lower_price: 60000
  upper_price: 70000
  grid_number: 20
  capital: 10000

Executing skill...

Skill result:

  Grid bot created
  bot_id: grid_123456
```

## Skill format

Each skill lives in `skills/<skill_name>/` and contains:

- `skill.yaml` — metadata (name, description, inputs)
- `index.js` — implementation exporting `run(input)`

Add new skills by creating a new folder following the same structure. The agent will discover them automatically on startup.
