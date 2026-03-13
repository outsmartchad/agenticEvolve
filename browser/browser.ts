import type { Page } from "playwright-core";
import type { LaunchOptions, RunningBrowser } from "./browser-launch.js";
import { launchBrowser, stopBrowser } from "./browser-launch.js";
import type {
  BrowserConsoleMessage,
  BrowserPageError,
} from "./pw-session.js";
import {
  connectBrowser,
  disconnectBrowser,
  getPageConsole,
  getPageErrors,
} from "./pw-session.js";

export type {
  BrowserExecutable,
} from "./browser-executables.js";
export type { RunningBrowser, LaunchOptions } from "./browser-launch.js";
export type {
  BrowserConsoleMessage,
  BrowserPageError,
  BrowserNetworkRequest,
} from "./pw-session.js";

export type WaitForOptions =
  | { text: string; timeout?: number }
  | { selector: string; timeout?: number }
  | { url: string | RegExp; timeout?: number }
  | { timeout: number };

export type TypeOptions = {
  slowly?: boolean;
  submit?: boolean;
};

export type SnapshotOptions = {
  fullPage?: boolean;
};

// Resolves a selector string to Playwright-compatible locator string.
// Supports: CSS selectors, `text=...`, `role=...`
function resolveLocator(page: Page, selector: string): ReturnType<Page["locator"]> {
  if (selector.startsWith("text=")) {
    return page.getByText(selector.slice("text=".length));
  }
  if (selector.startsWith("role=")) {
    const rest = selector.slice("role=".length);
    const [rolePart, namePart] = rest.split(/\s*\[name="([^"]+)"\]/, 2) as [string, string?];
    const role = rolePart.trim() as Parameters<Page["getByRole"]>[0];
    return namePart
      ? page.getByRole(role, { name: namePart })
      : page.getByRole(role);
  }
  return page.locator(selector);
}

export class Browser {
  private running: RunningBrowser | null = null;
  private page: Page | null = null;
  private cdpUrl: string | null = null;

  async launch(opts: LaunchOptions = {}): Promise<void> {
    this.running = await launchBrowser(opts);
    this.cdpUrl = this.running.cdpUrl;
    const session = await connectBrowser(this.cdpUrl);
    this.page = session.page;
  }

  async attachTo(cdpUrl: string): Promise<void> {
    this.cdpUrl = cdpUrl;
    const session = await connectBrowser(cdpUrl);
    this.page = session.page;
  }

  private getPage(): Page {
    if (!this.page) {
      throw new Error(
        "Browser not started. Call launch() or attachTo() first.",
      );
    }
    return this.page;
  }

  async navigate(url: string): Promise<void> {
    await this.getPage().goto(url, { waitUntil: "domcontentloaded" });
  }

  async snapshot(): Promise<string> {
    const page = this.getPage();
    // Use aria snapshot for structured accessibility tree representation
    return page.locator("body").ariaSnapshot();
  }

  async click(selector: string): Promise<void> {
    const page = this.getPage();
    await resolveLocator(page, selector).click();
  }

  async type(
    selector: string,
    text: string,
    opts: TypeOptions = {},
  ): Promise<void> {
    const page = this.getPage();
    const locator = resolveLocator(page, selector);
    if (opts.slowly) {
      await locator.pressSequentially(text, { delay: 80 });
    } else {
      await locator.fill(text);
    }
    if (opts.submit) {
      await locator.press("Enter");
    }
  }

  async screenshot(opts: SnapshotOptions = {}): Promise<Buffer> {
    const result = await this.getPage().screenshot({
      fullPage: opts.fullPage ?? false,
    });
    return result;
  }

  async evaluate(fn: string): Promise<unknown> {
    return this.getPage().evaluate(fn);
  }

  async pressKey(key: string): Promise<void> {
    await this.getPage().keyboard.press(key);
  }

  async hover(selector: string): Promise<void> {
    const page = this.getPage();
    await resolveLocator(page, selector).hover();
  }

  async waitFor(opts: WaitForOptions): Promise<void> {
    const page = this.getPage();
    if ("text" in opts) {
      const timeout = opts.timeout ?? 30_000;
      await page.getByText(opts.text).waitFor({ timeout });
      return;
    }
    if ("selector" in opts) {
      const timeout = opts.timeout ?? 30_000;
      await page.locator(opts.selector).waitFor({ timeout });
      return;
    }
    if ("url" in opts) {
      const timeout = opts.timeout ?? 30_000;
      await page.waitForURL(opts.url, { timeout });
      return;
    }
    // Plain timeout
    await page.waitForTimeout(opts.timeout);
  }

  async scrollIntoView(selector: string): Promise<void> {
    const page = this.getPage();
    await resolveLocator(page, selector).scrollIntoViewIfNeeded();
  }

  async selectOption(selector: string, values: string | string[]): Promise<void> {
    const page = this.getPage();
    const normalized = Array.isArray(values) ? values : [values];
    await resolveLocator(page, selector).selectOption(normalized);
  }

  getConsole(): BrowserConsoleMessage[] {
    if (!this.page) return [];
    return getPageConsole(this.page);
  }

  getErrors(): BrowserPageError[] {
    if (!this.page) return [];
    return getPageErrors(this.page);
  }

  async close(): Promise<void> {
    await disconnectBrowser();
    this.page = null;
    if (this.running) {
      await stopBrowser(this.running);
      this.running = null;
    }
    this.cdpUrl = null;
  }
}

// Convenience factory
export function createBrowser(): Browser {
  return new Browser();
}

// Re-export low-level primitives for advanced use
export {
  launchBrowser,
  stopBrowser,
  connectBrowser,
  disconnectBrowser,
  getPageConsole,
  getPageErrors,
};
