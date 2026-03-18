# agenticEvolve

**自己進化するAIエージェント — 毎日自動的に成長。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-33-orange?style=for-the-badge" alt="33 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-44-blue?style=for-the-badge" alt="44 Commands"></a>
</p>

**[English](README.md)** | **[简体中文](README.zh.md)** | **[繁體中文](README.zh-TW.md)**

---

`claude -p` 上に構築された永続エージェントランタイム。Python asyncioゲートウェイ搭載。6層メモリ + クロスレイヤー自動リコール。クローズドループスキル合成。音声入出力。ブラウザ自動化。組み込みcron。2層セキュリティ。マルチプラットフォーム（Telegram + Discord + WhatsApp）。Rich TUI搭載のインタラクティブCLI REPL。39のTelegramコマンド + 32のCLIコマンド — 開発環境をポケットに。

---

## 何ができるのか？

**代わりにウェブを閲覧**
> 「Anthropicのドキュメントに行って最新のClaudeモデルの料金を調べて。」エージェントがABPブラウザを開き、ナビゲートし、データを抽出し、簡潔なサマリーを送ってくれる。Cloudflareにブロックされたら自動でBraveに切り替え。

**WhatsAppとDiscordのグループでサービス提供**
> `/serve` → WhatsApp → グループ → 開発グループをオン。これでグループ内の誰でもAIエージェントと会話できる。すべてのメッセージに応答し、グループごとの会話メモリを維持し、すべてをTelegramのインラインキーボードで制御できる。Discordチャンネルも同様——エージェントがChrome DevTools Protocolを通じてデスクトップアプリに接続する。

**チャンネルをサブスクライブしてダイジェストを取得**
> `/subscribe` → Discord → よく見るチャンネルを選択。翌朝 `/discord` を実行すれば、見逃した内容の簡潔なサマリーが届く——主要な議論、共有されたリンク、言及されたツール、アクションアイテム。Discordチャンネル、WhatsAppグループ、WeChatグループに対応。500件の未読メッセージをスクロールする必要はもうない。

**自分のWeChatチャット履歴を検索**
> WeChatの内蔵検索はひどい。エージェントがローカルのWeChatデータベースを読み取り、検索可能なエクスポートを提供する——連絡先、メッセージ、グループ、お気に入り。すべてオフライン、すべて自分のマシン上。

**グループチャットからアイデアを寝ている間に吸収**
> 毎朝6時の `/evolve` cronはGitHubをスキャンするだけではない。WeChatの技術グループチャットも読み取り、過去24時間の議論を要約する——メンバーが言及した新ツール、共有されたリポジトリ、議論された技術——そして最良のアイデアをスキルとして吸収する。朝起きたら、グループの集合知がシステムに組み込まれている。

**トレンドシグナルからビジネスアイデアをブレインストーミング**
> `/produce` — エージェントが11のソース（GitHub Trending、Hacker News、X/Twitter、Reddit、Product Hunt、Lobste.rs、ArXiv、HuggingFace、BestOfJS、WeChatグループ、スター付きリポジトリ）から本日のシグナルを集約し、新興トレンドを特定し、収益モデル・技術スタック・MVPスコープを含む5つの具体的なアプリ/ビジネスアイデアをブレインストーミングする。オンデマンドのシグナル駆動アイデア創出。

**自己改善するUX**
> 毎晩午前1時、エージェントがその日の会話を読み、待ち時間が長すぎたり混乱する応答があった摩擦点を見つけ、自らのコードにパッチを当てて修正する。朝起きたら、より良いエージェントになっている。

**スマホからコードを書く**
> 地下鉄に乗っている。`/do APIにレート制限を追加` とメッセージを送る。エージェントがコードベースを読み、ミドルウェアを書き、テストを実行し、gitにプッシュする。駅に着く前にサマリーが届く。

**一つのメッセージで任意のリポジトリを吸収**
> Twitterでかっこいいリポジトリを見つけた。スクリーンショットをボットに送る。エージェントが画像をOCRし、GitHub URLを見つけ、リポジトリをクローンし、アーキテクチャをマッピングし、あなたのスタックに役立つパターンを抽出し、スキルとしてインストールする——写真一枚で完了。

**書いた覚えのない新スキルが朝には入っている**
> 毎朝6時に `/evolve` cronが自動で起動。Telegramを開く頃には、エージェントがGitHub Trendingをスキャンし、新しいテストフレームワークを発見し、スキルを構築し、2層セキュリティを通過させ、自動インストールし、リポジトリにプッシュしている。一晩で賢くなった。

**どんな言語でもコードベースと会話**
> 英語、広東語、北京語、日本語、韓国語、その他40以上の対応言語で音声メッセージを送信。エージェントがローカルのwhisper.cppで転写（約500ms）、言語を自動検出し、テキストで応答し、edge-ttsで同じ言語で読み上げてくれる。

**`/learn` で何でも深掘り**
> `/learn https://github.com/some/repo` — エージェントがクローンし、全ファイルを読み、アーキテクチャをマッピングし、ワークフローにどう役立つか評価し、ADOPT / ADAPT / SKIP の判定を出し、オプションでスキルを構築する。

