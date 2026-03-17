# agenticEvolve

**一個自我進化的 AI 智能體 —— 每天自動成長。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-33-orange?style=for-the-badge" alt="33 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-44-blue?style=for-the-badge" alt="44 Commands"></a>
</p>

**[English](README.md)** | **[简体中文](README.zh.md)** | **[日本語](README.ja.md)**

---

基於 `claude -p` 建構的持久化智能體執行環境，搭配 Python asyncio 閘道。6 層記憶體系 + 跨層自動召回。閉環技能合成。語音輸入輸出。瀏覽器自動化。內建排程任務。雙層安全機制。多平台（Telegram + Discord + WhatsApp）。互動式 CLI REPL 搭配 Rich TUI。39 個 Telegram 指令 + 32 個 CLI 指令——你的整個開發環境裝進口袋。

---

## 你能用它做什麼？

**替你瀏覽網頁**
> 「去 Anthropic 文件找最新的 Claude 模型定價。」智能體開啟 ABP 瀏覽器，導覽頁面，提取資料，傳送一份簡潔摘要。如果 Cloudflare 攔截，自動切換到 Brave。

**在你的 WhatsApp 和 Discord 群組中服務**
> `/serve` → WhatsApp → 群組 → 開啟你的開發群。現在群組裡任何人都能和你的 AI 智能體對話。它回覆每則訊息，維護每個群組的對話記憶，你透過 Telegram 內聯鍵盤控制一切。Discord 頻道同樣支援——智能體透過 Chrome DevTools Protocol 接入你的桌面應用程式。

**訂閱頻道並取得摘要**
> `/subscribe` → Discord → 選擇你常看的頻道。隔天早上執行 `/discord`，就能取得一份簡潔的摘要——關鍵討論、分享的連結、提到的工具、待辦事項。支援 Discord 頻道、WhatsApp 群組和微信群。再也不用翻 500 則未讀訊息了。

**搜尋你自己的微信聊天記錄**
> 微信內建的搜尋太爛了。智能體讀取你本地的微信資料庫，給你一個可搜尋的匯出——聯絡人、訊息、群組、收藏。全部離線，全在你自己的機器上。

**在睡夢中從群組聊天吸收想法**
> 你的 `/evolve` 排程任務在早上 6 點不只是掃描 GitHub。它還會讀取你的微信技術群聊天記錄，總結過去 24 小時的討論——別人提到的新工具、分享的儲存庫、討論的技術方案——並將最好的想法吸收為技能。你醒來時，群組的集體智慧已經融入你的系統。

**從趨勢訊號中腦力激盪商業點子**
> `/produce` — 智能體彙整今天來自 11 個來源的訊號（GitHub Trending、Hacker News、X/Twitter、Reddit、Product Hunt、Lobste.rs、ArXiv、HuggingFace、BestOfJS、微信群組和你 star 的儲存庫），辨識新興趨勢，並腦力激盪 5 個具體的應用/商業點子，包含營收模式、技術棧和 MVP 範圍。按需進行訊號驅動的創意發想。

**自我改進的使用者體驗**
> 每天凌晨 1 點，智能體讀取當天的對話，找出你等待太久或收到令人困惑回覆的摩擦點，然後直接修補自己的程式碼來修復它們。你醒來後面對的是一個更好的智能體。

**在手機上寫程式**
> 你在地鐵上，發一條訊息 `/do 給 API 加上限流`。智能體讀取你的程式碼庫，編寫中介層，跑測試，推送到 git。你到站之前就收到總結。

**一條訊息吸收任何儲存庫**
> 你在 Twitter 上看到一個很酷的儲存庫，截圖發給機器人。智能體 OCR 辨識圖片，找到 GitHub 連結，複製儲存庫，映射架構，提取對你技術棧有用的模式，安裝為技能——一張圖搞定。

