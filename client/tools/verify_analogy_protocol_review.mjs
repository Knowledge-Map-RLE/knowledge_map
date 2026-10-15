// Проверка автономного русского отчёта и привязки всех цитат к источникам.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root = path.resolve(process.argv[2]);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const data = read(path.join(root, 'data.json'));
const v = data.verification;
assert.equal(v.findings, 6); assert.equal(v.reviewed_tasks, 4);
assert.equal(v.confirmed_transfers, 0); assert.equal(v.python_tests_passed, 114);
const folder = path.resolve(root, '../runs', v.run_id);
const sources = Object.fromEntries(Object.entries(data.source_index).map(([sid, p]) => [sid, read(path.join(folder, p)).source]));
for (const finding of data.findings) for (const e of finding.evidence) {
  const source = sources[e.source_id];
  assert.equal(Array.from(source.text).slice(e.start, e.end).join(''), e.text);
  assert.equal(crypto.createHash('sha256').update(e.text).digest('hex'), e.sha256);
  assert.ok(e.end <= source.content_end);
}
const html = fs.readFileSync(path.join(root, 'report.html'), 'utf8');
assert.ok(html.includes('lang="ru"'));
assert.ok(!/(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i.test(html));
const receipt = {report_sha256: crypto.createHash('sha256').update(html).digest('hex'),
  findings_verified: 6, source_unicode_verified: true, external_resources: 0, visual_inspection: false};
const output = path.join(root, 'html-verification.json');
const raw = JSON.stringify(receipt, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), raw);
else fs.writeFileSync(output, raw, {flag: 'wx'});
console.log(JSON.stringify(receipt));
