# Interface

Usage examples from Telegram.

## Chat

```
> research the top 5 competitors in the AI code editor space and summarize their pricing
  [searches web, reads pricing pages, compiles data]
  Here's the breakdown: Cursor ($20/mo), Windsurf ($15/mo)...

> write a twitter thread about why developers should use AI agents
  [drafts thread with hook, insights, CTA]
  Done. 8 tweets. Want me to adjust the tone?

> deploy the staging branch and run the migration
  [pulls branch, runs deploy script, executes migration]
  Deployed. Migration applied — 3 tables updated, 0 errors.
```

## Evolve

```
> /evolve
  [scans GitHub trending, HN — scores 12 signals]
  2 new skills built and auto-installed: api-rate-limiting, structured-logging
```

## Absorb

```
> /absorb https://github.com/trending-project
  [clones repo, scans architecture, diffs patterns]
  Implemented 3 improvements: retry logic, health checks, graceful shutdown.
```

## Learn

```
> /learn https://github.com/some-saas-boilerplate
  [deep-dives codebase, extracts patterns]
  ADOPT: their auth flow. STEAL: the webhook retry pattern. SKIP: their ORM choice.
```

## Recall

```
> /recall rate limiting
  Recall: rate limiting
  5 results across 3 layers

  ## Past Conversations
  - discussed nginx rate limiting config (session: API hardening, 2026-03-10)

  ## Absorbed Knowledge
  - token bucket with sliding window, 429 retry-after header (from: github.com/foo/bar, verdict: STEAL)

  ## Observed Patterns
  - prefer per-route rate limits over global (conf: 0.7, seen 3x)
```

## Reply Context

Reply to any bot message to use it as context for your next command:

```
[bot message about a repo with URL]
  -> reply: /absorb       (absorbs the repo from the replied message)
  -> reply: /learn         (learns from it)
  -> reply: /notify 30m   (reminds you about it in 30 min)
  -> reply: tell me more   (Claude sees the replied message as context)
```
