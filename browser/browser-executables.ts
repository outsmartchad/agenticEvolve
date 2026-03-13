import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export type BrowserExecutable = {
  kind: "brave" | "canary" | "chromium" | "chrome" | "custom" | "edge";
  path: string;
};

const CHROMIUM_BUNDLE_IDS = new Set([
  "com.google.Chrome",
  "com.google.Chrome.beta",
  "com.google.Chrome.canary",
  "com.google.Chrome.dev",
  "com.brave.Browser",
  "com.brave.Browser.beta",
  "com.brave.Browser.nightly",
  "com.microsoft.Edge",
  "com.microsoft.EdgeBeta",
  "com.microsoft.EdgeDev",
  "com.microsoft.EdgeCanary",
  "org.chromium.Chromium",
  "com.vivaldi.Vivaldi",
  "com.operasoftware.Opera",
  "company.thebrowser.Browser",
]);

const CHROMIUM_DESKTOP_IDS = new Set([
  "google-chrome.desktop",
  "google-chrome-beta.desktop",
  "google-chrome-unstable.desktop",
  "brave-browser.desktop",
  "microsoft-edge.desktop",
  "microsoft-edge-beta.desktop",
  "microsoft-edge-dev.desktop",
  "chromium.desktop",
  "chromium-browser.desktop",
  "vivaldi.desktop",
  "vivaldi-stable.desktop",
  "opera.desktop",
  "org.chromium.Chromium.desktop",
]);

const CHROMIUM_EXE_NAMES = new Set([
  "chrome.exe",
  "msedge.exe",
  "brave.exe",
  "brave-browser.exe",
  "chromium.exe",
  "vivaldi.exe",
  "opera.exe",
  "google chrome",
  "google chrome canary",
  "brave browser",
  "microsoft edge",
  "chromium",
  "chrome",
  "brave",
  "msedge",
  "brave-browser",
  "google-chrome",
  "google-chrome-stable",
  "google-chrome-beta",
  "google-chrome-unstable",
  "microsoft-edge",
  "microsoft-edge-beta",
  "microsoft-edge-dev",
  "microsoft-edge-canary",
  "chromium-browser",
  "vivaldi",
  "vivaldi-stable",
  "opera",
]);

function fileExists(filePath: string): boolean {
  try {
    return fs.existsSync(filePath);
  } catch {
    return false;
  }
}

function execText(
  command: string,
  args: string[],
  timeoutMs = 1200,
  maxBuffer = 1024 * 1024,
): string | null {
  try {
    const output = execFileSync(command, args, {
      timeout: timeoutMs,
      encoding: "utf8",
      maxBuffer,
    });
    return String(output ?? "").trim() || null;
  } catch {
    return null;
  }
}

function inferKindFromIdentifier(
  identifier: string,
): BrowserExecutable["kind"] {
  const id = identifier.toLowerCase();
  if (id.includes("brave")) return "brave";
  if (id.includes("edge")) return "edge";
  if (id.includes("chromium")) return "chromium";
  if (id.includes("canary")) return "canary";
  if (
    id.includes("opera") ||
    id.includes("vivaldi") ||
    id.includes("thebrowser")
  ) {
    return "chromium";
  }
  return "chrome";
}

function inferKindFromExecutableName(
  name: string,
): BrowserExecutable["kind"] {
  const lower = name.toLowerCase();
  if (lower.includes("brave")) return "brave";
  if (lower.includes("edge") || lower.includes("msedge")) return "edge";
  if (lower.includes("chromium")) return "chromium";
  if (lower.includes("canary") || lower.includes("sxs")) return "canary";
  if (lower.includes("opera") || lower.includes("vivaldi")) return "chromium";
  return "chrome";
}

