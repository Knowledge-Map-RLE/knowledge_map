// Независимая проверка подстановок, неизменности условий, источников и русского автономного отчёта.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/licensed-part-analogy-v1');
const read = path => readFileSync(resolve(root, path));
const json = path => JSON.parse(read(path).toString('utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
function canonical(v) {
  if (Array.isArray(v)) return v.map(canonical);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])]));
  return v;
}
const fingerprint = v => hash(Buffer.from(JSON.stringify(canonical(v))));
// Числовые лексемы Python сохраняются: 1.0 нельзя хешировать как JavaScript-число 1.
function fingerprintRaw(bytes) {
  const source = bytes.toString('utf8'); let pos = 0;
  const space = () => { while (/\s/.test(source[pos] || '') && pos < source.length) pos++; };
  function string() {
    const start = pos++; let escaped = false;
    while (pos < source.length) {
      const char = source[pos++];
      if (char === '"' && !escaped) return JSON.stringify(JSON.parse(source.slice(start, pos)));
      if (char === '\\' && !escaped) escaped = true; else escaped = false;
    }
    throw new Error('Незавершённая JSON-строка');
  }
  function value() {
    space(); const char = source[pos];
    if (char === '"') return string();
    if (char === '[') {
      pos++; space(); const items = [];
      if (source[pos] !== ']') while (true) {
        items.push(value()); space(); if (source[pos] !== ',') break; pos++;
      }
      assert.equal(source[pos++], ']'); return '[' + items.join(',') + ']';
    }
    if (char === '{') {
      pos++; space(); const rows = [];
      if (source[pos] !== '}') while (true) {
        space(); const key = string(); space(); assert.equal(source[pos++], ':');
        rows.push([JSON.parse(key), key, value()]); space(); if (source[pos] !== ',') break; pos++;
      }
      assert.equal(source[pos++], '}');
      rows.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
      return '{' + rows.map(r => r[1] + ':' + r[2]).join(',') + '}';
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(source.slice(pos));
    assert.ok(token, 'Недопустимый JSON-токен'); pos += token[0].length; return token[0];
  }
  const serialized = value(); space(); assert.equal(pos, source.length);
  return hash(Buffer.from(serialized));
}
const id = (article, kind, local) => fingerprint({ article_id: article, node_kind: kind, local_id: local });
const roles = s => Object.fromEntries(s.roles.map(r => [r.role, r.value]));
const v = json('review-v1/verification.json'), data = json('review-v1/data.json');
for (const [name, digest] of Object.entries(v.files)) assert.equal(hash(read(`review-v1/${name}`)), digest);
for (const [name, digest] of Object.entries(v.inputs)) assert.equal(hash(read(name)), digest);
assert.equal(hash(read('build_review.py')), v.builder_sha256);
assert.equal(hash(read('test-results-v7.xml')), v.tests_sha256);
assert.equal(v.complete_result_reproduced, true); assert.equal(v.domain_seals_checked, true);
assert.equal(v.tests_passed, 108); assert.equal(v.canonical_coverage_checked, 890);
assert.equal(v.candidate_frames_unique, 35); assert.equal(v.without_dependencies_equal, true);
assert.equal(data.sources, 10); assert.equal(data.canonical_blocks, 890); assert.equal(data.native_statements, 1797);
assert.equal(data.licensed_parts, 809); assert.equal(data.admitted_parts, 74);
assert.equal(data.all_candidates.length, 35); assert.equal(data.ranked_candidates.length, 20);
assert.equal(data.coverage.length, 890); assert.equal(data.confirmed_predictions, 0);
assert.equal(data.future_results_scored, 0); assert.equal(data.model_calls, 0); assert.equal(data.target_read, false);
assert.equal(data.scientific_success, false); assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.ablation.without_visible_dependencies_same_result, true);
assert.deepEqual(data.ranked_candidates, data.all_candidates.slice(0, 20));
const folder = `runs/${data.run_id}`, result = json(`${folder}/predictions.json`);
assert.equal(fingerprint(result), json(`${folder}/seal.json`).prediction_sha256);
assert.equal(fingerprint(result.binding), data.run_id);
const parts = json(`${folder}/inputs/parts/predictions.json`), args = json(`${folder}/inputs/arguments/predictions.json`);
assert.equal(fingerprintRaw(read(`${folder}/inputs/parts/predictions.json`)), result.binding.parts_artifact_sha256);
assert.equal(fingerprintRaw(read(`${folder}/inputs/arguments/predictions.json`)), result.binding.arguments_artifact_sha256);
assert.equal(fingerprintRaw(read(`${folder}/inputs/parts/predictions.json`)), json(`${folder}/inputs/parts/seal.json`).prediction_sha256);
assert.equal(fingerprintRaw(read(`${folder}/inputs/arguments/predictions.json`)), json(`${folder}/inputs/arguments/seal.json`).prediction_sha256);
assert.equal(parts.target_read, false); assert.equal(args.target_read, false);
const graph = args.semantic_graph;
const operandProofs = new Map(data.direction_operand_proofs.map(p => [p.id, p]));
assert.equal(operandProofs.size, 4);
let removed = 0, witnesses = 0, quotations = 0;
for (const p of operandProofs.values()) {
  assert.equal(p.id, fingerprint(Object.fromEntries(Object.entries(p).filter(([k]) => k !== 'id'))));
  assert.equal(p.conditions_removed, false); assert.equal(p.participants_changed, false);
  assert.equal(p.direction_inferred_from_numbers, false); assert.equal(p.statistical_significance_transferred, false);
  const input = p.input_frame.statements[0], output = p.output_frame.statements[0];
  assert.equal(input.predicate, 'memory performance improved'); assert.deepEqual(input.scope, output.scope);
  assert.deepEqual(input.roles, output.roles);
  const positions = new Set(p.removed_summaries.map(a => a.position));
  assert.deepEqual(output.attributes, input.attributes.filter((_, pos) => !positions.has(pos)));
  for (const a of p.removed_summaries) {
    removed++; assert.deepEqual(input.attributes[a.position], a.attribute);
    const value = Number(a.attribute.value); assert.ok(Number.isFinite(value));
    if (a.kind === 'reported_memory_readout') {
      assert.equal(a.attribute.unit, 'percent'); assert.ok(value >= 0 && value <= 100);
    } else {
      assert.equal(a.kind, 'reported_memory_test_summary'); assert.equal(a.attribute.unit, 'dimensionless');
      assert.ok(value >= 0 && value <= 1);
    }
  }
}
assert.equal(removed, 16);
const headKeys = new Set();
for (const c of data.all_candidates) {
  const key = fingerprint({ frame: c.frame, recipient: c.recipient_article });
  assert.ok(!headKeys.has(key)); headKeys.add(key);
  assert.equal(c.id, fingerprint({ frame: c.frame, recipient_article: c.recipient_article }));
  assert.equal(c.conclusion_confirmed, false); assert.equal(c.logical_entailment, false);
  assert.equal(c.predicted_p_value, null); assert.equal(c.probability, null); assert.equal(c.effect_size, null);
  assert.deepEqual(c.conclusion_support_families, []);
  assert.equal(c.proposed_scope_status, 'donor_conditions_retained_recipient_response_not_observed');
  const head = c.frame.statements[0]; assert.match(head.scope.modality, /^hypothesis;/);
  for (const w of c.witnesses) {
    witnesses++; assert.equal(w.premises.length, 3); assert.equal(w.author_asserted_rule, false);
    const [a, b, q] = w.premises.map(p => p.frame.statements[0]);
    assert.equal(a.predicate, b.predicate);
    assert.ok(Object.keys(w.substitutions).filter(k => ['intervention', 'factor', 'exposure'].includes(k)).length === 1);
    assert.equal(w.premises[0].native_key[0], w.premises[2].native_key[0]);
    assert.deepEqual(head.attributes, q.attributes);
    assert.deepEqual(head.scope, { ...q.scope, modality: 'hypothesis; analogical response transport not established' });
    assert.deepEqual(roles(head), Object.fromEntries(Object.entries(roles(q)).map(([role, value]) => [role, w.substitutions[role]?.to ?? value])));
    for (const [role, change] of Object.entries(w.substitutions)) {
      assert.equal(roles(a)[role], change.from); assert.equal(roles(b)[role], change.to);
      assert.equal(roles(q)[role], change.from);
    }
    assert.equal(w.transport_obligations.causal_response_transport_established, false);
    assert.equal(w.transport_obligations.donor_conditions_retained_not_recipient_protocol, true);
    assert.ok(c.all_transport_obligations.some(o => fingerprint(o) === fingerprint(w.transport_obligations)));
    for (const p of w.premises) {
      const proof = data.proof_registry[p.projection_proof_id]; assert.ok(proof);
      assert.equal(proof.id, fingerprint(Object.fromEntries(Object.entries(proof).filter(([k]) => k !== 'id'))));
      assert.deepEqual(proof.parent_key, p.native_key); assert.equal(proof.origin.origin, 'primary_result');
      assert.deepEqual(proof.complete_native_knowledge, graph.parents[id(p.native_key[0], 'knowledge', p.native_key[1])].complete_parent);
      const native = graph.statements[id(p.native_key[0], 'statement', proof.native_statement_id)];
      assert.equal(native.position, proof.statement_position);
      for (const eid of native.evidence) {
        const e = graph.source_units[eid]; quotations++;
        assert.equal(e.article_id, p.native_key[0]); assert.equal(Array.from(e.text).length, e.end - e.start);
        assert.equal(hash(Buffer.from(e.text)), e.sha256);
      }
      if (p.direction_operand_proof_id) {
        const operand = operandProofs.get(p.direction_operand_proof_id); assert.ok(operand);
        assert.equal(operand.source_part_proof_id, proof.id); assert.deepEqual(operand.output_frame, p.frame);
      } else {
        const parent = proof.comparison_parent_frame;
        assert.deepEqual(p.frame, { ...parent, logic: 'single', statements: [parent.statements[proof.statement_position]] });
      }
    }
  }
}
assert.equal(witnesses, 57); assert.ok(quotations > 0);
const html = read('review-v1/report.html').toString('utf8');
assert.match(html, /<html lang="ru">/); assert.match(html, /Подтверждённых прогнозов: 0/);
assert.match(html, /протокол получателя/); assert.match(html, /не является визуальной|не научная экспертиза/i);
assert.doesNotMatch(html, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.equal([...html.matchAll(/<article id='кандидат-/g)].length, 35);
for (const c of data.all_candidates) assert.ok(html.includes(`id='кандидат-${c.id}'`));
const receipt = { проверка: 'успешна', знаний: 890, исходных_утверждений: 1797,
  разных_черновиков: 35, зафиксировано_первых: 20, групп_свидетельств: witnesses,
  проверено_ссылок_на_источник: quotations, сводок_памяти_в_доказательстве: removed,
  тестов: 108, подтверждённых_прогнозов: 0, без_видимых_зависимостей_тот_же_результат: true,
  визуальная_проверка: false, научная_экспертиза: false,
  проверяющий_файл_sha256: hash(readFileSync(import.meta.path)), отчёт_sha256: hash(read('review-v1/report.html')) };
const dest = resolve(root, 'review-v1/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(dest, bytes, { flag: 'wx' }); }
catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(dest), bytes); }
console.log(JSON.stringify(receipt));
