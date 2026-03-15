# agenticEvolve

**開発能力を毎日自動進化させるパーソナル・クローズドループ・エージェントシステム。**

<p align="center">
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Engine-Claude%20Code-blueviolet?style=for-the-badge" alt="Claude Code"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Skills-26-orange?style=for-the-badge" alt="26 Skills"></a>
  <a href="https://github.com/outsmartchad/agenticEvolve"><img src="https://img.shields.io/badge/Commands-35-blue?style=for-the-badge" alt="35 Commands"></a>
</p>

---

`claude -p` 上に構築された永続エージェントランタイム。Python asyncio ゲートウェイ搭載。6層メモリ + クロスレイヤー自動リコール。クローズドループスキル合成。音声入出力。ブラウザ自動化。組み込みcron。2層セキュリティ。Telegram経由でアクセス——開発環境をポケットに。

---

## 何ができるのか？

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
| **ビルド** | Telegram経由でフルClaude Code——ターミナル、ファイルI/O、Web検索、MCP、26スキル |
| **進化** | 5段階パイプライン：収集 → 分析 → 構築 → レビュー → 自動インストール。11ソースをスキャン：GitHub Trending + HN + X/Twitter + Reddit + Product Hunt + Lobste.rs + ArXiv + HuggingFace + BestOfJS + WeChatグループ、スキルを合成 |
| **吸収** | `/absorb <url>` — リポジトリをクローン、アーキテクチャをマッピング、パターンを比較、改善をシステムに統合 |
| **学習** | `/learn <target>` — 深掘り抽出、ADOPT / ADAPT / SKIP の判定を出力 |
| **音声** | 音声メッセージ送信 → ローカルwhisper.cpp転写（~500ms）。`/speak` → edge-tts、300+音声。広東語/北京語/日本語/韓国語を自動検出 |
| **ブラウザ** | ABP（Agent Browser Protocol）をデフォルトブラウザとして使用。Cloudflareブロック時はBrave/Chrome（CDP）に自動切替。隔離されたエージェントプロファイル |
| **自動リコール** | 毎回の応答前に6層メモリに対して `unified_search()` を実行（約400 tokens/メッセージ） |
| **cron** | `/loop every 6h /evolve` — スケジュールに従い自律的に成長 |
| **セキュリティ** | L1：インストール前の正規表現スキャン（リバースシェル、認証情報窃取、マイナー）。L2：AgentShieldインストール後スキャン（1282テスト、102ルール）。重大な問題は自動ロールバック |
| **フック** | 型付き非同期イベントシステム — `message_received`、`before_invoke`、`llm_output`、`tool_call`、`session_start`、`session_end` |
| **セマンティックリコール** | TF-IDF コサイン類似度検索レイヤーがFTS5キーワード検索を補強。5000特徴ベクトライザー、バイグラム対応。セッション、学習記録、直感、メモリファイルからコーパスを再構築。`~/.agenticEvolve/cache/` にキャッシュ |
| **直感エンジン** | 行動パターン観察がスコアリングされ直感テーブルにルーティング。高信頼度の直感（0.8以上、2プロジェクト以上または5回以上の観察）がMEMORY.mdに自動昇格 |
| **耐障害性** | シャットダウン時ドレイン（処理中リクエストを最大30秒待機）。型付き障害分類（認証/課金/レート制限）。3パスコンテキスト圧縮。ホットコンフィグリロード。ループ検出（3回同一ターン警告、5回終了）。メモリキュー読み透し（デバウンス原子書き込み、古いデータ読み取りなし）。並行BUILDステージ（ThreadPoolExecutor、3つの隔離ワークスペース） |
| **テスト** | 219の自動テスト（219パス、1 xfail）。カバレッジ：81のコマンドハンドラー統合テスト（全35+ハンドラー）、セッションDB、FTS5検索、セキュリティスキャナー、シグナル重複排除、セマンティック検索、直感昇格、cronパーサー、コスト上限、ループ検出、コンテキスト圧縮、フラグ解析 |

---

## セットアップ

