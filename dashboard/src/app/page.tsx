"use client";

import { useEffect, useState } from "react";
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
  TestTube2,
  Brain,
  GitCommit,
  Activity,
  Clock,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock data — will be replaced by API calls
// ---------------------------------------------------------------------------

const summaryCards = [
  {
    label: "Commands",
    value: 1_247,
    icon: Terminal,
    color: "bg-blue-500",
    progress: 78,
  },
  {
    label: "Tests",
    value: "142 / 148",
    icon: TestTube2,
    color: "bg-green-500",
    progress: 96,
  },
  {
    label: "Patterns",
    value: 38,
    icon: Brain,
    color: "bg-purple-500",
    progress: 62,
  },
  {
    label: "Commits",
    value: 312,
    icon: GitCommit,
    color: "bg-amber-500",
    progress: 85,
  },
];

const taskQueue = {
  done: 24,
  pending: 3,
  active: 1,
};

const agentMetrics = [
  { metric: "Total Sessions", value: "89" },
  { metric: "Tasks Completed", value: "1,247" },
  { metric: "Patterns Extracted", value: "38" },
  { metric: "Cost Today", value: "$4.23" },
  { metric: "Autopilot Status", value: "Active" },
];

const modules = [
  { name: "Gateway", status: "ready" as const },
  { name: "Telegram Adapter", status: "active" as const },
  { name: "WhatsApp Bridge", status: "active" as const },
  { name: "Discord Adapter", status: "configured" as const },
  { name: "Evolve Pipeline", status: "ready" as const },
  { name: "Learn Pipeline", status: "ready" as const },
  { name: "Cron Scheduler", status: "active" as const },
  { name: "Memory Engine", status: "ready" as const },
];

const recentActivity = [
  {
    time: "2 min ago",
    text: "Session #89 started — Telegram @outsmartchad",
  },
  {
    time: "8 min ago",
    text: "Evolve cycle completed — 2 skills installed",
  },
  { time: "15 min ago", text: "Cost alert: daily spend reached $4.00" },
  {
    time: "32 min ago",
    text: "WhatsApp bridge reconnected",
  },
  { time: "1 hr ago", text: "Cron job signal-scan executed" },
];

const statusColor: Record<string, string> = {
  ready: "bg-green-500/15 text-green-500 border-green-500/30",
  active: "bg-blue-500/15 text-blue-500 border-blue-500/30",
  configured: "bg-yellow-500/15 text-yellow-500 border-yellow-500/30",
  error: "bg-red-500/15 text-red-500 border-red-500/30",
};

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Simulate data fetch
    const t = setTimeout(() => setLoading(false), 600);
    return () => clearTimeout(t);
  }, []);

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
          {/* Task Queue */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Task Queue</CardTitle>
            </CardHeader>
            <CardContent className="flex gap-3">
              <Badge
                variant="outline"
                className="bg-green-500/15 text-green-500 border-green-500/30"
              >
                Done: {taskQueue.done}
              </Badge>
              <Badge
                variant="outline"
                className="bg-yellow-500/15 text-yellow-500 border-yellow-500/30"
              >
                Pending: {taskQueue.pending}
              </Badge>
              <Badge
                variant="outline"
                className="bg-blue-500/15 text-blue-500 border-blue-500/30"
              >
                Active: {taskQueue.active}
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
              <div className="grid gap-2 sm:grid-cols-2">
                {modules.map((m) => (
                  <div
                    key={m.name}
                    className="flex items-center justify-between rounded-md border px-3 py-2"
                  >
                    <span className="text-sm">{m.name}</span>
                    <Badge
                      variant="outline"
                      className={statusColor[m.status]}
                    >
                      {m.status}
                    </Badge>
                  </div>
                ))}
              </div>
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
            <div className="space-y-4">
              {recentActivity.map((a, i) => (
                <div key={i}>
                  <div className="flex items-start gap-2">
                    <Clock className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                    <div>
                      <p className="text-sm">{a.text}</p>
                      <p className="text-xs text-muted-foreground">{a.time}</p>
                    </div>
                  </div>
                  {i < recentActivity.length - 1 && (
                    <Separator className="mt-3" />
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
