import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { JSDOM } from 'jsdom';

// Проверяем математику, полные основания и границы заявления, без научной аттестации.
const file = path.resolve(process.argv[2]), folder = path.dirname(file), root = path.dirname(folder);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const doc = new JSDOM(fs.readFileSync(file, 'utf8')).window.document;
assert.equal(doc.documentElement.lang, 'ru');
assert.equal(doc.querySelectorAll('script,img,link,iframe').length, 0);
assert.equal(doc.querySelectorAll('.card').length, 4);
assert.equal(doc.querySelectorAll('details.consequence').length, 86);
assert.ok(doc.body.textContent.includes('Критерий успеха не достигнут'));
assert.ok(doc.body.textContent.includes('Преимущество графа не доказано'));
assert.ok(doc.body.textContent.includes('точность не определена'));
for (const a of doc.querySelectorAll('a')) {
  const href = a.getAttribute('href'); assert.ok(!/^[a-z]+:/i.test(href));
  const target = path.resolve(folder, href);
  assert.ok(target.startsWith(root + path.sep) && fs.existsSync(target));
}
const data = read(path.join(folder, 'data.json')), v = data.verification;
assert.equal(v.canonical_blocks, 812); assert.equal(v.native_statements, 1593);
assert.equal(v.admitted_parents, 19); assert.equal(v.computed_contrasts, 86);
assert.equal(v.python_tests_passed, 142); assert.equal(v.model_calls, 0);
assert.equal(v.target_read, false); assert.equal(v.new_empirical_predictions, 0);
assert.equal(v.future_results_scored, 0); assert.equal(v.accuracy, null);
assert.equal(v.scientific_success, false); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(hash(fs.readFileSync(path.join(root, 'test-results-v2.xml'))), v.test_results_sha256);
const run = path.join(root, 'runs', v.run_id), result = read(path.join(run, 'predictions.json'));
assert.deepEqual(data.consequences, result.consequences);
assert.deepEqual(result.ablation.graph, result.ablation.same_semantics_without_dependencies);
assert.equal(result.ablation.operator_uses_visible_edges, false);
const manifest = read(path.join(run, 'inputs-manifest.json')), maps = new Map(), parents = new Map();
assert.equal(manifest.sources.length, 9);
for (const e of manifest.sources) {
  const bytes = fs.readFileSync(path.join(run, e.map_path)); assert.equal(hash(bytes), e.map_file_sha256);
  const m = JSON.parse(bytes), text = Array.from(m.source.text);
  assert.equal(hash(Buffer.from(m.source.text)), m.source.sha256);
  assert.notEqual(m.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  for (const u of m.source.units) assert.equal(text.slice(u.start, u.end).join(''), u.text);
  maps.set(m.article_id, m);
  for (const k of m.graph.knowledge) parents.set(JSON.stringify([m.article_id, k.knowledge_id]), k);
  if (e.coverage_path) assert.equal(hash(fs.readFileSync(path.join(run, e.coverage_path))), e.coverage_sha256);
}
assert.equal(parents.size, 812);
function fixed(value) {
  const m = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value); assert.ok(m);
  return { n: BigInt((m[1] === '-' ? '-' : '') + m[2] + (m[3] ?? '')), scale: (m[3] ?? '').length };
}
function exactSubtract(c) {
  const a = fixed(c.operand_a), b = fixed(c.operand_b), d = fixed(c.reported_parameter_difference);
  const scale = Math.max(a.scale, b.scale, d.scale);
  const expand = x => x.n * 10n ** BigInt(scale - x.scale);
  assert.equal(expand(b) - expand(a), expand(d));
}
function dag(graph) {
  const nodes = new Set(graph.nodes.map(n => n.id)); assert.equal(nodes.size, graph.nodes.length);
  const counts = new Map([...nodes].map(n => [n, 0])), children = new Map([...nodes].map(n => [n, []]));
  for (const e of graph.edges) {
    assert.ok(nodes.has(e.source) && nodes.has(e.target));
    counts.set(e.target, counts.get(e.target) + 1); children.get(e.source).push(e.target);
  }
  const ready = [...nodes].filter(n => counts.get(n) === 0); let seen = 0;
  while (ready.length) {
    const n = ready.pop(); seen++;
    for (const c of children.get(n)) { counts.set(c, counts.get(c) - 1); if (counts.get(c) === 0) ready.push(c); }
  }
  assert.equal(seen, nodes.size);
}
const native = new Set();
for (const [i, c] of data.consequences.entries()) {
  const p = c.proof, parent = parents.get(JSON.stringify(p.parent_key)), source = maps.get(p.parent_key[0]).source;
  native.add(JSON.stringify(p.parent_key));
  assert.deepEqual(p.complete_native_knowledge, parent);
  assert.deepEqual(p.complete_parent_provenance, parent.semantic_frame.statements.map(s => s.provenance));
  assert.deepEqual(p.all_parent_positions_retained, parent.semantic_frame.statements.map((s, i) => i));
  assert.equal(p.conditions_removed, false); assert.equal(p.parts_independently_asserted, false);
  assert.equal(p.independent_replication, false); assert.equal(c.future_empirical_prediction, false);
  assert.equal(c.transfer_to_other_model_or_population, false);
  assert.equal(c.confidence_interval, null); assert.equal(c.p, null);
  assert.equal(c.statistical_finding, 'not_established');
  assert.notEqual(c.from_category, c.basis.reference); assert.notEqual(c.to_category, c.basis.reference);
  exactSubtract(c); dag(c.proof_graph);
  assert.equal(c.conclusion_frame.kind, 'state'); assert.equal(c.conclusion_frame.logic, 'single');
  const s = c.conclusion_frame.statements[0];
  assert.equal(s.scope.study_group, p.parent_key[0]);
  assert.ok(c.basis.scope.conditions.every(v => s.scope.conditions.includes(v)));
  assert.equal(s.attributes.find(a => a.name === 'reported coefficient difference').value, c.reported_parameter_difference);
  for (const e of p.complete_model_audit.evidence) {
    assert.equal(Array.from(source.text).slice(e.start, e.end).join(''), e.text);
    assert.equal(hash(Buffer.from(e.text)), e.sha256);
  }
  const detail = doc.querySelectorAll('details.consequence')[i];
  assert.ok(detail.querySelector('summary').textContent.includes(p.parent_key.join(' / ')));
  assert.ok(detail.querySelector('.equation').textContent.includes(c.reported_parameter_difference));
}
assert.equal(native.size, 19);
for (const [name, digest] of Object.entries(result.binding.implementation))
  assert.equal(hash(fs.readFileSync(path.join(run, 'implementation', name))), digest);
for (const [name, digest] of Object.entries(result.binding.metadata.input_audit_file_sha256))
  assert.equal(hash(fs.readFileSync(path.join(run, name + '.json'))), digest);
assert.equal(Object.values(data.counts).reduce((a, b) => a + b, 0), 812);
const check = { passed: true, language: 'ru', external_resources: 0, computed_contrasts: 86,
  closed_parents_verified: 19, unicode_provenance_verified: true, exact_decimal_math_verified: true,
  proof_graphs_dag_verified: true, python_tests_passed: 142, scientific_success: false,
  graph_advantage_demonstrated: false, visual_inspection: false };
const output = path.join(folder, 'html-verification.json'), bytes = JSON.stringify(check, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), bytes);
else fs.writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(check));
