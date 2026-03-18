"""Dashboard API server — aiohttp web server embedded in the gateway process.

Provides REST API endpoints, WebSocket real-time events, and static file
serving for the Next.js dashboard frontend.

Usage:
    # In GatewayRunner.start():
    from .dashboard_api import DashboardServer
    dashboard = DashboardServer(self, self.config)
    await dashboard.start()
"""
import asyncio
import json
import logging
import mimetypes
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web, WSMsgType

if TYPE_CHECKING:
    from .run import GatewayRunner

log = logging.getLogger("agenticEvolve.dashboard")

VERSION = "2.6.1"

# Keys that may be updated via POST /api/config
_CONFIG_WHITELIST = {
    "model", "daily_cost_cap", "weekly_cost_cap",
    "session_idle_minutes", "autonomy",
}

# Substrings in config key names that indicate sensitive values
_SENSITIVE_SUBSTRINGS = {"token", "key", "secret", "password"}

# Static file directory (Next.js export output)
_STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "out"

# Known gateway modules to probe for /api/modules
_MODULE_NAMES = [
    "content_sanitizer", "context", "diagnostics", "evolve",
    "gc", "hooks", "loop_detector", "plugin_loader",
    "rate_limit", "redact", "retro", "sandbox",
    "security", "self_audit", "semantic", "session_db",
    "voice", "watchdog",
]


# ── Helpers ──────────────────────────────────────────────────────


def _redact_config(obj, _depth: int = 0):
    """Recursively redact sensitive values in a config dict."""
    if _depth > 10:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(s in k.lower() for s in _SENSITIVE_SUBSTRINGS):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact_config(v, _depth + 1)
        return out
    if isinstance(obj, list):
        return [_redact_config(i, _depth + 1) for i in obj]
    return obj


