---
name: firecrawl
description: Use when the user wants to scrape a webpage, crawl a website, search the web, map site URLs, extract structured data, or download documentation. Also use when /evolve needs web signals, /absorb needs to read doc sites, or /learn needs to cleanly scrape any page. Trigger on "scrape", "crawl", "search the web", "download docs", "map site", "extract from website", "web research".
---

# Firecrawl — Web Scraping & Crawling via CLI

The `firecrawl` CLI is installed globally. Use it for all web scraping, crawling, searching, and structured extraction tasks. It handles JavaScript rendering, anti-bot bypasses, and returns clean markdown.

## Pre-flight Check

Before any firecrawl command, verify authentication:

```bash
firecrawl --status
```

If "Not authenticated" → tell the user to run `firecrawl login` or set `FIRECRAWL_API_KEY` in `~/.agenticEvolve/.env`.

## Commands

### 1. Scrape — Single page to clean markdown

```bash
# Basic scrape (returns markdown)
firecrawl scrape <url>

# Scrape with specific formats
firecrawl scrape <url> --formats markdown,html,links

# Scrape multiple URLs concurrently
firecrawl scrape <url1> <url2> <url3>

# Scrape only specific content (CSS selector)
firecrawl scrape <url> --include-tags "article,main,.content"

# Exclude navigation/footer noise
firecrawl scrape <url> --exclude-tags "nav,footer,sidebar,.ads"

# Wait for JS to render
firecrawl scrape <url> --wait 3000

# Output to file
firecrawl scrape <url> -o result.md
```

**When to use:** Single page reading. Getting article/blog content. Cleaning up a messy webpage. Reading documentation pages.

### 2. Crawl — Multi-page website crawling

```bash
# Crawl a site (follows links, default depth)
firecrawl crawl <url>

# Limit pages crawled
firecrawl crawl <url> --limit 50

# Check status of async crawl
firecrawl crawl <job-id>
```

**When to use:** Downloading entire doc sites. Analyzing multi-page projects. Collecting all pages from a domain.

### 3. Download — Save entire site as local files

```bash
# Download site into .firecrawl/ as nested markdown files
firecrawl download <url>

# With page limit
firecrawl download <url> --limit 100
```

**When to use:** Creating local copies of documentation. Offline reference material. Feeding into /absorb or /learn.

### 4. Search — Web search with content extraction

```bash
# Search the web (returns scraped results, not just links)
firecrawl search "query terms"

# Limit results
firecrawl search "query terms" --limit 5

# Search with scrape format
firecrawl search "query terms" --formats markdown
```

**When to use:** Web research. Finding information across the internet. Signal collection for /evolve. Answering questions that need current web data.

### 5. Map — Discover all URLs on a site

```bash
# Map all URLs on a domain
firecrawl map <url>

# Output as JSON
firecrawl map <url> --format json
```

**When to use:** Understanding site structure before crawling. Finding specific pages. Pre-planning a targeted crawl.

### 6. Agent — AI-powered data extraction

```bash
# Run an AI agent to extract specific data
firecrawl agent "Find the pricing for Anthropic's Claude API"

# Check status
firecrawl agent <job-id>
```

**When to use:** Complex research tasks. Structured data extraction. Multi-step web research.

## Integration with Pipelines

### /evolve signal collection
Use `firecrawl search` to find trending tools, techniques, and patterns:
```bash
firecrawl search "best new developer tools 2025" --limit 10
firecrawl search "TypeScript patterns" --limit 5
```

### /absorb doc ingestion
Use `firecrawl download` to grab entire doc sites before analysis:
```bash
firecrawl download https://docs.example.com --limit 50
# Then analyze the downloaded .firecrawl/ directory
```

### /learn page scraping
Use `firecrawl scrape` to cleanly extract any page:
```bash
firecrawl scrape https://blog.example.com/article --formats markdown -o /tmp/article.md
```

## Credit Usage

- `scrape`: 1 credit per page
- `crawl`: 1 credit per page discovered
- `search`: 1 credit per result
- `map`: 1 credit per call
- `agent`: varies (5-50 credits)
- Free tier: 500 credits total
- Hobby ($16/mo): 3,000 credits/mo

## Output Location

Results are cached in `.firecrawl/` in the working directory. Add `.firecrawl/` to `.gitignore`.

## Error Handling

- **401/403**: Not authenticated → `firecrawl login`
- **429**: Rate limited → wait and retry
- **Credits exhausted**: Switch to `brave-search` skill or `WebFetch` tool as fallback

Source: https://docs.firecrawl.dev/sdks/cli
