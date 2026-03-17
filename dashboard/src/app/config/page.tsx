"use client";

import { useEffect, useState, useRef } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ---------------------------------------------------------------------------
// Config shape matching actual API keys
// ---------------------------------------------------------------------------

interface ConfigData {
  model: string;
  daily_cost_cap: number;
  weekly_cost_cap: number;
  session_idle_minutes: number;
  autonomy: string;
  auto_approve_skills: boolean;
}

const defaultConfig: ConfigData = {
  model: "claude-sonnet-4-20250514",
  daily_cost_cap: 25.0,
  weekly_cost_cap: 100.0,
  session_idle_minutes: 30,
  autonomy: "full",
  auto_approve_skills: true,
};

const fieldMeta: {
  key: keyof ConfigData;
  label: string;
  type: "text" | "number" | "toggle";
  section: string;
}[] = [
  { key: "model", label: "Model", type: "text", section: "Agent" },
  {
    key: "autonomy",
    label: "Autonomy Level",
    type: "text",
    section: "Agent",
  },
  {
    key: "auto_approve_skills",
    label: "Auto-Approve Skills",
    type: "toggle",
    section: "Agent",
  },
  {
    key: "daily_cost_cap",
    label: "Daily Cost Cap ($)",
    type: "number",
    section: "Cost",
  },
  {
    key: "weekly_cost_cap",
    label: "Weekly Cost Cap ($)",
    type: "number",
    section: "Cost",
  },
  {
    key: "session_idle_minutes",
    label: "Session Idle Timeout (min)",
    type: "number",
    section: "Sessions",
  },
];

export default function ConfigPage() {
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<ConfigData>(defaultConfig);
  const [saving, setSaving] = useState(false);
  const originalConfig = useRef<ConfigData>(defaultConfig);

  useEffect(() => {
    fetchAPI("/api/config")
      .then((data) => {
        const merged = { ...defaultConfig, ...data };
        setConfig(merged);
        originalConfig.current = merged;
      })
      .catch(() => {
        /* use defaults */
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Only send changed fields
      const changed: Partial<ConfigData> = {};
      for (const key of Object.keys(config) as (keyof ConfigData)[]) {
        if (config[key] !== originalConfig.current[key]) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (changed as any)[key] = config[key];
        }
      }
      if (Object.keys(changed).length === 0) {
        toast.info("No changes to save");
        setSaving(false);
        return;
      }
      await fetchAPI("/api/config", {
        method: "POST",
        body: JSON.stringify(changed),
      });
      originalConfig.current = { ...config };
      toast.success("Configuration saved");
    } catch {
      toast.error("Failed to save — gateway may be offline");
    } finally {
      setSaving(false);
    }
  };

  const updateField = (key: keyof ConfigData, value: string | number | boolean) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-96 rounded-lg" />
      </div>
    );
  }

  // Group by section
  const sections = Array.from(new Set(fieldMeta.map((f) => f.section)));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Configuration</h1>
        <Button size="sm" onClick={handleSave} disabled={saving}>
          <Save className="mr-2 h-4 w-4" />
          {saving ? "Saving..." : "Save"}
        </Button>
      </div>

      {sections.map((section) => (
        <Card key={section}>
          <CardHeader>
            <CardTitle className="text-sm font-medium">{section}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {fieldMeta
              .filter((f) => f.section === section)
              .map((field) => (
                <div key={field.key}>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {field.label}
                  </label>
                  {field.type === "toggle" ? (
                    <Button
                      variant={
                        config[field.key] ? "default" : "outline"
                      }
                      size="sm"
                      onClick={() =>
                        updateField(field.key, !config[field.key])
                      }
                    >
                      {config[field.key] ? "Enabled" : "Disabled"}
                    </Button>
                  ) : (
                    <Input
                      type={field.type}
                      value={String(config[field.key])}
                      onChange={(e) =>
                        updateField(
                          field.key,
                          field.type === "number"
                            ? Number(e.target.value)
                            : e.target.value
                        )
                      }
                    />
                  )}
                </div>
              ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
