---
name: cloudflare-crawl
description: Use when you need to crawl websites for FREE without firecrawl credits, bulk-crawl documentation sites, or extract structured data from web pages using Cloudflare Browser Rendering REST API. Free fallback for firecrawl. Trigger on "free crawl", "crawl without credits", "cloudflare crawl", "bulk scrape free".
---

# Cloudflare Browser Rendering — Free Web Crawling via REST API

Free alternative to Firecrawl for crawling websites. Uses Cloudflare's Browser Rendering REST API which includes a full headless browser, JavaScript rendering, and AI extraction.

## Prerequisites

Requires a Cloudflare account with Browser Rendering enabled. The API is called via `curl` or any HTTP client.

Check if Cloudflare API credentials are set:
```bash
echo "CF_API_TOKEN: ${CF_API_TOKEN:-(not set)}"
echo "CF_ACCOUNT_ID: ${CF_ACCOUNT_ID:-(not set)}"
```

If not set, tell the user to:
1. Go to https://dash.cloudflare.com → Workers & Pages → Browser Rendering
2. Enable Browser Rendering
3. Create an API token with `Workers` permission
4. Set `CF_API_TOKEN` and `CF_ACCOUNT_ID` in `~/.agenticEvolve/.env`

## API Endpoints

Base URL: `https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering`

### 1. /crawl — Crawl a website

```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/browser-rendering/crawl" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.example.com",
    "maxPages": 50,
    "renderJs": true,
    "sitemap": true,
    "robotsTxt": true,
    "filterByPathPrefix": "/docs/",
    "transformations": {
      "extractMainContent": true,
      "outputFormat": "markdown"
    }
  }'
```

Returns a `crawl_id` for async results.

### 2. /scrape — Single page scrape

```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/browser-rendering/scrape" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/page",
    "renderJs": true,
    "transformations": {
      "extractMainContent": true,
      "outputFormat": "markdown"
    }
  }'
```

### 3. /snapshot — Get page HTML

```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/browser-rendering/snapshot" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/page",
    "renderJs": true,
    "viewport": { "width": 1280, "height": 800 }
  }'
```

### 4. /screenshot — Take screenshot

```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/browser-rendering/screenshot" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "screenshotOptions": {
      "fullPage": true,
      "type": "png"
    }
  }' --output screenshot.png
```

### 5. AI Extraction (with Workers AI)

```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/browser-rendering/scrape" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/pricing",
    "renderJs": true,
    "transformations": {
      "aiExtract": {
        "prompt": "Extract all pricing tiers with their features and costs",
        "model": "@cf/meta/llama-3.1-8b-instruct"
      }
    }
  }'
```

## Free Tier Limits

- 5 crawls/day
- 100 pages/crawl
- 10 minutes browser time/day
- Paid: $0.09/hr, up to 100k pages

## When to Prefer Over Firecrawl

- Firecrawl credits exhausted
- Need free crawling for non-critical tasks
- Already have Cloudflare account
- Need AI extraction without additional API costs (Workers AI included)

## When to Prefer Firecrawl Instead

- Need higher rate limits
- Need cleaner markdown output
- Firecrawl `search` (web search, not just crawling)
- Need `firecrawl agent` for complex multi-step research

Source: https://developers.cloudflare.com/browser-rendering/rest-api/crawl/
