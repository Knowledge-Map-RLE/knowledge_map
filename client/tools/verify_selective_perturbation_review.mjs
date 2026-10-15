import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Проверяем автономность и действительные квитанции, не научную интерпретацию.
const file = path.resolve(process.argv[2]);
const html = fs.readFileSync(file, 'utf8');
const dom = new JSDOM(html); const doc = dom.window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,iframe,img,link').length, 0);
assert.equal(doc.querySelectorAll('.candidate').length, 2);
assert.ok(doc.body.textContent.includes('Преимущество графа не доказано'));
assert.ok(doc.body.textContent.includes('Точность не определена'));
for (const a of doc.querySelectorAll('a')) {
  assert.ok(!a.href.startsWith('http')); assert.ok(fs.existsSync(path.resolve(path.dirname(file), a.getAttribute('href'))));
}
const data = JSON.parse(fs.readFileSync(path.join(path.dirname(file), 'data.json')));
const v = data.verification;
assert.equal(v.canonical_blocks, 759); assert.equal(v.statements, 1478);
assert.equal(data.coverage.length, 759); assert.equal(v.python_tests_passed, 126);
assert.equal(v.future_results_scored, 0); assert.equal(v.accuracy, null);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(data.candidates.semantic_role_join.length, 2);
for (const c of data.candidates.semantic_role_join) {
  assert.equal(c.logical_entailment, false); assert.equal(c.comparative_efficacy_predicted, false);
  assert.equal(c.parent_frames.length, 3); assert.equal(c.source_quotes.length, 15);
  assert.equal(Object.keys(c.identity_parent_frames).length, 3);
}
const root = path.dirname(path.dirname(file));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v4.xml'))), v.test_results_sha256);
const source = JSON.parse(fs.readFileSync(path.join(root, 'screening-v1/PMC10313728/source-v1.json')));
assert.equal(hash(Buffer.from(source.text)), source.sha256);
for (const q of data.screening.screening.at(-1).evidence) {
  assert.equal(Array.from(source.text).slice(q.start, q.end).join(''), q.text);
}
const check = { passed: true, language: 'ru', external_resources: 0, candidates: 2, future_results_scored: 0,
  scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false };
const output = path.join(path.dirname(file), 'html-verification.json');
const bytes = JSON.stringify(check, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(check));
