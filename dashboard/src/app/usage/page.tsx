"use client";

import { useEffect, useState, useCallback } from "react";
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
import { fetchAPI } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DailyUsage {
  date: string;
  cost: number;
  sessions: number;
  messages: number;
}

interface CostCard {
  label: string;
  value: string;
  icon: typeof DollarSign;
}

export default function UsagePage() {
  const [loading, setLoading] = useState(true);
  const [todayCost, setTodayCost] = useState(0);
  const [weekCost, setWeekCost] = useState(0);
  const [totalCost, setTotalCost] = useState(0);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [usageData, statusData] = await Promise.all([
        fetchAPI("/api/usage?days=14"),
        fetchAPI("/api/status"),
      ]);
      setTodayCost(statusData.today_cost ?? 0);
      setWeekCost(statusData.week_cost ?? 0);
      setTotalCost(usageData.total_cost ?? 0);
      setDaily(usageData.daily ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch usage data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

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

  if (error && daily.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-lg font-semibold">Usage &amp; Cost</h1>
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Failed to load usage data: {error}
          </CardContent>
        </Card>
      </div>
    );
  }

  const costSummary: CostCard[] = [
    { label: "Today", value: `$${todayCost.toFixed(2)}`, icon: DollarSign },
    { label: "This Week", value: `$${weekCost.toFixed(2)}`, icon: TrendingUp },
    { label: "Total (14 days)", value: `$${totalCost.toFixed(2)}`, icon: Calendar },
  ];

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

      {/* Daily breakdown table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Daily Breakdown
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Sessions</TableHead>
                <TableHead className="text-right">Messages</TableHead>
                <TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {daily.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    No usage data available
                  </TableCell>
                </TableRow>
              ) : (
                daily.map((d) => (
                  <TableRow key={d.date}>
                    <TableCell className="text-sm">{d.date}</TableCell>
                    <TableCell className="text-right">{d.sessions}</TableCell>
                    <TableCell className="text-right">{d.messages}</TableCell>
                    <TableCell className="text-right font-medium">
                      ${d.cost.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
