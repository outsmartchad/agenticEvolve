/**
 * agenticEvolve WhatsApp Bridge
 *
 * Communicates with the Python gateway via JSON over stdin/stdout.
 *
 * Inbound (stdout → Python):
 *   { "type": "qr", "qr": "<qr_string>" }
 *   { "type": "ready" }
 *   { "type": "message", "chat_id": "...", "user_id": "...", "text": "...", "message_id": "..." }
 *   { "type": "error", "error": "..." }
 *   { "type": "history_messages", "request_id": "...", "chat_id": "...", "messages": [...] }
 *
 * Outbound (stdin ← Python):
 *   { "type": "send", "chat_id": "...", "text": "..." }
 *   { "type": "fetch_messages", "chat_id": "...", "count": 50 }
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  downloadMediaMessage,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const path = require("path");
const readline = require("readline");
const os = require("os");

const fs = require("fs");
const AUTH_DIR = path.join(__dirname, "auth");
const logger = pino({ level: "silent" }); // quiet baileys internal logs

let sock = null;

// Track all seen chat JIDs (contacts + groups) from incoming messages
const seenChats = new Map(); // jid -> { name, lastSeen }

// Track latest message key per chat (needed as anchor for fetchMessageHistory)
const latestMsgKeys = new Map(); // chatJid -> { key: WAMessageKey, timestamp: number }

// Pending history fetch requests: requestId -> { resolve, timer }
const pendingHistoryFetches = new Map();

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

async function startBridge() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    logger,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    printQRInTerminal: false,
    generateHighQualityLinkPreview: false,
  });

  // ── Connection events ───────────────────────────────────────

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      // Show QR in terminal for scanning
      qrcode.generate(qr, { small: true });
      emit({ type: "qr", qr });
    }

    if (connection === "close") {
      const statusCode =
        lastDisconnect?.error?.output?.statusCode ||
        lastDisconnect?.error?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      emit({
        type: "error",
        error: `Connection closed (status ${statusCode}). ${
          shouldReconnect ? "Reconnecting..." : "Logged out."
        }`,
      });

      if (shouldReconnect) {
        setTimeout(startBridge, 3000);
      } else {
        process.exit(1);
      }
    }

    if (connection === "open") {
      emit({ type: "ready" });
    }
  });

  // ── Save credentials on update ──────────────────────────────

  sock.ev.on("creds.update", saveCreds);

  // ── Incoming messages ───────────────────────────────────────

  sock.ev.on("messages.upsert", ({ messages, type: upsertType }) => {
    if (upsertType !== "notify") return;

    for (const msg of messages) {
      // Skip own messages and status broadcasts
      if (msg.key.fromMe) continue;
      if (msg.key.remoteJid === "status@broadcast") continue;

      const chatId = msg.key.remoteJid;
      // For groups, participant is the sender. For DMs, it's the chat itself.
      const userId = msg.key.participant || chatId;

      // Track message key as anchor for history fetching
      const msgTs = typeof msg.messageTimestamp === "number"
        ? msg.messageTimestamp
        : (msg.messageTimestamp?.toNumber?.() || Math.floor(Date.now() / 1000));
      const existing = latestMsgKeys.get(chatId);
      if (!existing || msgTs > existing.timestamp) {
        latestMsgKeys.set(chatId, {
          key: msg.key,
          timestamp: msgTs,
        });
      }

      // Track seen JIDs for contact/group listing
      if (chatId && !chatId.endsWith("@broadcast")) {
        seenChats.set(chatId, {
          name: msg.pushName || chatId.split("@")[0],
          lastSeen: Date.now(),
        });
      }
      if (userId && userId !== chatId && userId.endsWith("@s.whatsapp.net")) {
        seenChats.set(userId, {
          name: msg.pushName || userId.split("@")[0],
          lastSeen: Date.now(),
        });
      }

      // Extract text from various message types
      const text =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        msg.message?.imageMessage?.caption ||
        null;

      // Check for image message
      const imageMsg = msg.message?.imageMessage;
      let imagePath = null;

      if (imageMsg) {
        try {
          const buffer = await downloadMediaMessage(msg, "buffer", {}, {
            logger,
            reuploadRequest: sock.updateMediaMessage,
          });
          // Save to temp file
          const tmpDir = path.join(os.tmpdir(), "agenticEvolve-wa-images");
          if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
          const ext = (imageMsg.mimetype || "image/jpeg").split("/")[1] || "jpg";
          const filename = `${msg.key.id}.${ext}`;
          imagePath = path.join(tmpDir, filename);
          fs.writeFileSync(imagePath, buffer);
        } catch (imgErr) {
          // Non-fatal: emit message without image
          imagePath = null;
        }
      }

      // Skip messages with no text AND no image
      if (!text && !imagePath) continue;

      const payload = {
        type: "message",
        chat_id: chatId,
        user_id: userId,
        sender_name: msg.pushName || userId.split("@")[0],
        text: text || "",
        message_id: msg.key.id,
        timestamp: msgTs,
      };
      if (imagePath) payload.image_path = imagePath;

      emit(payload);
    }
  });

  // ── History sync handler (for fetchMessageHistory responses) ──

  sock.ev.on("messaging-history.set", ({ messages, peerDataRequestSessionId }) => {
    // Route history messages to any pending fetch request
    if (peerDataRequestSessionId) {
      for (const [reqId, pending] of pendingHistoryFetches) {
        if (pending.sessionId === peerDataRequestSessionId) {
          // Extract text messages from history
          const extracted = [];
          for (const msg of messages) {
            const chatId = msg.key?.remoteJid;
            const userId = msg.key?.participant || chatId;
            const text =
              msg.message?.conversation ||
              msg.message?.extendedTextMessage?.text ||
              null;
            if (!text || !chatId) continue;

            const msgTs = typeof msg.messageTimestamp === "number"
              ? msg.messageTimestamp
              : (msg.messageTimestamp?.toNumber?.() || 0);

            extracted.push({
              chat_id: chatId,
              user_id: userId,
              sender_name: msg.pushName || userId?.split("@")[0] || "unknown",
              text,
              message_id: msg.key?.id,
              timestamp: msgTs,
              from_me: !!msg.key?.fromMe,
            });

            // Update anchor tracking
            const existing = latestMsgKeys.get(chatId);
            if (!existing || msgTs > existing.timestamp) {
              latestMsgKeys.set(chatId, { key: msg.key, timestamp: msgTs });
            }
          }
          pending.messages.push(...extracted);
          // Don't resolve yet — more chunks may come. Timer handles completion.
          // Reset the timer on each chunk
          if (pending.timer) clearTimeout(pending.timer);
          pending.timer = setTimeout(() => {
            pendingHistoryFetches.delete(reqId);
            emit({
              type: "history_messages",
              request_id: reqId,
              chat_id: pending.chatId,
              messages: pending.messages,
            });
          }, 5000); // 5s after last chunk = done
          break;
        }
      }
    }
  });

  // ── Read commands from stdin ────────────────────────────────

  const rl = readline.createInterface({ input: process.stdin });

  rl.on("line", async (line) => {
    try {
      const cmd = JSON.parse(line.trim());
      if (cmd.type === "list_groups") {
        try {
          const groups = await sock.groupFetchAllParticipating();
          const result = Object.values(groups).map((g) => ({
            id: g.id,
            subject: g.subject,
            size: g.size || g.participants?.length || 0,
          }));
          emit({ type: "groups", groups: result });
        } catch (e) {
          emit({ type: "error", error: `list_groups failed: ${e.message}` });
        }
      } else if (cmd.type === "list_contacts") {
        // Combine: 1) lid-mapping files from auth store, 2) seen chat JIDs, 3) chatFetchAll if available
        const contactMap = new Map(); // jid -> name

        // Source 1: Read lid-mapping-<phone>.json files from auth dir
        try {
          const files = fs.readdirSync(AUTH_DIR);
          for (const f of files) {
            const m = f.match(/^lid-mapping-(\d+)\.json$/);
            if (m) {
              const phone = m[1];
              const jid = `${phone}@s.whatsapp.net`;
              contactMap.set(jid, phone);
            }
          }
        } catch (e) { /* ignore */ }

        // Source 2: Seen chats (from incoming messages this session)
        for (const [jid, info] of seenChats) {
          if (jid.endsWith("@s.whatsapp.net")) {
            contactMap.set(jid, info.name || jid.split("@")[0]);
          }
        }

        // Source 3: Try chatFetchAll (works in some Baileys versions)
        try {
          const chats = await sock.chatFetchAll?.() || [];
          for (const c of chats) {
            if (c.id?.endsWith("@s.whatsapp.net")) {
              contactMap.set(c.id, c.name || c.id.split("@")[0]);
            }
          }
        } catch (e) { /* v7 may not support this */ }

        // Exclude own JID
        const ownJid = sock.user?.id?.replace(/:.*@/, "@");
        if (ownJid) contactMap.delete(ownJid);

        const contacts = Array.from(contactMap).map(([id, name]) => ({ id, name }));
        emit({ type: "contacts", contacts });
      } else if (cmd.type === "fetch_messages" && cmd.chat_id) {
        // Fetch historical messages for a chat using on-demand history sync
        const chatId = cmd.chat_id;
        const count = cmd.count || 50;
        const requestId = cmd.request_id || `fetch_${Date.now()}`;

        // We need an anchor message key for this chat
        const anchor = latestMsgKeys.get(chatId);
        if (!anchor) {
          emit({
            type: "history_messages",
            request_id: requestId,
            chat_id: chatId,
            messages: [],
            error: "no_anchor",
          });
        } else {
          try {
            const sessionId = await sock.fetchMessageHistory(
              count,
              anchor.key,
              anchor.timestamp * 1000 // API expects ms
            );
            // Register pending request — results come via messaging-history.set
            pendingHistoryFetches.set(requestId, {
              chatId,
              sessionId,
              messages: [],
              timer: setTimeout(() => {
                // Timeout: no history received after 30s
                pendingHistoryFetches.delete(requestId);
                emit({
                  type: "history_messages",
                  request_id: requestId,
                  chat_id: chatId,
                  messages: [],
                  error: "timeout",
                });
              }, 30000),
            });
          } catch (e) {
            emit({
              type: "error",
              error: `fetch_messages failed: ${e.message}`,
            });
            emit({
              type: "history_messages",
              request_id: requestId,
              chat_id: chatId,
              messages: [],
              error: e.message,
            });
          }
        }
      } else if (cmd.type === "send" && cmd.chat_id && cmd.text) {
        // LID JIDs can't receive messages — resolve to phone JID if available
        let targetJid = cmd.chat_id;
        if (targetJid.endsWith("@lid")) {
          const phoneJid = sock.user?.id?.replace(/:.*@/, "@") || targetJid;
          if (phoneJid.endsWith("@s.whatsapp.net")) targetJid = phoneJid;
        }
        try {
          const msgPayload = { text: cmd.text };
          // Support reply-to (quote) by passing the original message key
          if (cmd.quoted) {
            msgPayload.quoted = {
              key: cmd.quoted,
              message: { conversation: "" }, // minimal placeholder
            };
          }
          await sock.sendMessage(targetJid, msgPayload);
        } catch (sendErr) {
          emit({ type: "error", error: `send failed: ${sendErr.message}` });
        }
      }
    } catch (err) {
      emit({ type: "error", error: `stdin parse error: ${err.message}` });
    }
  });
}

// ── Start ─────────────────────────────────────────────────────

startBridge().catch((err) => {
  emit({ type: "error", error: `Fatal: ${err.message}` });
  process.exit(1);
});
