import {
  type ChildProcessWithoutNullStreams,
  spawn,
} from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { resolveBrowserExecutable } from "./browser-executables.js";

export type { BrowserExecutable } from "./browser-executables.js";

export type RunningBrowser = {
  pid: number;
  cdpPort: number;
  cdpUrl: string;
  proc: ChildProcessWithoutNullStreams;
};

export type LaunchOptions = {
  cdpPort?: number;
  headless?: boolean;
  noSandbox?: boolean;
  executablePath?: string;
  extraArgs?: string[];
};

const DEFAULT_CDP_PORT = 9222;

function resolveUserDataDir(): string {
  return path.join(os.homedir(), ".ae", "browser", "default", "user-data");
}

function cdpHttpUrl(port: number): string {
  return `http://127.0.0.1:${port}`;
}

async function isCdpReachable(
  cdpUrl: string,
  timeoutMs = 500,
): Promise<boolean> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${cdpUrl}/json/version`, {
      signal: ctrl.signal,
    });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

async function waitForCdp(
  cdpUrl: string,
  deadlineMs: number,
): Promise<boolean> {
  while (Date.now() < deadlineMs) {
    if (await isCdpReachable(cdpUrl, 500)) return true;
    await new Promise((r) => setTimeout(r, 200));
  }
  return isCdpReachable(cdpUrl, 500);
}

function buildArgs(
  cdpPort: number,
  userDataDir: string,
  opts: LaunchOptions,
): string[] {
  const args: string[] = [
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-features=Translate,MediaRouter",
    "--disable-session-crashed-bubble",
    "--hide-crash-restore-bubble",
    "--password-store=basic",
    // Stealth: suppress navigator.webdriver flag
    "--disable-blink-features=AutomationControlled",
  ];
  if (opts.headless) {
    args.push("--headless=new", "--disable-gpu");
  }
  if (opts.noSandbox) {
    args.push("--no-sandbox", "--disable-setuid-sandbox");
  }
  if (process.platform === "linux") {
    args.push("--disable-dev-shm-usage");
  }
  if (opts.extraArgs && opts.extraArgs.length > 0) {
    args.push(...opts.extraArgs);
  }
  args.push("about:blank");
  return args;
}

function spawnBrowser(
  execPath: string,
  args: string[],
): ChildProcessWithoutNullStreams {
  return spawn(execPath, args, {
    stdio: "pipe",
    env: { ...process.env, HOME: os.homedir() },
  });
}

export async function launchBrowser(
  opts: LaunchOptions = {},
): Promise<RunningBrowser> {
  const cdpPort = opts.cdpPort ?? DEFAULT_CDP_PORT;
  const exe = resolveBrowserExecutable({ executablePath: opts.executablePath });
  if (!exe) {
    throw new Error(
      "No supported browser found (Chrome/Brave/Edge/Chromium).",
    );
  }
  const userDataDir = resolveUserDataDir();
  fs.mkdirSync(userDataDir, { recursive: true });

  const args = buildArgs(cdpPort, userDataDir, opts);
  const proc = spawnBrowser(exe.path, args);

  const cdpUrl = cdpHttpUrl(cdpPort);
  const deadline = Date.now() + 15_000;
  const ready = await waitForCdp(cdpUrl, deadline);

  if (!ready) {
    try {
      proc.kill("SIGKILL");
    } catch {
      // ignore
    }
    throw new Error(
      `Chrome CDP did not become reachable on port ${cdpPort} within 15s.`,
    );
  }

  return {
    pid: proc.pid ?? -1,
    cdpPort,
    cdpUrl,
    proc,
  };
}

export async function stopBrowser(
  running: RunningBrowser,
  timeoutMs = 2500,
): Promise<void> {
  const { proc } = running;
  if (proc.killed) return;
  try {
    proc.kill("SIGTERM");
  } catch {
    // ignore
  }
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (proc.exitCode != null || proc.killed) return;
    const alive = await isCdpReachable(running.cdpUrl, 200);
    if (!alive) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  try {
    proc.kill("SIGKILL");
  } catch {
    // ignore
  }
}
