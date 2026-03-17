"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Terminal,
  MessageSquare,
  DollarSign,
  TrendingUp,
  Activity,
  Clock,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StatusData {
  uptime_secs: number;
  platforms: Record<string, boolean>;
  active_sessions: number;
  today_cost: number;
  week_cost: number;
  total_sessions: number;
  total_messages: number;
  model: string;
  daily_cost_cap: number;
  weekly_cost_cap: number;
}

interface ModuleEntry {
  name: string;
  status: string;
}

interface MetricEvent {
  type: string;
  timestamp: string;
  data?: Record<string, unknown>;
  message?: string;
}

const statusColor: Record<string, string> = {
  ready: "bg-green-500/15 text-green-500 border-green-500/30",
  active: "bg-blue-500/15 text-blue-500 border-blue-500/30",
  configured: "bg-yellow-500/15 text-yellow-500 border-yellow-500/30",
  error: "bg-red-500/15 text-red-500 border-red-500/30",
  stopped: "bg-gray-500/15 text-gray-400 border-gray-500/30",
};

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<StatusData | null>(null);
  const [modules, setModules] = useState<ModuleEntry[]>([]);
  const [events, setEvents] = useState<MetricEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [statusData, modulesData, metricsData] = await Promise.all([
        fetchAPI("/api/status"),
        fetchAPI("/api/modules").catch(() => ({ modules: [] })),
        fetchAPI("/api/metrics").catch(() => ({ events: [] })),
      ]);
      setStatus(statusData);
      setModules(modulesData.modules ?? modulesData ?? []);
      const rawEvents = metricsData.recent_events ?? metricsData.events ?? [];
      setEvents(Array.isArray(rawEvents) ? rawEvents.slice(-5).reverse() : []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10_000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );
  }

  if (error && !status) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Failed to connect to gateway: {error}
        </CardContent>
      </Card>
    );
  }

  const s = status!;
  const costTodayPct = s.daily_cost_cap > 0 ? Math.min(100, (s.today_cost / s.daily_cost_cap) * 100) : 0;
  const costWeekPct = s.weekly_cost_cap > 0 ? Math.min(100, (s.week_cost / s.weekly_cost_cap) * 100) : 0;

  const summaryCards = [
    {
      label: "Sessions",
      value: s.total_sessions,
      icon: Terminal,
      color: "bg-blue-500",
      progress: Math.min(100, s.total_sessions),
    },
    {
      label: "Messages",
      value: s.total_messages,
      icon: MessageSquare,
      color: "bg-green-500",
      progress: Math.min(100, s.total_messages),
    },
    {
      label: "Cost Today",
      value: `$${s.today_cost.toFixed(2)}`,
      icon: DollarSign,
      color: costTodayPct > 80 ? "bg-red-500" : "bg-purple-500",
      progress: costTodayPct,
    },
    {
      label: "Cost This Week",
      value: `$${s.week_cost.toFixed(2)}`,
      icon: TrendingUp,
      color: costWeekPct > 80 ? "bg-red-500" : "bg-amber-500",
      progress: costWeekPct,
    },
  ];

  const agentMetrics = [
    { metric: "Total Sessions", value: String(s.total_sessions) },
    { metric: "Total Messages", value: String(s.total_messages) },
    { metric: "Today Cost", value: `$${s.today_cost.toFixed(2)}` },
    { metric: "Week Cost", value: `$${s.week_cost.toFixed(2)}` },
    { metric: "Model", value: s.model },
    { metric: "Uptime", value: formatUptime(s.uptime_secs) },
  ];

  return (
    <div className="space-y-6">
      {/* ---- Summary Cards ---- */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {summaryCards.map((c) => (
          <Card key={c.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">
                {c.label}
              </CardDescription>
              <c.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{c.value}</p>
              <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
                <div
                  className={`h-full rounded-full ${c.color}`}
                  style={{ width: `${c.progress}%` }}
                />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* ---- Left column: Metrics + Modules ---- */}
        <div className="space-y-6 lg:col-span-2">
          {/* Active Sessions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Active Sessions</CardTitle>
            </CardHeader>
            <CardContent className="flex gap-3">
              <Badge
                variant="outline"
                className="bg-blue-500/15 text-blue-500 border-blue-500/30"
              >
                Active: {s.active_sessions}
              </Badge>
              <Badge
                variant="outline"
                className="bg-green-500/15 text-green-500 border-green-500/30"
              >
                Platforms: {s.platforms ? Object.keys(s.platforms).filter(k => s.platforms[k]).join(", ") : "none"}
              </Badge>
            </CardContent>
          </Card>

          {/* Agent Metrics */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Agent Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agentMetrics.map((m) => (
                    <TableRow key={m.metric}>
                      <TableCell className="font-medium">
                        {m.metric}
                      </TableCell>
                      <TableCell className="text-right">{m.value}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Module Health */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Module Health
              </CardTitle>
            </CardHeader>
            <CardContent>
              {modules.length === 0 ? (
                <p className="text-sm text-muted-foreground">No module data available</p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {modules.map((m, i) => (
                    <div
                      key={m.name || i}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <span className="text-sm">{m.name}</span>
                      <Badge
                        variant="outline"
                        className={statusColor[m.status] || statusColor.ready}
                      >
                        {m.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ---- Right column: Activity Feed ---- */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Activity className="h-4 w-4" /> Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            {events.length === 0 ? (
              <p className="text-sm text-muted-foreground">No recent events</p>
            ) : (
              <div className="space-y-4">
                {events.map((a, i) => (
                  <div key={i}>
                    <div className="flex items-start gap-2">
                      <Clock className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                      <div>
                        <p className="text-sm">
                          {a.message || a.type || "Event"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {a.timestamp ? relativeTime(a.timestamp) : "just now"}
                        </p>
                      </div>
                    </div>
                    {i < events.length - 1 && (
                      <Separator className="mt-3" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
