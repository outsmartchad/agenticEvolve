---
name: market-research
description: Conduct market research, competitive analysis, technology evaluation, and industry intelligence with source attribution and decision-oriented summaries. Use when the user wants market sizing, competitor comparisons, technology scans, tool evaluations, "what's the best X for Y", "who are the competitors to", "is this market worth entering", "evaluate these options", or any research that informs a build-or-buy, enter-or-skip, or invest-or-pass decision.
---

# Market Research

Produce research that supports decisions, not research theater. The output should make someone more confident in their next move — or more confident that they should wait.

## Research Standards

1. Every important claim needs a source.
2. Prefer recent data and call out stale data explicitly.
3. Include contrarian evidence and downside cases — not just the bull case.
4. Translate findings into a recommendation, not just a summary.
5. Separate fact, inference, and recommendation clearly.

## Research Modes

### Competitive Analysis
Collect: product reality (not marketing copy), funding/investors, traction metrics where available, distribution/pricing, strengths/weaknesses/positioning gaps.

Focus on what you can verify: GitHub stars, npm downloads, job postings, pricing pages, public launches. Don't fabricate revenue numbers.

### Market Sizing
Use: top-down from reports, bottom-up from realistic assumptions. Make every leap explicit.

Example: "If there are ~500K active Claude Code users (inference from download metrics), and 10% would pay $20/mo for a skill marketplace, that's a ~$12M/yr TAM."

### Technology / Tool Evaluation
Collect: how it works, trade-offs, adoption signals (stars, downloads, contributors), integration complexity, lock-in risk, security/compliance considerations.

This is the most common mode for individual developers — "should I use X or Y?"

### Investor / Fund Diligence
Collect: fund size, stage, check size, relevant portfolio, public thesis, recent activity, fit assessment, red flags.

## Output Format

1. Executive summary (lead with the recommendation)
2. Key findings (with sources)
3. Implications (what this means for the user)
4. Risks and caveats
5. Recommendation (clear, actionable)
6. Sources

## Quality Gate

Before delivering:
- All numbers sourced or labeled as estimates
- Old data flagged with date
- Recommendation follows from evidence (not vibes)
- Risks and counterarguments included
- Output makes a decision easier, not harder

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) market-research skill