function detectDefaultBrowserBundleIdMac(): string | null {
  const plistPath = path.join(
    os.homedir(),
    "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist",
  );
  if (!fileExists(plistPath)) return null;
  const handlersRaw = execText(
    "/usr/bin/plutil",
    ["-extract", "LSHandlers", "json", "-o", "-", "--", plistPath],
    2000,
    5 * 1024 * 1024,
  );
  if (!handlersRaw) return null;
  let handlers: unknown;
  try {
    handlers = JSON.parse(handlersRaw);
  } catch {
    return null;
  }
  if (!Array.isArray(handlers)) return null;
  const resolveScheme = (scheme: string): string | null => {
    for (const entry of handlers as unknown[]) {
      if (!entry || typeof entry !== "object") continue;
      const record = entry as Record<string, unknown>;
      if (record["LSHandlerURLScheme"] !== scheme) continue;
      const role =
        (typeof record["LSHandlerRoleAll"] === "string" &&
          record["LSHandlerRoleAll"]) ||
        (typeof record["LSHandlerRoleViewer"] === "string" &&
          record["LSHandlerRoleViewer"]) ||
        null;
      if (role) return role;
    }
    return null;
  };
  return resolveScheme("http") ?? resolveScheme("https");
}

function detectDefaultChromiumExecutableMac(): BrowserExecutable | null {
  const bundleId = detectDefaultBrowserBundleIdMac();
  if (!bundleId || !CHROMIUM_BUNDLE_IDS.has(bundleId)) return null;
  const appPathRaw = execText("/usr/bin/osascript", [
    "-e",
    `POSIX path of (path to application id "${bundleId}")`,
  ]);
  if (!appPathRaw) return null;
  const appPath = appPathRaw.trim().replace(/\/$/, "");
  const exeName = execText("/usr/bin/defaults", [
    "read",
    path.join(appPath, "Contents", "Info"),
    "CFBundleExecutable",
  ]);
  if (!exeName) return null;
  const exePath = path.join(appPath, "Contents", "MacOS", exeName.trim());
  if (!fileExists(exePath)) return null;
  return { kind: inferKindFromIdentifier(bundleId), path: exePath };
}

function findDesktopFilePath(desktopId: string): string | null {
  const candidates = [
    path.join(os.homedir(), ".local", "share", "applications", desktopId),
    path.join("/usr/local/share/applications", desktopId),
    path.join("/usr/share/applications", desktopId),
    path.join("/var/lib/snapd/desktop/applications", desktopId),
  ];
  for (const candidate of candidates) {
    if (fileExists(candidate)) return candidate;
  }
  return null;
}

function readDesktopExecLine(desktopPath: string): string | null {
  try {
    const raw = fs.readFileSync(desktopPath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith("Exec=")) return line.slice("Exec=".length).trim();
    }
  } catch {
    // ignore
  }
  return null;
}

function splitExecLine(line: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let inQuotes = false;
  let quoteChar = "";
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i] as string;
    if ((ch === '"' || ch === "'") && (!inQuotes || ch === quoteChar)) {
      inQuotes = !inQuotes;
      quoteChar = inQuotes ? ch : "";
      continue;
    }
    if (!inQuotes && /\s/.test(ch)) {
      if (current) {
        tokens.push(current);
        current = "";
      }
      continue;
    }
    current += ch;
  }
  if (current) tokens.push(current);
  return tokens;
}

