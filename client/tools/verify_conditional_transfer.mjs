// Независимая проверка происхождения, исключения семьи и раздельных входов.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/conditional-transfer-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p));
const hash = x => createHash('sha256').update(x).digest('hex');
const fp = x => rawJsonFingerprint(Buffer.from(JSON.stringify(x)));
function field(raw, name) {
  const text = raw.toString('utf8'), match = new RegExp('^  "' + name + '":\\s*', 'm').exec(text);
  assert.ok(match); const start = match.index + match[0].length;
  let depth = 0, quoted = false, escaped = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (quoted) { if (escaped) escaped = false; else if (ch === '\\') escaped = true; else if (ch === '"') quoted = false; continue; }
    if (ch === '"') { quoted = true; continue; }
    if (ch === '{' || ch === '[') depth++; else if (ch === '}' || ch === ']') depth--;
    if (depth === 0) return Buffer.from(text.slice(start, i + 1));
  }
  assert.fail('Незавершённое поле');
}
function sealed(folder) {
  const raw = readFileSync(resolve(folder, 'predictions.json')), data = JSON.parse(raw);
  assert.equal(rawJsonFingerprint(raw), JSON.parse(readFileSync(resolve(folder, 'seal.json'))).prediction_sha256);
  assert.equal(rawJsonFingerprint(field(raw, 'binding')), data.run_id);
  for (const [name, digest] of Object.entries(data.binding.implementation))
    assert.equal(hash(readFileSync(resolve(folder, 'implementation', name))), digest);
  assert.equal(data.model_calls, 0); return {raw, data};
}
function tupleCompare(a, b) {
  if (Array.isArray(a)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) { const c = tupleCompare(a[i], b[i]); if (c) return c; }
    return a.length - b.length;
  }
  return a < b ? -1 : a > b ? 1 : 0;
}
const receipt = json('review-v2/verification.json'), report = json('review-v2/data.json');
for (const [name, digest] of Object.entries(receipt.files)) assert.equal(hash(read('review-v2/' + name)), digest);
for (const [path, digest] of Object.entries(receipt.builders)) assert.equal(hash(readFileSync(path)), digest);
assert.equal(hash(read('tests-v3.xml')), receipt.tests_sha256);
const testXml = read('tests-v3.xml').toString();
assert.equal(report.tests, 193); assert.match(testXml, /tests="193"/);
assert.match(testXml, /failures="0"/); assert.match(testXml, /errors="0"/);
const folder = resolve(root, 'runs', report.run_id), frozen = sealed(folder);
const forecast = frozen.data;
assert.equal(forecast.question, null); assert.equal(forecast.held_out_results_used_for_learning, false);
assert.equal(forecast.retrospective_annotation_and_validation_used_results, true);
assert.equal(forecast.scientific_success, false); assert.equal(forecast.graph_advantage_demonstrated, false);
const descriptor = JSON.parse(readFileSync(resolve(folder, 'input-corpus.json')));
const applicability = sealed(descriptor.snapshot);
assert.equal(rawJsonFingerprint(applicability.raw), forecast.binding.input_sha256);
assert.equal(rawJsonFingerprint(readFileSync(resolve(folder, 'input-applicability.json'))), forecast.binding.input_sha256);
const priorDescriptor = JSON.parse(readFileSync(resolve(descriptor.snapshot, 'input-corpus.json')));
const upstream = sealed(priorDescriptor.snapshot);
assert.equal(rawJsonFingerprint(upstream.raw), applicability.data.binding.input_sha256);
const manifest = JSON.parse(readFileSync(resolve(priorDescriptor.snapshot, 'inputs-manifest.json')));
assert.equal(manifest.sources.length, 11);
const maps = new Map(), groups = new Map(); let canonical = 0;
for (const entry of manifest.sources) {
  const bytes = readFileSync(resolve(priorDescriptor.snapshot, entry.map_path));
  assert.equal(hash(bytes), entry.map_file_sha256);
  const map = JSON.parse(bytes); maps.set(map.article_id, map); canonical += map.graph.knowledge.length;
  assert.equal(map.source.sha256, hash(map.source.text));
  assert.notEqual(map.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  assert.equal(map.source.offset_encoding, 'unicode_codepoints');
  const nodes = new Map(map.graph.nodes.map(n => [n.id, n.knowledge_id]));
  const indegree = new Map([...nodes.keys()].map(k => [k, 0])), adjacency = new Map([...nodes.keys()].map(k => [k, []]));
  for (const edge of map.graph.edges) {
    assert.ok(nodes.has(edge.source) && nodes.has(edge.target));
    adjacency.get(edge.source).push(edge.target); indegree.set(edge.target, indegree.get(edge.target) + 1);
  }
  const queue = [...indegree.keys()].filter(k => indegree.get(k) === 0); let visited = 0;
  while (queue.length) { const k = queue.pop(); visited++; for (const next of adjacency.get(k)) {
    indegree.set(next, indegree.get(next) - 1); if (!indegree.get(next)) queue.push(next);
  }}
  assert.equal(visited, nodes.size);
  for (const t of map.graph.transitions) {
    const body = t.sources.map(s => [map.article_id, nodes.get(s)]).sort(tupleCompare);
    const group = [body, [map.article_id, nodes.get(t.target)]];
    groups.set(JSON.stringify(group), group);
  }
}
assert.equal(canonical, 943); assert.equal(upstream.data.part_views.length, 906);
const allGroups = [...groups.values()].sort(tupleCompare);
assert.equal(fp(allGroups), forecast.binding.author_groups_sha256);
const axes = ['species','disease_model','target','intervention_action','route','phase','measurement_kind'];
const cases = new Map(applicability.data.cases.map(c => [c.case_id, c]));
let quotes = 0;
for (const c of cases.values()) {
  const map = maps.get(c.article_id), units = new Map(map.source.units.map(u => [u.id, u]));
  const native = new Map(map.graph.knowledge.map(k => [k.knowledge_id, k]));
  const allowed = new Set();
  for (const b of c.complete_basis) {
    assert.equal(b.native_key[0], c.article_id); assert.deepEqual(b.knowledge, native.get(b.native_key[1]));
    for (const s of b.knowledge.semantic_frame.statements) for (const u of s.provenance.unit_ids) allowed.add(u);
  }
  for (const label of ['method', 'measurement', 'result']) {
    const part = c[label]; assert.deepEqual(part.projection_proof.complete_native_knowledge, native.get(part.native_key[1]));
    assert.equal(fp(part.frame), part.projection_proof.view_frame_sha256);
    assert.equal(part.projection_proof.origin.origin, label === 'result' ? 'primary_result' : 'primary_method');
  }
  assert.deepEqual(Object.keys(c.features).sort(), [...axes].sort());
  for (const evidence of [...Object.values(c.source_annotation.feature_evidence).flat(), ...c.source_annotation.direction_evidence]) {
    const u = units.get(evidence.unit_id); assert.ok(u && allowed.has(evidence.unit_id));
    assert.ok(u.start <= evidence.start && evidence.end <= u.end && u.end <= map.source.content_end);
    const text = Array.from(map.source.text).slice(evidence.start, evidence.end).join('');
    assert.equal(text, evidence.text); assert.equal(hash(text), evidence.sha256);
    assert.equal(evidence.source_asserts_feature, true); quotes++;
  }
}
assert.equal(cases.size, 3); assert.equal(new Set([...cases.values()].map(c => c.primary_family)).size, 2);
const supported = applicability.data.schemata.filter(s => s.minimum_primary_support);
assert.equal(supported.length, 1); assert.equal(supported[0].new_prediction, false);
const fields = ['id','article_id','run_id','primary_family','features','feature_evidence','source_sha256','body'].sort();
for (const receiver of forecast.receivers) {
  assert.deepEqual(Object.keys(receiver).sort(), fields);
  const c = cases.get(receiver.id);
  assert.equal(receiver.article_id, c.article_id); assert.equal(receiver.primary_family, c.primary_family);
  assert.deepEqual(receiver.features, c.features); assert.deepEqual(receiver.feature_evidence, c.source_annotation.feature_evidence);
  assert.deepEqual(receiver.body, ['method','measurement'].map(f => ({key:c[f].key, native_key:c[f].native_key, frame:c[f].frame})));
  assert.ok(receiver.body.every(b => JSON.stringify(b.native_key) !== JSON.stringify(c.result.native_key)));
}
assert.equal(fp(forecast.receivers), forecast.binding.receiver_projection_sha256);
assert.deepEqual(JSON.parse(readFileSync(resolve(folder, 'receiver-inputs.json'))), forecast.receivers);
for (const [mode, folds] of Object.entries(forecast.modes)) {
  assert.equal(folds.length, 3);
  for (const fold of folds) {
    assert.equal(fold.held_out_family, cases.get(fold.receiver_id).primary_family);
    for (const id of fold.training_case_ids) assert.notEqual(cases.get(id).primary_family, fold.held_out_family);
    assert.equal(fold.excluded.held_out_family, [...cases.values()].filter(c => c.primary_family === fold.held_out_family).length);
    assert.equal(fold.rules.length, 0); assert.equal(fold.predictions.length, 0);
  }
  assert.equal(report.hypotheses[mode], 0);
}
const evaluationRaw = readFileSync(resolve(folder, 'evaluations', report.evaluation_id + '.json'));
assert.equal(rawJsonFingerprint(evaluationRaw), report.evaluation_id);
const evaluation = JSON.parse(evaluationRaw);
assert.equal(evaluation.forecast_sha256, rawJsonFingerprint(frozen.raw));
assert.equal(evaluation.resubstitution_diagnostic.is_independent_validation, false);
assert.equal(evaluation.resubstitution_diagnostic.candidates.length, 0);
assert.equal(evaluation.graph_advantage_demonstrated, false);
const comparatorRoles = [...cases.values()].map(c => c.method.frame.statements[0].roles.some(r => r.role === 'comparator'));
assert.deepEqual(comparatorRoles, [true,false,true]);
const html = read('review-v2/report.html').toString();
assert.match(html, /<html lang="ru">/); assert.ok(!/<script|https?:\/\/|(?:src|href)=/i.test(html));
assert.match(html, /PBS/); assert.match(html, /24|силлогистические/);
const result = {run_id:forecast.run_id, sources_verified:maps.size, canonical_blocks_verified:canonical,
  source_quotes_verified:quotes, receiver_inputs_verified:forecast.receivers.length,
  family_excluded_folds_verified:9, hypotheses:0, graph_advantage_demonstrated:false,
  verifier_sha256:hash(readFileSync(import.meta.path)), helper_sha256:hash(readFileSync(resolve(dirname(import.meta.path),'raw_json_fingerprint.mjs')))};
writeFileSync(resolve(root, 'review-v2/bun-verification.json'), JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
