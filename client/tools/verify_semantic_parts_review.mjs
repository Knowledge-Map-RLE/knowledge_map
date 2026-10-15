import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Проверяем автономность, точное происхождение и границы результата, не научную истинность.
const file = path.resolve(process.argv[2]), folder = path.dirname(file), root = path.dirname(folder);
const read = name => JSON.parse(fs.readFileSync(name, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const doc = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,iframe,img,link').length, 0);
assert.equal(doc.querySelectorAll('.card').length, 4);
assert.equal(doc.querySelectorAll('tbody tr').length, 4);
assert.ok(doc.body.textContent.includes('Критерий успеха не достигнут'));
assert.ok(doc.body.textContent.includes('Точность не определена'));
for (const a of doc.querySelectorAll('a')) {
  const href = a.getAttribute('href'); assert.ok(!/^[a-z]+:/i.test(href));
  const target = path.resolve(folder, href);
  assert.ok(target.startsWith(root + path.sep) && fs.existsSync(target));
}
const data = read(path.join(folder, 'data.json')), v = data.verification;
assert.equal(v.canonical_blocks, 812); assert.equal(v.native_statements, 1593);
assert.equal(v.licensed_parts, 552); assert.equal(v.source_count, 9);
assert.equal(v.licensed_parents + v.unlicensed_compound_parents + v.unknown_context_parents, 812);
assert.equal(v.model_calls, 0); assert.equal(v.target_read, false); assert.equal(v.future_results_scored, 0);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(v.source_semantic_completeness_certified, false); assert.equal(v.accuracy, null);
assert.equal(v.known_author_joint_group_required, false); assert.equal(v.python_tests_passed, 69);
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v4.xml'))), v.test_results_sha256);
const run = path.join(root, 'runs', v.run_id), artifact = read(path.join(run, 'predictions.json'));
assert.equal(artifact.part_views.length, 552); assert.equal(artifact.coverage.coverage.length, 812);
const inputs = read(path.join(run, 'inputs-manifest.json'));
assert.equal(inputs.sources.length, 9);
const parents = new Map(); let statements = 0;
for (const input of inputs.sources) {
  const bytes = fs.readFileSync(path.join(run, input.map_path));
  assert.equal(hash(bytes), input.map_file_sha256);
  const map = JSON.parse(bytes);
  assert.equal(hash(Buffer.from(map.source.text)), map.source.sha256);
  assert.notEqual(map.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  for (const u of map.source.units) assert.equal(Array.from(map.source.text).slice(u.start, u.end).join(''), u.text);
  for (const k of map.graph.knowledge) {
    parents.set(JSON.stringify([map.article_id, k.knowledge_id]), k);
    statements += k.semantic_frame.statements.length;
  }
  if (input.coverage_path) assert.equal(hash(fs.readFileSync(path.join(run, input.coverage_path))), input.coverage_sha256);
}
assert.equal(parents.size, 812); assert.equal(statements, 1593);
for (const view of artifact.part_views) {
  const proof = view.projection_proof, native = parents.get(JSON.stringify(view.native_key));
  assert.deepEqual(proof.complete_native_knowledge, native);
  assert.ok(['single', 'conjunction'].includes(native.semantic_frame.logic));
  assert.equal(proof.conditions_removed, false); assert.equal(proof.new_empirical_observation, false);
  assert.equal(proof.independent_replication, false);
  assert.equal(view.frame.kind, native.kind); assert.equal(view.frame.action_status, native.action_status);
  assert.deepEqual(proof.selected_provenance, proof.complete_parent_provenance[view.statement_position]);
}
for (const [name, digest] of Object.entries(artifact.binding.implementation)) {
  assert.equal(hash(fs.readFileSync(path.join(run, 'implementation', name))), digest);
}
for (const [name, digest] of Object.entries(artifact.binding.metadata.input_audit_file_sha256)) {
  assert.equal(hash(fs.readFileSync(path.join(run, name + '.json'))), digest);
}
for (const [i, row] of data.mode_rows.entries()) {
  assert.equal(row.new_forecasts, 0); assert.equal(artifact.predictions[row.mode].length, 0);
  const cells = [...doc.querySelectorAll('tbody tr')[i].querySelectorAll('td')].map(c => c.textContent);
  assert.deepEqual(cells, [row.label_ru, '0', '0', '0', row.unsupported_templates === null ? 'те же правила' : String(row.unsupported_templates)]);
}
const check = { passed: true, language: 'ru', external_resources: 0, source_count: 9,
  canonical_blocks: 812, native_statements: 1593, licensed_parts: 552,
  exact_native_parents_verified: true, unicode_provenance_verified: true, python_tests_passed: 69,
  scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false };
const output = path.join(folder, 'html-verification.json'), bytes = JSON.stringify(check, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(check));