**前提条件：** Python 3.11+、[Claude Code](https://docs.anthropic.com/en/docs/claude-code)（`npm install -g @anthropic-ai/claude-code`）、Node.js 18+

### クイックインストール

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
cd ~/.agenticEvolve && ae setup
```

セットアップウィザードがすべてを処理します——設定ファイル、Telegramボットトークン、ユーザーID、Python依存関係、およびオプションのlaunchdサービスインストール。

### 手動インストール

手動で設定する場合：

```bash
git clone https://github.com/outsmartchad/agenticEvolve.git ~/.agenticEvolve
cd ~/.agenticEvolve
pip install -r requirements.txt
cp config.yaml.example config.yaml
cp .env.example .env
```

`.env` を編集 — Telegramボットトークンを追加（[@BotFather](https://t.me/BotFather) から取得）：
```bash
TELEGRAM_BOT_TOKEN=your-token-here
TELEGRAM_CHAT_ID=your-user-id       # cronジョブの配信用
```

`config.yaml` を編集 — TelegramユーザーIDを追加（[@userinfobot](https://t.me/userinfobot) から取得）：
```yaml
platforms:
  telegram:
    allowed_users: [your-user-id]
```

ゲートウェイを起動：
```bash
ae gateway start
# または: cd ~/.agenticEvolve && python3 -m gateway.run
```

### 音声サポート（オプション）

```bash
brew install whisper-cpp ffmpeg
curl -L -o ~/.agenticEvolve/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

### 診断

```bash
ae doctor    # すべての前提条件と設定をチェック
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
| `/skills` | インストール済みスキル一覧（26個） |
| `/cost` | 使用量とコスト |
| `/wechat [--hours N]` | WeChatグループチャットダイジェスト（简体中文） |
| `/produce [--ideas N]` | 全シグナルからビジネスアイデアをブレインストーミング |
| `/digest` | 朝のブリーフィング |
| `/lang [code]` | `/produce`、`/learn`、`/wechat` の持続的な出力言語を設定 |
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
- **モジュラーコマンド** — 35のTelegramコマンドを8つのmixin（admin、pipelines、signals、cron、approval、search、media、misc）に分割。アダプターコアは630行。
- **二層リコール** — FTS5キーワード検索 + TF-IDFセマンティック検索。自動リコールが毎回のClaude呼び出し前に関連コンテキストを注入。
- **直感パイプライン** — セッション間で観察された行動パターンがスコアリング・重複排除され、信頼度が十分に高い場合にMEMORY.mdに自動昇格。

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

## スキル（26個インストール済み）

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
| next-ai-draw-io | 自然言語からアーキテクチャ図を生成 |
| mcp-elicitation | タスク中のMCPダイアログを傍受し無人パイプラインを実現 |
| skill-gap-scan | ローカルスキルとコミュニティカタログを比較し採用ギャップを発見 |
| context-optimizer | `/context` ヒントに基づいて古いメモリファイルを自動アーカイブ |

---

## 最近の変更

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

**テストハーネス — 219テスト（219パス、1 xfail）**

| テストファイル | テスト数 | カバレッジ |
|----------------|----------|-----------|
| `test_commands.py` | 81 | 全35+コマンドハンドラー：admin、pipelines、signals、cron、approval、search、media、misc + 30の認可拒否テスト |
| `test_session_db.py` | 25 | セッション、メッセージ、FTS5検索、学習記録、ユーザー設定、直感、統計 |
| `test_security.py` | 28 | 重大パターン（リバースシェル、fork爆弾、マイナー）、警告、プロンプトインジェクション、安全なコンテンツ、ディレクトリスキャン |
| `test_evolve.py` | 18 | シグナル読み込み、ランキング、URL/タイトル重複排除、エッジケース |
| `test_agent.py` | 27 | stderr分類、履歴圧縮（3パスカスケード）、タイトル生成、ループ検出 |
| `test_semantic.py` | 11 | コーパス構築（セッション、学習、直感）、検索関連性、キャッシュ、スコアフィルタリング |
| `test_instincts.py` | 8 | コンテキストバグ回帰、自動昇格（昇格、重複排除、文字制限） |
| `test_gateway.py` | 10 | cronパーサー（毎分/特定/ステップ/日跨ぎ）、セッションキー、コスト上限 |
| `test_telegram.py` | 13 | フラグ解析（bool/値/エイリアス/キャスト）、ユーザー許可リスト |

**バグ修正**
- `gateway/security.py` のfork爆弾正規表現を修正 — エスケープされていない `(){}` メタ文字がパターンを常にマッチ不能にしていた。
- `gateway/session_db.py` の `upsert_instinct` を修正 — SELECTクエリに `context` カラムが欠落しており、空コンテキストでの繰り返しupsert時にIndexErrorが発生していた。
- `gateway/commands/admin.py` の `_handle_newsession` を修正 — `set_session_title`（存在しない関数）→ `set_title`、および `generate_session_id()` の欠落がUNIQUE制約違反を引き起こしていた。
- `gateway/commands/misc.py` の `_extract_urls` を修正 — `_URL_RE` クラス属性が未定義で、すべてのプレーンテキストメッセージで `AttributeError` が発生していた。

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
