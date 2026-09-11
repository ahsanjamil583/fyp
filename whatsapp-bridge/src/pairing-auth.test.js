import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { validPairingGrant } from './pairing-auth.js';

const tenant = 'aaaaaaaaaaaaaaaaaaaaaaaa';
const secret = 'test-only-key';
const now = 1000;
function url(expires = 1300) {
  const grant = createHmac('sha256', secret).update(`pair:${tenant}:${expires}`).digest('hex');
  return new URL(`http://localhost/pair/${tenant}?expires=${expires}&grant=${grant}`);
}
test('valid scoped grant is accepted', () => assert.equal(validPairingGrant(url(), tenant, secret, now), true));
test('another tenant cannot reuse a grant', () => assert.equal(validPairingGrant(url(), 'bbbbbbbbbbbbbbbbbbbbbbbb', secret, now), false));
test('expired grant is rejected', () => assert.equal(validPairingGrant(url(999), tenant, secret, now), false));
test('grant with excessive lifetime is rejected', () => assert.equal(validPairingGrant(url(2000), tenant, secret, now), false));
test('missing or malformed grant is rejected', () => {
  assert.equal(validPairingGrant(new URL('http://localhost/'), tenant, secret, now), false);
  const altered = url();
  altered.searchParams.set('grant', 'bad');
  assert.equal(validPairingGrant(altered, tenant, secret, now), false);
});
