// Runs the real redactUrlSecrets/maskSecret out of template.js, so this test
// cannot drift from the code it checks. Run: node scripts/test-redact.js
const assert = require('assert');
const fs = require('fs');

const src = fs.readFileSync('template.js', 'utf8');
const fns = ['redactUrlSecrets', 'maskSecret'].map((name) => {
  const m = src.match(new RegExp('^function ' + name + '\\([\\s\\S]*?^}', 'm'));
  assert.ok(m, name + ' not found in template.js');
  return m[0];
});
const { redactUrlSecrets } = new Function(fns.join('\n') + '\nreturn { redactUrlSecrets };')();

const KEY = 'abcd1234567890abcdefghijklmnopqrstuvWXYZ';
const stape = (k) => 'https://acme.eu.stape.io/stape-api/' + k + '/v2/data-manager/events/ingest';

// The container API key is masked, and enough survives to tell two keys apart.
let out = redactUrlSecrets(stape(KEY));
assert.strictEqual(out, stape('abcd...WXYZ'));
assert.ok(!out.includes(KEY));

// The rest of the path keeps its place, so the endpoint stays readable.
assert.ok(out.endsWith('/v2/data-manager/events/ingest'));
assert.ok(out.startsWith('https://acme.eu.stape.io/stape-api/'));

// A short key is masked whole rather than mostly shown.
assert.strictEqual(redactUrlSecrets(stape('short12chars')), stape('[redacted]'));

// The 'own' auth flow hits Google directly and carries nothing sensitive.
const google = 'https://datamanager.googleapis.com/v1/events:ingest';
assert.strictEqual(redactUrlSecrets(google), google);

// A key at the end of the URL, with no trailing path, is still masked.
assert.strictEqual(
  redactUrlSecrets('https://acme.eu.stape.io/stape-api/' + KEY),
  'https://acme.eu.stape.io/stape-api/abcd...WXYZ'
);

console.log('test-redact: ok');
