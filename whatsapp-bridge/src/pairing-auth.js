import { createHmac, timingSafeEqual } from 'node:crypto';

export function validPairingGrant(url, tenantId, secret, now = Math.floor(Date.now() / 1000)) {
  const expires = url.searchParams.get('expires') || '';
  const grant = url.searchParams.get('grant') || '';
  if (!secret || !/^\d+$/.test(expires) || !/^[a-f0-9]{64}$/.test(grant)) return false;
  if (Number(expires) <= now || Number(expires) > now + 600) return false;
  const expected = createHmac('sha256', secret).update(`pair:${tenantId}:${expires}`).digest();
  return timingSafeEqual(expected, Buffer.from(grant, 'hex'));
}
