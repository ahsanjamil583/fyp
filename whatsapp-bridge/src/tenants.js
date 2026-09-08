import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

/**
 * Resolve the tenants this bridge should connect.
 *
 * The bridge used to take a single BIZXUS_TENANT_ID, so a second business meant a
 * second process on a second port with its own env file. Tenants are now a list, and
 * the single-tenant variables still work so existing setups keep running unchanged.
 *
 * Config is read from, in order of precedence:
 *   1. BIZXUS_TENANTS_FILE — path to a JSON array
 *   2. BIZXUS_TENANTS      — inline JSON array
 *   3. BIZXUS_TENANT_ID + BIZXUS_WHATSAPP_BRIDGE_TOKEN (legacy single tenant)
 *
 * Each entry: { "tenantId": "...", "bridgeToken": "...", "label": "optional", "authPath": "optional" }
 */
export function loadTenantConfigs(env = process.env) {
  const entries = readTenantEntries(env);

  if (entries.length === 0) {
    throw new Error(
      'No tenants configured. Set BIZXUS_TENANTS (JSON array), BIZXUS_TENANTS_FILE, ' +
        'or the single-tenant pair BIZXUS_TENANT_ID and BIZXUS_WHATSAPP_BRIDGE_TOKEN.',
    );
  }

  const seen = new Set();
  return entries.map((entry, index) => {
    const tenantId = String(entry.tenantId ?? '').trim();
    const bridgeToken = String(entry.bridgeToken ?? '').trim();

    if (!tenantId) throw new Error(`Tenant #${index + 1} is missing "tenantId".`);
    if (!bridgeToken) throw new Error(`Tenant ${tenantId} is missing "bridgeToken".`);
    if (seen.has(tenantId)) throw new Error(`Tenant ${tenantId} is listed more than once.`);
    seen.add(tenantId);

    return {
      tenantId,
      bridgeToken,
      label: String(entry.label ?? '').trim() || tenantId,
      // Each tenant is a separate linked device and must never share credentials.
      authPath: String(entry.authPath ?? '').trim() || path.join('.baileys_auth', tenantId),
    };
  });
}

function readTenantEntries(env) {
  const filePath = env.BIZXUS_TENANTS_FILE?.trim();
  if (filePath) {
    const raw = fs.readFileSync(filePath, 'utf8');
    return parseTenantArray(raw, `BIZXUS_TENANTS_FILE (${filePath})`);
  }

  const inline = env.BIZXUS_TENANTS?.trim();
  if (inline) {
    return parseTenantArray(inline, 'BIZXUS_TENANTS');
  }

  const tenantId = env.BIZXUS_TENANT_ID?.trim();
  const bridgeToken = env.BIZXUS_WHATSAPP_BRIDGE_TOKEN?.trim();
  if (tenantId && bridgeToken) {
    return [
      {
        tenantId,
        bridgeToken,
        label: env.BRIDGE_LABEL?.trim() || tenantId,
        authPath: env.WHATSAPP_AUTH_PATH?.trim() || '',
      },
    ];
  }

  return [];
}

function parseTenantArray(raw, source) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error(`${source} is not valid JSON: ${error.message}`);
  }
  if (!Array.isArray(parsed)) {
    throw new Error(`${source} must be a JSON array of tenant objects.`);
  }
  return parsed;
}
