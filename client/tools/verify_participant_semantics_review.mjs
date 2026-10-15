import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Проверка происхождения и автономности не удостоверяет научную правильность.
const file = path.resolve(process.argv[2]);
const folder = path.dirname(file), root = path.dirname(folder);
const read = name => JSON.parse(fs.readFileSync(name, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const doc = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,iframe,img,link').length, 0);
assert.equal(doc.querySelectorAll('.change').length, 4);
assert.equal(doc.querySelectorAll('tbody tr').length, 6);
assert.ok(doc.body.textContent.includes('Критерий успеха не достигнут'));
for (const a of doc.querySelectorAll('a')) {
  const href = a.getAttribute('href');
  assert.ok(!/^[a-z]+:/i.test(href));
  const target = path.resolve(folder, href);
  assert.ok(target.startsWith(root + path.sep) && fs.existsSync(target));
}
const data = read(path.join(folder, 'data.json')), v = data.verification;
assert.equal(v.canonical_blocks, 812); assert.equal(v.source_count, 9);
assert.equal(v.statement_count_before, 1563); assert.equal(v.statement_count_after, 1593);
assert.equal(v.flags_before, 16); assert.equal(v.flags_after, 0);
assert.equal(v.python_tests_passed, 105); assert.equal(v.model_calls, 0);
assert.equal(v.future_results_scored, 0); assert.equal(v.accuracy, null);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.new_independent_experiments, 0); assert.equal(v.source_semantic_completeness_certified, false);
assert.equal(data.whole_map_coverage.length, 812);
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v3.xml'))), v.test_results_sha256);
for (const [i, row] of data.mode_comparison.entries()) {
  assert.equal(row.before, i < 4 ? 0 : 20); assert.equal(row.after, row.before);
}
const mapFolder = path.join(root, 'maps', v.map_run), map = read(path.join(mapFolder, 'map.json'));
const manifest = read(path.join(mapFolder, 'manifest.json'));
for (const [name, digest] of Object.entries(manifest.files)) {
  const target = path.resolve(mapFolder, name);
  assert.ok(target.startsWith(mapFolder + path.sep));
  assert.equal(hash(fs.readFileSync(target)), digest);
}
assert.equal(hash(Buffer.from(map.source.text)), map.source.sha256);
for (const unit of map.source.units) {
  assert.equal(Array.from(map.source.text).slice(unit.start, unit.end).join(''), unit.text);
}
assert.equal(map.graph.knowledge.length, 53);
assert.equal(map.graph.knowledge.reduce((sum, k) => sum + k.semantic_frame.statements.length, 0), 115);
const old = read(path.resolve(root, '../tnfr1-primary-expansion-v1/maps/6b9e85af-2004-5c1e-b344-167dbed156ab/map.json'));
assert.deepEqual(map.source, old.source); assert.deepEqual(map.graph.edges, old.graph.edges);
assert.deepEqual(map.graph.knowledge.map(k => [k.knowledge_id, k.display_text]), old.graph.knowledge.map(k => [k.knowledge_id, k.display_text]));
assert.deepEqual(map.translations.ru.labels, old.translations.ru.labels);
const gene = map.graph.concepts.find(c => c.display_text === 'Mouse Cldn1 gene');
const protein = map.graph.concepts.find(c => c.display_text === 'Mouse CLDN1 protein');
assert.ok(gene && protein && gene.id !== protein.id);
const mapDoc = new JSDOM(fs.readFileSync(path.join(mapFolder, 'map.html'), 'utf8')).window.document;
assert.equal(mapDoc.querySelectorAll('script[src],link[href],iframe').length, 0);
assert.equal(JSON.parse(mapDoc.getElementById('data').textContent).run_id, v.map_run);
const check = { passed: true, language: 'ru', report_external_resources: 0, change_cards: 4,
  whole_map_blocks: 812, source_count: 9, statement_count: 1593, flags_before: 16, flags_after: 0,
  python_tests_passed: 105, unicode_provenance_verified: true, visible_map_preserved: true,
  scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false };
const output = path.join(folder, 'html-verification.json'), bytes = JSON.stringify(check, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(check));
