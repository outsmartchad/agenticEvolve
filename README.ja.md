# agenticEvolve

**開発能力を毎日自動進化させるパーソナル・クローズドループ・エージェントシステム。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-23-orange?style=for-the-badge" alt="23 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-35-blue?style=for-the-badge" alt="35 Commands"></a>
</p>

---

`claude -p` 上に構築された永続エージェントランタイム。Python asyncio ゲートウェイ搭載。6層メモリ + クロスレイヤー自動リコール。クローズドループスキル合成。音声入出力。ブラウザ自動化。組み込みcron。2層セキュリティ。Telegram経由でアクセス——開発環境をポケットに。

---

## 何ができるのか？

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

**代わりにウェブを閲覧**
> 「Anthropicのドキュメントに行って最新のClaudeモデルの料金を調べて。」エージェントがABPブラウザを開き、ナビゲートし、データを抽出し、簡潔なサマリーを送ってくれる。Cloudflareにブロックされたら自動でBraveに切り替え。

**自分のWeChatチャット履歴を検索**
> WeChatの内蔵検索はひどい。エージェントがローカルのWeChatデータベースを読み取り、検索可能なエクスポートを提供する——連絡先、メッセージ、グループ、お気に入り。すべてオフライン、すべて自分のマシン上。

**グループチャットからアイデアを寝ている間に吸収**
> 毎朝6時の `/evolve` cronはGitHubをスキャンするだけではない。WeChatの技術グループチャットも読み取り、過去24時間の議論を要約する——メンバーが言及した新ツール、共有されたリポジトリ、議論された技術——そして最良のアイデアをスキルとして吸収する。朝起きたら、グループの集合知があなたのシステムに組み込まれている。

**トレンドシグナルからビジネスアイデアをブレインストーミング**
> `/produce` — エージェントが11のソース（GitHub Trending、Hacker News、X/Twitter、Reddit、Product Hunt、Lobste.rs、ArXiv、HuggingFace、BestOfJS、WeChatグループ、スター付きリポジトリ）から本日のシグナルを集約し、新興トレンドを特定し、収益モデル・技術スタック・MVPスコープを含む5つの具体的なアプリ/ビジネスアイデアをブレインストーミングする。オンデマンドのシグナル駆動アイデア創出。

**自己改善するUX**
> 毎晩午前1時、エージェントがその日の会話を読み、待ち時間が長すぎたり混乱する応答があった摩擦点を見つけ、自らのコードにパッチを当てて修正する。朝起きたら、より良いエージェントになっている。

---

## コア機能

| 機能 | 説明 |
|------|------|
| **ビルド** | Telegram経由でフルClaude Code——ターミナル、ファイルI/O、Web検索、MCP、23スキル |
| **進化** | 5段階パイプライン：収集 → 分析 → 構築 → レビュー → 自動インストール。11ソースをスキャン：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChatグループ、スキルを合成 |
| **吸収** | `/absorb <url>` — リポジトリをクローン、アーキテクチャをマッピング、パターンを比較、改善をシステムに統合 |
| **学習** | `/learn <target>` — 深掘り抽出、ADOPT / ADAPT / SKIP の判定を出力 |
| **音声** | 音声メッセージ送信 → ローカルwhisper.cpp転写（~500ms）。`/speak` → edge-tts、300+音声。広東語/北京語/日本語/韓国語を自動検出 |
| **ブラウザ** | ABP（Agent Browser Protocol）をデフォルトブラウザとして使用。Cloudflareブロック時はBrave/Chrome（CDP）に自動切替。隔離されたエージェントプロファイル |
| **自動リコール** | 毎回の応答前に6層メモリに対して `unified_search()` を実行（約400 tokens/メッセージ） |
| **cron** | `/loop every 6h /evolve` — スケジュールに従い自律的に成長 |
| **セキュリティ** | L1：インストール前の正規表現スキャン（リバースシェル、認証情報窃取、マイナー）。L2：AgentShieldインストール後スキャン（1282テスト、102ルール）。重大な問題は自動ロールバック |
| **フック** | 型付き非同期イベントシステム — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **耐障害性** | シャットダウン時ドレイン（処理中リクエストを最大30秒待機）。型付き障害分類（認証/課金/レート制限）。3パスコンテキスト圧縮。ホットコンフィグリロード |

---

## セットアップ

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
pip install -r ~/.agenticEvolve/requirements.txt
brew install whisper-cpp ffmpeg  # 音声サポート
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

## コマンド

| コマンド | 機能 |
|----------|------|
| _(任意のメッセージ)_ | Claude Codeとチャット |
| _(音声メッセージ)_ | 自動転写（whisper.cpp）+ 応答（音声モード時は音声も返信） |
| _(画像送信)_ | ビジョン分析——スクリーンショット認識、図表理解、OCR、UI検査 |
| _(ファイル送信)_ | ファイル分析——PDF、コードファイル、テキストファイル |
| `/evolve` | シグナルをスキャン、スキルを構築・自動インストール |
| `/absorb <url>` | 任意のリポジトリからパターンを吸収 |
| `/learn <target>` | 深掘り分析と判定 |
| `/speak <text>` | テキスト→音声変換（言語自動検出） |
| `/recall <query>` | クロスレイヤー検索（全6層メモリ） |
| `/search <query>` | FTS5セッション履歴検索 |
| `/do <instruction>` | 自然言語 → 構造化コマンド |
| `/loop <cron> <cmd>` | 定期実行をスケジュール |
| `/memory` | エージェントメモリ状態を表示 |
| `/skills` | インストール済みスキル一覧（23個） |
| `/cost` | 使用量とコスト |
| `/wechat [--hours N]` | WeChatグループチャットダイジェスト（简体中文） |
| `/produce [--ideas N]` | 全シグナルからビジネスアイデアをブレインストーミング |
| `/digest` | 朝のブリーフィング |
| `/restart` | ゲートウェイをリモート再起動 |

