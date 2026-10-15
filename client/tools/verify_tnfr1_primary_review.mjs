import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Проверяются автономность, реальные результаты и Unicode-происхождение, не научная истинность.
const file = path.resolve(process.argv[2]);
const folder = path.dirname(file), root = path.dirname(folder);
const html = fs.readFileSync(file, 'utf8');
const doc = new JSDOM(html).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,iframe,img,link').length, 0);
assert.equal(doc.querySelectorAll('.evidence').length, 5);
assert.equal(doc.querySelectorAll('tbody tr').length, 6);
assert.ok(doc.body.textContent.includes('Критерий успеха не достигнут'));
assert.ok(doc.body.textContent.includes('Преимущество графа не доказано'));
assert.ok(doc.body.textContent.includes('Точность не определена'));
for (const a of doc.querySelectorAll('a')) {
  const href = a.getAttribute('href');
  assert.ok(!/^[a-z]+:/i.test(href));
  const target = path.resolve(folder, href);
  assert.ok(target.startsWith(root + path.sep));
  assert.ok(fs.existsSync(target));
}
const data = JSON.parse(fs.readFileSync(path.join(folder, 'data.json')));
const v = data.verification;
assert.equal(v.sources, 9); assert.equal(v.canonical_blocks, 812); assert.equal(v.statement_count, 1563);
assert.equal(v.new_statements_registered, 85); assert.equal(v.python_tests_passed, 77);
assert.equal(v.model_calls, 0); assert.equal(v.future_results_scored, 0); assert.equal(v.accuracy, null);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.semantic_completeness_certified, false);
assert.equal(data.whole_map_coverage.length, 812);
assert.equal(data.coverage.units.length, 135);
for (const row of data.mode_comparison) {
  assert.equal(row.before, row.new_empirical_forecasts ? 0 : 20);
  assert.equal(row.after, row.new_empirical_forecasts ? 0 : 20);
}
const hash = value => createHash('sha256').update(value).digest('hex');
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v5.xml'))), v.test_results_sha256);
const mapFolder = path.join(root, 'maps', v.map_run);
const map = JSON.parse(fs.readFileSync(path.join(mapFolder, 'map.json')));
assert.equal(hash(Buffer.from(map.source.text)), map.source.sha256);
for (const row of data.novelty.rows) {
  assert.equal(row.full_context_equivalence, false);
  assert.equal(row.future_match_scored, false);
  for (const proof of row.evidence) {
    assert.equal(Array.from(map.source.text).slice(proof.start, proof.end).join(''), proof.text);
    assert.equal(hash(Buffer.from(proof.text)), proof.sha256);
  }
}
const mapHtml = fs.readFileSync(path.join(mapFolder, 'map.html'), 'utf8');
const mapDoc = new JSDOM(mapHtml).window.document;
assert.equal(mapDoc.querySelectorAll('script[src],link[href],iframe').length, 0);
const embedded = JSON.parse(mapDoc.getElementById('data').textContent);
assert.equal(embedded.run_id, map.run_id);
assert.equal(embedded.graph.knowledge.length, 53);
assert.ok(embedded.translations.ru);
const check = { passed: true, language: 'ru', report_external_resources: 0, evidence_cards: 5,
  whole_map_blocks: 812, source_units: 135, scientific_success: false, graph_advantage_demonstrated: false,
  unicode_provenance_verified: true, visual_inspection: false };
const output = path.join(folder, 'html-verification.json');
const bytes = JSON.stringify(check, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(check));
