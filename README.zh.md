# agenticEvolve

**一个每天自动进化你开发能力的个人闭环智能体系统。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-23-orange?style=for-the-badge" alt="23 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-32-blue?style=for-the-badge" alt="32 Commands"></a>
</p>

---

基于 `claude -p` 构建的持久化智能体运行时，配合 Python asyncio 网关。6 层记忆体系 + 跨层自动召回。闭环技能合成。语音输入输出。浏览器自动化。内置定时任务。双层安全机制。通过 Telegram 操控——你的整个开发环境装进口袋。

---

## 你能用它做什么？

**在手机上写代码**
> 你在地铁上，发一条消息 `/do 给 API 加上限流`。代理读取你的代码库，编写中间件，跑测试，推送到 git。你到站之前就收到总结。

**一条消息吸收任何仓库**
> 你在 Twitter 上看到一个很酷的仓库，截图发给机器人。代理 OCR 识别图片，找到 GitHub 链接，克隆仓库，映射架构，提取对你技术栈有用的模式，安装为技能——一张图搞定。

**一觉醒来多了你没写过的新技能**
> 每天早上 6 点 `/evolve` 定时任务自动触发。等你打开 Telegram，代理已经扫描了 GitHub Trending，发现了一个新测试框架，为它构建了技能，通过双层安全审查，自动安装并推送到你的仓库。你一夜之间变强了。

**用任何语言和你的代码库对话**
> 用英语、粤语、普通话、日语、韩语或 40+ 种支持语言发送语音消息。代理通过本地 whisper.cpp 转写（~500ms），自动检测语言，以文字回复，并通过 edge-tts 用相同语言朗读给你。

**用 `/learn` 深入研究任何东西**
> `/learn https://github.com/some/repo` — 代理克隆仓库，读取每个文件，映射架构，评估它如何有益于你的工作流，给出 ADOPT / ADAPT / SKIP 判定，并可选地从中构建技能。

**替你浏览网页**
> "去 Anthropic 文档找最新的 Claude 模型定价。" 代理打开 ABP 浏览器，导航，提取数据，发送简洁摘要。如果 Cloudflare 拦截，自动切换到 Brave。

**搜索你自己的微信聊天记录**
> 微信自带的搜索太烂了。代理读取你本地的微信数据库，给你一个可搜索的导出——联系人、消息、群聊、收藏。全部离线，全在你自己的机器上。

**在睡梦中从群聊中吸收想法**
> 你的 `/evolve` 定时任务在早上 6 点不只是扫描 GitHub。它还会读取你的微信技术群聊天记录，总结过去 24 小时的讨论——别人提到的新工具、分享的仓库、讨论的技术方案——并将最好的想法吸收为技能。你醒来时，群组的集体智慧已经融入你的系统。

**自我改进的用户体验**
> 每天凌晨 1 点，代理读取当天的对话，找出你等待太久或收到困惑回复的摩擦点，然后直接修补自己的代码来修复它们。你醒来后面对的是一个更好的代理。

---

## 核心能力

| 能力 | 描述 |
|------|------|
| **构建** | 通过 Telegram 使用完整的 Claude Code——终端、文件读写、网络搜索、MCP、23 个技能 |
| **进化** | 5 阶段流水线：收集 → 分析 → 构建 → 审查 → 自动安装。扫描 GitHub Trending + HN + 微信群聊摘要，合成技能 |
| **吸收** | `/absorb <url>` — 克隆仓库，映射架构，对比模式，将改进融入你的系统 |
| **学习** | `/learn <target>` — 深度提取，给出 ADOPT / ADAPT / SKIP 判定 |
| **语音** | 发送语音消息 → 本地 whisper.cpp 转写（~500ms）。`/speak` → edge-tts，300+ 种语音。自动检测粤语/普通话/日语/韩语 |
| **浏览器** | ABP（Agent Browser Protocol）作为默认浏览器。遇到 Cloudflare 拦截时自动切换到 Brave/Chrome（CDP）。隔离的代理配置文件 |
| **自动召回** | 每次回复前对 6 层记忆执行 `unified_search()`（约 400 tokens/条消息） |
| **定时任务** | `/loop every 6h /evolve` — 按计划自主成长 |
| **安全** | L1：预安装正则扫描（反向 shell、凭证窃取、挖矿程序）。L2：AgentShield 安装后扫描（1282 项测试，102 条规则）。发现严重问题自动回滚 |
| **钩子** | 类型化异步事件系统 — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **韧性** | 关机排空（等待进行中的请求最多 30 秒）。类型化故障分类（认证/计费/限流）。3 遍上下文压缩。热配置重载 |

