// Независимая проверка источников и следования через перебор областей классов.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/full-corpus-logical-v1');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const read = file => readFileSync(resolve(root, file));
const json = file => JSON.parse(read(file));
const fp = value => rawJsonFingerprint(Buffer.from(JSON.stringify(value)));

// Числовые лексемы исходного JSON сохраняются при проверке печатей Python.
function rawField(bytes, name) {
  const text = bytes.toString('utf8');
  const match = new RegExp('^  "' + name + '":\\s*', 'm').exec(text);
  assert.ok(match, 'Отсутствует поле ' + name);
  const start = match.index + match[0].length;
  let depth = 0, quoted = false, escaped = false;
  for (let i = start; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') quoted = false;
      continue;
    }
    if (char === '"') { quoted = true; continue; }
    if (char === '{' || char === '[') depth++;
    else if (char === '}' || char === ']') depth--;
    if (depth === 0) return Buffer.from(text.slice(start, i + 1));
  }
  assert.fail('Незавершённое поле ' + name);
}

function seal(folder) {
  const bytes = readFileSync(resolve(folder, 'predictions.json'));
  const data = JSON.parse(bytes), receipt = JSON.parse(readFileSync(resolve(folder, 'seal.json')));
  assert.equal(data.run_id, receipt.run_id);
  assert.equal(rawJsonFingerprint(bytes), receipt.prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(bytes, 'binding')), data.run_id);
  for (const [name, digest] of Object.entries(data.binding.implementation))
    assert.equal(hash(readFileSync(resolve(folder, 'implementation', name))), digest);
  assert.equal(data.model_calls, 0);
  return { folder, bytes, data };
}

function dag(graph) {
  const ids = new Set(graph.nodes.map(node => node.id));
  assert.equal(ids.size, graph.nodes.length);
  const indegree = new Map([...ids].map(id => [id, 0]));
  const adjacent = new Map([...ids].map(id => [id, []]));
  for (const edge of graph.edges) {
    assert.ok(ids.has(edge.source) && ids.has(edge.target));
    adjacent.get(edge.source).push(edge.target);
    indegree.set(edge.target, indegree.get(edge.target) + 1);
  }
  const queue = [...ids].filter(id => !indegree.get(id)); let visited = 0;
  while (queue.length) {
    const id = queue.pop(); visited++;
    for (const next of adjacent.get(id)) {
      indegree.set(next, indegree.get(next) - 1);
      if (!indegree.get(next)) queue.push(next);
    }
  }
  assert.equal(visited, ids.size, 'Видимый граф содержит цикл');
}

// Мир — набор непустых областей диаграммы Венна. Пустые классы разрешены.
function propositionHolds(proposition, terms, occupied) {
  const subject = terms.indexOf(proposition.subject), object = terms.indexOf(proposition.object);
  assert.ok(subject >= 0 && object >= 0);
  let overlap = false, outside = false;
  for (let region = 0; region < 2 ** terms.length; region++) {
    if (!(occupied & (1 << region)) || !(region & (1 << subject))) continue;
    if (region & (1 << object)) overlap = true;
    else outside = true;
  }
  switch (proposition.form) {
    case 'A': return !outside;
    case 'E': return !overlap;
    case 'I': return overlap;
    case 'O': return outside;
    default: assert.fail('Неизвестный квантор');
  }
}

function enumerate(premises, conclusion, existence = []) {
  for (const premise of premises) assert.deepEqual(premise.scope, conclusion.scope);
  const terms = [...new Set([...premises, conclusion].flatMap(p => [p.subject, p.object]))].sort();
  assert.ok(terms.length <= 3);
  assert.ok(existence.every(term => terms.includes(term)));
  let satisfying = 0, countermodels = 0;
  for (let occupied = 0; occupied < 2 ** (2 ** terms.length); occupied++) {
    if (!premises.every(p => propositionHolds(p, terms, occupied))) continue;
    if (!existence.every(term => propositionHolds({ form: 'I', subject: term, object: term }, terms, occupied))) continue;
    satisfying++;
    if (!propositionHolds(conclusion, terms, occupied)) countermodels++;
  }
  return { satisfying, countermodels, entailed: satisfying > 0 && countermodels === 0 };
}

