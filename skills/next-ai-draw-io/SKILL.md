---
name: ai-drawio
description: >
  Generate, modify, and export draw.io architecture diagrams from natural language
  using next-ai-draw-io — a Next.js app backed by any LLM provider (Claude, OpenAI,
  Gemini, Ollama, etc.). Use when the user wants to create a diagram, architecture
  chart, flowchart, sequence diagram, cloud infra map (AWS/GCP/Azure), or ER diagram
  from a text description. Also trigger when the user says "draw this", "diagram this",
  "make a flowchart", "architecture diagram", "visualize this flow", "draw.io",
  or wants to convert a written spec into a visual diagram.
argument-hint: "<description of diagram to generate>"
allowed-tools:
  - Bash
  - WebFetch
  - mcp__browser__browser_navigate
  - mcp__browser__browser_screenshot
  - mcp__browser__browser_action
---

# AI Draw.io — Diagram from Natural Language

Generate draw.io diagrams from text descriptions using an LLM-backed web app.

## Online Demo (no setup)

Navigate to: https://next-ai-drawio.jiang.jp/

Use the browser tool to open it, type the prompt, and screenshot the result.

## Local Setup

```bash
git clone https://github.com/DayuanJiang/next-ai-draw-io
cd next-ai-draw-io
npm install
cp env.example .env.local
# Edit .env.local — add your API key for the desired provider
npm run dev   # runs on http://localhost:6002
```

## Configuration (`.env.local`)

Set one of:
```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_AI_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434   # for local models
```

The UI lets you switch providers at runtime — set keys for any providers you want available.

## Usage Patterns

**Generate from prompt:**
> "Generate a GCP architecture: users → Cloud Load Balancer → 3 GKE pods → Cloud SQL"

**Replicate from image:**
> Upload a screenshot of an existing diagram, ask it to replicate or extend it.

**From document:**
> Upload a PDF/text spec, ask it to extract and diagram the architecture.

## Prompt Tips

- Name the diagram type explicitly: "sequence diagram", "ER diagram", "cloud arch"
- Specify icon sets when needed: "use AWS icons", "use GCP icons"
- For complex diagrams, describe layers top-down: "users → API → services → DB"
- Request animated connectors for flow diagrams: "add animated arrows"

## Desktop App

Download prebuilt binaries from GitHub Releases (macOS, Windows, Linux) — no Node.js needed.

## Export

Diagrams export as `.drawio` XML — open in draw.io desktop or diagrams.net.

Source: https://github.com/DayuanJiang/next-ai-draw-io
