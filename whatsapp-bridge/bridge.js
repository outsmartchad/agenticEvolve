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

// ── LID ↔ Phone JID resolution ─────────────────────────────────
// Baileys v7 may deliver DM messages under a LID JID (@lid) instead of
// the traditional phone JID (@s.whatsapp.net).  We maintain a bidirectional
// map so every layer (incoming messages, outbound sends, history, contacts)
// always works with phone JIDs.

const lidToPhone = new Map(); // "200725447631040" -> "85254083858"
const phoneToLid = new Map(); // "85254083858" -> "200725447631040"

/**
 * Load all lid-mapping-*_reverse.json files from AUTH_DIR on startup.
 * File format: { "phone": "85254083858" } (or just a bare number string).
 */
function loadLidMappings() {
  try {
    const files = fs.readdirSync(AUTH_DIR);
    for (const f of files) {
      // Forward: lid-mapping-<phone>.json  →  contains { lid: "..." }
      const fwd = f.match(/^lid-mapping-(\d+)\.json$/);
      if (fwd) {
        try {
          const data = JSON.parse(fs.readFileSync(path.join(AUTH_DIR, f), "utf-8"));
          const phone = fwd[1];
          const lid = String(data.lid || data).replace(/\D/g, "");
          if (lid && phone) {
            lidToPhone.set(lid, phone);
            phoneToLid.set(phone, lid);
          }
        } catch (_) { /* skip corrupt files */ }
      }
      // Reverse: lid-mapping-<lid>_reverse.json  →  contains { phone: "..." }
      const rev = f.match(/^lid-mapping-(\d+)_reverse\.json$/);
      if (rev) {
        try {
          const data = JSON.parse(fs.readFileSync(path.join(AUTH_DIR, f), "utf-8"));
          const lid = rev[1];
          const phone = String(data.phone || data).replace(/\D/g, "");
          if (lid && phone) {
            lidToPhone.set(lid, phone);
            phoneToLid.set(phone, lid);
          }
        } catch (_) { /* skip corrupt files */ }
      }
    }
  } catch (_) { /* auth dir may not exist yet */ }
}

/**
 * Resolve a JID: if it's a LID JID, convert to phone JID.
 * e.g. "200725447631040@lid" → "85254083858@s.whatsapp.net"
 * Non-LID JIDs are returned unchanged.
 */
function resolveJid(jid) {
  if (!jid) return jid;
  if (!jid.endsWith("@lid")) return jid;
  const lid = jid.replace("@lid", "");
  const phone = lidToPhone.get(lid);
  if (phone) return `${phone}@s.whatsapp.net`;
  return jid; // unknown LID — pass through (will be logged)
}

