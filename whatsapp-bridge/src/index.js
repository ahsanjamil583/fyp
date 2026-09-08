import http from 'node:http';
import process from 'node:process';
import QRCode from 'qrcode';
import pino from 'pino';
import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  useMultiFileAuthState,
} from 'baileys';

import { loadTenantConfigs } from './tenants.js';

if (!process.env.BIZXUS_API_BASE_URL?.trim()) {
  console.error('Missing required environment variable: BIZXUS_API_BASE_URL');
  process.exit(1);
}

let tenantConfigs;
try {
  tenantConfigs = loadTenantConfigs();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}

const config = {
  port: parseInteger(process.env.PORT, 3005, 1, 65535),
  apiBaseUrl: process.env.BIZXUS_API_BASE_URL.trim().replace(/\/$/, ''),
  bridgeName: process.env.BRIDGE_NAME?.trim() || 'BizXusAI WhatsApp Agent',
  fallbackReply:
    process.env.FALLBACK_REPLY?.trim() ||
    'Sorry, I could not generate a response right now. The business owner has been notified.',
};

const logger = pino({ level: process.env.BAILEYS_LOG_LEVEL?.trim() || 'silent' });
let shuttingDown = false;

/**
 * One WhatsApp connection per business.
 *
 * Every tenant is a distinct linked device with its own credentials, socket, and
 * message queues, so sessions can never bleed between businesses. Running them in one
 * process removes the previous need for a separate process and port per tenant.
 */
class TenantSession {
  constructor(tenantConfig) {
    this.config = tenantConfig;
    this.socket = null;
    this.generation = 0;
    this.reconnectTimer = null;
    this.status = 'starting';
    this.qrDataUrl = null;
    this.lastError = '';
    this.connectedNumber = '';
    this.processedMessageIds = new Map();
    this.chatQueues = new Map();
  }

  get tenantId() {
    return this.config.tenantId;
  }

  get label() {
    return this.config.label;
  }

  toStatusJson() {
    return {
      tenantId: this.tenantId,
      label: this.label,
      status: this.status,
      ready: this.status === 'ready',
      connectedNumber: this.connectedNumber ? maskNumber(this.connectedNumber) : '',
      lastError: this.lastError,
    };
  }

