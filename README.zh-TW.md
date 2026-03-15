# agenticEvolve

**一個每天自動進化你開發能力的個人閉環智能體系統。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-26-orange?style=for-the-badge" alt="26 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-35-blue?style=for-the-badge" alt="35 Commands"></a>
</p>

---

基於 `claude -p` 建構的持久化智能體執行環境，搭配 Python asyncio 閘道。6 層記憶體系 + 跨層自動召回。閉環技能合成。語音輸入輸出。瀏覽器自動化。內建排程任務。雙層安全機制。透過 Telegram 操控——你的整個開發環境裝進口袋。

---

## 你能用它做什麼？

**替你瀏覽網頁**
> 「去 Anthropic 文件找最新的 Claude 模型定價。」代理開啟 ABP 瀏覽器，導覽，提取資料，傳送簡潔摘要。如果 Cloudflare 攔截，自動切換到 Brave。

**搜尋你自己的微信聊天記錄**
> 微信自帶的搜尋太爛了。代理讀取你本地的微信資料庫，給你一個可搜尋的匯出——聯絡人、訊息、群組、收藏。全部離線，全在你自己的機器上。

**在睡夢中從群組聊天中吸收想法**
> 你的 `/evolve` 排程任務在早上 6 點不只是掃描 GitHub。它還會讀取你的微信技術群聊天記錄，總結過去 24 小時的討論——別人提到的新工具、分享的儲存庫、討論的技術方案——並將最好的想法吸收為技能。你醒來時，群組的集體智慧已經融入你的系統。

**從趨勢訊號中腦力激盪商業點子**
> `/produce` — 代理彙整今天來自 11 個來源的訊號（GitHub Trending、Hacker News、X/Twitter、Reddit、Product Hunt、Lobste.rs、ArXiv、HuggingFace、BestOfJS、微信群組和你 star 的儲存庫），辨識新興趨勢，並腦力激盪 5 個具體的應用/商業點子，包含營收模式、技術棧和 MVP 範圍。按需進行訊號驅動的創意發想。

**自我改進的使用者體驗**
> 每天凌晨 1 點，代理讀取當天的對話，找出你等待太久或收到困惑回覆的摩擦點，然後直接修補自己的程式碼來修復它們。你醒來後面對的是一個更好的代理。

**在手機上寫程式碼**
> 你在地鐵上，發一條訊息 `/do 給 API 加上限流`。代理讀取你的程式碼庫，編寫中介層，跑測試，推送到 git。你到站之前就收到總結。

**一條訊息吸收任何儲存庫**
> 你在 Twitter 上看到一個很酷的儲存庫，截圖發給機器人。代理 OCR 辨識圖片，找到 GitHub 連結，複製儲存庫，映射架構，提取對你技術棧有用的模式，安裝為技能——一張圖搞定。

**一覺醒來多了你沒寫過的新技能**
> 每天早上 6 點 `/evolve` 排程任務自動觸發。等你打開 Telegram，代理已經掃描了 GitHub Trending，發現了一個新測試框架，為它建構了技能，通過雙層安全審查，自動安裝並推送到你的儲存庫。你一夜之間變強了。

**用任何語言和你的程式碼庫對話**
> 用英語、粵語、國語、日語、韓語或 40+ 種支援語言傳送語音訊息。代理透過本地 whisper.cpp 轉寫（~500ms），自動偵測語言，以文字回覆，並透過 edge-tts 用相同語言朗讀給你。

**用 `/learn` 深入研究任何東西**
> `/learn https://github.com/some/repo` — 代理複製儲存庫，讀取每個檔案，映射架構，評估它如何有益於你的工作流程，給出 ADOPT / ADAPT / SKIP 判定，並可選地從中建構技能。

---

## 核心能力

