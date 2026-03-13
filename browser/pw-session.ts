import type {
  Browser,
  ConsoleMessage,
  Page,
  Request,
  Response,
} from "playwright-core";
import { chromium } from "playwright-core";

export type BrowserConsoleMessage = {
  type: string;
  text: string;
  timestamp: string;
  location?: { url?: string; lineNumber?: number; columnNumber?: number };
};

export type BrowserPageError = {
  message: string;
  name?: string;
  stack?: string;
  timestamp: string;
};

export type BrowserNetworkRequest = {
  id: string;
  timestamp: string;
  method: string;
  url: string;
  resourceType?: string;
  status?: number;
  ok?: boolean;
  failureText?: string;
};

type PageState = {
  console: BrowserConsoleMessage[];
  errors: BrowserPageError[];
  requests: BrowserNetworkRequest[];
  requestIds: WeakMap<Request, string>;
  nextRequestId: number;
};

type ConnectedSession = {
  browser: Browser;
  cdpUrl: string;
};

const pageStates = new WeakMap<Page, PageState>();
const observedPages = new WeakSet<Page>();

let cached: ConnectedSession | null = null;

function normalizeCdpUrl(raw: string): string {
  return raw.replace(/\/$/, "");
}

function findNetworkRequestById(
  state: PageState,
  id: string,
): BrowserNetworkRequest | undefined {
  for (let i = state.requests.length - 1; i >= 0; i -= 1) {
    const candidate = state.requests[i];
    if (candidate && candidate.id === id) return candidate;
  }
  return undefined;
}

function ensurePageState(page: Page): PageState {
  const existing = pageStates.get(page);
  if (existing) return existing;

  const state: PageState = {
    console: [],
    errors: [],
    requests: [],
    requestIds: new WeakMap(),
    nextRequestId: 0,
  };
  pageStates.set(page, state);

  if (!observedPages.has(page)) {
    observedPages.add(page);
    page.on("console", (msg: ConsoleMessage) => {
      state.console.push({
        type: msg.type(),
        text: msg.text(),
        timestamp: new Date().toISOString(),
        location: msg.location(),
      });
      if (state.console.length > 500) state.console.shift();
    });
    page.on("pageerror", (err: Error) => {
      state.errors.push({
        message: err?.message ? String(err.message) : String(err),
        name: err?.name ? String(err.name) : undefined,
        stack: err?.stack ? String(err.stack) : undefined,
        timestamp: new Date().toISOString(),
      });
      if (state.errors.length > 200) state.errors.shift();
    });
    page.on("request", (req: Request) => {
      state.nextRequestId += 1;
      const id = `r${state.nextRequestId}`;
      state.requestIds.set(req, id);
      state.requests.push({
        id,
        timestamp: new Date().toISOString(),
        method: req.method(),
        url: req.url(),
        resourceType: req.resourceType(),
      });
      if (state.requests.length > 500) state.requests.shift();
    });
    page.on("response", (resp: Response) => {
      const req = resp.request();
      const id = state.requestIds.get(req);
      if (!id) return;
      const rec = findNetworkRequestById(state, id);
      if (!rec) return;
      rec.status = resp.status();
      rec.ok = resp.ok();
    });
    page.on("requestfailed", (req: Request) => {
      const id = state.requestIds.get(req);
      if (!id) return;
      const rec = findNetworkRequestById(state, id);
      if (!rec) return;
      rec.failureText = req.failure()?.errorText;
      rec.ok = false;
    });
    page.on("close", () => {
      pageStates.delete(page);
      observedPages.delete(page);
    });
  }
  return state;
}

async function resolveWsEndpoint(cdpUrl: string): Promise<string> {
  try {
    const res = await fetch(`${cdpUrl}/json/version`, { signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      const data = (await res.json()) as { webSocketDebuggerUrl?: string };
      if (typeof data.webSocketDebuggerUrl === "string") {
        return data.webSocketDebuggerUrl;
      }
    }
  } catch {
    // fall through to cdpUrl
  }
  return cdpUrl;
}

export async function connectBrowser(
  cdpUrl: string,
): Promise<{ browser: Browser; page: Page }> {
  const normalized = normalizeCdpUrl(cdpUrl);
  if (cached?.cdpUrl !== normalized) {
    const endpoint = await resolveWsEndpoint(normalized);
    let lastErr: unknown;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const browser = await chromium.connectOverCDP(endpoint, {
          timeout: 5000 + attempt * 2000,
        });
        browser.on("disconnected", () => {
          if (cached?.browser === browser) cached = null;
        });
        for (const ctx of browser.contexts()) {
          for (const p of ctx.pages()) ensurePageState(p);
          ctx.on("page", (p) => ensurePageState(p));
        }
        cached = { browser, cdpUrl: normalized };
        break;
      } catch (err) {
        lastErr = err;
        await new Promise((r) => setTimeout(r, 300 + attempt * 200));
      }
    }
    if (!cached) {
      throw lastErr instanceof Error
        ? lastErr
        : new Error("Failed to connect to browser via CDP");
    }
  }
  const { browser } = cached!;
  const pages = browser.contexts().flatMap((c) => c.pages());
  const page = pages[0] ?? (await browser.contexts()[0]!.newPage());
  ensurePageState(page);
  return { browser, page };
}

export async function getPage(
  cdpUrl: string,
  targetId?: string,
): Promise<Page> {
  const { browser } = await connectBrowser(cdpUrl);
  const pages = browser.contexts().flatMap((c) => c.pages());
  if (!pages.length) throw new Error("No pages available in browser");
  if (!targetId) return pages[0]!;
  // Try to match by CDP targetId
  for (const p of pages) {
    try {
      const session = await p.context().newCDPSession(p);
      const info = (await session.send("Target.getTargetInfo")) as {
        targetInfo?: { targetId?: string };
      };
      const tid = String(info?.targetInfo?.targetId ?? "").trim();
      await session.detach().catch(() => {});
      if (tid === targetId) return p;
    } catch {
      // ignore
    }
  }
  return pages[0]!;
}

export async function disconnectBrowser(): Promise<void> {
  const cur = cached;
  cached = null;
  if (!cur) return;
  await cur.browser.close().catch(() => {});
}

export function getPageConsole(page: Page): BrowserConsoleMessage[] {
  return pageStates.get(page)?.console ?? [];
}

export function getPageErrors(page: Page): BrowserPageError[] {
  return pageStates.get(page)?.errors ?? [];
}

export function getPageRequests(page: Page): BrowserNetworkRequest[] {
  return pageStates.get(page)?.requests ?? [];
}
