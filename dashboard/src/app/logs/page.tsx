"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Pause, Play, Trash2 } from "lucide-react";
import { wsURL } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR";

interface LogEntry {
  id: number;
  ts: string;
  level: LogLevel;
  message: string;
}

const levelColors: Record<LogLevel, string> = {
  DEBUG: "bg-gray-500/15 text-gray-400 border-gray-500/30",
  INFO: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  WARNING: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  ERROR: "bg-red-500/15 text-red-400 border-red-500/30",
};

// ---------------------------------------------------------------------------
// Seed data (offline / demo mode)
// ---------------------------------------------------------------------------

let logCounter = 0;
function seedLogs(): LogEntry[] {
  const samples: [LogLevel, string][] = [
    ["INFO", "Gateway started on port 7777"],
    ["INFO", "Telegram adapter connected"],
    ["DEBUG", "Heartbeat sent to all adapters"],
    ["INFO", "WhatsApp bridge connected via Baileys v7"],
    ["WARNING", "Session ses-018 approaching cost cap ($4.80 / $5.00)"],
    ["INFO", "Evolve pipeline COLLECT stage started"],
    ["DEBUG", "Fetching signals from 3 collectors"],
    ["INFO", "Evolve pipeline BUILD stage — generating skill"],
    ["ERROR", "Discord adapter: connection refused (disabled)"],
    ["INFO", "Cron job signal-scan completed in 4.2s"],
    ["WARNING", "Memory file approaching 2200 char limit"],
    ["INFO", "Skill auto-installed: market-sentiment-v2"],
    ["DEBUG", "Session ses-019 idle for 120s"],
  ];
  return samples.map(([level, message]) => ({
    id: logCounter++,
    ts: new Date().toISOString(),
    level,
    message,
  }));
}

function parseDemoLevel(): LogLevel {
  const levels: LogLevel[] = ["DEBUG", "INFO", "WARNING", "ERROR"];
  return levels[Math.floor(Math.random() * levels.length)];
}

function makeDemoEntry(): LogEntry {
  const lvl = parseDemoLevel();
  return {
    id: logCounter++,
    ts: new Date().toISOString(),
    level: lvl,
    message: `[demo] ${lvl.toLowerCase()} log entry #${logCounter}`,
  };
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<LogLevel | "ALL">("ALL");
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pausedRef = useRef(paused);

  // Keep pausedRef in sync so WS callback can read latest value
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // Seed initial logs
  useEffect(() => {
    setLogs(seedLogs());
    setLoading(false);
  }, []);

  // WebSocket connection — connect once, not re-created on pause toggle
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | undefined;
    let wsConnected = false;

    function startDemoFallback() {
      if (interval) return;
      interval = setInterval(() => {
        if (pausedRef.current) return;
        setLogs((prev) => [...prev.slice(-500), makeDemoEntry()]);
      }, 3000);
    }

    try {
      const ws = new WebSocket(wsURL("/ws"));
      wsRef.current = ws;

      ws.onopen = () => {
        wsConnected = true;
      };

      ws.onmessage = (evt) => {
        if (pausedRef.current) return;
        try {
          const msg = JSON.parse(evt.data);
          let entry: LogEntry;

          if (msg.type === "log" && msg.data) {
            // {"type": "log", "data": {"level": "INFO", "message": "...", "timestamp": "..."}}
            entry = {
              id: logCounter++,
              ts: msg.data.timestamp || new Date().toISOString(),
              level: (msg.data.level?.toUpperCase() as LogLevel) || "INFO",
              message: msg.data.message || JSON.stringify(msg.data),
            };
          } else if (msg.type === "event" && msg.data) {
            // {"type": "event", "data": {...}} — show as INFO
            entry = {
              id: logCounter++,
              ts: msg.data.timestamp || new Date().toISOString(),
              level: "INFO",
              message: msg.data.message || `[event] ${JSON.stringify(msg.data)}`,
            };
          } else {
            // Unknown format — show raw
            entry = {
              id: logCounter++,
              ts: new Date().toISOString(),
              level: "INFO",
              message: typeof msg === "string" ? msg : JSON.stringify(msg),
            };
          }

          setLogs((prev) => [...prev.slice(-500), entry]);
        } catch {
          // Non-JSON message
          setLogs((prev) => [
            ...prev.slice(-500),
            {
              id: logCounter++,
              ts: new Date().toISOString(),
              level: "INFO",
              message: evt.data,
            },
          ]);
        }
      };

      ws.onerror = () => {
        if (!wsConnected) startDemoFallback();
      };

      ws.onclose = () => {
        startDemoFallback();
      };
    } catch {
      startDemoFallback();
    }

    return () => {
      wsRef.current?.close();
      if (interval) clearInterval(interval);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll
  useEffect(() => {
    if (!paused) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, paused]);

  const filtered =
    filter === "ALL" ? logs : logs.filter((l) => l.level === filter);

  const clearLogs = useCallback(() => setLogs([]), []);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-96 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Live Logs</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? (
              <Play className="mr-1 h-3 w-3" />
            ) : (
              <Pause className="mr-1 h-3 w-3" />
            )}
            {paused ? "Resume" : "Pause"}
          </Button>
          <Button variant="outline" size="sm" onClick={clearLogs}>
            <Trash2 className="mr-1 h-3 w-3" /> Clear
          </Button>
        </div>
      </div>

      {/* Level filters */}
      <div className="flex gap-2">
        {(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"] as const).map((lvl) => (
          <Button
            key={lvl}
            variant={filter === lvl ? "default" : "outline"}
            size="sm"
            className="text-xs"
            onClick={() => setFilter(lvl)}
          >
            {lvl}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Log Stream ({filtered.length} entries)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[calc(100vh-320px)] rounded-md border bg-black/30 p-2 font-mono text-xs">
            {filtered.map((entry) => (
              <div key={entry.id} className="flex gap-2 py-0.5">
                <span className="shrink-0 text-muted-foreground">
                  {new Date(entry.ts).toLocaleTimeString()}
                </span>
                <Badge
                  variant="outline"
                  className={`shrink-0 text-[10px] ${levelColors[entry.level]}`}
                >
                  {entry.level.padEnd(7)}
                </Badge>
                <span className="break-all">{entry.message}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
