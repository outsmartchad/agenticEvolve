"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DollarSign, TrendingUp, Calendar } from "lucide-react";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const costSummary = [
  { label: "Today", value: "$4.23", icon: DollarSign, change: "+12%" },
  { label: "This Week", value: "$18.67", icon: TrendingUp, change: "+5%" },
  { label: "This Month", value: "$52.41", icon: Calendar, change: "-8%" },
];

const perSessionCosts = [
  { id: "ses-025", model: "claude-sonnet-4-20250514", tokens: "12,340", cost: "$0.42" },
  { id: "ses-024", model: "claude-sonnet-4-20250514", tokens: "8,210", cost: "$0.28" },
  { id: "ses-023", model: "claude-sonnet-4-20250514", tokens: "24,500", cost: "$0.84" },
  { id: "ses-022", model: "claude-sonnet-4-20250514", tokens: "6,100", cost: "$0.21" },
  { id: "ses-021", model: "claude-opus-4-20250514", tokens: "3,200", cost: "$0.48" },
  { id: "ses-020", model: "claude-sonnet-4-20250514", tokens: "15,800", cost: "$0.54" },
  { id: "ses-019", model: "claude-sonnet-4-20250514", tokens: "9,700", cost: "$0.33" },
  { id: "ses-018", model: "claude-opus-4-20250514", tokens: "4,100", cost: "$0.62" },
];

export default function UsagePage() {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 500);
    return () => clearTimeout(t);
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Usage &amp; Cost</h1>

      {/* Cost summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        {costSummary.map((c) => (
          <Card key={c.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardDescription className="text-xs font-medium uppercase tracking-wide">
                {c.label}
              </CardDescription>
              <c.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{c.value}</p>
              <p
                className={`mt-1 text-xs ${
                  c.change.startsWith("+")
                    ? "text-red-400"
                    : "text-green-400"
                }`}
              >
                {c.change} vs previous period
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Chart placeholder */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Daily Cost (Last 14 Days)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-48 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
            Chart placeholder — install recharts to render
          </div>
        </CardContent>
      </Card>

      {/* Per-session breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Per-Session Cost Breakdown
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Session</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {perSessionCosts.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.id}</TableCell>
                  <TableCell className="text-xs">{r.model}</TableCell>
                  <TableCell className="text-right">{r.tokens}</TableCell>
                  <TableCell className="text-right font-medium">
                    {r.cost}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