[全35コマンド →](docs/commands.md)

---

## アーキテクチャ

```
ユーザー (Telegram/音声) → ゲートウェイ (asyncio) → フックディスパッチャー → セッション + コスト制御
  → 自動リコール (6層) → claude -p → SQLite → Git同期
```

カスタムエージェントループなし。Claude Codeが**そのまま**ランタイム——25+組み込みツール、MCPサーバー、スキル。ゲートウェイがその周囲にメモリ、ルーティング、リコール、cron、音声、ブラウザ、セキュリティを追加。

### 設計上の重要な決定
- **ツールシステムを作らない** — Claude Code自体がツールを持つ。スキルとインフラを構築し、抽象化層は作らない。
- **有界メモリ** — MEMORY.md（2200文字）+ USER.md（1375文字）+ SQLite FTS5。無制限な増加なし。
- **クローズドループ** — `auto_approve_skills: true`。進化 → 構築 → レビュー → インストール → gitに同期。人手による承認なし。
- **シャットダウン時ドレイン** — 処理中のリクエストは再起動前に完了。作業の損失なし。

---

## 音声パイプライン

| 方向 | 技術 | レイテンシ | コスト |
|------|------|-----------|--------|
| **音声 → テキスト** | ローカルwhisper.cpp（ggml-small多言語モデル） | Apple Siliconで約500ms | 無料 |
| **テキスト → 音声** | edge-tts（300+ニューラル音声） | 約1秒 | 無料 |
| **言語検出** | CJKヒューリスティック（嘅係唔 → 広東語、ひらがな → 日本語） | 即時 | 無料 |

自動TTSモード：`off`（`/speak`のみ）、`always`（毎回の応答）、`inbound`（ユーザーが音声を送信した場合に音声で返信）。

---

## ブラウザ自動化

| ブラウザ | 使用場面 | 方式 |
|----------|----------|------|
| **ABP**（デフォルト） | すべてのエージェントブラウジング | 組み込みChromium、アクション間JSフリーズ、Mind2Web 90.5% |
| **Brave** | ユーザー指定 / CloudflareがABPをブロック | CDPポート9222、隔離プロファイル |
| **Chrome** | ユーザー指定 / CloudflareがABPをブロック | CDPポート9223、隔離プロファイル |

エージェントプロファイルは `~/.agenticEvolve/browser-profiles/` にサンドボックス化——ユーザーの実ブラウザデータには一切触れません。

---

## セキュリティ

| レイヤー | ツール | タイミング | 重大問題時 |
|----------|--------|-----------|-----------|
| **L1** | `gateway/security.py` | インストール前：生ファイルをスキャン | ブロック + パイプライン中止 |
| **L2** | AgentShield（1282テスト） | インストール後：`~/.claude/` 設定をスキャン | インストール済みスキルを自動ロールバック |

スキャン対象：認証情報窃取、リバースシェル、難読化ペイロード、暗号通貨マイナー、macOS永続化、プロンプトインジェクション、npmフック悪用。

---

## スケジュールされたcronジョブ

4つの自律ジョブが毎日実行——人手によるトリガー不要。

| ジョブ | スケジュール（HKT） | 内容 |
|--------|-------------------|------|
| **evolve-daily** | 6:00 AM | 11ソースからシグナルを収集：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChatグループ、候補をスコアリング、最大3つの新スキルを構築、セキュリティレビュー、自動インストール、gitにプッシュ |
| **daily-digest** | 8:00 AM | 朝のブリーフィング——トップシグナル、構築済みスキル、セッション数、コストサマリー。Telegramに配信 |
| **wechat-digest** | 9:00 AM | 毎日のWeChatグループチャットダイジェスト——議論内容、言及されたツール、技術グループからの重要なインサイトを要約。Telegramに配信 |
| **daily-ux-review** | 1:00 AM | その日の会話を読み、摩擦点を発見、トップ3のUX改善を特定、直接実装 |

`/loop`、`/loops`、`/unloop`、`/pause`、`/unpause` で管理。設定ファイル：`cron/jobs.json`。

---

## シグナルソース（11個）

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

## スキル（23個インストール済み）

| スキル | 用途 |
|--------|------|
| agent-browser-protocol | MCP経由のABPブラウザ自動化 |
| browser-switch | マルチブラウザCDP切替（Brave/Chrome） |
| brave-search | Brave API経由のWeb検索 |
| firecrawl | Webスクレイピング、クロール、検索、構造化抽出 |
| cloudflare-crawl | 無料Webクロール（Cloudflare Browser Rendering API） |
| jshook-messenger | jshookmcp MCP経由のDiscord/WeChat/Telegram/Slack傍受 |
| wechat-decrypt | ローカルWeChatデータベースを読み取り、メッセージ・連絡先・グループをエクスポート（macOS） |
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

---

MIT
