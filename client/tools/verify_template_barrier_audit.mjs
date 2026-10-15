// Независимая проверка отсутствия повторений предикатов между первичными семействами.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/template-barrier-audit-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p));
const hash = x => createHash('sha256').update(x).digest('hex');
const receipt = json('review-v2/verification.json'), data = json('review-v2/data.json');
for (const [name, expected] of Object.entries(receipt.files)) assert.equal(hash(read('review-v2/' + name)), expected);
assert.equal(hash(readFileSync(resolve(import.meta.dir, '../../api/tools/render_template_barrier_audit.py'))), receipt.builder_sha256);
assert.equal(hash(read('tests-v4.xml')), receipt.test_xml_sha256);
assert.equal(receipt.tests, 92);
const folder = 'runs/' + data.run_id;
const raw = read(folder + '/predictions.json');
assert.equal(rawJsonFingerprint(raw), json(folder + '/seal.json').prediction_sha256);
assert.deepEqual(JSON.parse(raw), data);
const sourceRaw = read(folder + '/input-predictions.json'), source = JSON.parse(sourceRaw);
assert.equal(rawJsonFingerprint(sourceRaw), data.binding.input_sha256);
assert.equal(source.run_id, data.input_run_id);
for (const [name, expected] of Object.entries(data.binding.implementation)) assert.equal(hash(read(folder + '/implementation/' + name)), expected);
for (const d of [source, data]) {
  assert.equal(d.model_calls, 0); assert.equal(d.target_read, false);
  assert.equal(d.scientific_success, false); assert.equal(d.graph_advantage_demonstrated, false);
}
assert.equal(data.canonical_blocks, 943); assert.equal(data.licensed_parts, 854);
assert.equal(source.binding.references.length, 11);
const views = new Map(source.part_views.map(v => [JSON.stringify(v.key), v]));
const modeCounts = {};
for (const [mode, learned] of Object.entries(source.learning_by_mode)) {
  const rules = [...learned.publication_supported_rules, ...learned.learning.unsupported_rules];
  const origins = new Map([...source.primary_support_by_mode[mode], ...learned.unsupported_origin_support].map(s => [s.rule_id, s]));
  const patterns = new Map(); let primaryCount = 0;
  for (const r of rules) {
    const families = new Set();
    for (const e of origins.get(r.id).examples) {
      const v = views.get(JSON.stringify(e.part_head)); assert.ok(v);
      assert.deepEqual(v.native_key, e.native_head);
      assert.equal(v.projection_proof.origin.origin, e.origin);
      if (e.origin === 'primary_result' && e.declared_primary_family !== null) families.add(e.declared_primary_family);
    }
    if (!families.size) continue;
    primaryCount++;
    const body = r.body.flatMap(f => f.statements.map(s => [s.predicate, s.negated])).sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
    const head = r.head.statements.map(s => [s.predicate, s.negated]);
    const key = JSON.stringify([body, head]);
    if (!patterns.has(key)) patterns.set(key, new Set());
    for (const family of families) patterns.get(key).add(family);
  }
  const collisions = [...patterns.values()].filter(f => f.size >= 2).length;
  assert.equal(primaryCount, data.modes[mode].primary_result_templates);
  assert.equal(collisions, data.modes[mode].multi_family_predicate_patterns);
  assert.equal(collisions, 0);
  for (const policy of Object.values(data.modes[mode].policies)) {
    assert.equal(policy.multi_family_collision_groups, 0); assert.deepEqual(policy.collision_groups, []);
  }
  modeCounts[mode] = { primary_templates: primaryCount, predicate_patterns: patterns.size, multi_family_patterns: collisions };
}
for (const predictions of Object.values(source.predictions)) assert.equal(predictions.length, 0);
const html = read('review-v2/report.html').toString('utf8');
assert.ok(html.includes('lang="ru"')); assert.ok(!/<script|https?:\/\/|<iframe|<link/i.test(html));
assert.equal((html.match(/<table>/g) || []).length, 1);
assert.equal((html.match(/<tr>/g) || []).length, 4);
const proof = { run_id: data.run_id, sources: 11, knowledge: 943, modes: modeCounts,
  new_predictions: 0, graph_advantage_demonstrated: false, model_calls: 0,
  verifier_sha256: hash(readFileSync(import.meta.filename)), helper_sha256: hash(readFileSync(resolve(import.meta.dir, 'raw_json_fingerprint.mjs'))) };
writeFileSync(resolve(root, 'review-v2/bun-verification.json'), JSON.stringify(proof, null, 2) + '\n');
console.log(JSON.stringify(proof));