// Load mappings immediately
loadLidMappings();

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

  sock.ev.on("messages.upsert", async ({ messages, type: upsertType }) => {
    if (upsertType !== "notify") return;

    // Get our own JID for self-message filtering (strip device suffix)
    const ownJid = sock.user?.id?.replace(/:.*@/, "@");

    for (const msg of messages) {
      if (msg.key.remoteJid === "status@broadcast") continue;

      // Extract text early to check for @agent prefix
      const earlyText =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        msg.message?.imageMessage?.caption ||
        "";
      const isAgentInvoke = earlyText.toLowerCase().startsWith("@agent");

      // Skip own messages UNLESS it's an @agent invocation
      if (msg.key.fromMe && !isAgentInvoke) continue;

      const rawChatId = msg.key.remoteJid;
      const rawUserId = msg.key.participant || rawChatId;

      // Extra self-message guard: Baileys on linked devices sometimes delivers
      // our own sent messages with fromMe=false. Check sender JID explicitly.
      // But allow @agent invocations through.
      if (ownJid && !isAgentInvoke) {
        const senderJid = (rawUserId || "").replace(/:.*@/, "@");
        if (senderJid === ownJid) continue;
      }
      // Resolve LID JIDs → phone JIDs so Python can match against serve targets
      const chatId = resolveJid(rawChatId);
      const userId = resolveJid(rawUserId);

      // Track message key as anchor for history fetching
      // NOTE: store under BOTH raw and resolved JID so fetch_messages can find anchors
      const msgTs = typeof msg.messageTimestamp === "number"
        ? msg.messageTimestamp
        : (msg.messageTimestamp?.toNumber?.() || Math.floor(Date.now() / 1000));
      const existing = latestMsgKeys.get(chatId);
      if (!existing || msgTs > existing.timestamp) {
        latestMsgKeys.set(chatId, { key: msg.key, timestamp: msgTs });
      }
      // Also store under raw JID (LID) so history sync can find anchor
      if (rawChatId !== chatId) {
        const existingRaw = latestMsgKeys.get(rawChatId);
        if (!existingRaw || msgTs > existingRaw.timestamp) {
          latestMsgKeys.set(rawChatId, { key: msg.key, timestamp: msgTs });
        }
      }

      // Track seen JIDs for contact/group listing (use resolved JIDs)
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
        msg.message?.documentMessage?.caption ||
        msg.message?.videoMessage?.caption ||
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

      // Check for document/file message (PDF, TXT, DOCX, etc.)
      const docMsg = msg.message?.documentMessage;
      let filePath = null;
      let fileName = null;

      if (docMsg) {
        try {
          const buffer = await downloadMediaMessage(msg, "buffer", {}, {
            logger,
            reuploadRequest: sock.updateMediaMessage,
          });
          const tmpDir = path.join(os.tmpdir(), "agenticEvolve-wa-files");
          if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
          // Use original filename if available, fallback to message ID + extension
          fileName = docMsg.fileName || `${msg.key.id}`;
          if (!fileName.includes(".") && docMsg.mimetype) {
            const ext = docMsg.mimetype.split("/")[1] || "bin";
            fileName += `.${ext}`;
          }
          filePath = path.join(tmpDir, fileName);
          fs.writeFileSync(filePath, buffer);
        } catch (docErr) {
          filePath = null;
          fileName = null;
        }
      }

      // Check for audio/voice message
      const audioMsg = msg.message?.audioMessage;
      let audioPath = null;

      if (audioMsg) {
        try {
          const buffer = await downloadMediaMessage(msg, "buffer", {}, {
            logger,
            reuploadRequest: sock.updateMediaMessage,
          });
          const tmpDir = path.join(os.tmpdir(), "agenticEvolve-wa-audio");
          if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
          const ext = audioMsg.ptt ? "ogg" : ((audioMsg.mimetype || "audio/ogg").split("/")[1] || "ogg");
          const filename = `${msg.key.id}.${ext}`;
          audioPath = path.join(tmpDir, filename);
          fs.writeFileSync(audioPath, buffer);
        } catch (audioErr) {
          audioPath = null;
        }
      }

      // Extract quoted/replied-to message (contextInfo)
      const contextInfo =
        msg.message?.extendedTextMessage?.contextInfo ||
        msg.message?.imageMessage?.contextInfo ||
        msg.message?.documentMessage?.contextInfo ||
        msg.message?.audioMessage?.contextInfo ||
        null;
      let quotedText = null;
      let quotedSender = null;
      if (contextInfo?.quotedMessage) {
        quotedText =
          contextInfo.quotedMessage.conversation ||
          contextInfo.quotedMessage.extendedTextMessage?.text ||
          contextInfo.quotedMessage.imageMessage?.caption ||
          contextInfo.quotedMessage.documentMessage?.caption ||
          null;
        if (contextInfo.participant) {
          const resolvedParticipant = resolveJid(contextInfo.participant);
          quotedSender = resolvedParticipant?.split("@")[0] || null;
        }
      }

      // Skip messages with no text AND no media
      if (!text && !imagePath && !filePath && !audioPath) continue;

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
      if (filePath) {
        payload.file_path = filePath;
        payload.file_name = fileName;
      }
      if (audioPath) payload.audio_path = audioPath;
      if (quotedText) payload.quoted_text = quotedText;
      if (quotedSender) payload.quoted_sender = quotedSender;

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
            const chatId = resolveJid(msg.key?.remoteJid);
            const userId = resolveJid(msg.key?.participant || msg.key?.remoteJid);
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
        // Resolve LID JIDs → phone JIDs using our mapping
        let targetJid = resolveJid(cmd.chat_id);
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

      } else if (cmd.type === "send_image" && cmd.chat_id && cmd.image_path) {
        // Send an image file to a chat
        let targetJid = resolveJid(cmd.chat_id);
        try {
          const imgBuffer = fs.readFileSync(cmd.image_path);
          const msgPayload = {
            image: imgBuffer,
            caption: cmd.caption || undefined,
          };
          if (cmd.quoted) {
            msgPayload.quoted = {
              key: cmd.quoted,
              message: { conversation: "" },
            };
          }
          await sock.sendMessage(targetJid, msgPayload);
        } catch (sendErr) {
          emit({ type: "error", error: `send_image failed: ${sendErr.message}` });
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