---

## コア機能

| 機能 | 説明 |
|------|------|
| **CLI REPL** | `ae` — Rich TUI搭載のインタラクティブREPL。ストリーミング出力、Markdownレンダリング、ツール使用スピナー、Tabオートコンプリート対応の32コマンド、セッション永続化、自動リコール。ゲートウェイ不要 |
| **マルチプラットフォーム** | Telegram（Bot API）+ Discord（デスクトップCDP + REST）+ WhatsApp（Baileys v7ブリッジ）。`/subscribe` でチャンネルをモニタリングしてダイジェストを取得、`/serve` でエージェントが任意のグループやDMで応答 |
| **ビルド** | TelegramまたはCLI経由でフルClaude Code — ターミナル、ファイルI/O、Web検索、MCP、26スキル |
| **進化** | 5段階パイプライン：収集 → 分析 → 構築 → レビュー → 自動インストール。11ソースをスキャン：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChatグループ、スキルを合成 |
| **吸収** | `/absorb <url>` — リポジトリをクローン、アーキテクチャをマッピング、パターンを比較、改善をシステムに統合 |
| **学習** | `/learn <target>` — 深掘り抽出、ADOPT / ADAPT / SKIP の判定を出力 |
| **音声** | 音声メッセージ送信 → ローカルwhisper.cpp転写（~500ms）。`/speak` → edge-tts、300+音声。広東語/北京語/日本語/韓国語を自動検出 |
| **ブラウザ** | ABP（Agent Browser Protocol）をデフォルトブラウザとして使用。Cloudflareブロック時はBrave/Chrome（CDP）に自動切替。隔離されたエージェントプロファイル |
| **自動リコール** | 毎回の応答前に6層メモリに対して `unified_search()` を実行（~400 tokens/メッセージ） |
| **cron** | `/loop every 6h /evolve` — スケジュールに従い自律的に成長 |
| **セキュリティ** | L1：インストール前の正規表現スキャン（リバースシェル、認証情報窃取、暗号通貨マイナー）。L2：AgentShieldインストール後スキャン（1282テスト、102ルール）。重大な問題は自動ロールバック |
| **フック** | 型付き非同期イベントシステム — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **セマンティックリコール** | TF-IDFコサイン類似度検索レイヤーがFTS5キーワード検索を補強。5000特徴ベクトライザー、バイグラム対応。セッション、学習記録、直感、メモリファイルからコーパスを再構築。`~/.agenticEvolve/cache/` にキャッシュ |
| **直感エンジン** | 行動パターン観察がスコアリングされ直感テーブルにルーティング。高信頼度の直感（0.8以上、2プロジェクト以上または5回以上の観察）がMEMORY.mdに自動昇格 |
| **耐障害性** | シャットダウン時ドレイン（処理中リクエストを最大30秒待機）。型付き障害分類（認証/課金/レート制限）。3パスコンテキスト圧縮。ホットコンフィグリロード。ループ検出（3回同一ターンで警告、5回で終了）。メモリキュー読み透し（デバウンス原子書き込み、古いデータ読み取りなし）。並行BUILDステージ（ThreadPoolExecutor、3つの隔離ワークスペース） |
| **テスト** | 423の自動テスト（423パス、1 xfail）。カバレッジ：81のコマンドハンドラー統合テスト（全35+ハンドラー）、セッションDB、FTS5検索、セキュリティスキャナー、シグナル重複排除、セマンティック検索、直感昇格、cronパーサー、コスト上限、ループ検出、コンテキスト圧縮、フラグ解析 |

---

## セットアップ

### 1. インストール

```bash
curl -fsSL https://raw.githubusercontent.com/outsmartchad/agenticEvolve/main/scripts/install.sh | bash
```

インストーラーがすべてを処理します — クローン、依存関係、PATH設定、対話式セットアップウィザードの実行。前提条件はPython 3とgitのみ。

インストール後：

```bash
source ~/.zshrc    # シェルをリロード（または: source ~/.bashrc）
```