**一覺醒來多了你沒寫過的新技能**
> 每天早上 6 點 `/evolve` 排程任務自動觸發。等你打開 Telegram，智能體已經掃描了 GitHub Trending，發現一個新測試框架，為它建構了技能，通過雙層安全審查，自動安裝並推送到你的儲存庫。你一夜之間變強了。

**用任何語言和你的程式碼庫對話**
> 用英語、粵語、國語、日語、韓語或 40+ 種支援語言傳送語音訊息。智能體透過本地 whisper.cpp 轉寫（~500ms），自動偵測語言，以文字回覆，並透過 edge-tts 用相同語言朗讀給你。

**用 `/learn` 深入研究任何東西**
> `/learn https://github.com/some/repo` — 智能體複製儲存庫，讀取每個檔案，映射架構，評估它如何有益於你的工作流程，給出 ADOPT / ADAPT / SKIP 判定，並可選地從中建構技能。

---

## 核心能力

| 能力 | 描述 |
|------|------|
| **CLI REPL** | `ae` — 互動式 Rich TUI，支援串流輸出、Markdown 渲染、工具使用轉圈動畫、32 個指令搭配 Tab 自動補全、工作階段持久化、自動召回。無需閘道程序 |
| **多平台** | Telegram（Bot API）+ Discord（桌面 CDP + REST）+ WhatsApp（Baileys v7 橋接）。`/subscribe` 監控頻道取得摘要，`/serve` 讓智能體在任意群組或私訊中主動回覆 |
| **建構** | 透過 Telegram 或 CLI 使用完整的 Claude Code——終端機、檔案讀寫、網路搜尋、MCP、26 個技能 |
| **進化** | 5 階段流水線：收集 → 分析 → 建構 → 審查 → 自動安裝。掃描 11 個來源：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + 微信群組，合成技能 |
| **吸收** | `/absorb <url>` — 複製儲存庫，映射架構，比對模式差異，將改進融入你的系統 |
| **學習** | `/learn <target>` — 深度提取，給出 ADOPT / ADAPT / SKIP 判定 |
| **語音** | 傳送語音訊息 → 本地 whisper.cpp 轉寫（~500ms）。`/speak` → edge-tts，300+ 種語音。自動偵測粵語/國語/日語/韓語 |
| **瀏覽器** | ABP（Agent Browser Protocol）作為預設瀏覽器。遇到 Cloudflare 攔截時自動切換到 Brave/Chrome（CDP）。隔離的智能體設定檔 |
| **自動召回** | 每次回覆前對 6 層記憶執行 `unified_search()`（約 400 tokens/則訊息） |
| **排程任務** | `/loop every 6h /evolve` — 按計劃自主成長 |
| **安全** | L1：預安裝正規表示式掃描（反向 shell、憑證竊取、挖礦程式）。L2：AgentShield 安裝後掃描（1282 項測試，102 條規則）。發現嚴重問題自動復原 |
| **鉤子** | 型別化非同步事件系統 — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **語意召回** | TF-IDF 餘弦相似度搜尋層增強 FTS5 關鍵字搜尋。5000 特徵向量化器，支援二元組。語料庫從工作階段、學習紀錄、直覺、記憶檔案重建。快取在 `~/.agenticEvolve/cache/` |
| **直覺引擎** | 行為模式觀察被評分並路由到直覺表。高信心度直覺（0.8+ 跨 2+ 專案或 5+ 次觀察）自動提升到 MEMORY.md |
| **韌性** | 關機排空（等待進行中的請求最多 30 秒）。型別化故障分類（驗證/計費/限流）。3 遍上下文壓縮。熱設定重載。迴圈偵測（3 次相同輪次警告，5 次終止）。記憶佇列讀透（去抖動原子寫入，無陳舊讀取）。並行建構階段（ThreadPoolExecutor，3 個隔離工作區） |
| **測試** | 423 個自動化測試（423 通過，1 個 xfail）。涵蓋：81 個指令處理器整合測試（全部 35+ 處理器）、工作階段資料庫、FTS5 搜尋、安全掃描、訊號去重、語意搜尋、直覺提升、排程解析、費用上限、迴圈偵測、上下文壓縮、參數解析 |