| 能力 | 描述 |
|------|------|
| **建構** | 透過 Telegram 使用完整的 Claude Code——終端機、檔案讀寫、網路搜尋、MCP、26 個技能 |
| **進化** | 5 階段流水線：收集 → 分析 → 建構 → 審查 → 自動安裝。掃描 11 個來源：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + 微信群組，合成技能 |
| **吸收** | `/absorb <url>` — 複製儲存庫，映射架構，比對模式，將改進融入你的系統 |
| **學習** | `/learn <target>` — 深度提取，給出 ADOPT / ADAPT / SKIP 判定 |
| **語音** | 傳送語音訊息 → 本地 whisper.cpp 轉寫（~500ms）。`/speak` → edge-tts，300+ 種語音。自動偵測粵語/國語/日語/韓語 |
| **瀏覽器** | ABP（Agent Browser Protocol）作為預設瀏覽器。遇到 Cloudflare 攔截時自動切換到 Brave/Chrome（CDP）。隔離的代理設定檔 |
| **自動召回** | 每次回覆前對 6 層記憶執行 `unified_search()`（約 400 tokens/則訊息） |
| **排程任務** | `/loop every 6h /evolve` — 按計劃自主成長 |
| **安全** | L1：預安裝正規表示式掃描（反向 shell、憑證竊取、挖礦程式）。L2：AgentShield 安裝後掃描（1282 項測試，102 條規則）。發現嚴重問題自動復原 |
| **鉤子** | 型別化非同步事件系統 — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **韌性** | 關機排空（等待進行中的請求最多 30 秒）。型別化故障分類（驗證/計費/限流）。3 遍上下文壓縮。熱設定重載。迴圈偵測（3 次相同輪次警告，5 次終止）。記憶佇列讀透（去抖動原子寫入，無陳舊讀取）。並行建構階段（ThreadPoolExecutor，3 個隔離工作區） |

---

## 安裝

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
brew install whisper-cpp ffmpeg  # 語音支援
```

```bash
# ~/.agenticEvolve/.env
TELEGRAM_BOT_TOKEN=<token>
```

```yaml
# ~/.agenticEvolve/config.yaml
platforms:
  telegram:
    allowed_users: [<user-id>]
```

```bash
cd ~/.agenticEvolve && python3 -m gateway.run
```

---

## 指令

| 指令 | 功能 |
|------|------|
| _(任意訊息)_ | 與 Claude Code 對話 |
| _(語音訊息)_ | 自動轉寫（whisper.cpp）+ 回覆（語音模式下附帶語音） |
| _(傳送圖片)_ | 視覺分析——截圖辨識、圖表理解、OCR、UI 檢查 |
| _(傳送檔案)_ | 檔案分析——PDF、程式碼檔案、文字檔案 |
| `/evolve` | 掃描訊號，建構並自動安裝技能 |
| `/absorb <url>` | 從任意儲存庫吸收模式 |
| `/learn <target>` | 深度分析並給出判定 |
| `/speak <text>` | 文字轉語音（自動偵測語言） |
| `/recall <query>` | 跨層搜尋（全部 6 層記憶） |
| `/search <query>` | FTS5 搜尋歷史工作階段 |
| `/do <instruction>` | 自然語言 → 結構化指令 |
| `/loop <cron> <cmd>` | 排程定期執行 |
| `/memory` | 檢視代理記憶狀態 |
| `/skills` | 列出已安裝技能（26 個） |
| `/cost` | 使用量與開銷 |
| `/wechat [--hours N]` | 微信群組聊天摘要（簡體中文） |
| `/produce [--ideas N]` | 從所有訊號中腦力激盪商業點子 |
| `/digest` | 每日早間簡報 |
| `/restart` | 遠端重啟閘道 |

[全部 35 個指令 →](docs/commands.md)

---

## 架構

```
使用者 (Telegram/語音) → 閘道 (asyncio) → 鉤子分發器 → 工作階段 + 費用控制
  → 自動召回 (6 層) → claude -p → SQLite → Git 同步