const receipt = json('review-v1/verification.json'), report = json('review-v1/data.json');
for (const [name, digest] of Object.entries(receipt.files)) assert.equal(hash(read('review-v1/' + name)), digest);
for (const [file, digest] of Object.entries(receipt.builders)) assert.equal(hash(readFileSync(file)), digest);
assert.equal(hash(read('tests-v1.xml')), receipt.tests_sha256);
const testDom = new JSDOM(read('tests-v1.xml').toString(), { contentType: 'text/xml' }).window.document;
const suites = [...testDom.querySelectorAll('testsuite')];
assert.ok(suites.length);
assert.equal(suites.reduce((sum, suite) => sum + Number(suite.getAttribute('tests')), 0), 70);
for (const suite of suites) for (const name of ['failures', 'errors', 'skipped'])
  assert.equal(Number(suite.getAttribute(name)), 0);

const main = seal(receipt.main_snapshot), control = seal(receipt.control_snapshot);
for (const field of ['sources', 'families', 'metadata', 'map_hashes', 'implementation', 'context_audit_sha256',
  'model_audit_sha256', 'origin_audit_sha256', 'limits', 'version', 'dictionary_sha256', 'normalizer'])
  assert.deepEqual(main.data.binding[field], control.data.binding[field]);
for (const field of ['predictions', 'numeric_consequences', 'categorical_inference'])
  assert.deepEqual(main.data[field], control.data[field]);
assert.equal(main.data.canonical_blocks, 943);
assert.equal(control.data.canonical_blocks, 943);
assert.equal(main.data.numeric_consequences.proofs.length, 151);
assert.equal(main.data.graph_advantage_demonstrated, false);
assert.equal(control.data.licensed_categorical_inference.status, 'not_supplied');
const licensed = main.data.licensed_categorical_inference;
assert.equal(licensed.status, 'source_definitions_licensed');
assert.equal(licensed.licensed_parent_blocks, 2);
assert.equal(licensed.licensed_views, 3);
assert.equal(licensed.coverage.length, 946);
assert.deepEqual(Object.fromEntries(Object.entries(licensed.consequences).map(([mode, items]) => [mode, items.length])),
  { graph: 0, without_dependencies: 2, source_neighborhood: 0, permuted_dependencies: 0 });
assert.equal(rawJsonFingerprint(readFileSync(resolve(main.folder, 'categorical-licenses.json'))), licensed.audit_sha256);
assert.equal(licensed.audit_sha256, main.data.binding.categorical_licenses_sha256);