> **必要：** [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（`npm install -g @anthropic-ai/claude-code`）— インストーラーが存在を確認し、未インストールの場合はインストールコマンドを表示します。

### 2. インタラクティブチャット（CLI REPL）

```bash
ae
```

これだけです。ストリーミング出力、Markdownレンダリング、ツール使用スピナー、Tabオートコンプリート対応の32コマンドを備えたRich TUIが起動します。`ae --resume <session_id>` で前回のセッションを再開できます。

### 3. ゲートウェイを起動（Telegram/Discord/WhatsApp用）

```bash
ae gateway start
```

Telegramでボットにメッセージを送るか、WhatsAppグループやDiscordチャンネルでエージェントを活用しましょう。

### 便利なコマンド

| コマンド | 機能 |
|----------|------|
| `ae` | インタラクティブチャットREPL（デフォルト） |
| `ae --resume ID` | 前回のセッションを再開 |
| `ae setup` | セットアップウィザードを再実行 |
| `ae doctor` | 問題を診断 |
| `ae gateway start` | メッセージングゲートウェイを起動 |
| `ae gateway stop` | ゲートウェイを停止 |
| `ae gateway install` | launchdサービスとしてインストール（ログイン時に自動起動） |
| `ae status` | システム概要 |
| `ae cost` | 使用量とコスト |

### 音声サポート（オプション）

```bash
brew install whisper-cpp ffmpeg
curl -L -o ~/.agenticEvolve/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

---

## コマンド

すべてのコマンドはCLI REPL（`ae`）とTelegramの両方で動作します。CLI REPLでは全コマンドのTabオートコンプリートと説明が利用可能です。

### コア

| コマンド | 機能 |
|----------|------|
| _(任意のメッセージ)_ | Claude Codeとチャット |
| _(音声メッセージ)_ | 自動転写（whisper.cpp）+ 応答（Telegramのみ） |

### パイプライン（LLM連携）

| コマンド | 機能 |
|----------|------|
| `/evolve [--dry-run]` | シグナルをスキャン、スキルを構築・自動インストール |
| `/absorb <url>` | 任意のリポジトリからパターンを吸収 |
| `/learn <target>` | ADOPT/STEAL/SKIPの判定付き深掘り分析 |
| `/produce [--ideas N]` | 全シグナルからビジネスアイデアをブレインストーミング |
| `/reflect [--days N]` | 自己分析：パターン、回避行動、次のアクション |
| `/digest [--days N]` | 朝のブリーフィング（セッション、シグナル、コスト） |
| `/gc [--dry-run]` | ガベージコレクション（古いセッション、孤立データ） |
| `/wechat [--hours N]` | WeChatグループチャットダイジェスト（ローカルDB読み取り） |
| `/discord [--hours N]` | Discordチャンネルダイジェスト（保存済みメッセージから） |
| `/whatsapp [--hours N]` | WhatsAppグループダイジェスト（保存済みメッセージから） |

### 情報

| コマンド | 機能 |
|----------|------|
| `/recall <query>` | クロスレイヤー検索（全6層メモリ） |
| `/search <query>` | FTS5セッション履歴検索 |
| `/memory` | MEMORY.md + USER.md を表示 |
| `/soul` | SOUL.md パーソナリティを表示 |
| `/config` | config.yaml 設定を表示 |
| `/skills` | インストール済みスキル一覧（26個） |
| `/learnings [query]` | 過去の学習記録を一覧・検索 |
| `/sessions [N]` | 最近のセッション一覧 |
| `/cost` | 使用量とコスト |
| `/status` | システム概要 |
| `/heartbeat` | クイックヘルスチェック |

### cron

| コマンド | 機能 |
|----------|------|
| `/loop <interval> <prompt>` | 定期実行をスケジュール（例：`/loop 6h /evolve`） |
| `/loops` | アクティブなcronジョブを一覧 |
| `/unloop <id>` | cronジョブを削除 |
| `/pause <id\|--all>` | cronジョブを一時停止 |
| `/unpause <id\|--all>` | cronジョブを再開 |
| `/notify <delay> <msg>` | ワンショット遅延通知 |

### 管理

| コマンド | 機能 |
|----------|------|
| `/model [name]` | モデルの表示または切り替え |
| `/autonomy [level]` | 自律レベルの表示または設定（full/supervised/locked） |
| `/new` | 新しいセッションを開始 |
| `/queue` | 承認待ちスキルを表示 |
| `/approve <name>` | キュー内のスキルを承認 |
| `/reject <name>` | キュー内のスキルを拒否 |

### Telegram専用

| コマンド | 機能 |
|----------|------|
| `/speak <text>` | テキスト→音声変換（edge-tts、言語自動検出） |
| `/do <instruction>` | 自然言語 → 構造化コマンド |
| `/subscribe` | ダイジェスト用にモニタリングするチャンネルを選択 |
| `/serve` | エージェントが応答するチャンネル/連絡先を選択 |
| `/lang [code]` | 持続的な出力言語を設定 |
| `/restart` | ゲートウェイをリモート再起動 |

[全コマンド →](docs/commands.md)

---

## アーキテクチャ

```
ユーザー (CLI REPL / Telegram / Discord / WhatsApp / 音声)
  → ゲートウェイ (asyncio) または CLI (スタンドアロン) → フックディスパッチャー → セッション + コスト制御
  → 自動リコール (6層) → claude -p → SQLite → Git同期
```

カスタムエージェントループなし。Claude Codeが**そのまま**ランタイム — 25+組み込みツール、MCPサーバー、スキル。ゲートウェイがその周囲にメモリ、ルーティング、リコール、cron、音声、ブラウザ、マルチプラットフォーム、セキュリティを追加する。CLI REPL（`ae`）はゲートウェイを完全にバイパスし、同じメモリ・リコール・セッション基盤で `claude -p` を直接呼び出す。

### 設計上の重要な決定
- **ツールシステムを作らない** — Claude Code自体がツールを持つ。スキルとインフラを構築し、抽象化層は作らない。
- **有界メモリ** — MEMORY.md（2200文字）+ USER.md（1375文字）+ SQLite FTS5。無制限な増加なし。
- **クローズドループ** — `auto_approve_skills: true`。進化 → 構築 → レビュー → インストール → gitに同期。人手による承認なし。
- **シャットダウン時ドレイン** — 処理中のリクエストは再起動前に完了。作業の損失なし。
- **モジュラーコマンド** — 39のTelegramコマンドを9つのmixin（admin、pipelines、signals、cron、approval、search、media、misc、subscribe）に分割。32コマンドをCLI REPL用に再実装。アダプターコアは630行。
- **二層リコール** — FTS5キーワード検索 + TF-IDFセマンティック検索。自動リコールが毎回のClaude呼び出し前に関連コンテキストを注入。
- **直感パイプライン** — セッション間で観察された行動パターンがスコアリング・重複排除され、信頼度が十分に高い場合にMEMORY.mdに自動昇格。

---

## 音声パイプライン

| 方向 | 技術 | レイテンシ | コスト |
|------|------|-----------|--------|
| **音声 → テキスト** | ローカルwhisper.cpp（ggml-small多言語モデル） | Apple Siliconで~500ms | 無料 |
| **テキスト → 音声** | edge-tts（300+ニューラル音声） | ~1秒 | 無料 |
| **言語検出** | CJKヒューリスティック（嘅係唔 → 広東語、ひらがな → 日本語） | 即時 | 無料 |

自動TTSモード：`off`（`/speak`のみ）、`always`（毎回の応答）、`inbound`（ユーザーが音声を送信した場合に音声で返信）。

---

## ブラウザ自動化

| ブラウザ | 使用場面 | 方式 |
|----------|----------|------|
| **ABP**（デフォルト） | すべてのエージェントブラウジング | 組み込みChromium、アクション間JSフリーズ、Mind2Web 90.5% |
| **Brave** | ユーザー指定 / CloudflareがABPをブロック | CDPポート9222、隔離プロファイル |
| **Chrome** | ユーザー指定 / CloudflareがABPをブロック | CDPポート9223、隔離プロファイル |

エージェントプロファイルは `~/.agenticEvolve/browser-profiles/` にサンドボックス化 — ユーザーの実ブラウザデータには一切触れない。

---

## セキュリティ

| レイヤー | ツール | タイミング | 重大問題時 |
|----------|--------|-----------|-----------|
| **L1** | `gateway/security.py` | インストール前：生ファイルをスキャン | ブロック + パイプライン中止 |
| **L2** | AgentShield（1282テスト） | インストール後：`~/.claude/` 設定をスキャン | インストール済みスキルを自動ロールバック |

スキャン対象：認証情報窃取、リバースシェル、難読化ペイロード、暗号通貨マイナー、macOS永続化、プロンプトインジェクション、npmフック悪用。

---

## スケジュールされたcronジョブ

4つの自律ジョブが毎日実行 — 人手によるトリガー不要。

| ジョブ | スケジュール（HKT） | 内容 |
|--------|-------------------|------|
| **evolve-daily** | 6:00 AM | 11ソースからシグナルを収集：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChatグループ、候補をスコアリング、最大3つの新スキルを構築、セキュリティレビュー、自動インストール、gitにプッシュ |
| **daily-digest** | 8:00 AM | 朝のブリーフィング — トップシグナル、構築済みスキル、セッション数、コストサマリー。Telegramに配信 |
| **wechat-digest** | 9:00 AM | 毎日のWeChatグループチャットダイジェスト — 議論内容、言及されたツール、技術グループからの重要なインサイトを要約。Telegramに配信 |
| **daily-ux-review** | 1:00 AM | その日の会話を読み、摩擦点を発見、トップ3のUX改善を特定、直接実装 |

`/loop`、`/loops`、`/unloop`、`/pause`、`/unpause` で管理。設定ファイル：`cron/jobs.json`。

---

## シグナルソース（12個）

| ソース | コレクター | API | 収集内容 |
|--------|-----------|-----|----------|
| GitHub Search | `github.sh` | GitHub API (gh CLI) | キーワード別トレンドリポジトリ、スター付きリポジトリの活動、リリース監視 |
| GitHub Trending | `github-trending.py` | GitHub API (gh CLI) | 過去7日間に作成されたホットな新リポジトリ |
| Hacker News | `hackernews.sh` | Algolia API | キーワード検索 + フロントページ + Show HN |
| X / Twitter | `x-search.sh` | Brave Search API | オープンソース、開発ツール、AIに関するバイラルツイート |
| Reddit | `reddit.py` | Pullpush.io API | 13のサブレディット：LocalLLaMA、programming、ClaudeAI等 |
| Product Hunt | `producthunt.py` | RSS/Atom feed | 開発ツール + AI製品のローンチ |
| Lobste.rs | `lobsters.py` | JSON API | 厳選された技術ニュース（高い信号対雑音比） |
| ArXiv | `arxiv.py` | ArXiv API | cs.AI、cs.CL、cs.SE、cs.LGの論文 |
| HuggingFace | `huggingface.py` | HF API | トレンドモデルとSpaces |
| BestOfJS | `bestofjs.py` | Static JSON API | 日次スター増加数によるJavaScript/TypeScriptプロジェクトのトレンド |
| WeChat | `wechat.py` | Local DB | グループチャットメッセージ（ローカルデータを読み取り） |

---

## スキル（26個インストール済み）

| スキル | 用途 |
|--------|------|
| agent-browser-protocol | MCP経由のABPブラウザ自動化 |
| browser-switch | マルチブラウザCDP切替（Brave/Chrome） |
| brave-search | Brave API経由のWeb検索 |
| firecrawl | Webスクレイピング、クロール、検索、構造化抽出 |
| cloudflare-crawl | Cloudflare Browser Rendering API経由の無料Webクロール |
| jshook-messenger | jshookmcp MCP経由のDiscord/WeChat/Telegram/Slack傍受 |
| wechat-decrypt | macOS上でローカルWeChatデータベースを読み取り、メッセージ・連絡先・グループをエクスポート |
| session-search | FTS5セッション履歴検索 |
| cron-manager | cronジョブ管理 |
| skill-creator | Anthropic公式スキル作成 |
| deep-research | マルチソースリサーチパイプライン |
| market-research | 市場/競合分析 |
| article-writing | 長文コンテンツ作成 |
| video-editing | FFmpeg動画編集ガイド |
| security-review | コードセキュリティチェックリスト |
| security-scan | AgentShield設定スキャナー |
| autonomous-loops | 自律型エージェントループ |
| continuous-learning-v2 | パターン抽出パイプライン |
| eval-harness | スキル評価フレームワーク |
| claude-agent-sdk-v0.2.74 | Claude Agent SDKパターン |
| nah | クイック拒否/取消 |
| unf | 圧縮コンテンツの展開/拡張 |
| next-ai-draw-io | 自然言語からアーキテクチャ図を生成 |
| mcp-elicitation | タスク中のMCPダイアログを傍受し無人パイプラインを実現 |
| skill-gap-scan | ローカルスキルとコミュニティカタログを比較し採用ギャップを発見 |
| context-optimizer | `/context` ヒントに基づいて古いメモリファイルを自動圧縮 |

---

## 最近の変更

### v2.7 — IronClaw導入（フェーズ1-6）

**フェーズ1：スマートモデルルーティング**
- 13次元の正規表現複雑度スコアラー（コードパターン、会話の深さ、マルチステップ推論など）
- メッセージごとに自動でSonnet/Opusをルーティング — APIコストを1日$10-20節約
- カスケード検出：Sonnetが不確実な応答を返した場合、推論モデルで再呼び出し

**フェーズ2：プロバイダーチェーン**
- Retry → CircuitBreaker → Cacheデコレーターパターン（IronClawのプロバイダーチェーンアーキテクチャ）
- 指数バックオフ付き自動リトライ
- サーキットブレーカーによるカスケード障害の防止
- 繰り返しクエリに対するレスポンスキャッシュ

**フェーズ3：セキュリティ強化**
- `credential_guard.py`：LeakDetectorが.envシークレットをスキャン（生データ、base64、URLエンコード）
- 二層出力リダクション（credential_guard + redact.py）
- コンテンツサニタイザーを全プラットフォームに接続（以前はWhatsAppのみ）
- サンドボックス拒否パターンをプロンプトに注入

**フェーズ4：可用性アップグレード**
- WhatsAppメッセージの並行処理（シリアルから`Semaphore(5)`に変更）
- イベントバス（pub/sub）、デフォルトトリガー付き（コストアラート、エラー連続、再接続）
- ハートビートヘルスモニタリング、自動無効化通知対応
- 全19フックが接続完了（以前は5つが未接続）

**フェーズ5：メモリアップグレード**
- sentence-transformersによるベクトル埋め込み（all-MiniLM-L6-v2、ローカル実行、API呼び出しなし）
- ハイブリッド検索：FTS5 + 埋め込み + RRFフュージョンランキング
- LLM要約によるコンテキスト圧縮（トランケーションを置き換え）
- メモリ統合：制限超過時にSonnetを使ってMEMORY.mdを自動プルーニング
- メモリダッシュボードページ（検索、統計、埋め込みステータス）

**フェーズ6：自己拡張エンハンスメント**
- SubagentOrchestratorがevolve BUILDステージにフック（オブザーバビリティ）
- `skill_metrics`テーブル：使用状況、評価、陳腐化スキルを追跡
- バックグラウンド`/learn`：BackgroundTaskManagerによるノンブロッキング実行

**統計：** テスト822件パス（以前は約700件）。新規モジュール10個。スマートルーティングにより1日$10-20の節約見込み。

### v2.6 — セキュリティ、オブザーバビリティ、プラットフォーム統一
- **コンテンツサニタイザー**：ランダム化された境界マーカーとUnicode同形文字フォールディングによるプロンプトインジェクション防御（OpenClawより改編）
- **ログリダクション**：17の正規表現パターンにより、全ログ出力からAPIキー、トークン、PEMブロックを自動除去
- **リトライユーティリティ**：一時的な障害に対する指数バックオフ + ジッター、Telegramリトライヘルパー
- **ローリングログ**：RotatingFileHandler（50MB、5バックアップ）が無制限なログファイルを置き換え
- **ツールループ検出器**：4モード検出（汎用リピート、ポーリング無進捗、ピンポン、グローバルサーキットブレーカー）で暴走セッションを防止
- **セキュリティ自己監査**：`/doctor` コマンドで環境権限、設定シークレット、コスト上限、依存関係、サンドボックスの健全性、DB整合性をチェック
- **診断イベントバス**：型付きイベント（メッセージ、使用量、セッション、ループ、ハートビート）、JSONLシンクとステータスサマリー対応
- **WhatsAppコマンド**：`/cost`、`/status`、`/doctor`、`/help` がWhatsAppで利用可能に
- **音声パイプライン修正**：長時間音声のチャンキング（48分 → 10分チャンク）、OGG→WAV変換、3層重複排除、音声のフォースリプライ、2部構成応答（転写 + 要約）
- **セキュリティ修正**：CLI/TUIでの環境変数サニタイズ、動的オーナーパス、サーブグループのコンテンツラッピング

### v2.5 — セキュリティ + インテリジェンス + プラグインシステム

**フェーズ1：セキュリティ + コスト保護**
- 環境変数サニタイズ — `claude -p` から30以上のシークレットパターンを除去し、プロンプトによる認証情報漏洩を防止。
- ユーザーごとのスライディングウィンドウレート制限（5回/分、30回/時間、設定可能）。
- `[NO_REPLY]` トークン — エージェントがグループ内の無関係なメッセージをスキップ可能。
- メッセージデバウンス — サーブチャンネルの高速メッセージをバッチ処理（2.5秒ウィンドウ、8秒最大待機）。
- `@agent <prompt>` トリガー — グループ+DMで誰でも利用可能、引用返信コンテキストとブラウザMCP対応。
- Dockerサンドボックス — サーブチャットの分離されたPython実行環境（`--network=none`、`--cap-drop=ALL`、512MBメモリ）。

**フェーズ2：UX + 効率**
- Telegramストリーミング — インプレース編集、1.5秒スロットル更新と「...」プレースホルダー。
- コンテキストウィンドウ管理 — トークン推定、60%/85%閾値での自動圧縮。
- ID連携 — `/link` と `/whoami` コマンドでクロスプラットフォームのユーザーID解決。

**フェーズ3：インテリジェンス**
- 19フックポイントのプラグインシステム。優先度順序、マージ関数、O(1) `has_hooks()` チェック対応。
- プラグインローダー — `~/.agenticEvolve/plugins/` から検出・ロード。各プラグインは `register(hooks, config)` をエクスポート。
- バックグラウンドタスクマネージャー — 分離された長時間実行タスク、進捗追跡付き。`/tasks` と `/cancel` コマンド。
- サブエージェントオーケストレーター — 汎用マルチClaude実行：`run_parallel`、`run_pipeline`、`run_dag`（依存関係グラフ）。

**フェーズ4：ポリッシュ**
- ゲートウェイ実行モード — ホスト実行、3段階セキュリティ（deny/allowlist/full）、設定可能な承認（off/on-miss/always）。60以上の安全バイナリ自動承認、13の拒否リストパターンで危険なコマンドをブロック。
- 設定検証 — 適用前のセマンティックチェック。`/reload` コマンド（検証 + `config_reload` フック付き）。
- `/allowlist` コマンドで実行許可リスト管理。`/hooks` コマンドで登録済みフックリスナーを確認。
- テスト合計556件（すべてパス）。

### v2.3 — CLI REPL + WhatsApp LID解決

**インタラクティブCLI REPL（`ae`）**
- `ae` でスタンドアロンのRich TUI REPLが起動 — ゲートウェイプロセス不要。ストリーミング出力、Markdownレンダリング、ツール使用スピナー、コストトラッキング搭載。
- Tabオートコンプリートと説明付きの32スラッシュコマンド。全パイプラインコマンド（`/produce`、`/evolve`、`/learn`、`/absorb`、`/reflect`、`/digest`、`/gc`）、情報コマンド（`/memory`、`/soul`、`/config`、`/skills`、`/learnings`、`/recall`、`/search`、`/sessions`）、cron管理（`/loop`、`/loops`、`/unloop`、`/pause`、`/unpause`、`/notify`）、管理コマンド（`/model`、`/autonomy`、`/queue`、`/approve`、`/reject`）。
- セッション永続化 — すべてのメッセージが自動タイトル付きでSQLiteに保存。`ae --resume <session_id>` で前回のセッションを再開。
- 毎回の呼び出し前に全6メモリ層から自動リコール。コスト上限の強制。
- prompt-toolkit入力、ファイルバック履歴、自動サジェスト。

**WhatsApp LID JID解決**
- Baileys v7がDMメッセージをLID JID（`@lid`）で配信し、電話番号JID（`@s.whatsapp.net`）ではない重大なバグを修正。ブリッジが起動時に `lid-mapping-*_reverse.json` ファイルを読み込み、受信メッセージ・送信メッセージ・履歴同期でLID→電話番号を解決するように変更。
- 以前は、`85254083858` のようなサーブ対象の連絡先が、PythonがLID JIDを電話番号ベースのサーブターゲットとマッチングできなかったため、無言で破棄されていた。

**WhatsApp DM連絡先のサーブ対応**
- `/serve` が個別のWhatsApp連絡先（グループだけでなく）をサポート。`_serve_groups` に加えて `_serve_contacts` セットを追加。サーブ対象連絡先の `allowed_users` をバイパスするようDMルーティングを更新。

**WhatsAppメディアサポート**
- 受信WhatsApp画像、ドキュメント（PDF、TXT、CSVなど）、音声メッセージをBaileysの `downloadMediaMessage` でダウンロードし、`/tmp/` に保存、Claude Codeに渡して分析。メディア付きメッセージは自動的にopusモデルにエスカレーション。

**自動モデルエスカレーション**
- 数学、コーディング、ロジック問題を含むメッセージを正規表現で自動検出し、デフォルトの `serve_model`（sonnet）ではなく `serve_reasoning_model`（opus）にルーティング。画像・ファイルメッセージもエスカレーションをトリガー。

**チャンネル固有ナレッジ**
- `run.py` の `_CHANNEL_KNOWLEDGE` ディクショナリがチャンネル/グループIDをエキスパートナレッジプロンプトにマッピング。DiscordとWhatsAppのサーブチャンネルで、パーソナリティプロンプトの後に注入。degen-damm DiscordチャンネルでのDAMM v2エキスパティーズに使用。

### v2.2 — マルチプラットフォーム + サブスクライブ/サーブ

**マルチプラットフォーム対応**
- **Discordデスクトップアダプター**（`gateway/platforms/discord_client.py`）— Chrome DevTools Protocol（CDP）を通じて実行中のDiscordデスクトップアプリに接続。ネットワークリクエストから認証トークンを抽出し、Discord REST APIでメッセージング。ギルドリスト、チャンネルリスト（カテゴリ別グループ化）、DMチャンネル、メッセージポーリングをサポート。
- **WhatsAppブリッジ**（`whatsapp-bridge/bridge.js`）— Baileys v7 Node.jsブリッジ、stdin/stdout経由のJSON通信。QRコードをTelegramに配信してスキャンを容易に。送信メッセージのLIDから電話番号への解決。グループプレフィックスフィルタリング（`/ask`、`@agent`）。認証ストアのlid-mappingファイル + ライブメッセージトラッキングから連絡先を検出。
- **WeChat** — 復号化されたローカルSQLCipherデータベースへの読み取り専用アクセス。グループと連絡先は `contact.db` から、メッセージは `message_0.db` から。

**サブスクライブとサーブコマンド**
- `/subscribe` — Telegramインラインキーボードでのチャンネル選択UI。Discordチャンネル、WhatsAppグループ/連絡先、WeChatグループをダイジェスト用に選択。ページネーション（1ページ40件）、Discordはカテゴリヘッダー付き。WhatsAppはグループ/連絡先のサブビューに分割。
- `/serve` — 同じUI、エージェントが積極的に応答する場所を選択。WhatsAppのサーブグループはすべてのメッセージを受け入れ（プレフィックス不要、allowed_usersゲートなし）。サーブターゲットはゲートウェイ起動時にDBからロード。切り替え時にアダプターを動的に更新。
- **サブスクリプションDB** — session_dbの `subscriptions` テーブル。user_id、platform、target_id、target_name、target_type、modeを含む。CRUD関数：`add_subscription`、`remove_subscription`、`get_subscriptions`、`get_serve_targets`、`is_subscribed`。
- **ショートIDレジストリ** — Telegramの `callback_data` は64バイト制限。長いWhatsApp JID（`120363427198529523@g.us`）やWeChatチャットルームIDは制限を超過。解決策：メモリ内数値IDマップ（`sub:toggle:whatsapp:group:120363...` の代わりに `sub:t:3`）。

### v2.1 — モジュラーアーキテクチャ + セマンティックリコール + テストハーネス

**アーキテクチャ**
- `telegram.py` を3870行から8つのコマンドmixin（`gateway/commands/`）に分割：admin、pipelines、signals、cron、approval、search、media、misc。アダプターコアを630行に削減。
- ユーザーごとの言語設定（`/lang`）をSQLite `user_prefs` テーブルに永続化。
- evolveパイプラインでのクロスソースシグナル重複排除（URL + タイトルマッチング）。
- コレクターリトライ、5秒指数バックオフ。

**セマンティック検索 + 直感エンジン**
- TF-IDFコサイン類似度検索レイヤーがFTS5キーワード検索を補強。`unified_search()` が両レイヤーをクエリ。
- 直感自動昇格：高信頼度の行動パターン（信頼度 >= 0.8、2プロジェクト以上または5回以上の観察）がセッションクリーンアップ時にMEMORY.mdに自動昇格。
- セマンティックコーパスをセッション、学習記録、直感、メモリファイルから再構築。高速リロードのためpickleとしてキャッシュ。

**テストハーネス — 423テスト（423パス、1 xfail）**

| テストファイル | テスト数 | カバレッジ |
|----------------|----------|-----------|
| `test_commands.py` | 81 | 全35+コマンドハンドラー：admin、pipelines、signals、cron、approval、search、media、misc + 30の認可拒否テスト |
| `test_session_db.py` | 25 | セッション、メッセージ、FTS5検索、学習記録、ユーザー設定、直感、統計 |
| `test_security.py` | 28 | 重大パターン（リバースシェル、fork爆弾、マイナー）、警告、プロンプトインジェクション、安全なコンテンツ、ディレクトリスキャン |
| `test_evolve.py` | 72 | シグナル読み込み、ランキング、URL/タイトル重複排除、エッジケース、コレクター、スキル承認/拒否、ハッシュ検証、キュー、レポート |
| `test_agent.py` | 27 | stderr分類、履歴圧縮（3パスカスケード）、タイトル生成、ループ検出 |
| `test_semantic.py` | 11 | コーパス構築（セッション、学習、直感）、検索関連性、キャッシュ、スコアフィルタリング |
| `test_instincts.py` | 8 | コンテキストバグ回帰、自動昇格（昇格、重複排除、文字制限） |
| `test_gateway.py` | 10 | cronパーサー（毎回/特定/ステップ/日跨ぎ）、セッションキー、コスト上限 |
| `test_voice.py` | 57 | TTS設定、言語検出、音声フォーマット変換、STT転写、TTSディレクティブ |
| `test_absorb.py` | 49 | コンストラクター、レポート、スキャンプロンプト、セキュリティプリスキャン、WeChat時間解析、ドライラン、AgentShield |
| `test_telegram.py` | 13 | フラグ解析（bool/値/エイリアス/キャスト）、ユーザー許可リスト |

**バグ修正**
- `gateway/security.py` のfork爆弾正規表現を修正 — エスケープされていない `(){}` メタ文字がパターンを常にマッチ不能にしていた。
- `gateway/session_db.py` の `upsert_instinct` を修正 — SELECTクエリに `context` カラムが欠落しており、空コンテキストでの繰り返しupsert時にIndexErrorが発生していた。
- `gateway/commands/admin.py` の `_handle_newsession` を修正 — `set_session_title`（存在しない関数）→ `set_title`、および `generate_session_id()` の欠落がUNIQUE制約違反を引き起こしていた。
- `gateway/commands/misc.py` の `_extract_urls` を修正 — `_URL_RE` クラス属性が未定義で、すべてのプレーンテキストメッセージで `AttributeError` が発生していた。
- `/restart` が重複ゲートウェイインスタンスを生成する問題を修正 — `os.getpid()` を使用して現在のプロセスのみを終了するように変更。
- `_extract_urls` のクラッシュを修正 — `_URL_RE` クラス属性が `MiscMixin` 上で未定義だった。

---

## ドキュメント

| ドキュメント | 説明 |
|-------------|------|
| [インターフェース](docs/interface.md) | 使用例とインタラクションパターン |
| [メモリ](docs/memory.md) | 6層メモリアーキテクチャ、自動リコール、直感スコアリング |
| [コマンド](docs/commands.md) | 全35コマンドのフラグと使用例 |
| [パイプライン](docs/pipelines.md) | Evolve、Absorb、Learn、Do、GCパイプライン |
| [スキル](docs/skills.md) | 完全スキルカタログ |
| [セキュリティ](docs/security.md) | スキャナー、自律レベル、セーフティゲート |
| [アーキテクチャ](docs/architecture.md) | メッセージフロー、プロジェクト構造、設計決定 |
| [ロードマップ](docs/roadmap.md) | 統合計画 — Firecrawl、ビジョン、サンドボックス |

---

## 系譜

| プロジェクト | 採用したパターン |
|-------------|-----------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | エージェントランタイム — 25+ツール、MCP、スキル、サブエージェント |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 有界メモリ、セッション永続化、メッセージングゲートウェイ、プログレッシブステータスメッセージ |
| [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) | 自律レベル、デフォルト拒否、ホットコンフィグリロード、リスク階層分類 |
| [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | 9スキル改編、AgentShieldセキュリティ、評価駆動開発、フックプロファイル |
| [openclaw](https://github.com/openclaw/openclaw) | 音声パイプライン（TTS/STT）、ブラウザ自動化パターン、自動TTSモード |
| [ABP](https://github.com/theredsix/agent-browser-protocol) | ブラウザMCP — アクション間フリーズChromium、Mind2Web 90.5% |
| [deer-flow](https://github.com/bytedance/deer-flow) | 並行サブエージェントBUILDステージ、候補ごとの隔離ワークスペース、ループ検出、メモリキューデバウンス書き込み |

---

MIT
