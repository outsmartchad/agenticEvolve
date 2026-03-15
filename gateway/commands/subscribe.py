"""Subscribe and Serve commands — manage which channels/users the bot monitors."""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..session_db import (
    add_subscription, remove_subscription, get_subscriptions,
    is_subscribed,
)

log = logging.getLogger("agenticEvolve.subscribe")


class SubscribeMixin:
    """Mixin for /subscribe and /serve Telegram commands."""

    # Short ID registry: maps numeric IDs to (platform, target_id, target_name, target_type)
    # Avoids Telegram's 64-byte callback_data limit for long WhatsApp/WeChat JIDs.
    _target_registry: dict[int, tuple[str, str, str, str]] = {}
    _target_counter: int = 0

    def _register_target(self, platform: str, target_id: str, target_name: str, target_type: str) -> int:
        """Register a target and return a short numeric ID for callback_data."""
        # Reuse existing ID if same target
        for k, v in self._target_registry.items():
            if v == (platform, target_id, target_name, target_type):
                return k
        self._target_counter += 1
        self._target_registry[self._target_counter] = (platform, target_id, target_name, target_type)
        return self._target_counter

    def _lookup_target(self, tid: int) -> tuple[str, str, str, str] | None:
        """Look up a registered target by short ID."""
        return self._target_registry.get(tid)

    # ── /subscribe ───────────────────────────────────────────────

    async def _handle_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show platform selection for subscribing to channels/users (digest mode)."""
        user_id = update.message.from_user.id
        if not self._is_allowed(user_id):
            return

        # Show current subscriptions + platform buttons
        subs = get_subscriptions(str(user_id), mode="subscribe")
        text = "📡 *Subscribe* — select channels/users to monitor for digests.\n\n"

        if subs:
            text += "*Current subscriptions:*\n"
            for s in subs:
                text += f"  • `{s['platform']}` — {s['target_name']} ({s['target_type']})\n"
            text += "\n"

        text += "Select a platform to browse:"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Discord", callback_data="sub:platform:discord"),
                InlineKeyboardButton("WhatsApp", callback_data="sub:platform:whatsapp"),
                InlineKeyboardButton("WeChat", callback_data="sub:platform:wechat"),
            ],
            [
                InlineKeyboardButton("View All", callback_data="sub:view:all"),
                InlineKeyboardButton("Clear All", callback_data="sub:clear:all"),
            ],
        ])
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    # ── /serve ───────────────────────────────────────────────────

    async def _handle_serve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show platform selection for serve mode (agent actively responds)."""
        user_id = update.message.from_user.id
        if not self._is_allowed(user_id):
            return

        subs = get_subscriptions(str(user_id), mode="serve")
        text = "🤖 *Serve* — select channels/users where the agent responds.\n\n"

        if subs:
            text += "*Currently serving:*\n"
            for s in subs:
                text += f"  • `{s['platform']}` — {s['target_name']} ({s['target_type']})\n"
            text += "\n"

        text += "Select a platform:"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Discord", callback_data="serve:platform:discord"),
                InlineKeyboardButton("WhatsApp", callback_data="serve:platform:whatsapp"),
            ],
            [
                InlineKeyboardButton("View All", callback_data="serve:view:all"),
                InlineKeyboardButton("Clear All", callback_data="serve:clear:all"),
            ],
        ])
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    # ── Callback handler ─────────────────────────────────────────

    async def _handle_subscribe_callback(self, query, user_id: str, data: str):
        """Route subscribe/serve callback button presses."""
        parts = data.split(":")
        # parts[0] = "sub" or "serve"
        mode = "subscribe" if parts[0] == "sub" else "serve"
        action = parts[1]  # platform, view, clear, guild, channel, toggle, group, dm

        if action == "platform":
            platform = parts[2]
            await self._show_platform_targets(query, user_id, platform, mode)

        elif action == "view":
            await self._show_all_subscriptions(query, user_id, mode)

        elif action == "clear":
            await self._clear_all_subscriptions(query, user_id, mode)

        elif action == "guild":
            # sub:guild:<guild_id>[:<page>]
            guild_id = parts[2]
            page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
            await self._show_guild_channels(query, user_id, guild_id, mode, page=page)

        elif action == "toggle":
            # sub:toggle:<platform>:<target_type>:<target_id>:<target_name>  (legacy)
            # sub:t:<short_id>  (new short format)
            platform = parts[2]
            target_type = parts[3]
            target_id = parts[4]
            target_name = ":".join(parts[5:])  # name may contain colons
            await self._toggle_subscription(
                query, user_id, platform, target_id, target_name, target_type, mode
            )

        elif action == "t":
            # sub:t:<short_id>  — short-ID toggle (avoids 64-byte limit)
            tid = int(parts[2])
            info = self._lookup_target(tid)
            if not info:
                await query.edit_message_text("Target expired. Please re-run the command.")
                return
            platform, target_id, target_name, target_type = info
            await self._toggle_subscription(
                query, user_id, platform, target_id, target_name, target_type, mode
            )

        elif action == "wag":
            # sub:wag:<page> — WhatsApp groups pagination
            await self._show_whatsapp_groups(query, user_id, mode, page=int(parts[2]))

        elif action == "wac":
            # sub:wac:<page> — WhatsApp contacts pagination
            await self._show_whatsapp_contacts(query, user_id, mode, page=int(parts[2]))

        elif action == "back":
            # Return to platform selection
            await self._show_platform_selection(query, user_id, mode)

    # ── Platform targets ─────────────────────────────────────────

    async def _show_platform_targets(self, query, user_id: str, platform: str, mode: str):
        prefix = "sub" if mode == "subscribe" else "serve"

        if platform == "discord":
            await self._show_discord_targets(query, user_id, mode)
        elif platform == "whatsapp":
            await self._show_whatsapp_targets(query, user_id, mode)
        elif platform == "wechat":
            await self._show_wechat_targets(query, user_id, mode)
        else:
            await query.edit_message_text(f"Unknown platform: {platform}")

    async def _show_discord_targets(self, query, user_id: str, mode: str):
        """Show Discord guilds as selection buttons."""
        prefix = "sub" if mode == "subscribe" else "serve"
        adapter = self._get_adapter("discord")
        if not adapter or not hasattr(adapter, "list_guilds"):
            await query.edit_message_text(
                "Discord client adapter not connected.\n"
                "Launch Discord with `--remote-debugging-port=9224` and enable in config."
            )
            return

        await query.edit_message_text("Loading Discord servers...")

        guilds = await adapter.list_guilds()
        if not guilds:
            await query.edit_message_text("No Discord servers found.")
            return

        # Also get DM channels
        dms = await adapter.list_dm_channels()

        rows = []
        # Guild buttons (2 per row)
        for i in range(0, len(guilds), 2):
            row = []
            for g in guilds[i:i + 2]:
                name = g["name"][:20]
                cb = f"{prefix}:guild:{g['id']}:{name}"
                row.append(InlineKeyboardButton(f"🏠 {name}", callback_data=cb[:64]))
            rows.append(row)

        # DM buttons (top 10)
        if dms:
            rows.append([InlineKeyboardButton("── DMs ──", callback_data="noop")])
            for dm in dms[:10]:
                name = dm["name"][:25]
                is_sub = is_subscribed(user_id, "discord", dm["id"], mode)
                icon = "✅" if is_sub else "⬜"
                tid = self._register_target("discord", dm["id"], name, "dm")
                cb = f"{prefix}:t:{tid}"
                rows.append([InlineKeyboardButton(
                    f"{icon} {name}", callback_data=cb
                )])

        rows.append([InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:back:main")])

        keyboard = InlineKeyboardMarkup(rows)
        label = "subscribe to" if mode == "subscribe" else "serve in"
        await query.edit_message_text(
            f"Select Discord servers/DMs to {label}:",
            reply_markup=keyboard
        )

    async def _show_guild_channels(self, query, user_id: str, guild_id: str, mode: str, page: int = 0):
        """Show channels in a Discord guild with pagination."""
        prefix = "sub" if mode == "subscribe" else "serve"
        adapter = self._get_adapter("discord")
        if not adapter:
            return

        await query.edit_message_text("Loading channels...")
        channels = await adapter.list_channels(guild_id)

        PAGE_SIZE = 40
        total_pages = max(1, (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE)
        page_channels = channels[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

        rows = []
        current_cat = None
        for ch in page_channels:
            cat = ch.get("category", "")
            if cat and cat != current_cat:
                current_cat = cat
                rows.append([InlineKeyboardButton(f"── {cat[:30]} ──", callback_data="noop")])
            name = ch["name"][:25]
            is_sub = is_subscribed(user_id, "discord", ch["id"], mode)
            icon = "✅" if is_sub else "⬜"
            tid = self._register_target("discord", ch["id"], name, "channel")
            cb = f"{prefix}:t:{tid}"
            rows.append([InlineKeyboardButton(
                f"{icon} #{name}", callback_data=cb
            )])

        # Pagination buttons
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"{prefix}:guild:{guild_id}:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ➡", callback_data=f"{prefix}:guild:{guild_id}:{page + 1}"))
        if nav:
            rows.append(nav)

        rows.append([InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:platform:discord")])
        keyboard = InlineKeyboardMarkup(rows)
        await query.edit_message_text(
            f"Select channels (page {page + 1}/{total_pages}):",
            reply_markup=keyboard
        )

    async def _show_whatsapp_targets(self, query, user_id: str, mode: str):
        """Show WhatsApp sub-menu: Groups or Contacts."""
        prefix = "sub" if mode == "subscribe" else "serve"
        adapter = self._get_adapter("whatsapp")
        if not adapter or not hasattr(adapter, "list_groups"):
            await query.edit_message_text(
                "WhatsApp adapter not connected or doesn't support listing."
            )
            return

        label = "subscribe to" if mode == "subscribe" else "serve in"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👥 Groups", callback_data=f"{prefix}:wag:0"),
                InlineKeyboardButton("👤 Contacts", callback_data=f"{prefix}:wac:0"),
            ],
            [InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:back:main")],
        ])
        await query.edit_message_text(
            f"WhatsApp — select what to {label}:",
            reply_markup=keyboard
        )

    async def _show_whatsapp_groups(self, query, user_id: str, mode: str, page: int = 0):
        """Show paginated WhatsApp groups."""
        prefix = "sub" if mode == "subscribe" else "serve"
        adapter = self._get_adapter("whatsapp")
        if not adapter:
            return

        await query.edit_message_text("Loading WhatsApp groups...")
        groups = await adapter.list_groups()

        PAGE_SIZE = 40
        total_pages = max(1, (len(groups) + PAGE_SIZE - 1) // PAGE_SIZE)
        page_groups = groups[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

        rows = []
        for g in page_groups:
            name = (g.get("subject") or g["id"])[:25]
            is_sub = is_subscribed(user_id, "whatsapp", g["id"], mode)
            icon = "✅" if is_sub else "⬜"
            tid = self._register_target("whatsapp", g["id"], name, "group")
            cb = f"{prefix}:t:{tid}"
            rows.append([InlineKeyboardButton(
                f"{icon} 👥 {name} ({g.get('size', '?')})",
                callback_data=cb
            )])

        if not groups:
            rows.append([InlineKeyboardButton("No groups found", callback_data="noop")])

        # Pagination
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"{prefix}:wag:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ➡", callback_data=f"{prefix}:wag:{page + 1}"))
        if nav:
            rows.append(nav)

        rows.append([InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:platform:whatsapp")])
        keyboard = InlineKeyboardMarkup(rows)
        label = "subscribe to" if mode == "subscribe" else "serve in"
        await query.edit_message_text(
            f"WhatsApp groups to {label} (page {page + 1}/{total_pages}):",
            reply_markup=keyboard
        )

    async def _show_whatsapp_contacts(self, query, user_id: str, mode: str, page: int = 0):
        """Show paginated WhatsApp contacts."""
        prefix = "sub" if mode == "subscribe" else "serve"
        adapter = self._get_adapter("whatsapp")
        if not adapter:
            return

        await query.edit_message_text("Loading WhatsApp contacts...")
        contacts = await adapter.list_contacts()

        # Merge in allowed_users from config
        known_jids = {c["id"] for c in contacts}
        for jid in adapter.allowed_users:
            if jid.endswith("@s.whatsapp.net") and jid not in known_jids:
                phone = jid.split("@")[0]
                contacts.append({"id": jid, "name": phone})

        # For serve mode, sync allowed_users into subscriptions DB
        # (these are implicitly served by the adapter)
        if mode == "serve":
            for jid in adapter.allowed_users:
                if jid.endswith("@s.whatsapp.net") and not is_subscribed(user_id, "whatsapp", jid, mode):
                    phone = jid.split("@")[0]
                    add_subscription(user_id, "whatsapp", jid, phone, "contact", mode)

        PAGE_SIZE = 40
        total_pages = max(1, (len(contacts) + PAGE_SIZE - 1) // PAGE_SIZE)
        page_contacts = contacts[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

        rows = []
        for c in page_contacts:
            name = (c.get("name") or c["id"].split("@")[0])[:25]
            is_sub = is_subscribed(user_id, "whatsapp", c["id"], mode)
            icon = "✅" if is_sub else "⬜"
            tid = self._register_target("whatsapp", c["id"], name, "contact")
            cb = f"{prefix}:t:{tid}"
            rows.append([InlineKeyboardButton(
                f"{icon} 👤 {name}", callback_data=cb
            )])

        if not contacts:
            rows.append([InlineKeyboardButton("No contacts found", callback_data="noop")])

        # Pagination
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"{prefix}:wac:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ➡", callback_data=f"{prefix}:wac:{page + 1}"))
        if nav:
            rows.append(nav)

        rows.append([InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:platform:whatsapp")])
        keyboard = InlineKeyboardMarkup(rows)
        label = "subscribe to" if mode == "subscribe" else "serve in"
        await query.edit_message_text(
            f"WhatsApp contacts to {label} (page {page + 1}/{total_pages}):",
            reply_markup=keyboard
        )

    async def _show_wechat_targets(self, query, user_id: str, mode: str):
        """Show WeChat groups from decrypted databases."""
        prefix = "sub" if mode == "subscribe" else "serve"

        await query.edit_message_text("Loading WeChat groups...")

        try:
            import sqlite3
            from pathlib import Path
            decrypt_dir = Path.home() / ".agenticEvolve" / "tools" / "wechat-decrypt" / "decrypted"
            contact_db = decrypt_dir / "contact" / "contact.db"
            msg_db = decrypt_dir / "message" / "message_0.db"

            # Load chatroom names from contact.db
            name_map = {}
            if contact_db.exists():
                conn = sqlite3.connect(str(contact_db))
                for row in conn.execute(
                    "SELECT username, nick_name FROM contact WHERE username LIKE '%@chatroom'"
                ):
                    name_map[row[0]] = row[1] or row[0]
                conn.close()

            # Also load non-chatroom contacts for the contacts section
            contacts = []
            if contact_db.exists():
                conn = sqlite3.connect(str(contact_db))
                for row in conn.execute(
                    "SELECT username, nick_name, remark FROM contact "
                    "WHERE username NOT LIKE '%@chatroom' "
                    "AND username NOT LIKE 'gh_%' "
                    "AND username NOT LIKE 'fake_%' "
                    "AND username != '' "
                    "AND local_type != 0 "
                    "ORDER BY nick_name"
                ):
                    display = row[2] or row[1] or row[0]  # remark > nick_name > username
                    contacts.append({"id": row[0], "name": display})
                conn.close()

            # Get chatroom IDs from message DB (Name2Id table)
            chatroom_ids = set(name_map.keys())
            if msg_db.exists():
                conn = sqlite3.connect(str(msg_db))
                for row in conn.execute(
                    "SELECT user_name FROM Name2Id WHERE user_name LIKE '%@chatroom'"
                ):
                    chatroom_ids.add(row[0])
                conn.close()

            groups = []
            for cid in sorted(chatroom_ids):
                groups.append({"id": cid, "name": name_map.get(cid, cid)})

        except Exception as e:
            log.warning(f"Could not load WeChat data from DB: {e}")
            groups = []
            contacts = []

        btn_rows = []
        if groups:
            btn_rows.append([InlineKeyboardButton("── Groups ──", callback_data="noop")])
            for g in groups[:25]:
                name = (g.get("name") or g["id"])[:25]
                is_sub = is_subscribed(user_id, "wechat", g["id"], mode)
                icon = "✅" if is_sub else "⬜"
                tid = self._register_target("wechat", g["id"], name, "group")
                cb = f"{prefix}:t:{tid}"
                btn_rows.append([InlineKeyboardButton(f"{icon} 👥 {name}", callback_data=cb)])

        if contacts:
            btn_rows.append([InlineKeyboardButton("── Contacts ──", callback_data="noop")])
            for c in contacts[:20]:
                name = (c.get("name") or c["id"])[:25]
                is_sub = is_subscribed(user_id, "wechat", c["id"], mode)
                icon = "✅" if is_sub else "⬜"
                tid = self._register_target("wechat", c["id"], name, "contact")
                cb = f"{prefix}:t:{tid}"
                btn_rows.append([InlineKeyboardButton(f"{icon} 👤 {name}", callback_data=cb)])

        if not groups and not contacts:
            btn_rows.append([InlineKeyboardButton(
                "No WeChat data found. Run wechat-decrypt first.",
                callback_data="noop"
            )])

        btn_rows.append([InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:back:main")])
        keyboard = InlineKeyboardMarkup(btn_rows)
        label = "subscribe to" if mode == "subscribe" else "serve in"
        await query.edit_message_text(
            f"Select WeChat targets to {label} (read-only digest):",
            reply_markup=keyboard
        )

    # ── Toggle / View / Clear ────────────────────────────────────

    async def _toggle_subscription(self, query, user_id: str, platform: str,
                                    target_id: str, target_name: str,
                                    target_type: str, mode: str):
        """Toggle a subscription on/off."""
        if is_subscribed(user_id, platform, target_id, mode):
            remove_subscription(user_id, platform, target_id, mode)
            action = "Unsubscribed from" if mode == "subscribe" else "Stopped serving"
        else:
            add_subscription(user_id, platform, target_id, target_name, target_type, mode)
            action = "Subscribed to" if mode == "subscribe" else "Now serving"

            # For serve mode, dynamically update the adapter
            if mode == "serve":
                self._update_serve_targets(platform)

        await query.answer(f"{action} {target_name}")

        # Refresh the view — go back to platform targets
        prefix = "sub" if mode == "subscribe" else "serve"
        await self._show_platform_targets(query, user_id, platform, mode)

    async def _show_all_subscriptions(self, query, user_id: str, mode: str):
        """Show all current subscriptions."""
        subs = get_subscriptions(user_id, mode=mode)
        label = "Subscriptions" if mode == "subscribe" else "Serving"

        if not subs:
            await query.edit_message_text(f"No {label.lower()} yet.")
            return

        text = f"📋 *{label}:*\n\n"
        for s in subs:
            text += f"• `{s['platform']}` — {s['target_name']} ({s['target_type']})\n"

        prefix = "sub" if mode == "subscribe" else "serve"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data=f"{prefix}:back:main")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    async def _clear_all_subscriptions(self, query, user_id: str, mode: str):
        """Clear all subscriptions for a user."""
        from ..session_db import _connect
        conn = _connect()
        try:
            conn.execute(
                "DELETE FROM subscriptions WHERE user_id=? AND mode=?",
                (user_id, mode)
            )
            conn.commit()
        finally:
            conn.close()

        label = "Subscriptions" if mode == "subscribe" else "Serve targets"
        await query.answer(f"All {label.lower()} cleared.")

        prefix = "sub" if mode == "subscribe" else "serve"
        await self._show_platform_selection(query, user_id, mode)

    async def _show_platform_selection(self, query, user_id: str, mode: str):
        """Show the platform selection screen."""
        prefix = "sub" if mode == "subscribe" else "serve"
        label = "subscribe to" if mode == "subscribe" else "serve in"
        platforms = [
            InlineKeyboardButton("Discord", callback_data=f"{prefix}:platform:discord"),
            InlineKeyboardButton("WhatsApp", callback_data=f"{prefix}:platform:whatsapp"),
        ]
        if mode == "subscribe":
            platforms.append(
                InlineKeyboardButton("WeChat", callback_data=f"{prefix}:platform:wechat")
            )

        keyboard = InlineKeyboardMarkup([
            platforms,
            [
                InlineKeyboardButton("View All", callback_data=f"{prefix}:view:all"),
                InlineKeyboardButton("Clear All", callback_data=f"{prefix}:clear:all"),
            ],
        ])
        await query.edit_message_text(
            f"Select a platform to {label}:", reply_markup=keyboard
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _get_adapter(self, platform: str):
        """Get a platform adapter from the gateway."""
        if not self._gateway:
            return None
        for adapter in self._gateway.adapters:
            if adapter.name == platform:
                return adapter
        return None

    def _update_serve_targets(self, platform: str):
        """Update adapter watch_channels/allowed_users from serve subscriptions."""
        from ..session_db import get_serve_targets
        adapter = self._get_adapter(platform)
        if not adapter:
            return

        targets = get_serve_targets(platform)

        if platform == "discord" and hasattr(adapter, "watch_channels"):
            channel_ids = {t["target_id"] for t in targets if t["target_type"] in ("channel", "dm")}
            # Merge serve channels into watch_channels (keep config channels too)
            adapter._serve_channels = channel_ids
            adapter.watch_channels |= channel_ids
            # Restart polling if needed
            if hasattr(adapter, "_poll_task") and adapter._poll_task:
                adapter._poll_task.cancel()
                adapter._poll_task = asyncio.create_task(adapter._poll_messages())
            log.info(f"Discord serve targets updated: {len(channel_ids)} channels")

        elif platform == "whatsapp":
            # For WhatsApp, we accept all messages from groups we're serving
            # The read loop already handles this via allowed_users
            group_ids = {t["target_id"] for t in targets if t["target_type"] == "group"}
            if hasattr(adapter, "_serve_groups"):
                adapter._serve_groups = group_ids
            log.info(f"WhatsApp serve targets updated: {len(group_ids)} groups")
