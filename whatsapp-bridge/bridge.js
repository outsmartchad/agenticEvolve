/**
 * agenticEvolve WhatsApp Bridge
 *
 * Communicates with the Python gateway via JSON over stdin/stdout.
 *
 * Inbound (stdout → Python):
 *   { "type": "qr", "qr": "<qr_string>" }
 *   { "type": "ready" }
 *   { "type": "message", "chat_id": "...", "user_id": "...", "text": "..." }
 *   { "type": "error", "error": "..." }
 *
 * Outbound (stdin ← Python):
 *   { "type": "send", "chat_id": "...", "text": "..." }
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const path = require("path");
const readline = require("readline");

const fs = require("fs");
const AUTH_DIR = path.join(__dirname, "auth");
const logger = pino({ level: "silent" }); // quiet baileys internal logs

let sock = null;

// Track all seen chat JIDs (contacts + groups) from incoming messages
const seenChats = new Map(); // jid -> { name, lastSeen }

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
        null;




      if (!text) continue;

      emit({
        type: "message",
        chat_id: chatId,
        user_id: userId,
        sender_name: msg.pushName || userId.split("@")[0],
        text,
      });
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
      } else if (cmd.type === "send" && cmd.chat_id && cmd.text) {
        // LID JIDs can't receive messages — resolve to phone JID if available
        let targetJid = cmd.chat_id;
        if (targetJid.endsWith("@lid")) {
          const phoneJid = sock.user?.id?.replace(/:.*@/, "@") || targetJid;
          if (phoneJid.endsWith("@s.whatsapp.net")) targetJid = phoneJid;
        }
        try {
          await sock.sendMessage(targetJid, { text: cmd.text });
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
