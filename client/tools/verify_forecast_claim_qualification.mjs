// Независимая проверка реестра, происхождения и включения точки во временное окно.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/claim-time-and-novelty-v1');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const read = file => readFileSync(resolve(root, file));
const json = file => JSON.parse(read(file));
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
  const receipt = JSON.parse(readFileSync(resolve(folder, 'seal.json')));
  assert.equal(rawJsonFingerprint(bytes), receipt.prediction_sha256);
  assert.equal(rawJsonFingerprint(field(bytes, 'binding')), data.run_id);
  for (const [file, digest] of Object.entries(data.binding.implementation))
    assert.equal(hash(readFileSync(resolve(folder, 'implementation', file))), digest);
  assert.equal(data.model_calls, 0); return { folder, bytes, data };
}
function dag(graph) {
  const ids = new Set(graph.nodes.map(n => n.id)); assert.equal(ids.size, graph.nodes.length);
  const indegrees = new Map([...ids].map(id => [id, 0])), adjacent = new Map([...ids].map(id => [id, []]));
  for (const e of graph.edges) {
    assert.ok(ids.has(e.source) && ids.has(e.target));
    indegrees.set(e.target, indegrees.get(e.target) + 1); adjacent.get(e.source).push(e.target);
  }
  const queue = [...ids].filter(id => !indegrees.get(id)); let visited = 0;
  while (queue.length) {
    const id = queue.pop(); visited++;
    for (const next of adjacent.get(id)) { indegrees.set(next, indegrees.get(next) - 1); if (!indegrees.get(next)) queue.push(next); }
  }
  assert.equal(visited, ids.size);
}
const receipt = json('review-v2/verification.json'), report = json('review-v2/data.json');
for (const [file, digest] of Object.entries(receipt.files)) assert.equal(hash(read('review-v2/' + file)), digest);
assert.equal(hash(read('tests-v5.xml')), receipt.tests_sha256);
assert.equal(hash(readFileSync(resolve(import.meta.dir, '../../api/tools/render_forecast_claim_qualification.py'))), receipt.builder_sha256);
assert.equal(hash(readFileSync(resolve(import.meta.dir, '../../api/tools/render_template_barrier_audit.py'))), receipt.render_helper_sha256);
const tests = new JSDOM(read('tests-v5.xml').toString(), { contentType: 'text/xml' }).window.document;
let count = 0;
for (const s of tests.querySelectorAll('testsuite')) {
  count += Number(s.getAttribute('tests'));
  for (const k of ['failures', 'errors', 'skipped']) assert.equal(Number(s.getAttribute(k)), 0);
}
assert.equal(count, 63); assert.equal(receipt.tests_passed, count);
const current = seal(report.run_path), frozen = seal(report.forecast_path), result = current.data;
assert.equal(result.run_id, receipt.run_id);
assert.equal(rawJsonFingerprint(frozen.bytes), result.forecast_sha256);
const auditBytes = readFileSync(resolve(current.folder, 'audit.json')), audit = JSON.parse(auditBytes);
assert.equal(rawJsonFingerprint(auditBytes), result.audit_sha256);
assert.equal(result.version, 'frozen-forecast-claim-qualification-3');
const previousDescriptor = JSON.parse(readFileSync(resolve(frozen.folder, 'input-corpus.json')));
const applicability = seal(previousDescriptor.snapshot);
assert.equal(rawJsonFingerprint(applicability.bytes), frozen.data.binding.input_sha256);
const upstreamDescriptor = JSON.parse(readFileSync(resolve(applicability.folder, 'input-corpus.json')));
const upstream = seal(upstreamDescriptor.snapshot);
assert.equal(rawJsonFingerprint(upstream.bytes), applicability.data.binding.input_sha256);
assert.deepEqual(audit.map_hashes, upstream.data.binding.map_hashes);
const manifest = JSON.parse(readFileSync(resolve(upstream.folder, 'source-manifest.json')));
const index = JSON.parse(readFileSync(resolve(upstream.folder, 'inputs-manifest.json')));
assert.equal(index.target_read, false); assert.equal(index.model_calls, 0);
assert.equal(manifest.sources.length, 11); assert.equal(index.sources.length, 11);
const maps = new Map(); let canonical = 0, statements = 0, provenance = 0;
for (const [i, row] of index.sources.entries()) {
  const bytes = readFileSync(resolve(upstream.folder, row.map_path)), m = JSON.parse(bytes), entry = manifest.sources[i];
  assert.equal(hash(bytes), row.map_file_sha256); assert.equal(hash(bytes), entry.file_sha256);
  assert.equal(rawJsonFingerprint(field(bytes, 'graph')), entry.graph_sha256);
  for (const k of ['article_id', 'pipeline_id', 'run_id']) assert.equal(m[k], row.reference[k]);
  assert.equal(hash(Buffer.from(m.source.text)), m.source.sha256);
  assert.equal(m.graph.schema_version, 6); dag(m.graph);
  const points = Array.from(m.source.text), units = new Map(m.source.units.map(u => [u.id, u]));
  for (const k of m.graph.knowledge) {
    const record = result.inventory.find(v => v.article_id === m.article_id && v.knowledge_id === k.knowledge_id);
    assert.ok(record); assert.equal(record.run_id, m.run_id);
    assert.equal(record.statement_count, k.semantic_frame.statements.length);
    assert.match(record.semantic_sha256, /^[a-f0-9]{64}$/);
    statements += record.statement_count;
    for (const s of k.semantic_frame.statements) {
      assert.ok(s.provenance.unit_ids.length);
      for (const uid of s.provenance.unit_ids) {
        const u = units.get(uid); assert.ok(u);
        assert.ok(u.start < u.end && u.end <= m.source.content_end);
        assert.equal(points.slice(u.start, u.end).join(''), u.text); provenance++;
      }
    }
  }
  if (row.coverage_path) assert.equal(hash(readFileSync(resolve(upstream.folder, row.coverage_path))), row.coverage_sha256);
  canonical += m.graph.knowledge.length; maps.set(m.article_id, m);
}
assert.equal(canonical, 943); assert.equal(statements, 1897);
assert.equal(result.inventory.length, canonical);
assert.equal(new Set(result.inventory.map(r => r.article_id + '/' + r.knowledge_id)).size, canonical);
assert.equal(result.canonical_blocks, canonical); assert.equal(result.semantic_statements, statements);
let quotes = 0;
function quote(source, e) {
  const u = source.units.find(v => v.id === e.unit_id); assert.ok(u);
  assert.ok(u.start <= e.start && e.start < e.end && e.end <= u.end && u.end <= source.content_end);
  assert.equal(Array.from(source.text).slice(e.start, e.end).join(''), e.text);
  assert.equal(hash(Buffer.from(e.text)), e.sha256); quotes++;
}
assert.equal(result.citation_occurrences.length, 1);
for (const e of result.citation_occurrences) {
  const m = maps.get(e.article_id); assert.equal(m.source.sha256, e.source_sha256);
  assert.equal(Array.from(m.source.text).slice(e.start, e.end).join(''), e.text);
  assert.equal(hash(Buffer.from(e.text)), e.sha256); assert.equal(e.fact_equivalence, false);
  assert.equal(e.section, 'references'); assert.ok(e.start >= m.source.content_end);
}
const sourceBytes = readFileSync(resolve(frozen.folder, 'external-source.json')), source = JSON.parse(sourceBytes);
assert.equal(rawJsonFingerprint(sourceBytes), audit.external_source_packet_sha256);
const candidates = new Map(frozen.data.modes.graph.flatMap(f => f.predictions).map(c => [c.id, c]));
assert.equal(candidates.size, 2); assert.equal(result.candidates.length, 2);
for (const row of result.candidates) {
  const c = candidates.get(row.prediction_id); assert.ok(c);
  assert.equal('temporal_scope' in c.head, false);
  assert.equal(row.temporal.status, 'missing_prediction_temporal_contract');
  assert.equal(row.temporal.scientific_confirmation, false); assert.equal(row.full_fact_equivalence, false);
  for (const e of row.known_pattern_evidence) {
    const m = maps.get(e.article_id); assert.equal(m.source.sha256, e.source_sha256); quote(m.source, e);
    assert.equal(e.license_kind, 'explicit_therapeutic_activity_eae');
    assert.ok(e.text.includes('demonstrated therapeutic activity in the EAE model'));
    assert.ok(c.head.participants.intervention.toLowerCase().includes(e.intervention_alias.toLowerCase()));
  }
  const annotation = audit.candidates.find(a => a.prediction_id === row.prediction_id); assert.ok(annotation);
  for (const o of annotation.outcome_temporal_observations) for (const e of o.evidence) quote(source.source, e);
}
assert.deepEqual(result.status_counts, {not_established: 1, known_coarse_pattern: 1});
assert.equal(result.source_consequences.length, 1);
const consequence = result.source_consequences[0], observed = consequence.source_observation;
assert.equal(consequence.rule, 'point_in_method_window_then_existential_introduction');
assert.equal(consequence.is_future_prediction, false); assert.equal(consequence.is_new_scientific_fact, false);
assert.deepEqual(consequence.contract.bindings, observed.contract.bindings);
assert.equal(consequence.contract.anchor, observed.contract.anchor);
assert.equal(consequence.contract.episode, observed.contract.episode);
assert.equal(consequence.contract.time_quantifier, 'some_assessed_time');
assert.equal(observed.contract.time_quantifier, 'specified_time'); assert.equal(observed.precision, 'exact');
assert.deepEqual(observed.assessment_times, ['3']);
const point = Number(observed.contract.window.start), begin = Number(consequence.contract.window.start), end = Number(consequence.contract.window.end);
assert.equal(point, 3); assert.equal(begin, 1); assert.equal(end, 28); assert.ok(begin <= point && point <= end);
assert.equal(consequence.proof.supported, true); assert.equal(consequence.proof.scientific_confirmation, false);
const receiver = frozen.data.receivers.find(r => r.id === consequence.receiver_id); assert.ok(receiver);
const attrs = body => Object.fromEntries(body.frame.statements[0].attributes.map(a => [a.name, a.value]));
assert.equal(attrs(receiver.body[0])['EAE-relative days'], '1; 4; 8; 12');
assert.equal(attrs(receiver.body[1])['explicit clinical observation end'], '28');
const h398 = frozen.data.receivers.find(r => r.id.includes('h398'));
assert.equal(attrs(h398.body[1])['explicit clinical observation end'], null);
assert.equal(attrs(h398.body[1])['histopathology endpoint, separate measure'], '85');
assert.ok(!result.source_consequences.some(c => c.receiver_id.includes('h398')));
assert.equal(result.new_scientific_knowledge_confirmed, false); assert.equal(result.graph_advantage_demonstrated, false);
const doc = new JSDOM(read('review-v2/report.html').toString()).window.document;
assert.equal(doc.documentElement.lang, 'ru'); assert.equal(doc.querySelectorAll('details').length, 2);
assert.equal(doc.querySelectorAll('script[src],link[href],img[src],iframe[src]').length, 0);
const output = {run_id: result.run_id, forecast_id: frozen.data.run_id, tests_passed: count,
  canonical_blocks: canonical, semantic_statements: statements, source_provenance_uses: provenance,
  quote_uses: quotes, citation_occurrences: 1, source_temporal_consequences: 1,
  frozen_predictions_changed: false, full_scientific_confirmations: 0, graph_advantage_demonstrated: false,
  model_calls: 0, visual_review_claimed: false,
  verifier_sha256: hash(readFileSync(import.meta.path)), helper_sha256: hash(readFileSync(resolve(import.meta.dir, 'raw_json_fingerprint.mjs')))};
const destination = resolve(root, 'review-v2/bun-verification.json'), bytes = JSON.stringify(output, null, 2) + '\n';
if (existsSync(destination)) assert.equal(readFileSync(destination).toString(), bytes);
else writeFileSync(destination, bytes, {flag: 'wx'});
console.log(JSON.stringify(output));
