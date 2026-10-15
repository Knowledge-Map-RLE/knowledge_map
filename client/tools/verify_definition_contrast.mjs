// Независимый контроль нового противопоставления, полноты реестра и посылок.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/definition-contrast-v1');
const read = file => readFileSync(resolve(root, file)), json = file => JSON.parse(read(file));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const fp = value => rawJsonFingerprint(Buffer.from(JSON.stringify(value)));
function rawField(bytes, name) {
  const text = bytes.toString(), match = new RegExp('^  "' + name + '":\\s*', 'm').exec(text);
  assert.ok(match); const start = match.index + match[0].length;
  let depth = 0, quoted = false, escaped = false;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; continue; }
    if (c === '"') { quoted = true; continue; }
    if (c === '{' || c === '[') depth++; else if (c === '}' || c === ']') depth--;
    if (!depth) return Buffer.from(text.slice(start, i + 1));
  }
  assert.fail('Незавершённое поле');
}
function seal(folder) {
  const bytes = readFileSync(resolve(folder, 'predictions.json')), data = JSON.parse(bytes);
  const sealed = JSON.parse(readFileSync(resolve(folder, 'seal.json')));
  assert.equal(rawJsonFingerprint(bytes), sealed.prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(bytes, 'binding')), data.run_id);
  for (const [file, digest] of Object.entries(data.binding.implementation))
    assert.equal(hash(readFileSync(resolve(folder, 'implementation', file))), digest);
  assert.equal(data.model_calls, 0); return { folder, bytes, data };
}
function dag(graph) {
  const ids = new Set(graph.nodes.map(n => n.id)); assert.equal(ids.size, graph.nodes.length);
  const incoming = new Map([...ids].map(id => [id, 0])), adjacent = new Map([...ids].map(id => [id, []]));
  for (const edge of graph.edges) {
    assert.ok(ids.has(edge.source) && ids.has(edge.target));
    incoming.set(edge.target, incoming.get(edge.target) + 1); adjacent.get(edge.source).push(edge.target);
  }
  const queue = [...ids].filter(id => !incoming.get(id)); let count = 0;
  while (queue.length) {
    const id = queue.pop(); count++;
    for (const next of adjacent.get(id)) { incoming.set(next, incoming.get(next) - 1); if (!incoming.get(next)) queue.push(next); }
  }
  assert.equal(count, ids.size);
}
// Проверка непосредственно на занятости областей, без вызова Python-оператора.
function countModels(premises, head) {
  const terms = [...new Set([...premises, head].flatMap(p => [p.subject, p.object]))].sort();
  assert.equal(terms.length, 3);
  const holds = (p, occupied) => {
    let overlap = false, outside = false;
    for (let region = 0; region < 8; region++) if (occupied & (1 << region)) {
      if (!(region & (1 << terms.indexOf(p.subject)))) continue;
      if (region & (1 << terms.indexOf(p.object))) overlap = true; else outside = true;
    }
    return { A: !outside, E: !overlap, I: overlap, O: outside }[p.form];
  };
  for (const p of premises) assert.deepEqual(p.scope, head.scope);
  let satisfying = 0, countermodels = 0;
  for (let occupied = 0; occupied < 256; occupied++) if (premises.every(p => holds(p, occupied))) {
    satisfying++; if (!holds(head, occupied)) countermodels++;
  }
  return { satisfying, countermodels };
}

const receipt = json('review-v1/verification.json'), report = json('review-v1/data.json');
for (const [file, digest] of Object.entries(receipt.files)) assert.equal(hash(read('review-v1/' + file)), digest);
for (const [file, digest] of Object.entries(receipt.builders)) assert.equal(hash(readFileSync(file)), digest);
assert.equal(hash(read('tests-v2.xml')), receipt.tests_sha256);
const testDom = new JSDOM(read('tests-v2.xml').toString(), { contentType: 'text/xml' }).window.document;
const suites = [...testDom.querySelectorAll('testsuite')];
assert.equal(suites.reduce((n, s) => n + Number(s.getAttribute('tests')), 0), 84);
for (const suite of suites) for (const attr of ['errors', 'failures', 'skipped']) assert.equal(Number(suite.getAttribute(attr)), 0);
const main = seal(receipt.main_snapshot), control = seal(receipt.control_snapshot);
for (const key of ['sources', 'families', 'metadata', 'map_hashes', 'implementation', 'context_audit_sha256',
  'model_audit_sha256', 'origin_audit_sha256', 'limits', 'version', 'dictionary_sha256'])
  assert.deepEqual(main.data.binding[key], control.data.binding[key]);