def _json_response(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _error_response(msg: str, status: int = 400) -> web.Response:
    return web.json_response({"error": msg}, status=status)


# ── CORS middleware ──────────────────────────────────────────────


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Add CORS headers for dev (localhost:3000) and prod origins."""
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as exc:
            resp = exc

    origin = request.headers.get("Origin", "")
    allowed_origins = {"http://localhost:3000", "http://127.0.0.1:3000"}
    if origin in allowed_origins:
        resp.headers["Access-Control-Allow-Origin"] = origin
    # else: no Origin header or unknown origin — do not set CORS header

    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Max-Age"] = "3600"
    return resp


# ── Auth middleware ──────────────────────────────────────────────


def make_auth_middleware(auth_token: str):
    """Return middleware that enforces Bearer token auth when token is set."""

    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        # Skip auth for OPTIONS (CORS preflight), static files, and WebSocket upgrade
        if request.method == "OPTIONS":
            return await handler(request)
        if not request.path.startswith("/api") and request.path != "/ws":
            return await handler(request)
        if not auth_token:
            return await handler(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header == f"Bearer {auth_token}":
            return await handler(request)

        # Also accept token as query param for WebSocket connections
        if request.path == "/ws" and request.query.get("token") == auth_token:
            return await handler(request)

        return _error_response("Unauthorized", status=401)

    return auth_middleware


# ── DashboardServer ──────────────────────────────────────────────


class DashboardServer:
    """aiohttp web server for the dashboard, embedded in the gateway process."""

    def __init__(self, runner: "GatewayRunner", config: dict):
        self.runner = runner
        self.config = config
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._diag_unsub = None
        self._log_handler = None
        self._runner_site: web.TCPSite | None = None
        self._app_runner: web.AppRunner | None = None

        # Build aiohttp app
        dashboard_cfg = config.get("dashboard", {})
        auth_token = dashboard_cfg.get("auth_token", "")
        middlewares = [cors_middleware]
        if auth_token:
            middlewares.append(make_auth_middleware(auth_token))

        self.app = web.Application(middlewares=middlewares)
        self._setup_routes()

    # ── Route setup ──────────────────────────────────────────

    def _setup_routes(self):
        self.app.router.add_get("/api/health", self._handle_health)
        self.app.router.add_get("/api/status", self._handle_status)
        self.app.router.add_get("/api/sessions", self._handle_sessions)
        self.app.router.add_get("/api/sessions/{id}", self._handle_session_detail)
        self.app.router.add_get("/api/usage", self._handle_usage)
        self.app.router.add_get("/api/config", self._handle_config_get)
        self.app.router.add_post("/api/config", self._handle_config_post)
        self.app.router.add_get("/api/metrics", self._handle_metrics)
        self.app.router.add_get("/api/modules", self._handle_modules)
        self.app.router.add_get("/api/git/log", self._handle_git_log)
        self.app.router.add_post("/api/chat", self._handle_chat)
        self.app.router.add_get("/api/memory/search", self._handle_memory_search)
        self.app.router.add_get("/api/memory/stats", self._handle_memory_stats)
        self.app.router.add_get("/ws", self._handle_ws)

        # Static files + SPA fallback (must be last)
        if _STATIC_DIR.exists():
            self.app.router.add_get("/{path:.*}", self._handle_static)
        else:
            self.app.router.add_get("/", self._handle_no_frontend)

    # ── API handlers ─────────────────────────────────────────

    async def _handle_health(self, request: web.Request) -> web.Response:
        uptime = time.time() - self.runner._start_time if self.runner._start_time else 0
        return _json_response({
            "status": "ok",
            "uptime_secs": round(uptime),
            "version": VERSION,
        })

    async def _handle_status(self, request: web.Request) -> web.Response:
        try:
            from .agent import get_today_cost, get_week_cost
            from .session_db import stats as db_stats

            uptime = time.time() - self.runner._start_time if self.runner._start_time else 0

            # Platform status
            platform_names = ["telegram", "whatsapp", "discord"]
            platforms = {}
            for name in platform_names:
                platforms[name] = name in self.runner._adapter_map

            st = db_stats()

            data = {
                "uptime_secs": round(uptime),
                "platforms": platforms,
                "active_sessions": len(self.runner._active_sessions),
                "today_cost": round(get_today_cost(), 4),
                "week_cost": round(get_week_cost(), 4),
                "total_sessions": st.get("total_sessions", 0),
                "total_messages": st.get("total_messages", 0),
                "model": self.runner.config.get("model", "sonnet"),
                "daily_cost_cap": self.runner.config.get("daily_cost_cap", 5.0),
                "weekly_cost_cap": self.runner.config.get("weekly_cost_cap", 25.0),
            }

            # Smart router stats
            if hasattr(self.runner, '_smart_router') and self.runner._smart_router:
                data["routing"] = self.runner._smart_router.stats.to_dict()

            # Provider chain stats (Retry → CircuitBreaker → Cache)
            if hasattr(self.runner, '_provider_chain') and self.runner._provider_chain:
                try:
                    from .provider_chain import walk_chain
                    layers = walk_chain(self.runner._provider_chain)
                    chain_data: dict = {}
                    cache = layers.get("cache")
                    if cache is not None:
                        chain_data["cache_hits"] = cache.hits
                        chain_data["cache_misses"] = cache.misses
                    cb = layers.get("circuit_breaker")
                    if cb is not None:
                        chain_data["circuit_state"] = cb.state.value
                        chain_data["circuit_failure_count"] = cb.failure_count
                    if chain_data:
                        data["provider_chain"] = chain_data
                except Exception:
                    pass

            return _json_response(data)
        except Exception as e:
            log.error(f"Status endpoint error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_sessions(self, request: web.Request) -> web.Response:
        try:
            from .session_db import list_sessions, stats as db_stats

            limit = int(request.query.get("limit", "50"))
            offset = int(request.query.get("offset", "0"))
            limit = min(limit, 200)  # cap

            # list_sessions doesn't support offset natively, so we fetch more and slice
            sessions = list_sessions(limit=limit + offset)
            st = db_stats()

            return _json_response({
                "sessions": sessions[offset:offset + limit],
                "total": st.get("total_sessions", 0),
            })
        except Exception as e:
            log.error(f"Sessions endpoint error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_session_detail(self, request: web.Request) -> web.Response:
        try:
            from .session_db import get_session_messages, _connect

            session_id = request.match_info["id"]

            # Get session metadata
            conn = _connect()
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            conn.close()

            if not row:
                return _error_response("Session not found", status=404)

            messages = get_session_messages(session_id)

            return _json_response({
                "session": dict(row),
                "messages": messages,
            })
        except Exception as e:
            log.error(f"Session detail error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_usage(self, request: web.Request) -> web.Response:
        try:
            from .session_db import _connect

            days = int(request.query.get("days", "7"))
            days = min(days, 90)  # cap

            conn = _connect()
            rows = conn.execute(
                """
                SELECT
                    date(timestamp) as date,
                    SUM(cost) as cost,
                    COUNT(DISTINCT session_id) as sessions,
                    COUNT(*) as entries
                FROM costs
                WHERE date(timestamp) >= date('now', ?)
                GROUP BY date(timestamp)
                ORDER BY date(timestamp) ASC
                """,
                (f"-{days} days",)
            ).fetchall()

            # Get total message count per day via messages table
            msg_rows = conn.execute(
                """
                SELECT date(timestamp) as date, COUNT(*) as messages
                FROM messages
                WHERE date(timestamp) >= date('now', ?)
                GROUP BY date(timestamp)
                """,
                (f"-{days} days",)
            ).fetchall()
            conn.close()

            msg_by_date = {r["date"]: r["messages"] for r in msg_rows}

            daily = []
            total_cost = 0.0
            for r in rows:
                cost = float(r["cost"] or 0)
                total_cost += cost
                daily.append({
                    "date": r["date"],
                    "cost": round(cost, 4),
                    "sessions": r["sessions"],
                    "messages": msg_by_date.get(r["date"], 0),
                })

            return _json_response({
                "daily": daily,
                "total_cost": round(total_cost, 4),
            })
        except Exception as e:
            log.error(f"Usage endpoint error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_config_get(self, request: web.Request) -> web.Response:
        try:
            from .config import load_config
            cfg = load_config()
            return _json_response(_redact_config(cfg))
        except Exception as e:
            log.error(f"Config GET error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_config_post(self, request: web.Request) -> web.Response:
        try:
            import yaml
            from .config import CONFIG_PATH, reload_config

            body = await request.json()
            if not isinstance(body, dict):
                return _error_response("Body must be a JSON object")

            # Filter to whitelisted keys only
            updates = {k: v for k, v in body.items() if k in _CONFIG_WHITELIST}
            if not updates:
                return _error_response(
                    f"No valid keys. Allowed: {', '.join(sorted(_CONFIG_WHITELIST))}")

            # Read current config.yaml, apply updates, write back
            if CONFIG_PATH.exists():
                raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}
            else:
                raw = {}

            for k, v in updates.items():
                raw[k] = v

            CONFIG_PATH.write_text(yaml.dump(raw, default_flow_style=False))

            # Hot-reload into running gateway
            self.runner.config, _ = reload_config()

            return _json_response({
                "ok": True,
                "updated": list(updates.keys()),
            })
        except json.JSONDecodeError:
            return _error_response("Invalid JSON body")
        except Exception as e:
            log.error(f"Config POST error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        try:
            from .diagnostics import get_status_summary, get_recent

            summary = get_status_summary()
            recent = get_recent(n=50)
            events = [asdict(e) for e in recent]

            return _json_response({
                "summary": summary,
                "recent_events": events,
            })
        except Exception as e:
            log.error(f"Metrics endpoint error: {e}")
            return _error_response(str(e), status=500)

    async def _handle_modules(self, request: web.Request) -> web.Response:
        modules = []
        for name in _MODULE_NAMES:
            try:
                __import__(f"gateway.{name}")
                modules.append({"name": name, "status": "ready"})
            except ImportError:
                modules.append({"name": name, "status": "missing"})
            except Exception as e:
                modules.append({"name": name, "status": f"error: {e}"})
        return _json_response({"modules": modules})

    # ── Git log ───────────────────────────────────────────────

    async def _handle_git_log(self, request: web.Request) -> web.Response:
        try:
            project_dir = Path(__file__).parent.parent
            result = subprocess.run(
                ["git", "log", "--oneline", "-20",
                 "--format={\"hash\":\"%H\",\"short\":\"%h\",\"message\":\"%s\",\"author\":\"%an\",\"date\":\"%ci\"}"],
                capture_output=True, text=True, timeout=10,
                cwd=str(project_dir),
            )
            if result.returncode != 0:
                return _error_response(
                    f"git log failed: {result.stderr.strip()}", status=500)

            commits = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    commits.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return _json_response({"commits": commits})
        except FileNotFoundError:
            return _error_response("git not installed", status=500)
        except subprocess.TimeoutExpired:
            return _error_response("git log timed out", status=500)
        except Exception as e:
            log.error(f"Git log endpoint error: {e}")
            return _error_response(str(e), status=500)

    # ── Chat ─────────────────────────────────────────────────

    async def _handle_chat(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            message = body.get("message", "").strip()
            if not message:
                return _error_response("message is required")

            response_text = await self.runner.handle_message(
                "dashboard", "web", "web_user", message)

            cost = 0.0
            # Try to get cost from the latest session
            try:
                from .session_db import _connect
                conn = _connect()
                row = conn.execute(
                    "SELECT cost FROM costs WHERE platform='dashboard' "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
                conn.close()
                if row:
                    cost = float(row["cost"] or 0)
            except Exception:
                pass

            return _json_response({
                "response": response_text or "",
                "cost": round(cost, 4),
            })
        except json.JSONDecodeError:
            return _error_response("Invalid JSON body")
        except Exception as e:
            log.error(f"Chat endpoint error: {e}")
            return _error_response(str(e), status=500)

    # ── Memory API ───────────────────────────────────────────

    async def _handle_memory_search(self, request: web.Request) -> web.Response:
        """GET /api/memory/search?q=query&limit=20 — hybrid search across all memory layers."""
        query = request.query.get("q", "").strip()
        if not query:
            return _error_response("q parameter is required")

        try:
            limit = min(int(request.query.get("limit", "20")), 50)
        except (ValueError, TypeError):
            limit = 20

        try:
            from .embeddings import hybrid_search
            results = hybrid_search(query, top_k=limit)
        except Exception:
            # Fallback to unified_search if embeddings not available
            try:
                from .session_db import unified_search
                results = unified_search(query, limit_per_layer=limit // 5 or 3)
            except Exception as e:
                log.error(f"Memory search failed: {e}")
                return _error_response(str(e), status=500)

        return _json_response({"query": query, "results": results, "count": len(results)})

    async def _handle_memory_stats(self, request: web.Request) -> web.Response:
        """GET /api/memory/stats — memory file sizes, DB counts, embedding index status."""
        try:
            from .session_db import get_memory_stats
            stats = get_memory_stats()
        except Exception as e:
            log.error(f"Memory stats failed: {e}")
            stats = {}

        # Add embedding index info
        try:
            from .embeddings import get_index
            idx = get_index()
            stats["embedding_docs"] = len(idx._docs) if idx._docs else 0
            stats["embedding_model"] = "all-MiniLM-L6-v2"
            stats["embedding_cached"] = idx._built_at.isoformat() if idx._built_at else None
        except Exception:
            stats["embedding_docs"] = 0
            stats["embedding_model"] = "not loaded"
            stats["embedding_cached"] = None

        return _json_response(stats)

    # ── WebSocket ────────────────────────────────────────────

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30.0)
        await ws.prepare(request)
        self._ws_clients.add(ws)
        log.info(f"Dashboard WS client connected ({len(self._ws_clients)} total)")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # Client can send pings or commands; ignore for now
                    pass
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._ws_clients.discard(ws)
            log.info(f"Dashboard WS client disconnected ({len(self._ws_clients)} total)")

        return ws

    def _broadcast_ws(self, msg_type: str, data: dict):
        """Push a JSON message to all connected WebSocket clients."""
        if not self._ws_clients:
            return
        payload = json.dumps({"type": msg_type, "data": data})
        stale = set()
        for ws in self._ws_clients:
            if ws.closed:
                stale.add(ws)
                continue
            try:
                asyncio.ensure_future(ws.send_str(payload))
            except Exception:
                stale.add(ws)
        self._ws_clients -= stale

    def _on_diagnostic_event(self, event):
        """Listener registered with diagnostics.on_event()."""
        try:
            self._broadcast_ws("event", asdict(event))
        except Exception:
            pass

    # ── Static file serving + SPA fallback ───────────────────

    async def _handle_static(self, request: web.Request) -> web.Response:
        path = request.match_info.get("path", "")
        if not path:
            path = "index.html"

        file_path = _STATIC_DIR / path

        # Security: prevent path traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(_STATIC_DIR.resolve())):
                return _error_response("Forbidden", status=403)
        except (ValueError, OSError):
            return _error_response("Forbidden", status=403)

        if file_path.is_file():
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or "application/octet-stream"

            # Cache headers: immutable for hashed assets, short for HTML
            cache = "public, max-age=31536000, immutable"
            if file_path.suffix in (".html", ".json"):
                cache = "public, max-age=0, must-revalidate"

            return web.FileResponse(
                file_path,
                headers={
                    "Content-Type": content_type,
                    "Cache-Control": cache,
                },
            )

        # SPA fallback: serve index.html for non-API, non-file paths
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return web.FileResponse(
                index,
                headers={
                    "Content-Type": "text/html",
                    "Cache-Control": "public, max-age=0, must-revalidate",
                },
            )

        return _error_response("Not found", status=404)

    async def _handle_no_frontend(self, request: web.Request) -> web.Response:
        return _json_response({
            "message": "Dashboard API is running. Frontend not built yet.",
            "hint": "Run 'cd gateway/dashboard && npm run build' to build the frontend.",
        })

    # ── Lifecycle ────────────────────────────────────────────

    async def start(self, host: str = "127.0.0.1", port: int = 7777):
        dashboard_cfg = self.config.get("dashboard", {})
        host = dashboard_cfg.get("host", host)
        port = dashboard_cfg.get("port", port)

        # Register diagnostic event listener for WebSocket push
        try:
            from .diagnostics import on_event
            self._diag_unsub = on_event(self._on_diagnostic_event)
        except Exception as e:
            log.warning(f"Dashboard: failed to register diagnostic listener: {e}")

        # Register log handler for WebSocket push
        try:
            self._log_handler = _DashboardLogHandler(self)
            gw_logger = logging.getLogger("agenticEvolve")
            gw_logger.addHandler(self._log_handler)
        except Exception as e:
            log.warning(f"Dashboard: failed to register log handler: {e}")

        # Warn if no auth token is configured
        auth_token = dashboard_cfg.get("auth_token", "")
        if not auth_token:
            log.warning(
                "Dashboard running without auth token — "
                "set dashboard.auth_token in config.yaml for production use"
            )

        self._app_runner = web.AppRunner(self.app, access_log=None)
        await self._app_runner.setup()
        self._runner_site = web.TCPSite(self._app_runner, host, port)
        await self._runner_site.start()
        log.info(f"Dashboard API server started on http://{host}:{port}")

    async def stop(self):
        # Remove log handler
        if self._log_handler:
            try:
                logging.getLogger("agenticEvolve").removeHandler(self._log_handler)
            except Exception:
                pass

        # Unsubscribe from diagnostics
        if self._diag_unsub:
            try:
                self._diag_unsub()
            except Exception:
                pass

        # Close all WebSocket connections
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()

        # Shutdown aiohttp
        if self._runner_site:
            await self._runner_site.stop()
        if self._app_runner:
            await self._app_runner.cleanup()

        log.info("Dashboard API server stopped")


# ── Log handler that pushes to WebSocket ─────────────────────────


class _DashboardLogHandler(logging.Handler):
    """Captures gateway log records and pushes them to WS clients."""

    def __init__(self, server: DashboardServer):
        super().__init__(level=logging.INFO)
        self._server = server

    def emit(self, record: logging.LogRecord):
        try:
            self._server._broadcast_ws("log", {
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
                "timestamp": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
            })
        except Exception:
            pass
