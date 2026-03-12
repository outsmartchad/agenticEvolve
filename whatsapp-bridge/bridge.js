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

const AUTH_DIR = path.join(__dirname, "auth");
const logger = pino({ level: "silent" }); // quiet baileys internal logs

let sock = null;

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
        text,
      });
    }
  });

  // ── Read commands from stdin ────────────────────────────────

  const rl = readline.createInterface({ input: process.stdin });

  rl.on("line", async (line) => {
    try {
      const cmd = JSON.parse(line.trim());
      if (cmd.type === "send" && cmd.chat_id && cmd.text) {
        await sock.sendMessage(cmd.chat_id, { text: cmd.text });
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