for (const key of ['predictions', 'numeric_consequences', 'categorical_inference']) assert.deepEqual(main.data[key], control.data[key]);
assert.equal(main.data.canonical_blocks, 943);
const licenses = JSON.parse(readFileSync(resolve(main.folder, 'categorical-licenses.json')));
const oldLicenses = JSON.parse(readFileSync(resolve(control.folder, 'categorical-licenses.json')));
assert.deepEqual(licenses.entries.slice(0, 2), oldLicenses.entries);
assert.equal(licenses.entries.length, 3);
assert.equal(rawJsonFingerprint(readFileSync(resolve(main.folder, 'categorical-licenses.json'))), main.data.binding.categorical_licenses_sha256);
const manifest = JSON.parse(readFileSync(resolve(main.folder, 'source-manifest.json'))), maps = new Map(); let nativeCount = 0;
for (const entry of manifest.sources) {
  const bytes = readFileSync(entry.path), map = JSON.parse(bytes);
  assert.equal(hash(bytes), entry.file_sha256); assert.equal(rawJsonFingerprint(rawField(bytes, 'graph')), entry.graph_sha256);
  assert.equal(hash(map.source.text), entry.source_sha256); assert.equal(map.source.sha256, entry.source_sha256);
  assert.notEqual(map.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  assert.equal(map.article_id, entry.reference.article_id); assert.equal(map.run_id, entry.reference.run_id);
  assert.equal(map.graph.schema_version, 6); dag(map.graph);
  maps.set(map.article_id, map); nativeCount += map.graph.knowledge.length;
}
assert.equal(nativeCount, 943); assert.equal(maps.size, 11);
const inventory = json('review-v1/definition-inventory.json'), nativeDefinitions = [];
for (const map of maps.values()) for (const k of map.graph.knowledge)
  if (k.knowledge_kind === 'definition') nativeDefinitions.push([map.article_id, k.knowledge_id]);
assert.equal(inventory.categorical_license_sha256, main.data.binding.categorical_licenses_sha256);
assert.equal(inventory.rows.length, 26); assert.equal(inventory.definition_statements, 45);
assert.deepEqual(inventory.rows.map(r => [r.article_id, r.knowledge_id]).sort(), nativeDefinitions.sort());
let evidenceCount = 0;
for (const row of inventory.rows) {
  const map = maps.get(row.article_id), native = map.graph.knowledge.find(k => k.knowledge_id === row.knowledge_id);
  assert.deepEqual(row.complete_knowledge, native); assert.equal(fp(native), row.knowledge_sha256);
  assert.equal(map.source.sha256, row.source_sha256); assert.equal(map.run_id, row.run_id);
  assert.ok(row.reason_ru);
  for (const evidence of row.evidence) {
    const unit = map.source.units.find(u => u.id === evidence.id); assert.ok(unit);
    assert.equal(Array.from(map.source.text).slice(evidence.start, evidence.end).join(''), evidence.text);
    assert.equal(evidence.text, unit.text); assert.equal(hash(evidence.text), evidence.sha256); evidenceCount++;
  }
}
const logic = main.data.licensed_categorical_inference, before = control.data.licensed_categorical_inference;
assert.equal(logic.licensed_parent_blocks, 3); assert.equal(logic.licensed_views, 5);
const proofIndex = new Map(logic.license_proofs.map(p => [JSON.stringify(p.key), p]));
const oldIds = new Set(before.consequences.without_dependencies.map(c => c.id));
assert.ok(before.consequences.without_dependencies.every(c => logic.consequences.without_dependencies.some(n => JSON.stringify(c) === JSON.stringify(n))));
const added = logic.consequences.without_dependencies.filter(c => !oldIds.has(c.id));
assert.equal(added.length, 1); assert.deepEqual(added, report.added_conclusions);
let necessary = 0;
for (const candidate of logic.consequences.without_dependencies) {
  assert.equal(candidate.novel_empirical_prediction, false); assert.equal(candidate.expert_validated, false);
  assert.deepEqual(candidate.proof.existence_conditions, []);
  const checked = countModels(candidate.proof.premises, candidate.conclusion);
  assert.equal(checked.countermodels, 0); assert.ok(checked.satisfying > 0);
  assert.equal(checked.satisfying, candidate.proof.satisfying_models);
  for (let i = 0; i < candidate.premises.length; i++) {
    const p = candidate.premises[i], licensed = proofIndex.get(JSON.stringify([p.article_id, p.view_id]));
    assert.ok(licensed); assert.equal(fp(licensed), p.license_proof_sha256);
    assert.deepEqual(licensed.clause, candidate.proof.premises[i]);
    assert.ok(countModels(candidate.proof.premises.filter((_, index) => index !== i), candidate.conclusion).countermodels > 0); necessary++;
  }
  dag(candidate.proof_graph);
}
const contrast = licenses.entries[2], map = maps.get(contrast.article_id);
const parent = map.graph.knowledge.find(k => k.knowledge_id === contrast.knowledge_id);
assert.equal(parent.knowledge_id, 'K11'); assert.equal(parent.semantic_frame.logic, 'contrast');
assert.equal(contrast.independent_contrast_parts, true);
for (const annotation of contrast.statements) {
  const native = parent.semantic_frame.statements.find(s => s.statement_id === annotation.statement_id);
  const constraints = { roles: native.roles.filter(r => r.role !== 'subject'), attributes: native.qualifiers.attributes,
    conditions: native.conditions, temporal_context: native.temporal_context };
  assert.deepEqual(annotation.native_constraints, constraints);
  assert.deepEqual(annotation.bindings.object.native_constraints, constraints);
  assert.deepEqual(contrast.shared_native_constraints, constraints);
  assert.equal(annotation.bindings.object.local_id, 'unary_property:has_death_domain:' + fp(constraints));
  assert.ok(contrast.scope.conditions.includes('native_definition_constraints_sha256:' + fp(constraints)));
  assert.equal(annotation.clause.form, native.negated ? 'E' : 'A');
}
for (const evidence of contrast.evidence) {
  assert.equal(Array.from(map.source.text).slice(evidence.start, evidence.end).join(''), evidence.text);
  assert.equal(hash(evidence.text), evidence.sha256);
  assert.match(evidence.text, /TNFR1, which contains the DD/); assert.match(evidence.text, /TNFR2 lacks the DD/);
}
assert.deepEqual(new Set(added[0].premises.map(p => p.knowledge_id)), new Set(['K11']));
assert.equal(added[0].conclusion.form, 'E');
assert.deepEqual(new Set([added[0].conclusion.subject, added[0].conclusion.object]),
  new Set(['concept:C25', 'concept:C26'].map(id => contrast.article_id + '::' + id)));
assert.deepEqual(Object.fromEntries(Object.entries(logic.consequences).map(([k, v]) => [k, v.length])),
  { graph: 0, without_dependencies: 3, source_neighborhood: 0, permuted_dependencies: 0 });
const dom = new JSDOM(read('review-v1/report.html').toString()).window.document;
assert.equal(dom.documentElement.lang, 'ru'); assert.equal(dom.querySelectorAll('script,iframe,[src],link,[lang="en"]').length, 0);
assert.equal(dom.querySelectorAll('tbody tr').length, 30);
assert.match(dom.body.textContent, /EAE второй фигуры/); assert.match(dom.body.textContent, /новых эмпирических прогнозов — ноль/);
const result = { sources_verified: 11, canonical_blocks_verified: nativeCount, definition_blocks_verified: 26,
  definition_statements_verified: 45, evidence_uses_verified: evidenceCount, logical_conclusions_verified: 3,
  additional_conclusions: 1, necessary_premises_verified: necessary, parent_contrast_preserved: true,
  independent_empirical_predictions: 0, graph_advantage_demonstrated: false, visual_inspection: false,
  verifier_sha256: hash(readFileSync(import.meta.path)),
  helper_sha256: hash(readFileSync(resolve(dirname(import.meta.path), 'raw_json_fingerprint.mjs'))) };
const output = resolve(root, 'review-v1/bun-verification.json'), bytes = JSON.stringify(result, null, 2) + '\n';
if (existsSync(output)) assert.equal(readFileSync(output, 'utf8'), bytes); else writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(result));