---

## 安装

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
brew install whisper-cpp ffmpeg  # 语音支持
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

## 命令

| 命令 | 功能 |
|------|------|
| _(任意消息)_ | 与 Claude Code 对话 |
| _(语音消息)_ | 自动转写（whisper.cpp）+ 回复（语音模式下附带语音） |
| _(发送图片)_ | 视觉分析——截图识别、图表理解、OCR、UI 检查 |
| _(发送文件)_ | 文件分析——PDF、代码文件、文本文件 |
| `/evolve` | 扫描信号，构建并自动安装技能 |
| `/absorb <url>` | 从任意仓库吸收模式 |
| `/learn <target>` | 深度分析并给出判定 |
| `/speak <text>` | 文字转语音（自动检测语言） |
| `/recall <query>` | 跨层搜索（全部 6 层记忆） |
| `/search <query>` | FTS5 搜索历史会话 |
| `/do <instruction>` | 自然语言 → 结构化命令 |
| `/loop <cron> <cmd>` | 调度定期执行 |
| `/memory` | 查看代理记忆状态 |
| `/skills` | 列出已安装技能（23 个） |
| `/cost` | 使用量和开销 |
| `/restart` | 远程重启网关 |

[全部 32 个命令 →](docs/commands.md)

---

## 架构

```
用户 (Telegram/语音) → 网关 (asyncio) → 钩子分发器 → 会话 + 费用控制
  → 自动召回 (6 层) → claude -p → SQLite → Git 同步
```

没有自定义代理循环。Claude Code **就是**运行时——25+ 内置工具、MCP 服务器、技能。网关在其周围添加了记忆、路由、召回、定时任务、语音、浏览器和安全层。

### 关键设计决策
- **不造工具系统** — Claude Code 自带工具。我们构建技能和基础设施，而非抽象层。
- **有界记忆** — MEMORY.md（2200 字符）+ USER.md（1375 字符）+ SQLite FTS5。无无限增长。
- **闭环** — `auto_approve_skills: true`。进化 → 构建 → 审查 → 安装 → 同步到 git。无人工审批。
- **关机排空** — 进行中的请求在重启前完成。不丢失工作。

---

## 语音流水线

| 方向 | 技术 | 延迟 | 费用 |
|------|------|------|------|
| **语音 → 文字** | 本地 whisper.cpp（ggml-small 多语言模型） | Apple Silicon 上约 500ms | 免费 |
| **文字 → 语音** | edge-tts（300+ 神经网络语音） | 约 1 秒 | 免费 |
| **语言检测** | CJK 启发式（嘅係唔 → 粤语，ひらがな → 日语） | 即时 | 免费 |

自动 TTS 模式：`off`（仅 `/speak`），`always`（每条回复），`inbound`（用户发语音时以语音回复）。

---

## 浏览器自动化

| 浏览器 | 使用场景 | 方式 |
|--------|----------|------|
| **ABP**（默认） | 所有代理浏览 | 内置 Chromium，操作间 JS 冻结，Mind2Web 90.5% |
| **Brave** | 用户要求 / Cloudflare 拦截 ABP | CDP 端口 9222，隔离配置文件 |
| **Chrome** | 用户要求 / Cloudflare 拦截 ABP | CDP 端口 9223，隔离配置文件 |

代理配置文件沙箱化在 `~/.agenticEvolve/browser-profiles/` — 绝不触碰用户真实浏览器数据。

---

## 安全

