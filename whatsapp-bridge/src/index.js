import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
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
import { validPairingGrant } from './pairing-auth.js';

if (!process.env.BIZXUS_API_BASE_URL?.trim()) {
  console.error('Missing required environment variable: BIZXUS_API_BASE_URL');
  process.exit(1);
}

// With a bridge key the tenant list comes from BizXusAI, so a business that has just
// been approved and saved its settings can pair without anyone editing this .env.
const bridgeKey = process.env.BIZXUS_BRIDGE_KEY?.trim() || '';

let tenantConfigs;
try {
  tenantConfigs = loadTenantConfigs(process.env, { allowEmpty: Boolean(bridgeKey) });
} catch (error) {
  console.error(error.message);
  process.exit(1);
}

if (!bridgeKey && tenantConfigs.length === 0) {
  console.error('No tenants configured and no BIZXUS_BRIDGE_KEY for discovery.');
  process.exit(1);
}

const config = {
  port: parseInteger(process.env.PORT, 3005, 1, 65535),
  apiBaseUrl: process.env.BIZXUS_API_BASE_URL.trim().replace(/\/$/, ''),
  bridgeName: process.env.BRIDGE_NAME?.trim() || 'BizXusAI WhatsApp Agent',
  fallbackReply:
    process.env.FALLBACK_REPLY?.trim() ||
    'Sorry, I could not generate a response right now. The business owner has been notified.',
  discoveryIntervalMs: parseInteger(process.env.BIZXUS_DISCOVERY_INTERVAL_SECONDS, 30, 5, 3600) * 1000,
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
    this.repairAttempts = 0;
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
      this.repairAttempts = 0;
      this.connectedNumber = normalizeJid(socket.user?.id);
      console.log(`[${this.label}] Ready. Connected number: ${maskNumber(this.connectedNumber)}`);
      await this.reportStatus();
    }

    if (connection === 'close') {
      const loggedOut = lastDisconnect?.error?.output?.statusCode === DisconnectReason.loggedOut;
      this.socket = null;
      this.connectedNumber = '';

      if (loggedOut) {
        // WhatsApp has invalidated this linked device, so the stored credentials can
        // never succeed again: every retry reproduces this same error. The page used to
        // stop here and ask for a folder to be deleted on the server, which a business
        // owner has no way to do. Clear the dead credentials and come back with a fresh
        // QR instead, so re-pairing stays self-service.
        this.repairAttempts += 1;
        this.status = 'logged_out';
        this.qrDataUrl = null;
        this.lastError = 'WhatsApp unlinked this device. Preparing a new QR code so you can connect again...';
        console.warn(`[${this.label}] ${this.lastError}`);
        await this.reportStatus();
        this.scheduleRepair(Math.min(30_000, 2_000 * this.repairAttempts));
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

  scheduleRepair(delayMs) {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.restartPairing().catch((error) => this.handleConnectionFailure(error));
    }, delayMs);
    this.reconnectTimer.unref();
  }

  /** Drop this tenant's linked-device credentials and detach the live socket. */
  async forgetCredentials() {
    clearTimeout(this.reconnectTimer);
    // Bump the generation first so events from the socket being discarded are ignored.
    this.generation += 1;
    try {
      this.socket?.ws?.close();
    } catch (error) {
      console.warn(`[${this.label}] Socket close warning during reset:`, error.message);
    }
    this.socket = null;
    this.qrDataUrl = null;
    this.connectedNumber = '';
    await fs.rm(this.config.authPath, { recursive: true, force: true });
  }

  /**
   * Start pairing from scratch: forget the old device and connect for a new QR.
   *
   * Used both when WhatsApp unlinks the device and when the owner presses "Get a new
   * QR code" on the pairing page.
   */
  async restartPairing(reason = '') {
    if (shuttingDown) return;
    await this.forgetCredentials();
    this.status = 'starting';
    this.lastError = reason;
    await this.reportStatus();
    await this.connect();
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

  async flushOutbound() {
    if (this.status !== 'ready' || !this.socket || this.flushingOutbound) return;
    this.flushingOutbound = true;
    try {
      const base = `${config.apiBaseUrl}/whatsapp/bridge/${encodeURIComponent(this.tenantId)}/outbound`;
      const headers = { 'Content-Type': 'application/json', 'X-BizXus-Bridge-Token': this.config.bridgeToken };
      for (let count = 0; count < 5 && this.status === 'ready'; count += 1) {
        const response = await fetch(`${base}/next`, { method: 'POST', headers, signal: AbortSignal.timeout(15000) });
        if (!response.ok) break;
        const body = await readJsonResponse(response);
        const message = body?.data;
        if (!message?.id) break;
        let deliveryStatus = 'sent';
        try {
          const digits = String(message.toPhone || '').replace(/\D/g, '');
          if (!/^\d{7,15}$/.test(digits)) throw new Error('Invalid recipient');
          await this.socket.sendMessage(`${digits}@s.whatsapp.net`, { text: message.messageText });
        } catch {
          deliveryStatus = 'failed';
        }
        // Claims are not automatically replayed: an interrupted acknowledgement
        // needs review, otherwise a restart could send the same report twice.
        const ack = await fetch(`${base}/${encodeURIComponent(message.id)}/ack`, { method: 'POST', headers, body: JSON.stringify({ deliveryStatus }), signal: AbortSignal.timeout(15000) });
        if (!ack.ok) throw new Error('Delivery acknowledgement failed; check the message log.');
      }
    } finally {
      this.flushingOutbound = false;
    }
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

/**
 * Live tenant registry, keyed by tenant id.
 *
 * Tenants listed in this bridge's .env are pinned: discovery may refresh their token but
 * never removes them. Tenants learned from the API are added and removed as businesses
 * connect and disconnect their WhatsApp agent.
 */
const sessions = new Map();
const pinnedTenantIds = new Set(tenantConfigs.map((tenantConfig) => tenantConfig.tenantId));

function startSession(tenantConfig) {
  const session = new TenantSession(tenantConfig);
  sessions.set(session.tenantId, session);
  console.log(`  + ${session.label} (${session.tenantId}) auth: ${session.config.authPath}`);
  session.connect().catch((error) => session.handleConnectionFailure(error));
  return session;
}

function listSessions() {
  return [...sessions.values()];
}

let discoveryInFlight = null;

/**
 * Reconcile the running sessions with the businesses BizXusAI reports.
 *
 * Concurrent callers share one request: the pairing page triggers a refresh whenever an
 * owner opens a link for a tenant this bridge has not seen yet, and that must not fan
 * out into a request per page refresh.
 */
async function syncTenantsFromApi() {
  if (!bridgeKey || shuttingDown) return;
  if (discoveryInFlight) return discoveryInFlight;

  discoveryInFlight = (async () => {
    let discovered;
    try {
      const response = await fetch(`${config.apiBaseUrl}/whatsapp/bridge/tenants`, {
        headers: { 'X-BizXus-Bridge-Key': bridgeKey },
      });
      const body = await readJsonResponse(response);
      if (!response.ok) {
        throw new Error(body?.detail || body?.message || `BizXusAI returned ${response.status}`);
      }
      discovered = body?.data?.tenants;
      if (!Array.isArray(discovered)) throw new Error('Tenant list was not an array.');
    } catch (error) {
      console.warn(`Could not refresh the tenant list: ${error.message}`);
      return;
    }

    const seen = new Set();
    for (const entry of discovered) {
      const tenantId = String(entry?.tenantId || '').trim();
      const bridgeToken = String(entry?.bridgeToken || '').trim();
      if (!tenantId || !bridgeToken) continue;
      seen.add(tenantId);

      const existing = sessions.get(tenantId);
      if (!existing) {
        startSession({
          tenantId,
          bridgeToken,
          label: String(entry?.label || '').trim() || tenantId,
          authPath: path.join('.baileys_auth', tenantId),
        });
        continue;
      }
      // A token refresh in the dashboard must not require a bridge restart.
      if (!pinnedTenantIds.has(tenantId) && existing.config.bridgeToken !== bridgeToken) {
        existing.config.bridgeToken = bridgeToken;
        console.log(`[${existing.label}] Bridge token updated from BizXusAI.`);
      }
      if (!pinnedTenantIds.has(tenantId) && entry?.label) {
        existing.config.label = String(entry.label).trim() || existing.config.label;
      }
    }

    for (const session of listSessions()) {
      if (seen.has(session.tenantId) || pinnedTenantIds.has(session.tenantId)) continue;
      console.log(`[${session.label}] No longer connected in BizXusAI; stopping this session.`);
      sessions.delete(session.tenantId);
      await session.shutdown().catch(() => undefined);
    }
  })().finally(() => {
    discoveryInFlight = null;
  });

  return discoveryInFlight;
}

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

const PAGE_STYLE =
  'body{font-family:system-ui,sans-serif;margin:0;background:#edf7f1;color:#162033}' +
  'main{max-width:760px;margin:44px auto;padding:0 16px}' +
  '.eyebrow{letter-spacing:.16em;text-transform:uppercase;color:#059669;font-weight:800;font-size:12px;text-align:center}' +
  'h1{text-align:center}' +
  '.tenant{background:#fff;border:1px solid #cfe8d6;border-radius:22px;box-shadow:0 18px 50px #065f4630;text-align:center;padding:24px;margin-bottom:20px}' +
  'img{max-width:100%;height:auto;border-radius:18px;border:1px solid #d9eadf}' +
  'code{background:#eef7f1;padding:4px 8px;border-radius:8px}' +
  '.success{font-weight:800;color:#047857}' +
  '.error{color:#b91c1c;overflow-wrap:anywhere}' +
  '.muted{color:#667085;font-size:14px;line-height:1.6}' +
  '.steps{text-align:left;max-width:360px;margin:16px auto;padding-left:20px;line-height:1.8}' +
  '.reset{margin-top:18px}' +
  '.reset button{font:inherit;font-weight:700;cursor:pointer;border:1px solid #cfe8d6;background:#f6fbf8;color:#065f46;border-radius:10px;padding:10px 16px}' +
  '.pending{display:inline-block;width:14px;height:14px;border:3px solid #cfe8d6;border-top-color:#059669;border-radius:50%;animation:spin 1s linear infinite;vertical-align:-2px;margin-right:8px}' +
  '@keyframes spin{to{transform:rotate(360deg)}}';

const LINK_STEPS =
  '<ol class="steps">' +
  '<li>Open WhatsApp on the business phone.</li>' +
  '<li>Go to <strong>Settings &rarr; Linked devices</strong>.</li>' +
  '<li>Tap <strong>Link a device</strong>.</li>' +
  '<li>Scan the code below.</li>' +
  '</ol>';

function renderPage(bodyHtml, { refreshSeconds = 5 } = {}) {
  const refresh = refreshSeconds ? `<meta http-equiv="refresh" content="${refreshSeconds}"/>` : '';
  return (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"/>' +
    '<meta name="viewport" content="width=device-width,initial-scale=1"/>' +
    `${refresh}<title>BizXusAI WhatsApp Bridge</title><style>${PAGE_STYLE}</style></head>` +
    '<body><main><div class="eyebrow">BizXusAI WhatsApp Bridge</div>' +
    `<h1>Connect Business WhatsApp</h1>${bodyHtml}` +
    '<p class="muted" style="text-align:center">This page refreshes automatically. ' +
    'Keep this bridge running while the WhatsApp agents are active.</p></main></body></html>'
  );
}

function renderTenantCard(session, suffix = '', prefix = '') {
  const statusText = session.status.replaceAll('_', ' ');
  const body = session.qrDataUrl
    ? `${LINK_STEPS}<img src="${session.qrDataUrl}" width="320" height="320" alt="WhatsApp QR code" />`
    : session.status === 'ready'
      ? '<p class="success">Connected. BizXusAI is replying from this number.</p>'
      : '<p><span class="pending"></span>Preparing your QR code. This page will show it automatically.</p>';
  const number = session.connectedNumber
    ? `<p>Connected number: <code>${escapeHtml(maskNumber(session.connectedNumber))}</code></p>`
    : '';
  const error = session.lastError ? `<p class="error">${escapeHtml(session.lastError)}</p>` : '';
  // Re-pairing is the owner's own recovery path, so it must be a button rather than a
  // filesystem instruction. It is offered whenever the session is not mid-scan.
  const reset = session.qrDataUrl
    ? ''
    : `<form class="reset" method="post" action="${prefix}/pair/${encodeURIComponent(session.tenantId)}/reset${escapeHtml(suffix)}">` +
      `<button type="submit">${session.status === 'ready' ? 'Disconnect and pair a different number' : 'Get a new QR code'}</button></form>`;
  return (
    `<section class="tenant"><h2>${escapeHtml(session.label)}</h2>` +
    `<p>Status: <code>${escapeHtml(statusText)}</code></p>` +
    `<p class="muted">Tenant: <code>${escapeHtml(session.tenantId)}</code></p>` +
    `${number}${body}${error}${reset}</section>`
  );
}

function renderUnknownTenantCard(tenantId) {
  // What the owner should do differs by deployment, so say which one this is rather than
  // giving instructions that do not apply.
  const advice = bridgeKey
    ? '<p class="muted">In the BizXusAI dashboard open <strong>WhatsApp Agent</strong>, enter the business ' +
      'WhatsApp number, press <strong>Save / Connect</strong>, then reload this page. If it still does not ' +
      'appear, the WhatsApp Agent module has not been approved for this business yet.</p>'
    : '<p class="muted">This bridge is not connected to BizXusAI tenant discovery. Set ' +
      '<code>BIZXUS_BRIDGE_KEY</code> in <code>whatsapp-bridge/.env</code> to match ' +
      '<code>WHATSAPP_BRIDGE_ADMIN_KEY</code> on the API and restart the bridge, or add this business to ' +
      '<code>BIZXUS_TENANTS</code> by hand.</p>';
  return (
    '<section class="tenant"><h2>This business is not connected yet</h2>' +
    `<p class="muted">Tenant: <code>${escapeHtml(tenantId)}</code></p>` +
    '<p class="error">BizXusAI has no saved WhatsApp settings for this business, so there is nothing to pair.</p>' +
    `${advice}</section>`
  );
}

function findSession(tenantId) {
  return sessions.get(tenantId) || null;
}

/**
 * Find a tenant's session, asking BizXusAI once if this bridge has not seen it.
 *
 * An owner clicks their pairing link the moment they save their settings, which is
 * usually before the next discovery poll. Refreshing on the miss means the link works
 * straight away instead of showing "not on the bridge yet" for up to a poll interval.
 */
async function resolveSession(tenantId) {
  const existing = findSession(tenantId);
  if (existing) return existing;
  await syncTenantsFromApi();
  return findSession(tenantId);
}

function sendHtml(response, statusCode, html) {
  response.writeHead(statusCode, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY' });
  response.end(html);
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`);
  // Named `route` rather than `path` so it does not shadow the node:path import.
  const route = url.pathname.length > 1 ? url.pathname.replace(/\/+$/, '') : url.pathname;
  const prefix = request.headers['x-forwarded-prefix'] === '/whatsapp-bridge' ? '/whatsapp-bridge' : '';
  const pairing = /^\/pair\/([a-f0-9]{24})(?:\/reset)?$/.exec(route);
  if (route.startsWith('/pair/')) {
    const session = pairing ? await resolveSession(pairing[1]) : null;
    if (!session || !validPairingGrant(url, session.tenantId, session.config.bridgeToken)) {
      sendHtml(response, 403, renderPage('<p>Open a fresh connection link from your business dashboard.</p>', { refreshSeconds: 0 }));
      return;
    }
  }

  if (route === '/health') {
    const all = listSessions();
    const allReady = all.length > 0 && all.every((session) => session.status === 'ready');
    response.writeHead(allReady ? 200 : 503, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    response.end(
      JSON.stringify({
        ready: allReady,
      }),
    );
    return;
  }

  // The dashboard links a business owner straight to their own pairing page, so one
  // owner never sees another tenant's card, id, or connected number.
  const resetMatch = /^\/pair\/([^/]+)\/reset$/.exec(route);
  if (resetMatch) {
    const tenantId = decodeURIComponent(resetMatch[1]);
    const session = await resolveSession(tenantId);
    if (!session) {
      sendHtml(response, 404, renderPage(renderUnknownTenantCard(tenantId), { refreshSeconds: 0 }));
      return;
    }
    if (request.method !== 'POST') {
      response.writeHead(405, { Allow: 'POST', 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Use POST to reset a pairing.');
      return;
    }
    console.log(`[${session.label}] Owner requested a new QR code from the pairing page.`);
    session
      .restartPairing('Reset requested. Scan the new QR code below.')
      .catch((error) => session.handleConnectionFailure(error));
    // Redirect so a page refresh does not repeat the reset.
    response.writeHead(303, { Location: `${prefix}/pair/${encodeURIComponent(session.tenantId)}${url.search}`, 'Cache-Control': 'no-store' });
    response.end();
    return;
  }

  const pairMatch = /^\/pair\/([^/]+)$/.exec(route);
  if (pairMatch) {
    const tenantId = decodeURIComponent(pairMatch[1]);
    const session = await resolveSession(tenantId);
    if (!session) {
      sendHtml(response, 404, renderPage(renderUnknownTenantCard(tenantId), { refreshSeconds: 0 }));
      return;
    }
    sendHtml(response, 200, renderPage(renderTenantCard(session, url.search, prefix)));
    return;
  }

  if (route === '/') {
    sendHtml(response, 200, renderPage('<p>Open your business dashboard to connect WhatsApp.</p>', { refreshSeconds: 0 }));
    return;
  }

  response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  response.end('Not found');
});

server.listen(config.port, '0.0.0.0', async () => {
  console.log(`BizXusAI WhatsApp bridge on http://localhost:${config.port}`);
  for (const tenantConfig of tenantConfigs) startSession(tenantConfig);
  const heartbeat = setInterval(() => {
    for (const session of listSessions()) {
      session.reportStatus().catch(() => undefined);
      session.flushOutbound().catch((error) => console.warn(`[${session.label}] Outbound queue: ${error.message}`));
    }
  }, 15000);
  heartbeat.unref();

  if (bridgeKey) {
    console.log(`Discovering businesses from ${config.apiBaseUrl} every ${config.discoveryIntervalMs / 1000}s.`);
    await syncTenantsFromApi();
    const timer = setInterval(() => {
      syncTenantsFromApi().catch((error) => console.warn('Tenant refresh failed:', error.message));
    }, config.discoveryIntervalMs);
    timer.unref();
  } else {
    console.log('BIZXUS_BRIDGE_KEY is not set, so only the businesses in this .env can pair.');
  }
  console.log(`Serving ${sessions.size} business(es).`);
});

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`\nReceived ${signal}. Closing WhatsApp bridge...`);
  await Promise.allSettled(listSessions().map((session) => session.shutdown()));
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('unhandledRejection', (reason) => console.error('Unhandled promise rejection:', reason));
process.on('uncaughtException', (error) => console.error('Uncaught exception:', error));
