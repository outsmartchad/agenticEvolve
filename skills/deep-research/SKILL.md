---
name: deep-research
description: Multi-source deep research using web search, crawling, and synthesis. Searches the web, reads full sources, cross-references findings, and delivers cited reports with source attribution. ALWAYS use this skill when the user wants thorough research on any topic — "research this", "deep dive into", "investigate", "what's the current state of", "compare these options", "due diligence on", "evaluate this technology", or any question requiring synthesis from multiple sources rather than a quick answer.
---

# Deep Research

Produce thorough, cited research reports from multiple web sources. The output should make a decision easier — not just summarize what's out there.

## Workflow

### Step 1: Understand the Goal
Ask 1-2 quick clarifying questions if needed. If user says "just research it" — skip ahead and use your judgment on scope.

### Step 2: Plan the Research
Break into 3-5 sub-questions. Example for "Should I use Bun or Node for my next project?":
1. Performance benchmarks (recent, real-world)?
2. Ecosystem compatibility and gaps?
3. Production adoption and stability?
4. Developer experience differences?
5. Community trajectory?

### Step 3: Multi-Source Search
For each sub-question, search using available tools (Brave Search, WebFetch, etc.):
- 2-3 keyword variations per sub-question
- Mix general and news queries
- 15-30 unique sources total
- Prioritize: official docs > benchmarks > reputable tech blogs > forums

### Step 4: Deep-Read Key Sources
Fetch full content for 3-5 most promising URLs. Snippets lie — full articles tell the truth.

### Step 5: Synthesize Report

```markdown
# [Topic]: Research Report
*Generated: [date] | Sources: [N] | Confidence: [High/Medium/Low]*

## Executive Summary
[3-5 sentences. Lead with the recommendation or key finding.]

## 1. [Theme]
[Findings with inline citations — ([Source](url))]

## Key Takeaways
- [Actionable insight 1]
- [Actionable insight 2]

## Risks and Caveats
- [What could go wrong]
- [What we couldn't verify]

## Sources
1. [Title](url) — [one-line summary]

## Methodology
Searched [N] queries across [M] sources. [Note any gaps.]
```

### Step 6: Deliver
Short topics: full report in chat. Long reports: summary in chat + save full report to file.

## Parallel Research
Use the Task tool to launch 2-3 research agents on different sub-questions simultaneously. This cuts research time significantly.

## Quality Rules

1. Every claim needs a source — no unsourced assertions
2. Cross-reference — single-source claims flagged as "[unverified]"
3. Recency matters — prefer last 12 months, flag anything older
4. Acknowledge gaps — if no good info found, say so explicitly
5. No hallucination — "insufficient data" beats a fabricated answer
6. Separate fact from inference — label estimates and opinions as such
7. Include contrarian evidence — don't just confirm what the user wants to hear

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) deep-research skill
