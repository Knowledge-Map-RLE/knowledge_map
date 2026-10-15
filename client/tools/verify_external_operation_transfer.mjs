// Независимый контроль печатей, происхождения, семейств и временной неопределённости.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/external-operation-transfer-v1');
const review = 'review-v2';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const read = file => readFileSync(resolve(root, file)), json = file => JSON.parse(read(file));
function field(bytes, name) {
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
  assert.fail('Незавершённый JSON');
}
function seal(folder) {
  const bytes = readFileSync(resolve(folder, 'predictions.json')), data = JSON.parse(bytes);
  const proof = JSON.parse(readFileSync(resolve(folder, 'seal.json')));
  assert.equal(rawJsonFingerprint(bytes), proof.prediction_sha256);
  assert.equal(rawJsonFingerprint(field(bytes, 'binding')), data.run_id);
  for (const [file, digest] of Object.entries(data.binding.implementation))
    assert.equal(hash(readFileSync(resolve(folder, 'implementation', file))), digest);
  assert.equal(data.model_calls, 0); return { folder, bytes, data };
}
function dag(graph) {
  const ids = new Set(graph.nodes.map(n => n.id)); assert.equal(ids.size, graph.nodes.length);
  const incoming = new Map([...ids].map(id => [id, 0])), adjacent = new Map([...ids].map(id => [id, []]));
  for (const e of graph.edges) {
    assert.ok(ids.has(e.source) && ids.has(e.target));
    incoming.set(e.target, incoming.get(e.target) + 1); adjacent.get(e.source).push(e.target);
  }
  const queue = [...ids].filter(id => !incoming.get(id)); let visited = 0;
  while (queue.length) {
    const id = queue.pop(); visited++;
    for (const next of adjacent.get(id)) { incoming.set(next, incoming.get(next) - 1); if (!incoming.get(next)) queue.push(next); }
  }
  assert.equal(visited, ids.size);
}
const receipt = json(review + '/verification.json'), report = json(review + '/data.json');
for (const [file, digest] of Object.entries(receipt.files)) assert.equal(hash(read(review + '/' + file)), digest);
assert.equal(hash(read('tests-v1.xml')), receipt.tests_sha256);
assert.equal(hash(readFileSync(resolve(import.meta.dir, '../../api/tools/render_external_operation_transfer.py'))), receipt.builder_sha256);
assert.equal(hash(readFileSync(resolve(import.meta.dir, '../../api/tools/render_template_barrier_audit.py'))), receipt.render_helper_sha256);
const tests = new JSDOM(read('tests-v1.xml').toString(), { contentType: 'text/xml' }).window.document;
let count = 0;
for (const suite of tests.querySelectorAll('testsuite')) {
  count += Number(suite.getAttribute('tests'));
  for (const k of ['failures', 'errors', 'skipped']) assert.equal(Number(suite.getAttribute(k)), 0);
}
assert.equal(count, 48); assert.equal(receipt.tests_passed, count);
const current = seal(report.run_path), result = current.data;
assert.equal(result.run_id, receipt.run_id);
const evalBytes = readFileSync(resolve(current.folder, 'evaluations', report.evaluation_id + '.json'));
const evaluation = JSON.parse(evalBytes);
assert.equal(rawJsonFingerprint(evalBytes), receipt.evaluation_id);
assert.equal(evaluation.forecast_sha256, rawJsonFingerprint(current.bytes));
const descriptor = JSON.parse(readFileSync(resolve(current.folder, 'input-corpus.json')));
const training = seal(descriptor.snapshot);
assert.equal(rawJsonFingerprint(training.bytes), result.binding.input_sha256);
const trainingDescriptor = JSON.parse(readFileSync(resolve(training.folder, 'input-corpus.json')));
const upstream = seal(trainingDescriptor.snapshot);
assert.equal(rawJsonFingerprint(upstream.bytes), training.data.binding.input_sha256);
const index = JSON.parse(readFileSync(resolve(upstream.folder, 'inputs-manifest.json')));
assert.equal(index.model_calls, 0); assert.equal(index.target_read, false);
assert.equal(index.sources.length, 11);
let canonical = 0;
const articleIds = new Set(), maps = new Map();
for (const [i, row] of index.sources.entries()) {
  const bytes = readFileSync(resolve(upstream.folder, row.map_path)), map = JSON.parse(bytes);
  assert.equal(hash(bytes), row.map_file_sha256);
  let loadedBytes = bytes;
  if (row.coverage_path) {
    const coverageBytes = readFileSync(resolve(upstream.folder, row.coverage_path));
    assert.equal(hash(coverageBytes), row.coverage_sha256);
    const coverage = JSON.parse(coverageBytes), units = new Map(map.source.units.map(u => [u.id, u]));
    const knowledge = new Map(map.graph.knowledge.map(k => [k.knowledge_id, k]));
    const represented = new Set(), statuses = {};
    assert.equal(coverage.units.length, units.size);
    assert.equal(new Set(coverage.units.map(u => u.unit_id)).size, units.size);
    for (const r of coverage.units) {
      const u = units.get(r.unit_id); assert.ok(u);
      assert.equal(r.start, u.start); assert.equal(r.end, u.end);
      statuses[r.status] = (statuses[r.status] ?? 0) + 1;
      if (['excluded', 'not_formalized_in_this_revision'].includes(r.status)) {
        assert.equal(r.knowledge_ids.length, 0); assert.ok(r.reason_ru);
      } else {
        assert.ok(r.knowledge_ids.length && !r.reason_ru);
        for (const id of r.knowledge_ids) {
          const k = knowledge.get(id); assert.ok(k);
          assert.ok(k.semantic_frame.statements.some(s => s.provenance.unit_ids.includes(r.unit_id)));
          represented.add(id);
        }
      }
    }
    assert.equal(represented.size, knowledge.size);
    const audit = {version: 'whole-map-input-audit-2', article_id: map.article_id, run_id: map.run_id,
      source_sha256: map.source.sha256, coverage_artifact_sha256: row.coverage_sha256,
      canonical_blocks: knowledge.size, source_units: units.size, unit_statuses: statuses,
      declared_complete_semantic_coverage: coverage.complete_semantic_coverage,
      expert_verified_complete_semantic_coverage: false,
      complete_source_reviewed: coverage.complete_source_reviewed === true,
      table_cells_exhaustively_formalized: coverage.table_cells_exhaustively_formalized === true,
      source_limitations: coverage.source_limitations ?? [],
      scope: coverage.complete_semantic_coverage ? 'declared_complete_map' : 'selected_propositions_only'};
    assert.deepEqual(audit, upstream.data.input_corpus_audit.sources.find(a => a.article_id === map.article_id));
    // Порт добавляет проверенный аудит к прочитанной карте; исходный файл не меняется.
    loadedBytes = Buffer.from(bytes.toString().trim().slice(0, -1) + ',"forecast_input_coverage":' + JSON.stringify(audit) + '}');
  }
  assert.equal(rawJsonFingerprint(loadedBytes), upstream.data.binding.map_hashes[i]);
  assert.equal(map.graph.schema_version, 6); dag(map.graph); canonical += map.graph.knowledge.length;
  assert.equal(hash(Buffer.from(map.source.text)), map.source.sha256);
  const mapPoints = Array.from(map.source.text), mapUnits = new Map(map.source.units.map(u => [u.id, u]));
  for (const k of map.graph.knowledge) for (const s of k.semantic_frame.statements) {
    assert.ok(s.provenance.unit_ids.length);
    for (const uid of s.provenance.unit_ids) {
      const u = mapUnits.get(uid); assert.ok(u);
      assert.ok(u.start < u.end && u.end <= map.source.content_end);
      assert.equal(mapPoints.slice(u.start, u.end).join(''), u.text);
    }
  }
  assert.notEqual(map.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  articleIds.add(map.article_id);
  maps.set(map.article_id, map);
}
assert.equal(canonical, 943); assert.equal(result.coverage.canonical_blocks, canonical);
const sourceBytes = readFileSync(resolve(current.folder, 'external-source.json')), source = JSON.parse(sourceBytes);
const methodBytes = readFileSync(resolve(current.folder, 'external-methods.json')), methods = JSON.parse(methodBytes);
const outcomes = JSON.parse(readFileSync(resolve(current.folder, 'external-outcomes.json')));
assert.equal(hash(Buffer.from(source.source.text)), source.source.sha256);
assert.equal(source.source.sha256, 'bf45c4b77e2ace6e3a17fc2dafa4f56d52eaf2650119d8dff0cc0ad5dc5c8fd5');
assert.equal(rawJsonFingerprint(sourceBytes), methods.source_packet_sha256);
assert.equal(rawJsonFingerprint(methodBytes), result.binding.receiver_packet_sha256);
assert.equal(outcomes.source_packet_sha256, methods.source_packet_sha256);
assert.equal(source.reference_count, 50); assert.equal(source.source.units.length, 70);
const xml = new JSDOM(read('source/article.xml').toString(), { contentType: 'text/xml' }).window.document;
assert.equal(xml.querySelectorAll('ref-list ref').length, 50);
assert.equal(xml.querySelector('article-id[pub-id-type="doi"]').textContent, source.doi);
const points = Array.from(source.source.text); let quoteUses = 0;
function quote(e) {
  const unit = source.source.units.find(u => u.id === e.unit_id); assert.ok(unit);
  assert.ok(e.start >= unit.start && e.end <= unit.end && e.end <= source.source.content_end);
  assert.equal(points.slice(e.start, e.end).join(''), e.text);
  assert.equal(hash(Buffer.from(e.text)), e.sha256); quoteUses++;
}
for (const r of methods.receivers) {
  assert.ok(!articleIds.has(r.article_id));
  assert.ok(!training.data.cases.some(c => c.primary_family === r.primary_family));
  assert.deepEqual(r, result.receivers.find(v => v.id === r.id));
  assert.equal(r.body.length, 2);
  for (const body of r.body) {
    assert.equal(body.frame.kind, 'action'); assert.equal(body.frame.action_status, 'performed');
    assert.equal(body.frame.statements[0].negated, false);
    assert.equal(body.frame.statements[0].scope.modality, null);
  }
  for (const items of Object.values(r.feature_evidence)) for (const e of items) quote(e);
}
for (const q of methods.method_evidence) for (const e of q.quotes) quote(e);
for (const o of outcomes.outcomes) for (const e of o.evidence) quote(e);
assert.equal(new Set(methods.receivers.map(r => r.primary_family)).size, 1);
assert.equal(result.external_results_used_in_training, false);
assert.equal(result.temporal_prediction_specified, false);
assert.equal(result.temporal_train_test_split, false);
assert.equal(result.target_question, null);
assert.equal(methods.results_previously_disclosed, true); assert.equal(methods.blind_control, false);
assert.ok(report.secondary_source_exposure_audit.length);
for (const record of report.secondary_source_exposure_audit) {
  const m = maps.get(record.article_id); assert.ok(m);
  assert.equal(record.source_sha256, m.source.sha256);
  assert.ok(m.source.text.includes(record.citation_doi));
  for (const u of record.units) assert.deepEqual(u, m.source.units.find(v => v.id === u.id));
}
const roles = part => Object.fromEntries(part.frame.statements[0].roles.map(r => [r.role, r.value]));
for (const [mode, folds] of Object.entries(result.modes)) {
  assert.equal(folds.length, 2); const assessed = evaluation.modes[mode];
  const candidates = folds.flatMap(f => f.predictions);
  assert.equal(candidates.length, mode === 'permuted_dependencies' ? 0 : 2);
  assert.equal(assessed.length, candidates.length);
  for (const c of candidates) {
    assert.equal(c.deductive_entailment, false); assert.equal(c.support_families.length, 2);
    const fold = folds.find(f => f.receiver_id === c.receiver_id), rule = fold.rules.find(r => r.id === c.rule_id);
    assert.ok(rule); assert.deepEqual(rule.support_case_ids, c.support_case_ids);
    assert.ok(!c.support_families.includes(c.receiver.primary_family));
    assert.equal('temporal_scope' in c.head, false);
    const bound = roles(c.receiver.body[0]);
    for (const key of ['population', 'intervention', 'challenge', 'comparator']) assert.equal(c.head.participants[key], bound[key]);
    for (const e of rule.evidence) {
      assert.ok(articleIds.has(e.article_id)); assert.notEqual(e.article_id, c.receiver.article_id);
      assert.equal(e.qualitative_direction, c.head.qualitative_direction);
      assert.equal(e.outcome_class, c.head.outcome_class);
      assert.deepEqual(e.features, c.receiver.features);
      assert.equal(roles(e.method).comparator, roles(e.result).comparator);
    }
    const row = assessed.find(v => v.prediction_id === c.id);
    assert.equal(row.relation, 'direction_match_temporal_scope_unresolved');
    assert.equal(row.coarse_direction_matches, true); assert.equal(row.full_fact_equivalence, false);
    assert.equal(row.independent_scientific_confirmation, false);
  }
}
assert.equal(outcomes.outcomes.find(o => o.id.includes('atrosab')).reported_initial_effect_end, '24');
assert.equal(outcomes.outcomes.find(o => o.id.includes('h398')).reported_initial_effect_end, 'approximately 35');
assert.equal(evaluation.new_scientific_knowledge_confirmed, false);
assert.equal(evaluation.graph_advantage_demonstrated, false);
const doc = new JSDOM(read(review + '/report.html').toString()).window.document;
assert.equal(doc.documentElement.lang, 'ru'); assert.equal(doc.querySelectorAll('details').length, 2);
assert.equal(doc.querySelectorAll('table tbody tr').length, 3);
assert.equal(doc.querySelectorAll('script[src],link[href],img[src],iframe[src]').length, 0);
assert.ok(doc.body.textContent.includes('рецидив'));
const output = { run_id: result.run_id, evaluation_id: report.evaluation_id,
  sources: 11, canonical_blocks: canonical, quote_uses: quoteUses, tests_passed: count,
  external_study_families: 1, hypotheses: { graph: 2, without_dependencies: 2, permuted_dependencies: 0 },
  temporal_confirmation_unresolved: 2, scientific_confirmations: 0, graph_advantage_demonstrated: false,
  model_calls: 0, visual_review_claimed: false, secondary_training_source_cites_external_doi: true,
  verifier_sha256: hash(readFileSync(import.meta.path)), helper_sha256: hash(readFileSync(resolve(import.meta.dir, 'raw_json_fingerprint.mjs'))) };
const bytes = JSON.stringify(output, null, 2) + '\n', destination = resolve(root, review + '/bun-verification.json');
if (existsSync(destination)) assert.equal(readFileSync(destination).toString(), bytes);
else writeFileSync(destination, bytes, { flag: 'wx' });
console.log(JSON.stringify(output));
