---
name: helixdb-rag
description: Use HelixDB — a graph + vector hybrid database (YC W26) — for RAG pipelines and AI retrieval in agenticEvolve. Use when the user says "set up helixdb", "graph RAG", "hybrid vector search", "HelixDB", "easier AI retrieval", or wants a simpler alternative to Pinecone/Weaviate with graph traversal built in.
user-invocable: true
version: 1.0.0
source: https://x.com/ycombinator/status/1927076180651278379 (YC W26, 2026-03-28 evolve cycle)
---

# HelixDB — Graph + Vector Hybrid Database for RAG

HelixDB is a YC W26-backed database purpose-built for AI retrieval. It combines graph traversal and vector similarity search in a single query, eliminating the glue code between separate graph and vector stores.

## When to Use

- Building a RAG pipeline for agenticEvolve's knowledge base
- Need graph-aware retrieval (e.g. "find signals related to this concept and their neighbors")
- Replacing multiple databases (vector store + knowledge graph) with one system
- Storing agent memory with rich relationship metadata

## Quick Install

```bash
# Via npm (embedded mode)
npm install helixdb

# Or run as a server
npx helixdb serve --port 6380
```

## Basic Usage

```typescript
import { HelixDB } from 'helixdb';

const db = new HelixDB({ path: '~/.agenticEvolve/knowledge/helix' });

// Store a signal with vector embedding + graph edges
await db.insert({
  id: 'signal-001',
  content: 'Claude Code releases cowork feature',
  embedding: await embed(content),   // your embed function
  edges: ['anthropic', 'claude-code', 'collaboration']
});

// Hybrid search: vector similarity + graph neighborhood
const results = await db.search({
  query: 'collaborative AI coding',
  embedding: await embed(query),
  traverse: { hops: 2, direction: 'both' },
  limit: 10
});
```

## agenticEvolve Integration

Candidate use: replace the flat NDJSON signal files with a queryable knowledge graph.

```yaml
# config.yaml addition
knowledge_db:
  backend: helixdb           # or: pinecone, weaviate, none
  path: ~/.agenticEvolve/knowledge/helix
  auto_ingest_signals: false # set true to auto-embed each evolve cycle's signals
```

## Evaluation Checklist

- [ ] Install and run embedded mode — confirm zero external dependencies
- [ ] Benchmark insert latency for 1000 signals
- [ ] Test hybrid query: vector similarity + 2-hop graph traversal
- [ ] Compare retrieval quality vs. plain cosine search on signal corpus
- [ ] Assess memory footprint vs. Chroma or FAISS

## Rules

- Do not store private keys, API tokens, or user PII in HelixDB
- Back up the database path before running schema migrations
- Evaluate on a sample before replacing NDJSON signal pipeline in production