---

## 安裝設定

### 1. 安裝

```bash
curl -fsSL https://raw.githubusercontent.com/outsmartchad/agenticEvolve/main/scripts/install.sh | bash
```

安裝程式會處理一切——複製、相依套件、PATH 設定，並執行互動式安裝精靈。除了 Python 3 和 git 以外無需其他前置條件。

安裝完成後：

```bash
source ~/.zshrc    # 重新載入 shell（或：source ~/.bashrc）
```

> **需要：** [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（`npm install -g @anthropic-ai/claude-code`）——安裝程式會檢查是否已安裝，若缺少會顯示安裝指令。

### 2. 互動式聊天（CLI REPL）

```bash
ae
```

就這樣。你會得到一個 Rich TUI，支援串流輸出、Markdown 渲染、工具使用轉圈動畫，以及全部 32 個指令的 Tab 自動補全。用 `ae --resume <session_id>` 恢復先前的工作階段。

### 3. 啟動閘道（用於 Telegram/Discord/WhatsApp）

```bash
ae gateway start
```

在 Telegram 上傳訊息給你的機器人，或讓智能體在你的 WhatsApp 群組和 Discord 頻道中服務。

### 常用指令

| 指令 | 功能 |
|------|------|
| `ae` | 互動式聊天 REPL（預設） |
| `ae --resume ID` | 恢復先前的工作階段 |
| `ae setup` | 重新執行安裝精靈 |
| `ae doctor` | 診斷問題 |
| `ae gateway start` | 啟動訊息閘道 |
| `ae gateway stop` | 停止閘道 |
| `ae gateway install` | 安裝為 launchd 服務（登入時自動啟動） |
| `ae status` | 系統概覽 |
| `ae cost` | 使用量與開銷 |

### 語音支援（可選）

```bash
brew install whisper-cpp ffmpeg
curl -L -o ~/.agenticEvolve/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

---

## 指令

所有指令在 CLI REPL（`ae`）和 Telegram 中均可使用。CLI REPL 支援 Tab 自動補全，並附帶所有指令的描述。

### 核心

| 指令 | 功能 |
|------|------|
| _(任意訊息)_ | 與 Claude Code 對話 |
| _(語音訊息)_ | 自動轉寫（whisper.cpp）+ 回覆（僅限 Telegram） |

### 流水線（LLM 驅動）

| 指令 | 功能 |
|------|------|
| `/evolve [--dry-run]` | 掃描訊號，建構並自動安裝技能 |
| `/absorb <url>` | 從任意儲存庫吸收模式 |
| `/learn <target>` | 深度分析，給出 ADOPT/STEAL/SKIP 判定 |
| `/produce [--ideas N]` | 從所有訊號中腦力激盪商業點子 |
| `/reflect [--days N]` | 自我分析：模式、迴避傾向、下一步行動 |
| `/digest [--days N]` | 每日早間簡報（工作階段、訊號、費用） |
| `/gc [--dry-run]` | 垃圾回收（過期工作階段、孤立資料） |
| `/wechat [--hours N]` | 微信群組聊天摘要（讀取本地資料庫） |
| `/discord [--hours N]` | Discord 頻道摘要（從已儲存的訊息） |
| `/whatsapp [--hours N]` | WhatsApp 群組摘要（從已儲存的訊息） |

### 資訊查詢

| 指令 | 功能 |
|------|------|
| `/recall <query>` | 跨層搜尋（全部 6 層記憶） |
| `/search <query>` | FTS5 搜尋歷史工作階段 |
| `/memory` | 檢視 MEMORY.md + USER.md |
| `/soul` | 檢視 SOUL.md 人格設定 |
| `/config` | 檢視 config.yaml 設定 |
| `/skills` | 列出已安裝技能（26 個） |
| `/learnings [query]` | 列出或搜尋過去的學習紀錄 |
| `/sessions [N]` | 列出最近的工作階段 |
| `/cost` | 使用量與開銷 |
| `/status` | 系統概覽 |
| `/heartbeat` | 快速健康檢查 |

### 排程任務

| 指令 | 功能 |
|------|------|
| `/loop <interval> <prompt>` | 排程定期執行（例如 `/loop 6h /evolve`） |
| `/loops` | 列出進行中的排程任務 |
| `/unloop <id>` | 移除排程任務 |
| `/pause <id\|--all>` | 暫停排程任務 |
| `/unpause <id\|--all>` | 恢復排程任務 |
| `/notify <delay> <msg>` | 單次延遲通知 |

### 管理

| 指令 | 功能 |
|------|------|
| `/model [name]` | 顯示或切換模型 |
| `/autonomy [level]` | 顯示或設定自治等級（full/supervised/locked） |
| `/new` | 開啟新的工作階段 |
| `/queue` | 顯示待審核的技能 |
| `/approve <name>` | 批准排隊中的技能 |
| `/reject <name>` | 拒絕排隊中的技能 |

### 僅限 Telegram

| 指令 | 功能 |
|------|------|
| `/speak <text>` | 文字轉語音（edge-tts，自動偵測語言） |
| `/do <instruction>` | 自然語言 → 結構化指令 |
| `/subscribe` | 選擇要監控摘要的頻道 |
| `/serve` | 選擇智能體主動回覆的頻道/聯絡人 |
| `/lang [code]` | 設定持久輸出語言 |
| `/restart` | 遠端重啟閘道 |

[全部指令 →](docs/commands.md)

---

## 架構

```
使用者 (CLI REPL / Telegram / Discord / WhatsApp / 語音)
  → 閘道 (asyncio) 或 CLI（獨立模式） → 鉤子分發器 → 工作階段 + 費用控制
  → 自動召回 (6 層) → claude -p → SQLite → Git 同步
```

沒有自訂智能體迴圈。Claude Code **就是**執行環境——25+ 內建工具、MCP 伺服器、技能。閘道在其周圍加上了記憶、路由、召回、排程任務、語音、瀏覽器、多平台和安全層。CLI REPL（`ae`）完全繞過閘道，直接呼叫 `claude -p`，使用相同的記憶、召回和工作階段基礎設施。

### 關鍵設計決策
- **不造工具系統** — Claude Code 自帶工具。我們建構技能和基礎設施，而非抽象層。
- **有界記憶** — MEMORY.md（2200 字元）+ USER.md（1375 字元）+ SQLite FTS5。無無限增長。
- **閉環** — `auto_approve_skills: true`。進化 → 建構 → 審查 → 安裝 → 同步到 git。無人工審批。
- **關機排空** — 進行中的請求在重啟前完成。不遺失工作。
- **模組化指令** — 39 個 Telegram 指令拆分為 9 個 mixin（admin、pipelines、signals、cron、approval、search、media、misc、subscribe）。32 個指令為 CLI REPL 重新實作。轉接器核心 630 行。
- **雙層召回** — FTS5 關鍵字搜尋 + TF-IDF 語意搜尋。自動召回在每次 Claude 呼叫前注入相關上下文。
- **直覺流水線** — 跨工作階段觀察的行為模式被評分、去重，信心度足夠高時自動提升到 MEMORY.md。

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
| **ABP**（預設） | 所有智能體瀏覽 | 內建 Chromium，操作間 JS 凍結，Mind2Web 90.5% |
| **Brave** | 使用者要求 / Cloudflare 攔截 ABP | CDP 連接埠 9222，隔離設定檔 |
| **Chrome** | 使用者要求 / Cloudflare 攔截 ABP | CDP 連接埠 9223，隔離設定檔 |

智能體設定檔沙箱化在 `~/.agenticEvolve/browser-profiles/` — 絕不觸碰使用者真實瀏覽器資料。

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
| **daily-ux-review** | 1:00 AM | 讀取當天對話，發現摩擦點，識別前 3 名體驗改進，直接實施修改 |

透過 `/loop`、`/loops`、`/unloop`、`/pause`、`/unpause` 管理。設定檔：`cron/jobs.json`。

---

## 訊號來源（12 個）

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
| autonomous-loops | 自主導向的智能體迴圈 |
| continuous-learning-v2 | 模式提取流水線 |
| eval-harness | 技能評估框架 |
| claude-agent-sdk-v0.2.74 | Claude Agent SDK 模式 |
| nah | 快速拒絕/復原 |
| unf | 展開/擴展壓縮內容 |
| next-ai-draw-io | 從自然語言生成架構圖 |
| mcp-elicitation | 攔截任務中 MCP 對話框，實現無人值守流水線 |
| skill-gap-scan | 對比本地技能與社群目錄，發現採用缺口 |
| context-optimizer | 基於 `/context` 提示自動壓縮陳舊記憶檔案 |

---

## 最近更新

### v2.6 — 安全、可觀測性與平台對齊
- **內容消毒器**：提示注入防禦，使用隨機化邊界標記、Unicode 同形字摺疊（改編自 OpenClaw）
- **日誌脫敏**：17 個正規表示式模式自動剝離所有日誌輸出中的 API 金鑰、權杖、PEM 區塊
- **重試工具**：指數退避 + 抖動處理瞬態故障，Telegram 重試輔助函式
- **滾動日誌**：RotatingFileHandler（50MB，5 個備份）取代無限增長的日誌檔案
- **工具迴圈偵測器**：4 種偵測模式（通用重複、輪詢無進展、乒乓模式、全域斷路器）防止失控工作階段
- **安全自檢**：`/doctor` 指令檢查環境權限、設定密鑰、費用上限、相依套件、沙箱健康狀態、資料庫完整性
- **診斷事件匯流排**：型別化事件（訊息、用量、工作階段、迴圈、心跳），支援 JSONL 輸出和狀態摘要
- **WhatsApp 指令**：`/cost`、`/status`、`/doctor`、`/help` 現在可在 WhatsApp 上使用
- **語音流水線修復**：長音訊分片（48 分鐘 → 10 分鐘分片）、OGG→WAV 轉換、三層去重、語音強制回覆、雙段回應（轉寫 + 摘要）
- **安全修復**：CLI/TUI 中的環境變數消毒、動態擁有者路徑、服務群組的內容包裝

### v2.5 — 安全 + 智能 + 外掛系統

**第一階段：安全 + 成本保護**
- 環境變數消毒 — 從 `claude -p` 中剝離 30+ 種密鑰模式，防止提示詞洩露憑證。
- 每用戶滑動視窗速率限制（5次/分鐘, 30次/小時，可配置）。
- `[NO_REPLY]` 令牌 — 智能體可以跳過群組中不相關的訊息。
- 訊息去抖 — 對服務頻道的快速訊息進行批次處理（2.5秒視窗, 8秒最大等待）。
- `@agent <prompt>` 觸發器 — 適用於群組+私訊中的任何人，支援引用回覆上下文和瀏覽器 MCP。
- Docker 沙箱 — 服務聊天的隔離 Python 執行環境（`--network=none`, `--cap-drop=ALL`, 512MB 記憶體）。

**第二階段：使用者體驗 + 效率**
- Telegram 串流傳輸 — 就地編輯，1.5秒節流更新和 "..." 佔位符。
- 上下文視窗管理 — 令牌估算，60%/85% 閾值自動壓縮。
- 身份連結 — `/link` 和 `/whoami` 指令，跨平台使用者身份關聯。

**第三階段：智能**
- 19 個鉤子點的外掛系統，支援優先級排序、合併函式和 O(1) `has_hooks()` 檢查。
- 外掛載入器 — 從 `~/.agenticEvolve/plugins/` 發現並載入。每個外掛匯出 `register(hooks, config)`。
- 背景任務管理器 — 分離的長時間執行任務，帶進度追蹤。`/tasks` 和 `/cancel` 指令。
- 子智能體編排器 — 通用多 Claude 執行：`run_parallel`、`run_pipeline`、`run_dag`（依賴圖）。

**第四階段：完善**
- 閘道執行模式 — 主機執行，3 級安全（deny/allowlist/full），可配置審批（off/on-miss/always）。60+ 安全二進位自動批准，13 個拒絕清單模式阻擋危險指令。
- 配置驗證 — 套用前進行語意檢查。`/reload` 指令，帶驗證 + `config_reload` 鉤子。
- `/allowlist` 指令管理執行允許清單。`/hooks` 指令檢視已註冊鉤子。
- 總計 556 個測試（全部通過）。

### v2.3 — CLI REPL + WhatsApp LID 解析

**互動式 CLI REPL（`ae`）**
- `ae` 啟動一個獨立的 Rich TUI REPL——無需閘道程序。串流輸出搭配 Markdown 渲染、工具使用轉圈動畫和費用追蹤。
- 32 個斜線指令搭配 Tab 自動補全和描述。所有流水線指令（`/produce`、`/evolve`、`/learn`、`/absorb`、`/reflect`、`/digest`、`/gc`），資訊查詢指令（`/memory`、`/soul`、`/config`、`/skills`、`/learnings`、`/recall`、`/search`、`/sessions`），排程管理（`/loop`、`/loops`、`/unloop`、`/pause`、`/unpause`、`/notify`），以及管理指令（`/model`、`/autonomy`、`/queue`、`/approve`、`/reject`）。
- 工作階段持久化——所有訊息儲存至 SQLite 並自動產生標題。用 `ae --resume <session_id>` 恢復先前的工作階段。
- 每次呼叫前自動從全部 6 層記憶召回。費用上限強制執行。
- prompt-toolkit 輸入，支援檔案備份的歷史紀錄和自動建議。

**WhatsApp LID JID 解析**
- 修復一個關鍵 bug：Baileys v7 將私訊訊息以 LID JID（`@lid`）而非電話 JID（`@s.whatsapp.net`）傳遞。橋接程式現在在啟動時載入 `lid-mapping-*_reverse.json` 檔案，並為收到的訊息、發送的訊息和歷史同步解析 LID→電話號碼。
- 先前，像 `85254083858` 這樣的服務聯絡人會被靜默丟棄，因為 Python 無法將 LID JID 與基於電話號碼的服務目標進行匹配。

**WhatsApp 私訊聯絡人服務**
- `/serve` 現在支援個別 WhatsApp 聯絡人（不僅限群組）。新增 `_serve_contacts` 集合，與 `_serve_groups` 並列。私訊路由更新為對已服務聯絡人繞過 `allowed_users` 檢查。

**WhatsApp 媒體支援**
- 收到的 WhatsApp 圖片、文件（PDF、TXT、CSV 等）和語音訊息透過 Baileys `downloadMediaMessage` 下載，儲存至 `/tmp/`，並傳遞給 Claude Code 進行分析。包含媒體的訊息自動升級到 opus 模型。

**自動模型升級**
- 包含數學、程式設計或邏輯問題的訊息會透過正規表示式自動偵測，並路由到 `serve_reasoning_model`（opus）而非預設的 `serve_model`（sonnet）。圖片和文件訊息同樣觸發升級。

**頻道專屬知識**
- `run.py` 中的 `_CHANNEL_KNOWLEDGE` 字典將頻道/群組 ID 映射到專家知識提示。在人格提示之後注入，適用於 Discord 和 WhatsApp 服務頻道。用於 degen-damm Discord 頻道的 DAMM v2 專業知識。

### v2.2 — 多平台 + 訂閱/服務

**多平台支援**
- **Discord 桌面轉接器**（`gateway/platforms/discord_client.py`）— 透過 Chrome DevTools Protocol（CDP）接入執行中的 Discord 桌面應用。從網路請求中擷取驗證權杖，然後使用 Discord REST API 進行訊息收發。支援伺服器列表、頻道列表（帶分類分組）、私訊頻道和訊息輪詢。
- **WhatsApp 橋接**（`whatsapp-bridge/bridge.js`）— Baileys v7 Node.js 橋接，透過 stdin/stdout JSON 通訊。QR 碼推送到 Telegram 方便掃碼連結。出站訊息的 LID 轉電話號碼解析。群組前綴過濾（`/ask`、`@agent`）。從驗證儲存 lid-mapping 檔案 + 即時訊息追蹤中發現聯絡人。
- **微信** — 透過解密本地 SQLCipher 資料庫唯讀存取。群組和聯絡人來自 `contact.db`，訊息來自 `message_0.db`。

**訂閱與服務指令**
- `/subscribe` — Telegram 內聯鍵盤 UI，選擇 Discord 頻道、WhatsApp 群組/聯絡人或微信群組進行摘要監控。分頁列表（每頁 40 項），Discord 帶分類標題。WhatsApp 分為群組/聯絡人子檢視。
- `/serve` — 相同 UI，選擇智能體主動回覆的位置。WhatsApp 服務群組接受所有訊息（無需前綴，無 allowed_users 限制）。服務目標在閘道啟動時從資料庫載入。切換時動態更新轉接器。
- **訂閱資料庫** — session_db 中的 `subscriptions` 表，包含 user_id、platform、target_id、target_name、target_type、mode。CRUD 函式：`add_subscription`、`remove_subscription`、`get_subscriptions`、`get_serve_targets`、`is_subscribed`。
- **短 ID 註冊表** — Telegram 限制 `callback_data` 為 64 位元組。長 WhatsApp JID（`120363427198529523@g.us`）和微信聊天室 ID 會超出限制。解決方案：記憶體內數字 ID 映射（`sub:t:3` 代替 `sub:toggle:whatsapp:group:120363...`）。

### v2.1 — 模組化架構 + 語意召回 + 測試體系

**架構**
- 將 `telegram.py` 從 3870 行拆分為 8 個指令 mixin（`gateway/commands/`）：admin、pipelines、signals、cron、approval、search、media、misc。轉接器核心縮減至 630 行。
- 每使用者語言偏好（`/lang`）持久化到 SQLite `user_prefs` 表。
- 進化流水線中的跨來源訊號去重（URL + 標題匹配）。
- 採集器重試，5 秒指數退避。

**語意搜尋 + 直覺引擎**
- TF-IDF 餘弦相似度搜尋層增強 FTS5 關鍵字搜尋。`unified_search()` 現在查詢兩個層。
- 直覺自動提升：高信心度行為模式（信心度 >= 0.8，跨 2+ 專案或 5+ 次觀察）在工作階段清理時自動提升到 MEMORY.md。
- 語意語料庫從工作階段、學習紀錄、直覺和記憶檔案重建。快取為 pickle 檔案以快速重載。

**測試體系 — 423 個測試（423 通過，1 個 xfail）**

| 測試檔案 | 數量 | 涵蓋範圍 |
|----------|------|----------|
| `test_commands.py` | 81 | 全部 35+ 指令處理器：admin、pipelines、signals、cron、approval、search、media、misc + 30 個授權拒絕測試 |
| `test_session_db.py` | 25 | 工作階段、訊息、FTS5 搜尋、學習紀錄、使用者偏好、直覺、統計 |
| `test_security.py` | 28 | 嚴重模式（反向 shell、fork 炸彈、挖礦）、警告、提示注入、安全內容、目錄掃描 |
| `test_evolve.py` | 72 | 訊號載入、排名、URL/標題去重、邊緣情況、採集器、技能批准/拒絕、雜湊驗證、佇列、報告 |
| `test_agent.py` | 27 | 錯誤分類、歷史壓縮（3 遍級聯）、標題產生、迴圈偵測 |
| `test_semantic.py` | 11 | 語料庫建構（工作階段、學習、直覺）、搜尋相關性、快取、分數過濾 |
| `test_instincts.py` | 8 | 上下文 bug 迴歸、自動提升（提升、去重、字元限制） |
| `test_gateway.py` | 10 | Cron 解析器（every/specific/step/wrap）、工作階段鍵、費用上限 |
| `test_voice.py` | 57 | TTS 設定、語言偵測、音訊格式轉換、STT 轉寫、TTS 指令 |
| `test_absorb.py` | 49 | 建構函式、報告、掃描提示、安全預掃描、微信時間解析、試執行、AgentShield |
| `test_telegram.py` | 13 | 參數解析（布林/值/別名/型別轉換）、使用者白名單 |

**Bug 修復**
- 修復 `gateway/security.py` 中的 fork 炸彈正規表示式 — 未跳脫的 `(){}` 元字元導致模式永遠無法匹配。
- 修復 `gateway/session_db.py` 中的 `upsert_instinct` — SELECT 查詢缺少 `context` 欄位，導致空上下文重複 upsert 時出現 IndexError。
- 修復 `gateway/commands/admin.py` 中的 `_handle_newsession` — `set_session_title`（不存在的函式）→ `set_title`，且缺少 `generate_session_id()` 導致 UNIQUE 約束衝突。
- 修復 `gateway/commands/misc.py` 中的 `_extract_urls` — `_URL_RE` 類別屬性從未定義，導致每則純文字訊息觸發 `AttributeError`。
- 修復 `/restart` 產生重複閘道實例的問題 — 現在使用 `os.getpid()` 僅終止當前程序。
- 修復 `_extract_urls` 崩潰 — `_URL_RE` 類別屬性從未在 `MiscMixin` 上定義。

---

## 文件

| 文件 | 描述 |
|------|------|
| [介面](docs/interface.md) | 使用範例和互動模式 |
| [記憶](docs/memory.md) | 6 層記憶架構、自動召回、直覺評分 |
| [指令](docs/commands.md) | 全部指令及參數和範例 |
| [流水線](docs/pipelines.md) | Evolve、Absorb、Learn、Do、GC 流水線 |
| [技能](docs/skills.md) | 完整技能目錄 |
| [安全](docs/security.md) | 掃描器、自治等級、安全閘門 |
| [架構](docs/architecture.md) | 訊息流、專案結構、設計決策 |
| [路線圖](docs/roadmap.md) | 整合計劃 — Firecrawl、視覺、沙箱 |

---

## 血脈

| 專案 | 採納的模式 |
|------|-----------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | 智能體執行環境 — 25+ 工具、MCP、技能、子智能體 |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 有界記憶、工作階段持久化、訊息閘道、漸進式狀態訊息 |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | 自治等級、預設拒絕、熱設定重載、風險分級分類 |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 9 個技能改編，AgentShield 安全，評估驅動開發，鉤子設定 |
| [openclaw](https://github.com/openclaw/openclaw) | 語音流水線（TTS/STT），瀏覽器自動化模式，自動 TTS 模式 |
| [ABP](https://github.com/theredsix/agent-browser-protocol) | 瀏覽器 MCP — 操作間凍結的 Chromium，Mind2Web 90.5% |
| [deer-flow](https://github.com/bytedance/deer-flow) | 並行子智能體建構階段、每候選隔離工作區、迴圈偵測、記憶佇列去抖動寫入 |

---

MIT