  async connect() {
    const generation = ++this.generation;
    this.status = 'connecting';
    this.lastError = '';
    await this.reportStatus();

    const { state, saveCreds } = await useMultiFileAuthState(this.config.authPath);
    const { version } = await fetchLatestBaileysVersion();

    const socket = makeWASocket({
      version,
      auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, logger) },
      logger,
      browser: [`${config.bridgeName} (${this.label})`, 'Chrome', '1.0.0'],
      markOnlineOnConnect: false,
      syncFullHistory: false,
      generateHighQualityLinkPreview: false,
      getMessage: async () => undefined,
    });
    this.socket = socket;

    socket.ev.on('creds.update', saveCreds);
    socket.ev.on('connection.update', (update) => this.onConnectionUpdate(generation, socket, update));
    socket.ev.on('messages.upsert', ({ type, messages }) => {
      if (generation !== this.generation || type !== 'notify') return;
      for (const message of messages) {
        this.enqueueForChat(message.key?.remoteJid, () => this.processIncomingMessage(socket, message));
      }
    });
  }

  async onConnectionUpdate(generation, socket, update) {
    if (generation !== this.generation || shuttingDown) return;
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      this.status = 'waiting_for_qr_scan';
      try {
        this.qrDataUrl = await QRCode.toDataURL(qr, { errorCorrectionLevel: 'M', margin: 2, width: 360 });
        console.log(`\n[${this.label}] Scan this QR from WhatsApp > Linked devices:\n`);
        console.log(await QRCode.toString(qr, { type: 'terminal', small: true }));
      } catch (error) {
        this.lastError = error.message;
        console.error(`[${this.label}] Could not generate QR code:`, error);
      }
      await this.reportStatus();
    }

    if (connection === 'open') {
      this.status = 'ready';
      this.qrDataUrl = null;
      this.lastError = '';
      this.connectedNumber = normalizeJid(socket.user?.id);
      console.log(`[${this.label}] Ready. Connected number: ${maskNumber(this.connectedNumber)}`);
      await this.reportStatus();
    }

    if (connection === 'close') {
      const loggedOut = lastDisconnect?.error?.output?.statusCode === DisconnectReason.loggedOut;
      this.socket = null;
      this.connectedNumber = '';

      if (loggedOut) {
        this.status = 'logged_out';
        this.qrDataUrl = null;
        this.lastError = `WhatsApp logged out this device. Delete ${this.config.authPath} and pair again.`;
        console.error(`[${this.label}] ${this.lastError}`);
        await this.reportStatus();
        return;
      }

      this.status = 'reconnecting';
      this.lastError = lastDisconnect?.error?.message || 'Connection closed';
      console.warn(`[${this.label}] Connection closed; reconnecting in 3s (${this.lastError}).`);
      await this.reportStatus();
      this.scheduleReconnect(3_000);
    }
  }

  scheduleReconnect(delayMs) {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.connect().catch((error) => this.handleConnectionFailure(error));
    }, delayMs);
    this.reconnectTimer.unref();
  }

  handleConnectionFailure(error) {
    this.status = 'connection_failed';
    this.lastError = error.message;
    console.error(`[${this.label}] Could not initialize WhatsApp:`, error);
    this.reportStatus().catch(() => undefined);
    if (!shuttingDown) this.scheduleReconnect(5_000);
  }

  async processIncomingMessage(socket, message) {
    const messageId = message.key?.id;
    const chatId = message.key?.remoteJid;
    if (!messageId || this.processedMessageIds.has(messageId) || message.key?.fromMe) return;
    if (isUnsupportedChat(chatId)) return;

    const customerText = extractText(message.message)?.trim();
    const displayChatId = await resolveDisplayChatId(socket, message);
    const customerPhone = normalizeJid(displayChatId || chatId);
    if (!customerText) {
      console.log(`[${this.label}] [IGNORED] Non-text message from ${maskChatId(displayChatId)}`);
      return;
    }

    this.markAsProcessed(messageId);
    console.log(`[${this.label}] [IN] ${maskChatId(displayChatId)}: ${customerText}`);

    try {
      await socket.sendPresenceUpdate('composing', chatId);
    } catch (error) {
      console.warn(`[${this.label}] Could not show typing status:`, error.message);
    }

    try {
      const reply = await this.requestBizXusReply({
        customerPhone,
        customerName: message.pushName || 'WhatsApp Customer',
        messageText: customerText,
        providerMessageId: messageId,
        rawPayload: { chatId, displayChatId, messageTimestamp: message.messageTimestamp },
      });
      if (reply) {
        await socket.sendMessage(chatId, { text: reply }, { quoted: message });
        console.log(`[${this.label}] [OUT] ${maskChatId(displayChatId)}: ${reply}`);
      }
    } catch (error) {
      console.error(`[${this.label}] Failed to process incoming message:`, error);
      try {
        await socket.sendMessage(chatId, { text: config.fallbackReply }, { quoted: message });
      } catch (sendError) {
        console.error(`[${this.label}] Could not send fallback reply:`, sendError);
      }
    } finally {
      try {
        await socket.sendPresenceUpdate('paused', chatId);
      } catch {
        // The socket may reconnect while BizXusAI is generating a reply.
      }
    }
  }

  async requestBizXusReply(payload) {
    const response = await fetch(`${config.apiBaseUrl}/whatsapp/bridge/inbound`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-BizXus-Bridge-Token': this.config.bridgeToken },
      body: JSON.stringify({ tenantId: this.tenantId, connectedNumber: this.connectedNumber, ...payload }),
    });
    const body = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(body?.detail || body?.message || `BizXusAI returned ${response.status}`);
    }
    return body?.data?.reply || '';
  }

  async reportStatus() {
    try {
      const response = await fetch(`${config.apiBaseUrl}/whatsapp/bridge/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-BizXus-Bridge-Token': this.config.bridgeToken },
        body: JSON.stringify({
          tenantId: this.tenantId,
          status: this.status,
          connectedNumber: this.connectedNumber,
          lastError: this.lastError,
        }),
      });
      if (!response.ok) {
        const body = await readJsonResponse(response);
        console.warn(`[${this.label}] Could not report status: ${body?.detail || response.statusText}`);
      }
    } catch (error) {
      console.warn(`[${this.label}] Could not report status: ${error.message}`);
    }
  }

  enqueueForChat(chatId, task) {
    if (!chatId) return;
    const previous = this.chatQueues.get(chatId) || Promise.resolve();
    const next = previous
      .catch(() => undefined)
      .then(task)
      .catch((error) => console.error(`[${this.label}] Chat queue failed for ${maskChatId(chatId)}:`, error))
      .finally(() => {
        if (this.chatQueues.get(chatId) === next) this.chatQueues.delete(chatId);
      });
    this.chatQueues.set(chatId, next);
  }

  markAsProcessed(messageId) {
    this.processedMessageIds.set(messageId, Date.now());
    if (this.processedMessageIds.size > 2000) {
      const oldest = [...this.processedMessageIds.entries()]
        .sort((a, b) => a[1] - b[1])
        .slice(0, 500)
        .map(([id]) => id);
      for (const id of oldest) this.processedMessageIds.delete(id);
    }
  }

  async shutdown() {
    clearTimeout(this.reconnectTimer);
    this.status = 'stopped';
    await this.reportStatus();
    try {
      this.socket?.ws?.close();
    } catch (error) {
      console.warn(`[${this.label}] Socket shutdown warning:`, error.message);
    }
  }
}

const sessions = tenantConfigs.map((tenantConfig) => new TenantSession(tenantConfig));

async function resolveDisplayChatId(socket, message) {
  const alternateJid = message.key?.remoteJidAlt;
  if (alternateJid?.endsWith('@s.whatsapp.net')) return alternateJid;

  const chatId = message.key?.remoteJid;
  if (!chatId?.endsWith('@lid')) return chatId;

  try {
    return (await socket.signalRepository.lidMapping.getPNForLID(chatId)) || chatId;
  } catch {
    return chatId;
  }
}

async function readJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function extractText(content) {
  let current = content;
  for (let depth = 0; current && depth < 5; depth += 1) {
    if (current.conversation) return current.conversation;
    if (current.extendedTextMessage?.text) return current.extendedTextMessage.text;
    current =
      current.ephemeralMessage?.message ||
      current.viewOnceMessage?.message ||
      current.viewOnceMessageV2?.message ||
      current.documentWithCaptionMessage?.message;
  }
  return null;
}

function isUnsupportedChat(chatId) {
  return (
    !chatId ||
    chatId === 'status@broadcast' ||
    chatId.endsWith('@g.us') ||
    chatId.endsWith('@newsletter') ||
    chatId.endsWith('@broadcast')
  );
}

function parseInteger(value, defaultValue, minimum, maximum) {
  const parsed = Number.parseInt(value ?? '', 10);
  return Number.isFinite(parsed) ? Math.min(maximum, Math.max(minimum, parsed)) : defaultValue;
}

function normalizeJid(value) {
  return String(value || '')
    .split('@')[0]
    .split(':')[0]
    .replace(/\D/g, '');
}

function maskNumber(number) {
  if (!number || number.length < 5) return number || 'unknown';
  return `${number.slice(0, 3)}***${number.slice(-3)}`;
}

function maskChatId(chatId) {
  return maskNumber(normalizeJid(chatId));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderTenantCard(session) {
  const statusText = session.status.replaceAll('_', ' ');
  const body = session.qrDataUrl
    ? `<p>Open WhatsApp &rarr; Linked devices &rarr; Link a device.</p><img src="${session.qrDataUrl}" width="320" height="320" alt="WhatsApp QR code" />`
    : session.status === 'ready'
      ? '<p class="success">Connected. BizXusAI is replying from this number.</p>'
      : '<p>Waiting for the WhatsApp connection or QR code...</p>';
  const number = session.connectedNumber
    ? `<p>Connected number: <code>${escapeHtml(maskNumber(session.connectedNumber))}</code></p>`
    : '';
  const error = session.lastError ? `<p class="error">${escapeHtml(session.lastError)}</p>` : '';
  return `<section class="tenant"><h2>${escapeHtml(session.label)}</h2><p>Status: <code>${escapeHtml(statusText)}</code></p><p class="muted">Tenant: <code>${escapeHtml(session.tenantId)}</code></p>${number}${body}${error}</section>`;
}

const server = http.createServer((request, response) => {
  if (request.url === '/health') {
    const allReady = sessions.every((session) => session.status === 'ready');
    response.writeHead(allReady ? 200 : 503, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(
      JSON.stringify({
        ready: allReady,
        tenantCount: sessions.length,
        tenants: sessions.map((session) => session.toStatusJson()),
      }),
    );
    return;
  }

  if (request.url !== '/') {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Not found');
    return;
  }

  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><meta http-equiv="refresh" content="5"/><title>BizXusAI WhatsApp Bridge</title><style>body{font-family:system-ui,sans-serif;margin:0;background:#edf7f1;color:#162033}main{max-width:760px;margin:44px auto;padding:0 16px}.eyebrow{letter-spacing:.16em;text-transform:uppercase;color:#059669;font-weight:800;font-size:12px;text-align:center}h1{text-align:center}.tenant{background:#fff;border:1px solid #cfe8d6;border-radius:22px;box-shadow:0 18px 50px #065f4630;text-align:center;padding:24px;margin-bottom:20px}img{max-width:100%;height:auto;border-radius:18px;border:1px solid #d9eadf}code{background:#eef7f1;padding:4px 8px;border-radius:8px}.success{font-weight:800;color:#047857}.error{color:#b91c1c;overflow-wrap:anywhere}.muted{color:#667085;font-size:14px;line-height:1.6}</style></head><body><main><div class="eyebrow">BizXusAI WhatsApp Bridge</div><h1>Connect Business WhatsApp</h1>${sessions.map(renderTenantCard).join('')}<p class="muted" style="text-align:center">This page refreshes automatically. Keep this bridge running while the WhatsApp agents are active.</p></main></body></html>`,
  );
});

server.listen(config.port, '0.0.0.0', () => {
  console.log(`BizXusAI WhatsApp bridge on http://localhost:${config.port} (${sessions.length} tenant(s))`);
  for (const session of sessions) {
    console.log(`  - ${session.label} (${session.tenantId}) auth: ${session.config.authPath}`);
    session.connect().catch((error) => session.handleConnectionFailure(error));
  }
});

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`\nReceived ${signal}. Closing WhatsApp bridge...`);
  await Promise.allSettled(sessions.map((session) => session.shutdown()));
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('unhandledRejection', (reason) => console.error('Unhandled promise rejection:', reason));
process.on('uncaughtException', (error) => console.error('Uncaught exception:', error));