```

沒有自訂代理迴圈。Claude Code **就是**執行環境——25+ 內建工具、MCP 伺服器、技能。閘道在其周圍加上了記憶、路由、召回、排程任務、語音、瀏覽器和安全層。

### 關鍵設計決策
- **不造工具系統** — Claude Code 自帶工具。我們建構技能和基礎設施，而非抽象層。
- **有界記憶** — MEMORY.md（2200 字元）+ USER.md（1375 字元）+ SQLite FTS5。無無限增長。
- **閉環** — `auto_approve_skills: true`。進化 → 建構 → 審查 → 安裝 → 同步到 git。無人工審批。
- **關機排空** — 進行中的請求在重啟前完成。不遺失工作。

---

## 語音流水線

| 方向 | 技術 | 延遲 | 費用 |
|------|------|------|------|
| **語音 → 文字** | 本地 whisper.cpp（ggml-small 多語言模型） | Apple Silicon 上約 500ms | 免費 |
| **文字 → 語音** | edge-tts（300+ 神經網路語音） | 約 1 秒 | 免費 |
| **語言偵測** | CJK 啟發式（嘅係唔 → 粵語，ひらがな → 日語） | 即時 | 免費 |

自動 TTS 模式：`off`（僅 `/speak`），`always`（每則回覆），`inbound`（使用者傳語音時以語音回覆）。

---

## 瀏覽器自動化

| 瀏覽器 | 使用場景 | 方式 |
|--------|----------|------|
| **ABP**（預設） | 所有代理瀏覽 | 內建 Chromium，操作間 JS 凍結，Mind2Web 90.5% |
| **Brave** | 使用者要求 / Cloudflare 攔截 ABP | CDP 連接埠 9222，隔離設定檔 |
| **Chrome** | 使用者要求 / Cloudflare 攔截 ABP | CDP 連接埠 9223，隔離設定檔 |

代理設定檔沙箱化在 `~/.agenticEvolve/browser-profiles/` — 絕不觸碰使用者真實瀏覽器資料。

---

## 安全

| 層級 | 工具 | 時機 | 嚴重問題處理 |
|------|------|------|-------------|
| **L1** | `gateway/security.py` | 預安裝：掃描原始檔案 | 阻擋 + 中止流水線 |
| **L2** | AgentShield（1282 項測試） | 安裝後：掃描 `~/.claude/` 設定 | 自動復原已安裝技能 |

掃描內容：憑證洩露、反向 shell、混淆酬載、加密貨幣挖礦、macOS 持久化、提示注入、npm 鉤子利用。

---

## 排程任務

4 個自治任務每天自動執行——無需人工觸發。

| 任務 | 時間（HKT） | 功能 |
|------|------------|------|
| **evolve-daily** | 6:00 AM | 收集 11 個來源的訊號：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + 微信群組，評分候選項，建構最多 3 個新技能，安全審查，自動安裝，推送到 git |
| **daily-digest** | 8:00 AM | 每日簡報——熱門訊號、已建構技能、工作階段數、費用摘要。推送到 Telegram |
| **wechat-digest** | 9:00 AM | 每日微信群組聊天摘要——總結討論內容、提到的工具、技術群的關鍵洞察。推送到 Telegram |
| **daily-ux-review** | 1:00 AM | 讀取當天對話，發現摩擦點，識別 Top 3 體驗改進，直接實施修改 |

透過 `/loop`、`/loops`、`/unloop`、`/pause`、`/unpause` 管理。設定檔：`cron/jobs.json`。

---

## 訊號來源（11 個）

| 來源 | 採集器 | API | 採集內容 |
|------|--------|-----|----------|
| GitHub Search | `github.sh` | GitHub API (gh CLI) | 按關鍵字搜尋趨勢儲存庫、star 儲存庫動態、發佈監控 |
| GitHub Trending | `github-trending.py` | GitHub API (gh CLI) | 最近 7 天建立的熱門新儲存庫 |
| Hacker News | `hackernews.sh` | Algolia API | 關鍵字搜尋 + 首頁 + Show HN |
| X / Twitter | `x-search.sh` | Brave Search API | 關於開源、開發工具、AI 的熱門推文 |
| Reddit | `reddit.py` | Pullpush.io API | 13 個子版塊：LocalLLaMA、programming、ClaudeAI 等 |
| Product Hunt | `producthunt.py` | RSS/Atom feed | 開發工具 + AI 產品發佈 |
| Lobste.rs | `lobsters.py` | JSON API | 精選技術新聞（高訊噪比） |
| ArXiv | `arxiv.py` | ArXiv API | cs.AI、cs.CL、cs.SE、cs.LG 論文 |
| HuggingFace | `huggingface.py` | HF API | 趨勢模型和 Spaces |
| BestOfJS | `bestofjs.py` | Static JSON API | 按每日 star 增長排名的 JavaScript/TypeScript 專案 |
| WeChat | `wechat.py` | Local DB | 群組聊天訊息（讀取本地資料） |

---

## 技能（已安裝 26 個）

| 技能 | 用途 |
|------|------|
| agent-browser-protocol | 透過 MCP 的 ABP 瀏覽器自動化 |
| browser-switch | 多瀏覽器 CDP 切換（Brave/Chrome） |
| brave-search | 透過 Brave API 網路搜尋 |
| firecrawl | 網頁抓取、爬取、搜尋、結構化提取 |
| cloudflare-crawl | 免費網頁爬取（Cloudflare Browser Rendering API） |
| jshook-messenger | 透過 jshookmcp MCP 攔截 Discord/微信/Telegram/Slack |
| wechat-decrypt | 讀取本地微信資料庫，匯出訊息、聯絡人、群組（macOS） |
| session-search | FTS5 工作階段歷史搜尋 |
| cron-manager | 排程任務管理 |
| skill-creator | 官方 Anthropic 技能建立 |
| deep-research | 多源研究流水線 |
| market-research | 市場/競品分析 |
| article-writing | 長文內容創作 |
| video-editing | FFmpeg 影片編輯指南 |
| security-review | 程式碼安全檢查清單 |
| security-scan | AgentShield 設定掃描器 |
| autonomous-loops | 自主導向的代理迴圈 |
| continuous-learning-v2 | 模式提取流水線 |
| eval-harness | 技能評估框架 |
| claude-agent-sdk-v0.2.74 | Claude Agent SDK 模式 |
| nah | 快速拒絕/復原 |
| unf | 展開/擴展壓縮內容 |
| next-ai-draw-io | 從自然語言生成架構圖 |
| mcp-elicitation | 攔截任務中 MCP 對話框，實現無人值守流水線 |
| skill-gap-scan | 對比本地技能與社群目錄，發現採用缺口 |
| context-optimizer | 基於 `/context` 提示自動歸檔陳舊記憶檔案 |

---

## 文件

| 文件 | 描述 |
|------|------|
| [互動](docs/interface.md) | 使用範例和互動模式 |
| [記憶](docs/memory.md) | 6 層記憶架構、自動召回、直覺評分 |
| [指令](docs/commands.md) | 全部 35 個指令及參數和範例 |
| [流水線](docs/pipelines.md) | Evolve、Absorb、Learn、Do、GC 流水線 |
| [技能](docs/skills.md) | 完整技能目錄 |
| [安全](docs/security.md) | 掃描器、自治等級、安全閘門 |
| [架構](docs/architecture.md) | 訊息流、專案結構、設計決策 |
| [路線圖](docs/roadmap.md) | 整合計劃 — Firecrawl、視覺、沙箱 |

---

## 血脈

| 專案 | 採納的模式 |
|------|-----------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | 代理執行環境 — 25+ 工具、MCP、技能、子代理 |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 有界記憶、工作階段持久化、訊息閘道、漸進式狀態訊息 |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | 自治等級、預設拒絕、熱設定重載、風險分級分類 |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 9 個技能改編，AgentShield 安全，評估驅動開發，鉤子設定 |
| [openclaw](https://github.com/openclaw/openclaw) | 語音流水線（TTS/STT），瀏覽器自動化模式，自動 TTS 模式 |
| [ABP](https://github.com/theredsix/agent-browser-protocol) | 瀏覽器 MCP — 操作間凍結的 Chromium，Mind2Web 90.5% |
| [deer-flow](https://github.com/bytedance/deer-flow) | 並行子代理建構階段、每候選隔離工作區、迴圈偵測、記憶佇列去抖動寫入 |

---

MIT
