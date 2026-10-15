// Скрининг совместимости не считается подтверждением или опровержением прогноза.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root = path.resolve(process.argv[2]);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
const data = read(path.join(root, 'data.json')); const v = data.verification;
const folder = path.resolve(root, '../runs', v.run_id); const result = read(path.join(folder, 'predictions.json'));
assert.equal(v.metadata_records, 46); assert.equal(v.specific_later_records, 8);
assert.equal(v.full_primary_sources, 2); assert.equal(v.confirmed_predictions, 0);
assert.equal(v.directional_outcomes_scored, 0); assert.equal(v.eligible_protocol_comparisons, 0);
assert.equal(v.accuracy, null); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(hash(fs.readFileSync(path.resolve(root, '../test-results-v1.xml'))), v.test_results_sha256);
assert.equal(v.python_tests_passed, 156); assert.deepEqual(data.comparisons, result.comparisons);
assert.equal(result.comparisons.length, 8); assert.ok(result.comparisons.every(c => c.status === 'incompatible_context'));
for (const entry of read(path.join(folder, 'source-manifest.json')).sources) {
  const raw = fs.readFileSync(path.join(folder, 'controls', entry.id + '.json'));
  assert.equal(hash(raw), entry.file_sha256); const p = JSON.parse(raw); const points = Array.from(p.source.text);
  assert.equal(hash(p.source.text), p.source.sha256);
  for (const u of p.source.units) assert.equal(points.slice(u.start, u.end).join(''), u.text);
}
for (const [name, digest] of Object.entries(result.binding.implementation)) assert.equal(hash(fs.readFileSync(path.join(folder, 'implementation', name))), digest);
const html = fs.readFileSync(path.join(root, 'report.html'), 'utf8');
assert.ok(html.includes('lang="ru"'));
assert.ok(!/<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i.test(html));
const receipt = {records: 46, later_records: 8, full_controls: 2, compatible: 0, confirmed: 0,
  source_unicode_verified: true, report_sha256: hash(html), external_resources: 0, visual_inspection: false};
const output = path.join(root, 'html-verification.json'); const raw = JSON.stringify(receipt, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), raw); else fs.writeFileSync(output, raw, {flag: 'wx'});
console.log(JSON.stringify(receipt));
