---
name: brave-search
description: Search the web using Brave Search API. Use when the user asks to search the web, look something up online, find recent information, or needs real-time data like news, prices, weather, trends, documentation, or current events. Also use when the user says "google this", "search for", "look up", "find me", "what's the latest on", or any variation of wanting information from the internet.
argument-hint: <search query> [--fresh pd|pw|pm|py] [--count N] [--country XX]
allowed-tools: Bash(curl *)
---

# Brave Web Search

Search the web using the Brave Search API and return formatted results.

## API Details

- **Endpoint**: `https://api.search.brave.com/res/v1/web/search`
- **Auth header**: `X-Subscription-Token: $BRAVE_API_KEY`
- **Method**: GET

## How to search

Run a curl command against the Brave Search API. Parse the JSON response and present results clearly.

```bash
curl -s "https://api.search.brave.com/res/v1/web/search?q=$(echo '$ARGUMENTS' | sed 's/ /+/g')&count=5&extra_snippets=true" \
  -H "X-Subscription-Token: $BRAVE_API_KEY" | jq '.'
```

## Parameters you can use

| Parameter | Description | Example |
|-----------|-------------|---------|
| `q` | Search query (URL-encoded) | `q=rust+web+frameworks` |
| `count` | Results per page (max 20, default 20) | `count=5` |
| `offset` | Pagination offset (0-9) | `offset=1` |
| `freshness` | Time filter: `pd` (24h), `pw` (week), `pm` (month), `py` (year), or date range `2024-01-01to2024-06-30` | `freshness=pw` |
| `country` | 2-char country code | `country=US` |
| `search_lang` | Content language (ISO 639-1) | `search_lang=en` |
| `safesearch` | `off`, `moderate` (default), `strict` | `safesearch=off` |
| `extra_snippets` | Get up to 5 extra excerpts per result | `extra_snippets=true` |

## Search operators (include in the query string itself)

- Exact phrase: `"machine learning tutorials"`
- Exclude term: `javascript -jquery`
- Site-specific: `site:github.com rust tutorials`
- File type: `filetype:pdf research paper`

## Interpreting arguments

Parse `$ARGUMENTS` for the search query and optional flags:
- `--fresh <value>` -> set `freshness` param
- `--count <N>` -> set `count` param
- `--country <XX>` -> set `country` param
- Everything else is the search query

## Output format

Present results as a concise list:
1. **Title** — URL
   Summary/description snippet

Include the total result count if available. If `more_results_available` is true, mention that more results exist.

## Error handling

- If `BRAVE_API_KEY` is not set, tell the user to set it (see instructions below)
- If the API returns an error, show the error message and HTTP status code

## Setup reminder

If the API key is missing, tell the user:
```
Export your Brave API key:
  export BRAVE_API_KEY="your-key-here"

Or add it to your shell profile:
  echo 'export BRAVE_API_KEY="your-key-here"' >> ~/.zshrc
```
