# agenticEvolve

**一个每天自动进化你开发能力的个人闭环智能体系统。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-26-orange?style=for-the-badge" alt="26 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-39-blue?style=for-the-badge" alt="39 Commands"></a>
</p>

---

基于 `claude -p` 构建的持久化智能体运行时，配合 Python asyncio 网关。6 层记忆体系 + 跨层自动召回。闭环技能合成。语音输入输出。浏览器自动化。内置定时任务。双层安全机制。多平台（Telegram + Discord + WhatsApp）。39 个 Telegram 命令——你的整个开发环境装进口袋。

---

## 你能用它做什么？

**替你浏览网页**
> "去 Anthropic 文档找最新的 Claude 模型定价。" 代理打开 ABP 浏览器，导航，提取数据，发送简洁摘要。如果 Cloudflare 拦截，自动切换到 Brave。

**在你的 WhatsApp 和 Discord 群组中服务**
> `/serve` → WhatsApp → 群组 → 开启 Crypto🚀。现在群组里任何人都能和你的 AI 代理对话。它回复每条消息，维护每个群组的对话记忆，你通过 Telegram 内联键盘控制一切。Discord 频道同样支持——代理通过 Chrome DevTools Protocol 接入你的桌面应用。

**搜索你自己的微信聊天记录**
> 微信自带的搜索太烂了。代理读取你本地的微信数据库，给你一个可搜索的导出——联系人、消息、群聊、收藏。全部离线，全在你自己的机器上。

**在睡梦中从群聊中吸收想法**
> 你的 `/evolve` 定时任务在早上 6 点不只是扫描 GitHub。它还会读取你的微信技术群聊天记录，总结过去 24 小时的讨论——别人提到的新工具、分享的仓库、讨论的技术方案——并将最好的想法吸收为技能。你醒来时，群组的集体智慧已经融入你的系统。

**从趋势信号中头脑风暴商业点子**
> `/produce` — 代理聚合今天来自 11 个来源的信号（GitHub Trending、Hacker News、X/Twitter、Reddit、Product Hunt、Lobste.rs、ArXiv、HuggingFace、BestOfJS、微信群聊和你 star 的仓库），识别新兴趋势，并头脑风暴 5 个具体的应用/商业点子，包含盈利模式、技术栈和 MVP 范围。按需进行信号驱动的创意发想。

**自我改进的用户体验**
> 每天凌晨 1 点，代理读取当天的对话，找出你等待太久或收到困惑回复的摩擦点，然后直接修补自己的代码来修复它们。你醒来后面对的是一个更好的代理。

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

---

## 核心能力

| 能力 | 描述 |
|------|------|
| **多平台** | Telegram（Bot API）+ Discord（桌面 CDP + REST）+ WhatsApp（Baileys v7 桥接）。`/subscribe` 监控频道获取摘要，`/serve` 让代理在任意群组或私聊中主动回复 |
| **构建** | 通过 Telegram 使用完整的 Claude Code——终端、文件读写、网络搜索、MCP、26 个技能 |
| **进化** | 5 阶段流水线：收集 → 分析 → 构建 → 审查 → 自动安装。扫描 11 个来源：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + 微信群聊，合成技能 |
| **吸收** | `/absorb <url>` — 克隆仓库，映射架构，对比模式，将改进融入你的系统 |
| **学习** | `/learn <target>` — 深度提取，给出 ADOPT / ADAPT / SKIP 判定 |
| **语音** | 发送语音消息 → 本地 whisper.cpp 转写（~500ms）。`/speak` → edge-tts，300+ 种语音。自动检测粤语/普通话/日语/韩语 |
| **浏览器** | ABP（Agent Browser Protocol）作为默认浏览器。遇到 Cloudflare 拦截时自动切换到 Brave/Chrome（CDP）。隔离的代理配置文件 |
| **自动召回** | 每次回复前对 6 层记忆执行 `unified_search()`（约 400 tokens/条消息） |
| **定时任务** | `/loop every 6h /evolve` — 按计划自主成长 |
| **安全** | L1：预安装正则扫描（反向 shell、凭证窃取、挖矿程序）。L2：AgentShield 安装后扫描（1282 项测试，102 条规则）。发现严重问题自动回滚 |
| **钩子** | 类型化异步事件系统 — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **语义召回** | TF-IDF 余弦相似度搜索层增强 FTS5 关键词搜索。5000 特征向量化器，支持二元组。语料库从会话、学习记录、直觉、记忆文件重建。缓存在 `~/.agenticEvolve/cache/` |
| **直觉引擎** | 行为模式观察被评分并路由到直觉表。高置信度直觉（0.8+ 跨 2+ 项目或 5+ 次观察）自动提升到 MEMORY.md |
| **韧性** | 关机排空（等待进行中的请求最多 30 秒）。类型化故障分类（认证/计费/限流）。3 遍上下文压缩。热配置重载。循环检测（3 次相同轮次警告，5 次终止）。记忆队列读透（去抖动原子写入，无陈旧读取）。并行构建阶段（ThreadPoolExecutor，3 个隔离工作区） |
| **测试** | 379 个自动化测试（379 通过，1 个 xfail）。覆盖：81 个命令处理器集成测试（全部 35+ 处理器）、会话数据库、FTS5 搜索、安全扫描、信号去重、语义搜索、直觉提升、定时解析、费用上限、循环检测、上下文压缩、参数解析 |

