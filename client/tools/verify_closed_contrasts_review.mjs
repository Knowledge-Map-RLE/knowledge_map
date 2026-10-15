import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Проверяется отчёт и точное происхождение, без заявления научной истинности.
const file = path.resolve(process.argv[2]), folder = path.dirname(file), root = path.dirname(folder);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const doc = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,link,img,iframe').length, 0);
assert.equal(doc.querySelectorAll('.card').length, 4);
assert.equal(doc.querySelectorAll('details.profile').length, 51);
assert.equal(doc.querySelectorAll('#sources tbody tr').length, 9);
assert.ok(doc.body.textContent.includes('Критерий успеха не достигнут'));
assert.ok(doc.body.textContent.includes('Точность не определена'));
for (const a of doc.querySelectorAll('a')) {
  const href = a.getAttribute('href'); assert.ok(!/^[a-z]+:/i.test(href));
  const target = path.resolve(folder, href);
  assert.ok(target.startsWith(root + path.sep) && fs.existsSync(target));
}
const data = read(path.join(folder, 'data.json')), v = data.verification;
assert.equal(v.canonical_blocks, 812); assert.equal(v.native_statements, 1593);
assert.equal(v.closed_profiles, 51); assert.equal(v.typed_table_parts, 165);
assert.equal(v.python_tests_passed, 99);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.accuracy, null); assert.equal(v.future_results_scored, 0);
assert.equal(v.target_read, false); assert.equal(v.model_calls, 0);
assert.equal(v.new_forecasts_from_this_stage, 0);
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v2.xml'))), v.test_results_sha256);
const run = path.join(root, 'runs', v.run_id), artifact = read(path.join(run, 'predictions.json'));
assert.deepEqual(artifact.profiles, data.profiles);
const inputs = read(path.join(run, 'inputs-manifest.json')), maps = new Map(), parents = new Map();
assert.equal(inputs.sources.length, 9);
for (const s of inputs.sources) {
  const bytes = fs.readFileSync(path.join(run, s.map_path));
  assert.equal(hash(bytes), s.map_file_sha256);
  const m = JSON.parse(bytes), text = Array.from(m.source.text);
  assert.equal(hash(Buffer.from(m.source.text)), m.source.sha256);
  assert.notEqual(m.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  for (const u of m.source.units) assert.equal(text.slice(u.start, u.end).join(''), u.text);
  maps.set(m.article_id, m);
  for (const k of m.graph.knowledge) parents.set(JSON.stringify([m.article_id, k.knowledge_id]), k);
  if (s.coverage_path) assert.equal(hash(fs.readFileSync(path.join(run, s.coverage_path))), s.coverage_sha256);
}
assert.equal(parents.size, 812);
assert.equal(new Set(data.profiles.map(p => p.id)).size, 51);
let parts = 0;
for (const [i, p] of data.profiles.entries()) {
  const proof = p.proof, parent = parents.get(JSON.stringify(p.key)), source = maps.get(p.key[0]).source;
  assert.deepEqual(proof.complete_native_knowledge, parent);
  assert.equal(parent.semantic_frame.logic, 'contrast');
  assert.equal(p.rows.length, parent.semantic_frame.statements.length);
  assert.deepEqual(proof.all_statement_positions, p.rows.map((r, j) => j));
  assert.equal(proof.conditions_removed, false); assert.equal(proof.causality_asserted, false);
  assert.equal(proof.independent_replication, false); assert.equal(p.forecast_of_future_article, false);
  assert.equal(p.separate_part_premise_license, false); assert.equal(p.measurement_basis.cross_source_measure_equivalence, false);
  const b = proof.source_binding;
  assert.equal(b.source_sha256, source.sha256);
  for (const span of [b.row, b.header].filter(Boolean))
    assert.equal(Array.from(source.text).slice(span.start, span.end).join(''), span.text);
  assert.deepEqual(proof.complete_parent_provenance, parent.semantic_frame.statements.map(s => s.provenance));
  for (const order of p.orders) {
    const values = p.rows.map(r => Number(r.summary[order.field]));
    assert.ok(values.every(Number.isFinite));
    const distinct = [...new Set(values)].sort((a, b) => a - b);
    assert.deepEqual(order.ascending_dense_ranks, values.map(x => distinct.indexOf(x) + 1));
    assert.equal(order.statistical_significance, 'not_established');
  }
  const detail = doc.querySelectorAll('details.profile')[i];
  assert.ok(detail.querySelector('summary').textContent.includes(p.key.join(' / ')));
  assert.equal(detail.querySelectorAll('tbody tr').length, p.rows.length);
  assert.equal(detail.querySelector('pre').textContent, b.row.text);
  parts += p.rows.length;
}
assert.equal(parts, 165);
assert.equal(Object.values(data.counts).reduce((a, b) => a + b, 0), 812);
assert.deepEqual(data.rejected.map(r => r.key).sort(), [['PMC5005896', 'K37'], ['PMC5005896', 'K38'], ['PMC6218168', 'K38']]);
for (const [name, digest] of Object.entries(artifact.binding.implementation))
  assert.equal(hash(fs.readFileSync(path.join(run, 'implementation', name))), digest);
for (const [name, digest] of Object.entries(artifact.binding.metadata.input_audit_file_sha256))
  assert.equal(hash(fs.readFileSync(path.join(run, name + '.json'))), digest);
const result = { passed: true, language: 'ru', external_resources: 0, canonical_blocks: 812,
  profiles: 51, typed_parts: 165, exact_native_parents_verified: true, unicode_provenance_verified: true,
  python_tests_passed: 99, scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false };
const output = path.join(folder, 'html-verification.json'), bytes = JSON.stringify(result, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(result));
