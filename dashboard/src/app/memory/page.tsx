"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Search, Brain, Database, FileText, HardDrive } from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MemoryStats {
  memory_chars: number;
  memory_limit: number;
  memory_pct: number;
  user_chars: number;
  user_limit: number;
  user_pct: number;
  instinct_count: number;
  learning_count: number;
  session_count: number;
  embedding_docs: number;
  embedding_model: string;
  embedding_cached: string | null;
}

interface SearchResult {
  content: string;
  source: string;
  meta?: string;
  score?: number;
  confidence?: number;
  seen_count?: number;
  session_title?: string;
  session_date?: string;
  target?: string;
  verdict?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sourceColor(source: string): string {
  if (source.includes("session")) return "bg-blue-500/10 text-blue-500";
  if (source.includes("learning")) return "bg-green-500/10 text-green-500";
  if (source.includes("instinct")) return "bg-purple-500/10 text-purple-500";
  if (source.includes("memory")) return "bg-amber-500/10 text-amber-500";
  if (source.includes("user")) return "bg-cyan-500/10 text-cyan-500";
  if (source.includes("embedding") || source.includes("semantic"))
    return "bg-pink-500/10 text-pink-500";
  return "bg-gray-500/10 text-gray-500";
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    session: "Session",
    learning: "Learning",
    instinct: "Instinct",
    memory: "Memory",
    user_profile: "User Profile",
    active_session: "Active Session",
    "semantic:session": "Semantic Session",
    "semantic:learning": "Semantic Learning",
    "semantic:instinct": "Semantic Instinct",
    "semantic:memory": "Semantic Memory",
    "semantic:embedding": "Embedding",
    embedding: "Embedding",
  };
  return labels[source] || source;
}

function UsageBar({ used, limit, label }: { used: number; limit: number; label: string }) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const color =
    pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-green-500";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span>
          {used.toLocaleString()} / {limit.toLocaleString()} chars ({pct.toFixed(0)}%)
        </span>
      </div>
      <div className="h-2 rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function MemoryPage() {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  // Load stats on mount
  useEffect(() => {
    fetchAPI("/api/memory/stats")
      .then((data) => setStats(data))
      .catch(() => {});
  }, []);

  const doSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setHasSearched(true);
    try {
      const data = await fetchAPI(`/api/memory/search?q=${encodeURIComponent(query)}&limit=20`);
      setResults(data.results || []);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [query]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Memory</h1>
        <p className="text-sm text-muted-foreground">
          Search across all memory layers with hybrid FTS5 + vector embedding fusion
        </p>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">MEMORY.md</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <UsageBar
                used={stats.memory_chars}
                limit={stats.memory_limit}
                label="Agent Notes"
              />
            ) : (
              <Skeleton className="h-8 w-full" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">USER.md</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <UsageBar
                used={stats.user_chars}
                limit={stats.user_limit}
                label="User Profile"
              />
            ) : (
              <Skeleton className="h-8 w-full" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Database</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Sessions</span>
                  <span className="font-mono">{stats.session_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Learnings</span>
                  <span className="font-mono">{stats.learning_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Instincts</span>
                  <span className="font-mono">{stats.instinct_count}</span>
                </div>
              </div>
            ) : (
              <Skeleton className="h-12 w-full" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Embeddings</CardTitle>
            <Brain className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Model</span>
                  <span className="font-mono text-xs">{stats.embedding_model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Indexed docs</span>
                  <span className="font-mono">{stats.embedding_docs}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last built</span>
                  <span className="font-mono text-xs">
                    {stats.embedding_cached
                      ? new Date(stats.embedding_cached).toLocaleDateString()
                      : "never"}
                  </span>
                </div>
              </div>
            ) : (
              <Skeleton className="h-12 w-full" />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Search box */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Hybrid Search
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              doSearch();
            }}
            className="flex gap-2"
          >
            <Input
              placeholder="Search across sessions, learnings, instincts, memory..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1"
            />
            <Button type="submit" disabled={searching || !query.trim()}>
              {searching ? "Searching..." : "Search"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Results */}
      {hasSearched && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              {results.length} result{results.length !== 1 ? "s" : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {results.length === 0 && !searching && (
              <p className="text-sm text-muted-foreground">No results found.</p>
            )}
            {searching && (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            )}
            {results.map((r, i) => (
              <div
                key={i}
                className="rounded-md border p-3 text-sm space-y-1.5"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className={sourceColor(r.source)}>
                    {sourceLabel(r.source)}
                  </Badge>
                  {r.score != null && (
                    <span className="text-xs text-muted-foreground">
                      score: {r.score.toFixed(4)}
                    </span>
                  )}
                  {r.confidence != null && (
                    <span className="text-xs text-muted-foreground">
                      conf: {r.confidence.toFixed(2)}
                    </span>
                  )}
                  {r.session_title && (
                    <span className="text-xs text-muted-foreground">
                      {r.session_title}
                    </span>
                  )}
                  {r.session_date && (
                    <span className="text-xs text-muted-foreground">
                      {r.session_date}
                    </span>
                  )}
                  {r.target && (
                    <span className="text-xs text-muted-foreground">
                      from: {r.target}
                    </span>
                  )}
                  {r.verdict && (
                    <Badge variant="outline" className="text-xs">
                      {r.verdict}
                    </Badge>
                  )}
                </div>
                <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">
                  {r.content}
                </p>
                {r.meta && (
                  <p className="text-xs text-muted-foreground">{r.meta}</p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
