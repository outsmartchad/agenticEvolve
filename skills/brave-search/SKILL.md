---
name: brave-search
description: Search the web using the Brave Search API for real-time information. ALWAYS use this skill before any web search, "google this", "look up", "find online", "what's the latest on", "any news about", current events, documentation lookups, comparing tools or libraries, or any question requiring up-to-date information from the internet — even if the user doesn't explicitly say "search".
argument-hint: <search query> [--fresh pd|pw|pm|py] [--count N] [--country XX]
allowed-tools: Bash(curl *)
---

# Brave Web Search

Search the web using the Brave Search API and return formatted results. Brave gives you real-time access to the internet — use it whenever your training data might be stale or when the user needs current information.

## How to Search

```bash
curl -s "https://api.search.brave.com/res/v1/web/search?q=$(echo '$ARGUMENTS' | sed 's/ /+/g')&count=5&extra_snippets=true" \
  -H "X-Subscription-Token: $BRAVE_API_KEY" | jq '.'
```

## Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `q` | Search query (URL-encoded) | `q=rust+web+frameworks` |
| `count` | Results per page (max 20, default 20) | `count=5` |
| `offset` | Pagination offset (0-9) | `offset=1` |
| `freshness` | Time filter: `pd` (24h), `pw` (week), `pm` (month), `py` (year), or date range `2024-01-01to2024-06-30` | `freshness=pw` |
| `country` | 2-char country code | `country=US` |
| `search_lang` | Content language (ISO 639-1) | `search_lang=en` |
| `extra_snippets` | Get up to 5 extra excerpts per result | `extra_snippets=true` |

## Search Operators (include in the query string)

- Exact phrase: `"machine learning tutorials"`
- Exclude term: `javascript -jquery`
- Site-specific: `site:github.com rust tutorials`
- File type: `filetype:pdf research paper`

## Interpreting Arguments

Parse `$ARGUMENTS` for the search query and optional flags:
- `--fresh <value>` → set `freshness` param
- `--count <N>` → set `count` param
- `--country <XX>` → set `country` param
- Everything else is the search query

## Output Format

Present results as a concise list:
1. **Title** — URL
   Summary/description snippet

Include the total result count if available. If `more_results_available` is true, mention that more results exist.

## Effective Search Strategies

- For recent events, always set `freshness=pw` or `freshness=pd`
- For technical comparisons, use `site:github.com` or `site:reddit.com` for real opinions
- For documentation, use `site:docs.X.com` to target official docs
- Chain multiple searches to triangulate: general query first, then targeted follow-ups

## Error Handling

- If `BRAVE_API_KEY` is not set, tell the user to set it in `~/.agenticEvolve/.env` or shell profile
- If the API returns an error, show the error message and HTTP status code

Source: https://brave.com/search/api/