---

## 安装

### 1. 安装

```bash
curl -fsSL https://raw.githubusercontent.com/outsmartchad/agenticEvolve/main/scripts/install.sh | bash
```

安装程序会处理一切——克隆、依赖、PATH 配置，并运行交互式安装向导。除 Python 3 和 git 外无需任何前置条件。

安装完成后：

```bash
source ~/.zshrc    # 重载 shell（或：source ~/.bashrc）
```

> **需要：** [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（`npm install -g @anthropic-ai/claude-code`）——安装程序会检测是否已安装，未安装时显示安装命令。

### 2. 启动网关

```bash
ae gateway start
```

### 3. 开始对话

在 Telegram 上给你的机器人发消息。就这么简单。

### 常用命令

| 命令 | 功能 |
|------|------|
| `ae setup` | 重新运行安装向导 |
| `ae doctor` | 诊断问题 |
| `ae gateway start` | 启动网关 |
| `ae gateway stop` | 停止网关 |
| `ae gateway install` | 安装为 launchd 服务（登录时自动启动） |
| `ae status` | 系统概览 |
| `ae cost` | 使用量和开销 |

### 语音支持（可选）

```bash
brew install whisper-cpp ffmpeg
curl -L -o ~/.agenticEvolve/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

---

## 命令

| 命令 | 功能 |
|------|------|
| _(任意消息)_ | 与 Claude Code 对话 |
| _(语音消息)_ | 自动转写（whisper.cpp）+ 回复（语音模式下附带语音） |
| `/evolve` | 扫描信号，构建并自动安装技能 |
| `/absorb <url>` | 从任意仓库吸收模式 |
| `/learn <target>` | 深度分析并给出判定 |
| `/speak <text>` | 文字转语音（自动检测语言） |
| `/recall <query>` | 跨层搜索（全部 6 层记忆） |
| `/search <query>` | FTS5 搜索历史会话 |
| `/do <instruction>` | 自然语言 → 结构化命令 |
| `/loop <cron> <cmd>` | 调度定期执行 |
| `/memory` | 查看代理记忆状态 |
| `/skills` | 列出已安装技能（26 个） |
| `/cost` | 使用量和开销 |
| `/subscribe` | 选择 Discord/WhatsApp/微信频道进行摘要监控 |
| `/serve` | 选择代理主动回复的频道/联系人 |
| `/wechat [--hours N]` | 微信群聊摘要（简体中文） |
| `/discord [--hours N]` | Discord 频道摘要（已订阅频道） |
| `/whatsapp` | WhatsApp 摘要（即将推出） |
| `/produce [--ideas N]` | 从所有信号中头脑风暴商业点子 |
| `/digest` | 每日早间简报 |
| `/lang [code]` | 设置 `/produce`、`/learn`、`/wechat` 的持久输出语言 |
| `/restart` | 远程重启网关 |

[全部 39 个命令 →](docs/commands.md)

---

## 架构

```
用户 (Telegram/Discord/WhatsApp/语音) → 网关 (asyncio) → 钩子分发器 → 会话 + 费用控制
  → 自动召回 (6 层) → claude -p → SQLite → Git 同步
```

没有自定义代理循环。Claude Code **就是**运行时——25+ 内置工具、MCP 服务器、技能。网关在其周围添加了记忆、路由、召回、定时任务、语音、浏览器、多平台、和安全层。

### 关键设计决策
- **不造工具系统** — Claude Code 自带工具。我们构建技能和基础设施，而非抽象层。
- **有界记忆** — MEMORY.md（2200 字符）+ USER.md（1375 字符）+ SQLite FTS5。无无限增长。
- **闭环** — `auto_approve_skills: true`。进化 → 构建 → 审查 → 安装 → 同步到 git。无人工审批。
- **关机排空** — 进行中的请求在重启前完成。不丢失工作。
- **模块化命令** — 39 个 Telegram 命令拆分为 9 个 mixin（admin、pipelines、signals、cron、approval、search、media、misc、subscribe）。适配器核心 630 行。
- **双层召回** — FTS5 关键词搜索 + TF-IDF 语义搜索。自动召回在每次 Claude 调用前注入相关上下文。
- **直觉流水线** — 跨会话观察的行为模式被评分、去重，置信度足够高时自动提升到 MEMORY.md。

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

4 个自治任务每天自动运行——无需人工触发。

| 任务 | 时间（HKT） | 功能 |
|------|------------|------|
| **evolve-daily** | 6:00 AM | 收集 11 个来源的信号：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + 微信群聊，评分候选项，构建最多 3 个新技能，安全审查，自动安装，推送到 git |
| **daily-digest** | 8:00 AM | 每日简报——热门信号、已构建技能、会话数、费用摘要。推送到 Telegram |
| **wechat-digest** | 9:00 AM | 每日微信群聊摘要——总结讨论内容、提到的工具、技术群的关键洞察。推送到 Telegram |
| **daily-ux-review** | 1:00 AM | 读取当天对话，发现摩擦点，识别 Top 3 体验改进，直接实施修改 |

通过 `/loop`、`/loops`、`/unloop`、`/pause`、`/unpause` 管理。配置文件：`cron/jobs.json`。

---

## 信号来源（11 个）

| 来源 | 采集器 | API | 采集内容 |
|------|--------|-----|----------|
| GitHub Search | `github.sh` | GitHub API (gh CLI) | 按关键词搜索趋势仓库、star 仓库动态、发布监控 |
| GitHub Trending | `github-trending.py` | GitHub API (gh CLI) | 最近 7 天创建的热门新仓库 |
| Hacker News | `hackernews.sh` | Algolia API | 关键词搜索 + 首页 + Show HN |
| X / Twitter | `x-search.sh` | Brave Search API | 关于开源、开发工具、AI 的热门推文 |
| Reddit | `reddit.py` | Pullpush.io API | 13 个子版块：LocalLLaMA、programming、ClaudeAI 等 |
| Product Hunt | `producthunt.py` | RSS/Atom feed | 开发工具 + AI 产品发布 |
| Lobste.rs | `lobsters.py` | JSON API | 精选技术新闻（高信噪比） |
| ArXiv | `arxiv.py` | ArXiv API | cs.AI、cs.CL、cs.SE、cs.LG 论文 |
| HuggingFace | `huggingface.py` | HF API | 趋势模型和 Spaces |
| BestOfJS | `bestofjs.py` | Static JSON API | 按每日 star 增长排名的 JavaScript/TypeScript 项目 |
| WeChat | `wechat.py` | Local DB | 群聊消息（读取本地数据） |

---

## 技能（已安装 26 个）

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
| next-ai-draw-io | 从自然语言生成架构图 |
| mcp-elicitation | 拦截任务中 MCP 对话框，实现无人值守流水线 |
| skill-gap-scan | 对比本地技能与社区目录，发现采用缺口 |
| context-optimizer | 基于 `/context` 提示自动归档陈旧记忆文件 |

---

## 最近更新

### v2.2 — 多平台 + 订阅/服务

**多平台支持**
- **Discord 桌面适配器**（`gateway/platforms/discord_client.py`）— 通过 Chrome DevTools Protocol（CDP）接入运行中的 Discord 桌面应用。从网络请求中提取认证令牌，然后使用 Discord REST API 进行消息收发。支持服务器列表、频道列表（带分类分组）、私聊频道和消息轮询。
- **WhatsApp 桥接**（`whatsapp-bridge/bridge.js`）— Baileys v7 Node.js 桥接，通过 stdin/stdout JSON 通信。QR 码推送到 Telegram 方便扫码。出站消息的 LID 转手机号解析。群组前缀过滤（`/ask`、`@agent`）。从认证存储 lid-mapping 文件 + 实时消息追踪中发现联系人。
- **微信** — 通过解密本地 SQLCipher 数据库只读访问。群组和联系人来自 `contact.db`，消息来自 `message_0.db`。

**订阅与服务命令**
- `/subscribe` — Telegram 内联键盘 UI，选择 Discord 频道、WhatsApp 群组/联系人或微信群组进行摘要监控。分页列表（每页 40 项），Discord 带分类标题。WhatsApp 分为群组/联系人子视图。
- `/serve` — 相同 UI，选择代理主动回复的位置。WhatsApp 服务群组接受所有消息（无需前缀，无 allowed_users 限制）。服务目标在网关启动时从数据库加载。切换时动态更新适配器。
- **订阅数据库** — session_db 中的 `subscriptions` 表，包含 user_id、platform、target_id、target_name、target_type、mode。CRUD 函数：`add_subscription`、`remove_subscription`、`get_subscriptions`、`get_serve_targets`、`is_subscribed`。
- **短 ID 注册表** — Telegram 限制 `callback_data` 为 64 字节。长 WhatsApp JID（`120363427198529523@g.us`）和微信聊天室 ID 会超出限制。解决方案：内存数字 ID 映射（`sub:t:3` 代替 `sub:toggle:whatsapp:group:120363...`）。

### v2.1 — 模块化架构 + 语义召回 + 测试体系

**架构**
- 将 `telegram.py` 从 3870 行拆分为 8 个命令 mixin（`gateway/commands/`）：admin、pipelines、signals、cron、approval、search、media、misc。适配器核心缩减至 630 行。
- 每用户语言偏好（`/lang`）持久化到 SQLite `user_prefs` 表。
- 进化流水线中的跨来源信号去重（URL + 标题匹配）。
- 采集器重试，5 秒指数退避。

**语义搜索 + 直觉引擎**
- TF-IDF 余弦相似度搜索层增强 FTS5 关键词搜索。`unified_search()` 现在查询两个层。
- 直觉自动提升：高置信度行为模式（置信度 >= 0.8，跨 2+ 项目或 5+ 次观察）在会话清理时自动提升到 MEMORY.md。
- 语义语料库从会话、学习记录、直觉和记忆文件重建。缓存为 pickle 文件以快速重载。

**测试体系 — 379 个测试（379 通过，1 个 xfail）**

| 测试文件 | 数量 | 覆盖范围 |
|----------|------|----------|
| `test_commands.py` | 81 | 全部 35+ 命令处理器：admin、pipelines、signals、cron、approval、search、media、misc + 30 个授权拒绝测试 |
| `test_session_db.py` | 25 | 会话、消息、FTS5 搜索、学习记录、用户偏好、直觉、统计 |
| `test_security.py` | 28 | 严重模式（反向 shell、fork 炸弹、挖矿）、警告、提示注入、安全内容、目录扫描 |
| `test_evolve.py` | 72 | 信号加载、排名、URL/标题去重、边缘情况、采集器、技能批准/拒绝、哈希验证、队列、报告 |
| `test_agent.py` | 27 | 错误分类、历史压缩（3 遍级联）、标题生成、循环检测 |
| `test_semantic.py` | 11 | 语料库构建（会话、学习、直觉）、搜索相关性、缓存、分数过滤 |
| `test_instincts.py` | 8 | 上下文 bug 回归、自动提升（提升、去重、字符限制） |
| `test_gateway.py` | 10 | Cron 解析器（每分钟/特定/步进/跨天）、会话键、费用上限 |
| `test_voice.py` | 57 | TTS 配置、语言检测、音频格式转换、STT 转写、TTS 指令 |
| `test_absorb.py` | 49 | 构造函数、报告、扫描提示、安全预扫描、微信时间解析、试运行、AgentShield |
| `test_telegram.py` | 13 | 参数解析（布尔/值/别名/类型转换）、用户白名单 |

**Bug 修复**
- 修复 `gateway/security.py` 中的 fork 炸弹正则 — 未转义的 `(){}` 元字符导致模式永远无法匹配。
- 修复 `gateway/session_db.py` 中的 `upsert_instinct` — SELECT 查询缺少 `context` 列，导致空上下文重复 upsert 时出现 IndexError。
- 修复 `gateway/commands/admin.py` 中的 `_handle_newsession` — `set_session_title`（不存在的函数）→ `set_title`，且缺少 `generate_session_id()` 导致 UNIQUE 约束冲突。
- 修复 `gateway/commands/misc.py` 中的 `_extract_urls` — `_URL_RE` 类属性从未定义，导致每条纯文本消息触发 `AttributeError`。
- 修复 `/restart` 产生重复网关实例的问题 — 现在使用 `os.getpid()` 仅终止当前进程。
- 修复 `_extract_urls` 崩溃 — `_URL_RE` 类属性从未在 `MiscMixin` 上定义。

---

## 文档

| 文档 | 描述 |
|------|------|
| [交互](docs/interface.md) | 使用示例和交互模式 |
| [记忆](docs/memory.md) | 6 层记忆架构、自动召回、直觉评分 |
| [命令](docs/commands.md) | 全部 35 个命令及参数和示例 |
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
| [deer-flow](https://github.com/bytedance/deer-flow) | 并行子代理构建阶段、每候选隔离工作区、循环检测、记忆队列去抖动写入 |

---

MIT