| 层级 | 工具 | 时机 | 严重问题处理 |
|------|------|------|-------------|
| **L1** | `gateway/security.py` | 预安装：扫描原始文件 | 阻止 + 中止流水线 |
| **L2** | AgentShield（1282 项测试） | 安装后：扫描 `~/.claude/` 配置 | 自动回滚已安装技能 |

扫描内容：凭证泄露、反向 shell、混淆载荷、加密货币挖矿、macOS 持久化、提示注入、npm 钩子利用。

---

## 定时任务

3 个自治任务每天自动运行——无需人工触发。

| 任务 | 时间（HKT） | 功能 |
|------|------------|------|
| **evolve-daily** | 6:00 AM | 收集 GitHub Trending + HN + 微信群聊摘要信号，评分候选项，构建最多 3 个新技能，安全审查，自动安装，推送到 git |
| **daily-digest** | 8:00 AM | 每日简报——热门信号、已构建技能、会话数、费用摘要。推送到 Telegram |
| **daily-ux-review** | 1:00 AM | 读取当天对话，发现摩擦点，识别 Top 3 体验改进，直接实施修改 |

通过 `/loop`、`/loops`、`/unloop`、`/pause`、`/unpause` 管理。配置文件：`cron/jobs.json`。

---

## 技能（已安装 23 个）

| 技能 | 用途 |
|------|------|
| agent-browser-protocol | 通过 MCP 的 ABP 浏览器自动化 |
| browser-switch | 多浏览器 CDP 切换（Brave/Chrome） |
| brave-search | 通过 Brave API 网络搜索 |
| firecrawl | 网页抓取、爬取、搜索、结构化提取 |
| cloudflare-crawl | 免费网页爬取（Cloudflare Browser Rendering API） |
| jshook-messenger | 通过 jshookmcp MCP 拦截 Discord/微信/Telegram/Slack |
| wechat-decrypt | 读取本地微信数据库，导出消息、联系人、群聊（macOS） |
| session-search | FTS5 会话历史搜索 |
| cron-manager | 定时任务管理 |
| skill-creator | 官方 Anthropic 技能创建 |
| deep-research | 多源研究流水线 |
| market-research | 市场/竞品分析 |
| article-writing | 长文内容创作 |
| video-editing | FFmpeg 视频编辑指南 |
| security-review | 代码安全检查清单 |
| security-scan | AgentShield 配置扫描器 |
| autonomous-loops | 自主导向的代理循环 |
| continuous-learning-v2 | 模式提取流水线 |
| eval-harness | 技能评估框架 |
| claude-agent-sdk-v0.2.74 | Claude Agent SDK 模式 |
| nah | 快速拒绝/撤销 |
| unf | 展开/扩展压缩内容 |

---

## 文档

| 文档 | 描述 |
|------|------|
| [交互](docs/interface.md) | 使用示例和交互模式 |
| [记忆](docs/memory.md) | 6 层记忆架构、自动召回、直觉评分 |
| [命令](docs/commands.md) | 全部 32 个命令及参数和示例 |
| [流水线](docs/pipelines.md) | Evolve、Absorb、Learn、Do、GC 流水线 |
| [技能](docs/skills.md) | 完整技能目录 |
| [安全](docs/security.md) | 扫描器、自治等级、安全门控 |
| [架构](docs/architecture.md) | 消息流、项目结构、设计决策 |
| [路线图](docs/roadmap.md) | 集成计划 — Firecrawl、视觉、沙箱 |

---

## 血脉

| 项目 | 采纳的模式 |
|------|-----------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | 代理运行时 — 25+ 工具、MCP、技能、子代理 |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 有界记忆、会话持久化、消息网关、渐进式状态消息 |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | 自治等级、默认拒绝、热配置重载、风险分级分类 |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 9 个技能改编，AgentShield 安全，评估驱动开发，钩子配置 |
| [openclaw](https://github.com/openclaw/openclaw) | 语音流水线（TTS/STT），浏览器自动化模式，自动 TTS 模式 |
| [ABP](https://github.com/theredsix/agent-browser-protocol) | 浏览器 MCP — 操作间冻结的 Chromium，Mind2Web 90.5% |

---

MIT