const manifest = JSON.parse(readFileSync(resolve(main.folder, 'source-manifest.json')));
const maps = new Map(); let knowledgeCount = 0, provenanceUses = 0;
assert.equal(manifest.sources.length, 11);
for (const entry of manifest.sources) {
  const bytes = readFileSync(entry.path), map = JSON.parse(bytes);
  assert.equal(hash(bytes), entry.file_sha256);
  assert.equal(rawJsonFingerprint(rawField(bytes, 'graph')), entry.graph_sha256);
  for (const field of ['article_id', 'pipeline_id', 'run_id']) assert.equal(map[field], entry.reference[field]);
  assert.equal(hash(map.source.text), entry.source_sha256);
  assert.equal(map.source.sha256, entry.source_sha256);
  assert.notEqual(map.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  assert.notEqual(map.run_id, 'ef432af7-79ae-4632-bfc5-d7adc899cb24');
  assert.equal(map.graph.schema_version, 6);
  assert.equal(map.source.offset_encoding, 'unicode_codepoints');
  dag(map.graph);
  const points = Array.from(map.source.text), units = new Map(map.source.units.map(unit => [unit.id, unit]));
  assert.equal(units.size, map.source.units.length);
  for (const knowledge of map.graph.knowledge) for (const statement of knowledge.semantic_frame.statements) {
    assert.ok(statement.provenance.unit_ids.length);
    for (const id of statement.provenance.unit_ids) {
      const unit = units.get(id); assert.ok(unit);
      assert.ok(0 <= unit.start && unit.start < unit.end && unit.end <= map.source.content_end && map.source.content_end <= points.length);
      assert.equal(points.slice(unit.start, unit.end).join(''), unit.text); provenanceUses++;
    }
  }
  if (entry.coverage_artifact) assert.equal(hash(readFileSync(entry.coverage_artifact.path)), entry.coverage_artifact.sha256);
  maps.set(map.article_id, map); knowledgeCount += map.graph.knowledge.length;
}
assert.equal(maps.size, 11); assert.equal(knowledgeCount, 943);
const licenses = new Map(); let quotes = 0;
for (const proof of licensed.license_proofs) {
  const map = maps.get(proof.native_key[0]); assert.ok(map);
  const parent = map.graph.knowledge.find(k => k.knowledge_id === proof.native_key[1]); assert.ok(parent);
  assert.deepEqual(parent.semantic_frame, proof.complete_parent_frame);
  assert.equal(fp(parent), proof.parent_knowledge_sha256);
  assert.equal(fp(parent.semantic_frame), proof.parent_frame_sha256);
  assert.ok(parent.semantic_frame.statements.some(s => s.statement_id === proof.statement_id));
  assert.deepEqual(proof.clause, proof.license.clause);
  assert.equal(proof.bindings.subject.id, proof.clause.subject);
  assert.equal(proof.bindings.object.id, proof.clause.object);
  for (const evidence of proof.evidence) {
    const unit = map.source.units.find(u => u.id === evidence.unit_id); assert.ok(unit);
    assert.ok(unit.start <= evidence.start && evidence.end <= unit.end);
    assert.equal(Array.from(map.source.text).slice(evidence.start, evidence.end).join(''), evidence.text);
    assert.equal(hash(evidence.text), evidence.sha256); quotes++;
  }
  licenses.set(JSON.stringify(proof.key), proof);
}
assert.equal(licenses.size, 3);
let necessaryPremises = 0;
for (const candidate of licensed.consequences.without_dependencies) {
  const proof = candidate.proof;
  assert.deepEqual(proof.conclusion, candidate.conclusion);
  assert.equal(candidate.novel_empirical_prediction, false);
  assert.equal(candidate.causality_asserted, false);
  assert.equal(candidate.expert_validated, false);
  assert.deepEqual(proof.existence_conditions, []);
  const proofWithoutId = structuredClone(proof); delete proofWithoutId.id;
  assert.equal(fp(proofWithoutId), proof.id);
  const identity = structuredClone(candidate.conclusion);
  [identity.subject, identity.object] = [identity.subject, identity.object].sort();
  assert.equal(fp(identity), candidate.id);
  assert.equal(candidate.premises.length, 2);
  for (let i = 0; i < candidate.premises.length; i++) {
    const premise = candidate.premises[i], license = licenses.get(JSON.stringify([premise.article_id, premise.view_id]));
    assert.ok(license); assert.equal(fp(license), premise.license_proof_sha256);
    assert.equal(maps.get(premise.article_id).run_id, premise.run_id);
    assert.equal(premise.statement_id, license.statement_id);
    assert.equal(premise.knowledge_id, license.native_key[1]);
    assert.deepEqual(proof.premises[i], license.clause);
  }
  const calculation = enumerate(proof.premises, candidate.conclusion);
  assert.equal(calculation.entailed, true);
  assert.equal(calculation.satisfying, proof.satisfying_models);
  assert.equal(calculation.countermodels, proof.countermodels);
  for (let i = 0; i < proof.premises.length; i++) {
    const reduced = enumerate(proof.premises.filter((_, index) => index !== i), candidate.conclusion);
    assert.ok(reduced.countermodels > 0, 'Посылка несущественна'); necessaryPremises++;
  }
  dag(candidate.proof_graph);
  assert.equal(candidate.proof_graph.nodes.length, 4);
  assert.deepEqual(candidate.proof_graph.joint_premises, ['premise:0', 'premise:1', 'operator']);
  assert.equal(candidate.proof_graph.edges.length, 3);
}

// Полный независимый перебор форм: условные формы не публикуются без непустоты.
const forms = ['A', 'E', 'I', 'O'], scope = { interpretation: 'абстрактные классы' };
const figures = [[['M', 'P'], ['S', 'M']], [['P', 'M'], ['S', 'M']],
  [['M', 'P'], ['M', 'S']], [['P', 'M'], ['M', 'S']]];
let moods = 0, unconditional = 0, conditional = 0;
for (const axes of figures) for (const major of forms) for (const minor of forms) for (const head of forms) {
  const premises = [major, minor].map((form, i) => ({ form, subject: axes[i][0], object: axes[i][1], scope }));
  const conclusion = { form: head, subject: 'S', object: 'P', scope }; moods++;
  if (enumerate(premises, conclusion).entailed) { unconditional++; continue; }
  let valid = false;
  for (let mask = 1; mask < 8; mask++)
    if (enumerate(premises, conclusion, ['S', 'M', 'P'].filter((_, i) => mask & (1 << i))).entailed) valid = true;
  if (valid) conditional++;
}
assert.equal(moods, 256); assert.equal(unconditional, 15); assert.equal(conditional, 9);
// Контроль невыполнимости ассоциаций как категорических посылок и скрытого существования.
assert.throws(() => enumerate([{ form: 'association', subject: 'S', object: 'M', scope }], { form: 'A', subject: 'S', object: 'P', scope }));
const darapti = [{ form: 'A', subject: 'M', object: 'P', scope }, { form: 'A', subject: 'M', object: 'S', scope }];
const particular = { form: 'I', subject: 'S', object: 'P', scope };
assert.equal(enumerate(darapti, particular).entailed, false);
assert.equal(enumerate(darapti, particular, ['M']).entailed, true);

const dom = new JSDOM(read('review-v1/report.html').toString()).window.document;
assert.equal(dom.documentElement.lang, 'ru');
assert.equal(dom.querySelectorAll('script,iframe,[src],link,[lang="en"]').length, 0);
assert.match(dom.body.textContent, /Новых эмпирических прогнозов — 0/);
assert.match(dom.body.textContent, /не выдаётся за преимущество прежнего DAG/);
assert.equal(report.tests, 70);
const verification = { sources_verified: 11, canonical_blocks_verified: 943, source_provenance_uses_verified: provenanceUses,
  licensed_views_verified: 3, source_quotes_verified: quotes, conclusions_verified: 2, necessary_premises_verified: necessaryPremises,
  independent_moods_enumerated: moods, unconditional_forms: unconditional, existence_conditional_forms: conditional,
  new_empirical_predictions: 0, graph_advantage_demonstrated: false, visual_inspection: false,
  verifier_sha256: hash(readFileSync(import.meta.path)),
  helper_sha256: hash(readFileSync(resolve(dirname(import.meta.path), 'raw_json_fingerprint.mjs'))) };
const output = resolve(root, 'review-v1/bun-verification.json'), bytes = JSON.stringify(verification, null, 2) + '\n';
if (existsSync(output)) assert.equal(readFileSync(output, 'utf8'), bytes);
else writeFileSync(output, bytes, { flag: 'wx' });
console.log(JSON.stringify(verification));