function extractExecutableFromExecLine(execLine: string): string | null {
  for (const token of splitExecLine(execLine)) {
    if (!token || token === "env") continue;
    if (token.includes("=") && !token.startsWith("/") && !token.includes("\\"))
      continue;
    return token.replace(/^["']|["']$/g, "");
  }
  return null;
}

function resolveLinuxExecutablePath(command: string): string | null {
  const cleaned = command.trim().replace(/%[a-zA-Z]/g, "");
  if (!cleaned) return null;
  if (cleaned.startsWith("/")) return cleaned;
  const resolved = execText("which", [cleaned], 800);
  return resolved ? resolved.trim() : null;
}

function detectDefaultChromiumExecutableLinux(): BrowserExecutable | null {
  const desktopId =
    execText("xdg-settings", ["get", "default-web-browser"]) ||
    execText("xdg-mime", ["query", "default", "x-scheme-handler/http"]);
  if (!desktopId) return null;
  const trimmed = desktopId.trim();
  if (!CHROMIUM_DESKTOP_IDS.has(trimmed)) return null;
  const desktopPath = findDesktopFilePath(trimmed);
  if (!desktopPath) return null;
  const execLine = readDesktopExecLine(desktopPath);
  if (!execLine) return null;
  const command = extractExecutableFromExecLine(execLine);
  if (!command) return null;
  const resolved = resolveLinuxExecutablePath(command);
  if (!resolved) return null;
  const exeName = path.posix.basename(resolved).toLowerCase();
  if (!CHROMIUM_EXE_NAMES.has(exeName)) return null;
  return { kind: inferKindFromExecutableName(exeName), path: resolved };
}

function readWindowsProgId(): string | null {
  const output = execText("reg", [
    "query",
    "HKCU\\Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\http\\UserChoice",
    "/v",
    "ProgId",
  ]);
  if (!output) return null;
  const match = output.match(/ProgId\s+REG_\w+\s+(.+)$/im);
  return match?.[1]?.trim() || null;
}

function readWindowsCommandForProgId(progId: string): string | null {
  const key =
    progId === "http"
      ? "HKCR\\http\\shell\\open\\command"
      : `HKCR\\${progId}\\shell\\open\\command`;
  const output = execText("reg", ["query", key, "/ve"]);
  if (!output) return null;
  const match = output.match(/REG_\w+\s+(.+)$/im);
  return match?.[1]?.trim() || null;
}

function expandWindowsEnvVars(value: string): string {
  return value.replace(/%([^%]+)%/g, (_match, name: string) => {
    const key = String(name ?? "").trim();
    return key ? (process.env[key] ?? `%${key}%`) : _match;
  });
}

function extractWindowsExecutablePath(command: string): string | null {
  const quoted = command.match(/"([^"]+\.exe)"/i);
  if (quoted?.[1]) return quoted[1];
  const unquoted = command.match(/([^\s]+\.exe)/i);
  return unquoted?.[1] ?? null;
}

function detectDefaultChromiumExecutableWindows(): BrowserExecutable | null {
  const progId = readWindowsProgId();
  const command =
    (progId ? readWindowsCommandForProgId(progId) : null) ||
    readWindowsCommandForProgId("http");
  if (!command) return null;
  const expanded = expandWindowsEnvVars(command);
  const exePath = extractWindowsExecutablePath(expanded);
  if (!exePath || !fileExists(exePath)) return null;
  const exeName = path.win32.basename(exePath).toLowerCase();
  if (!CHROMIUM_EXE_NAMES.has(exeName)) return null;
  return { kind: inferKindFromExecutableName(exeName), path: exePath };
}

function findFirstExecutable(
  candidates: BrowserExecutable[],
): BrowserExecutable | null {
  for (const candidate of candidates) {
    if (fileExists(candidate.path)) return candidate;
  }
  return null;
}

export function findChromeExecutableMac(): BrowserExecutable | null {
  const home = os.homedir();
  const candidates: BrowserExecutable[] = [
    {
      kind: "chrome",
      path: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    },
    {
      kind: "chrome",
      path: path.join(
        home,
        "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      ),
    },
    {
      kind: "brave",
      path: "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    },
    {
      kind: "brave",
      path: path.join(
        home,
        "Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
      ),
    },
    {
      kind: "edge",
      path: "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    },
    {
      kind: "edge",
      path: path.join(
        home,
        "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      ),
    },
    {
      kind: "chromium",
      path: "/Applications/Chromium.app/Contents/MacOS/Chromium",
    },
    {
      kind: "chromium",
      path: path.join(home, "Applications/Chromium.app/Contents/MacOS/Chromium"),
    },
    {
      kind: "canary",
      path: "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    },
  ];
  return findFirstExecutable(candidates);
}

export function findChromeExecutableLinux(): BrowserExecutable | null {
  const candidates: BrowserExecutable[] = [
    { kind: "chrome", path: "/usr/bin/google-chrome" },
    { kind: "chrome", path: "/usr/bin/google-chrome-stable" },
    { kind: "chrome", path: "/usr/bin/chrome" },
    { kind: "brave", path: "/usr/bin/brave-browser" },
    { kind: "brave", path: "/usr/bin/brave-browser-stable" },
    { kind: "brave", path: "/snap/bin/brave" },
    { kind: "edge", path: "/usr/bin/microsoft-edge" },
    { kind: "edge", path: "/usr/bin/microsoft-edge-stable" },
    { kind: "chromium", path: "/usr/bin/chromium" },
    { kind: "chromium", path: "/usr/bin/chromium-browser" },
    { kind: "chromium", path: "/snap/bin/chromium" },
  ];
  return findFirstExecutable(candidates);
}

export function findChromeExecutableWindows(): BrowserExecutable | null {
  const localAppData = process.env["LOCALAPPDATA"] ?? "";
  const programFiles = process.env["ProgramFiles"] ?? "C:\\Program Files";
  const programFilesX86 =
    process.env["ProgramFiles(x86)"] ?? "C:\\Program Files (x86)";
  const j = path.win32.join;
  const candidates: BrowserExecutable[] = [];
  if (localAppData) {
    candidates.push({
      kind: "chrome",
      path: j(localAppData, "Google", "Chrome", "Application", "chrome.exe"),
    });
    candidates.push({
      kind: "brave",
      path: j(
        localAppData,
        "BraveSoftware",
        "Brave-Browser",
        "Application",
        "brave.exe",
      ),
    });
    candidates.push({
      kind: "edge",
      path: j(localAppData, "Microsoft", "Edge", "Application", "msedge.exe"),
    });
    candidates.push({
      kind: "chromium",
      path: j(localAppData, "Chromium", "Application", "chrome.exe"),
    });
    candidates.push({
      kind: "canary",
      path: j(
        localAppData,
        "Google",
        "Chrome SxS",
        "Application",
        "chrome.exe",
      ),
    });
  }
  candidates.push({
    kind: "chrome",
    path: j(programFiles, "Google", "Chrome", "Application", "chrome.exe"),
  });
  candidates.push({
    kind: "chrome",
    path: j(programFilesX86, "Google", "Chrome", "Application", "chrome.exe"),
  });
  candidates.push({
    kind: "brave",
    path: j(
      programFiles,
      "BraveSoftware",
      "Brave-Browser",
      "Application",
      "brave.exe",
    ),
  });
  candidates.push({
    kind: "edge",
    path: j(programFiles, "Microsoft", "Edge", "Application", "msedge.exe"),
  });
  return findFirstExecutable(candidates);
}

export function resolveBrowserExecutable(opts?: {
  executablePath?: string;
}): BrowserExecutable | null {
  if (opts?.executablePath) {
    if (!fileExists(opts.executablePath)) {
      throw new Error(
        `executablePath not found: ${opts.executablePath}`,
      );
    }
    return { kind: "custom", path: opts.executablePath };
  }
  const platform = process.platform;
  // Try default browser first
  let detected: BrowserExecutable | null = null;
  if (platform === "darwin") detected = detectDefaultChromiumExecutableMac();
  else if (platform === "linux")
    detected = detectDefaultChromiumExecutableLinux();
  else if (platform === "win32")
    detected = detectDefaultChromiumExecutableWindows();
  if (detected) return detected;
  // Fall back to known install paths
  if (platform === "darwin") return findChromeExecutableMac();
  if (platform === "linux") return findChromeExecutableLinux();
  if (platform === "win32") return findChromeExecutableWindows();
  return null;
}
