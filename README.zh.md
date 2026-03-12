# agenticEvolve

一个个人闭环智能体系统，从开发者平台采集信号，分析有用的工具和模式，自动构建 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 技能，每天持续进化你的开发能力。

编排层很简单（约 150 行 bash）。智能在 LLM 提示词里。

```
┌─────────────────────────────────────────────────────────────────┐
│                       外层循环 (cron)                            │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  信号         │  │  分析         │  │  技能         │         │
│  │  采集器       │→ │  智能体       │→ │  构建器       │         │
│  │  (bash/curl)  │  │  (claude -p) │  │  (claude -p) │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         ↑                                    ↓                  │
│         │            ┌──────────────┐  ┌──────────────┐        │
│         └────────────│  记忆         │←─│  审查器       │        │
│                      │  (4 个文件)   │  │  (claude -p) │        │
│                      └──────────────┘  └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

## 工作原理

每个周期（通过 cron 每 2 小时执行一次）：

1. **采集** — bash 脚本从 GitHub、Hacker News 和 X/Twitter 拉取信号
2. **分析** — 一个全新的 `claude -p` 调用读取信号，挑选最具可操作性的单个项目
3. **构建** — 一个全新的 `claude -p` 调用根据最优行动项构建一个 Claude Code 技能
4. **审查** — 一个全新的 `claude -p` 调用（只读）验证安全性、质量和正确性
5. **通知** — 通过 Telegram 发送消息，附带批准/拒绝按钮

每个阶段都是**无状态的 Claude 调用**。没有会话延续。如果某个周期出了问题，下一个周期会从头开始。

## 核心设计决策

- **每周期一个任务** — 防止范围蔓延
- **每周期全新上下文** — 不使用 `--resume`，不保持会话
- **双层记忆** — `state.md`（精选知识，每周期优先读取）+ `log.md`（原始日志，仅追加）
- **技能三道门** — 自动审查智能体、队列、人工审核
- **成本上限** — 每天 $5，每周 $25（可配置）

## 项目结构

```
.
├── ae                      # CLI 入口（人类和智能体共用的单一命令）
├── config.sh               # 配置（成本上限、API 密钥、目录）
├── run-cycle.sh            # 主循环编排器（约 150 行）
├── run-gc.sh               # 每周垃圾回收
├── notify.sh               # Telegram 通知（带内联键盘）
├── telegram-listener.sh    # 轮询批准/拒绝按钮回调
├── collectors/
│   ├── github.sh           # 热门仓库、星标活动、发布（通过 gh CLI）
│   ├── hackernews.sh       # 关键词搜索 + Show HN（通过 Algolia API）
│   └── x-search.sh         # X/Twitter 信号（通过 Brave Search API）
├── prompts/
│   ├── initialize.md       # 一次性初始化智能体
│   ├── analyze.md          # 信号分析智能体
│   ├── build-skill.md      # 技能构建智能体
│   ├── review-skill.md     # 技能审查智能体（只读）
│   └── gc.md               # 垃圾回收智能体
├── memory/
│   ├── state.md            # 精选知识（每周期优先读取）
│   ├── log.md              # 仅追加的原始日志
│   ├── action-items.md     # 任务跟踪（复选框格式）
│   └── watchlist.md        # 监控的账号、关键词和筛选条件
├── signals/                # 原始采集信号（每日 JSON，已 gitignore）
├── skills-queue/           # 等待人工审核的技能（已 gitignore）
├── logs/                   # 周期日志 + cost.log（已 gitignore）
├── BUILD-PLAN.md           # 完整架构和设计决策
└── VISION.md               # 原始愿景和参考项目
```

## 安装

### 前置条件

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)（`npm install -g @anthropic-ai/claude-code`）
- [GitHub CLI](https://cli.github.com/)（`gh`）— 已登录
- `jq` 和 `curl`
- （可选）Brave Search API 密钥，用于 X/Twitter 信号采集
- （可选）Telegram 机器人，用于通知

### 安装步骤

```bash
# 克隆
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve

# 创建 CLI 软链接
mkdir -p ~/.local/bin
ln -sf ~/.agenticEvolve/ae ~/.local/bin/ae

# 确保 ~/.local/bin 在你的 PATH 中
# 如有需要，添加到 ~/.zshrc 或 ~/.bashrc：
# export PATH="$HOME/.local/bin:$PATH"

# 初始化（填充记忆文件，验证采集器）
ae init
```

### 配置（可选）

编辑 `~/.agenticEvolve/config.sh`：

```bash
# 成本上限
DAILY_CAP=5        # 每天美元上限
WEEKLY_CAP=25      # 每周美元上限

# Telegram 机器人（通过 @BotFather 创建）
TELEGRAM_BOT_TOKEN="your-token"
TELEGRAM_CHAT_ID="your-chat-id"

# Brave Search API（用于 X/Twitter 信号采集）
BRAVE_API_KEY="your-key"
```

## 使用方法

```bash
# 运行一个完整周期（采集 → 分析 → 构建 → 审查）
ae cycle

# 仅采集信号
ae collect              # 所有来源
ae collect github       # 仅 GitHub
ae collect hackernews   # 仅 HN

# 查看系统状态
ae status

# 交互式审核排队中的技能
ae review

# 批准或拒绝特定技能
ae approve <skill-name>
ae reject <skill-name>

# 查看记忆
ae state                # 精选知识
ae log 20               # 原始日志最后 20 行
ae watchlist            # 监控的账号/关键词

# 成本追踪
ae cost                 # 明细（今天 / 本周 / 累计）
ae cost check           # 未超限返回 0，超限返回 1

# 管理监控列表
ae watchlist add github anthropics
ae watchlist rm github anthropics

# 定时任务管理
ae start                # 启用（每 2 小时循环，每周 GC）
ae stop                 # 停用
ae pause 4              # 暂停 4 小时
```

## 信号采集器

| 来源 | 方式 | 是否需要认证 |
|------|------|-------------|
| GitHub | `gh` CLI（搜索 API、星标仓库、发布） | GitHub CLI 认证 |
| Hacker News | Algolia API | 不需要 |
| X/Twitter | Brave Search（`site:x.com`） | Brave API 密钥 |
| Discord | 计划中（第二阶段） | — |
| 企业微信/微信 | 计划中（第二阶段） | — |
| WhatsApp | 计划中（第二阶段） | — |

## 技能构建流程

1. 采集器发现信号（例如热门仓库或 HN 上关于新开发工具的帖子）
2. 分析器从相关性、可操作性和新颖性三个维度打分 — 选出最优项
3. 构建器创建 Claude Code 技能（带 YAML frontmatter 的 `SKILL.md`），放入 `skills-queue/`
4. 审查器验证安全性（无硬编码密钥）、质量（指令清晰、不超过 100 行）和正确性
5. 审查通过后，通过 Telegram 发送给人工审批
6. 人工批准 → 技能迁移到 `~/.claude/skills/`，在所有未来的 Claude Code 会话中可用

## 灵感来源

- [snarktank/ralph](https://github.com/snarktank/ralph) — 主要灵感（113 行 bash 编排器，双层学习，每周期全新上下文）
- [Anthropic 的编排工程研究](https://www.anthropic.com/) — 初始化智能体模式，内/外层循环框架
- [OpenAI 的多智能体模式](https://openai.com/) — 确定性检查器，挣扎即信号反馈循环

## 许可证

私有项目。禁止分发。
