// Runs the real getBigQueryConnectionInfo out of template.js, so this test
// cannot drift from the code. Run: node scripts/test-bq-target.js
const assert = require('assert');
const fs = require('fs');

const src = fs.readFileSync('template.js', 'utf8');
const m = src.match(/^function getBigQueryConnectionInfo\([\s\S]*?^}/m);
assert.ok(m, 'getBigQueryConnectionInfo not found in template.js');

// The function reads the tag config off a `data` global, as it does in the sandbox.
const build = (table) =>
  new Function('data', m[0] + '\nreturn getBigQueryConnectionInfo();')({
    logBigQueryTable: table
  });

// Three parts name the project explicitly.
assert.deepStrictEqual(build('my-project.dev_dataset.ragingbull_s2s'), {
  projectId: 'my-project',
  datasetId: 'dev_dataset',
  tableId: 'ragingbull_s2s'
});

// Two parts leave the project to GOOGLE_CLOUD_PROJECT, as an omitted projectId did.
assert.deepStrictEqual(build('dev_dataset.ragingbull_s2s'), {
  datasetId: 'dev_dataset',
  tableId: 'ragingbull_s2s'
});

// Anything else is not a table, and must not reach BigQuery.insert.
['', 'ragingbull_s2s', 'a.b.c.d', undefined].forEach((bad) => {
  assert.strictEqual(build(bad), undefined, 'accepted a bad table: ' + bad);
});

console.log('test-bq-target: ok');
