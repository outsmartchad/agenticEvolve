---
name: article-writing
description: Write articles, blog posts, guides, tutorials, newsletters, launch posts, and other long-form content in a distinctive voice — not generic AI slop. Use when the user wants polished written content longer than a paragraph, needs to turn notes or research into a publishable piece, wants to match a specific writing voice, or says "write a post", "draft an article", "help me write", "blog about", or "newsletter issue". Also use for tightening structure and removing filler from existing drafts.
---

# Article Writing

Write long-form content that sounds like a real person, not a language model. The goal is content that earns attention and trust — the kind of writing that makes someone forward it to a colleague.

## Core Rules

1. Lead with the concrete thing: example, output, anecdote, number, screenshot description, or code block.
2. Explain after the example, not before.
3. Prefer short, direct sentences over padded ones.
4. Use specific numbers when available and sourced.
5. Never invent biographical facts, company metrics, or customer evidence.

## Voice Capture Workflow

If the user wants a specific voice, collect one or more of:
- published articles or newsletters
- X / LinkedIn posts
- docs, memos, or READMEs
- a short style guide ("write like Paul Graham" counts)

Then extract:
- sentence length and rhythm
- formal vs conversational vs sharp
- favored devices: parentheses, lists, fragments, questions
- tolerance for humor, opinion, and contrarian framing
- formatting habits: headers, bullets, code blocks, pull quotes

If no voice references are given, default to a direct, builder-style voice: concrete, practical, low on hype. Think indie dev writing for other devs.

## Banned Patterns

Delete and rewrite any of these:
- Generic openings: "In today's rapidly evolving landscape"
- Filler transitions: "Moreover", "Furthermore", "Additionally"
- Hype phrases: "game-changer", "cutting-edge", "revolutionary", "unlock"
- Vague claims without evidence
- Biography or credibility claims not backed by provided context
- "As an AI" or any self-referential model language

## Writing Process

1. Clarify the audience and purpose (ask if unclear).
2. Build a skeletal outline with one purpose per section.
3. Start each section with evidence, example, or scene.
4. Expand only where the next sentence earns its place.
5. Remove anything that sounds templated or self-congratulatory.

## Structure by Format

### Technical Guides / Tutorials
- Open with what the reader gets (the result, not the journey)
- Use code or terminal examples in every major section
- End with concrete takeaways, not a soft summary

### Essays / Opinion Pieces
- Start with tension, contradiction, or a sharp observation
- Keep one argument thread per section
- Use examples that earn the opinion

### Launch Posts / Announcements
- Lead with what it does, not the backstory
- Show the output or demo immediately
- Save the "why we built this" for the second half

### Newsletters
- Keep the first screen strong — if it doesn't hook in 3 sentences, rewrite
- Mix insight with updates, not diary filler
- Use clear section labels for easy skimming

## Quality Gate

Before delivering:
- Verify factual claims against provided sources
- Remove filler and corporate language
- Confirm the voice matches supplied examples (or defaults to builder-style)
- Ensure every section adds new information
- Check formatting for the intended platform (Markdown, HTML, plain text)

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) article-writing skill
