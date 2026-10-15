// Полные группы проверяются независимо, без переписывания исходных семантических кадров.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';
const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/author-argument-circuits-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p));
const hash = v => createHash('sha256').update(v).digest('hex');
const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
const fp = v => hash(Buffer.from(JSON.stringify(canonical(v))));
const verification = json('operator-eligibility-review-v1/verification.json');
for (const [path, h] of Object.entries(verification.inputs)) assert.equal(hash(read(path)), h);
for (const [path, h] of Object.entries(verification.files)) assert.equal(hash(read('operator-eligibility-review-v1/' + path)), h);
assert.equal(hash(read('build_operator_eligibility_review.py')), verification.builder_sha256);
const folder = 'operator-eligibility-runs/' + verification.run_id;
const r = json(folder + '/predictions.json'), source = json(folder + '/inputs/source/predictions.json');
assert.equal(rawJsonFingerprint(read(folder + '/predictions.json')), json(folder + '/seal.json').prediction_sha256);
assert.equal(fp(r.binding), r.run_id);
// 1.0 и числовые ключи не канонизируются через свойства объекта JavaScript.
assert.equal(rawJsonFingerprint(read(folder + '/inputs/source/predictions.json')), r.binding.source_artifact_sha256);
assert.equal(r.binding.source_artifact_sha256, json(folder + '/inputs/source/seal.json').prediction_sha256);
assert.equal(r.binding.source_run_id, source.run_id); assert.equal(source.model_calls, 0); assert.equal(source.target_read, false);
const groups = source.argument_circuits.groups;
assert.equal(r.rows.length, 676); assert.equal(Object.keys(groups).length, 676);
assert.equal(new Set(r.rows.map(row => row.group_id)).size, 676);
assert.equal(r.canonical_blocks, 890); assert.equal(r.native_statements, 1797);
const routes = {}, arities = {}; let proofCount = 0, refs = 0, oversized = 0;
function fraction(s) { const [a, b = '1'] = s.split('/'); return [BigInt(a), BigInt(b)]; }
const equalSum = (terms, expected) => {
  let n = 0n, d = 1n;
  for (const [a, b] of terms) { n = n * b + a * d; d *= b; }
  const [a, b] = expected; assert.equal(n * b, a * d);
};
for (const row of r.rows) {
  const g = groups[row.group_id]; assert.ok(g);
  assert.equal(row.head, g.head); assert.deepEqual(row.full_premises, g.premises);
  assert.deepEqual(row.premise_occurrences, g.premise_occurrences); assert.equal(row.head_occurrence, g.head_occurrence);
  assert.equal(row.arity, g.premises.length); assert.equal(row.all_members_retained, true); assert.equal(row.alternative_groups_merged, false);
  assert.equal(row.automatically_licensed_empirical_rule, false);
  oversized += Number(row.arity > 3); routes[row.route] = (routes[row.route] || 0) + 1; arities[row.arity] = (arities[row.arity] || 0) + 1;
  for (const e of row.transition_evidence) {
    assert.equal(hash(Buffer.from(e.text)), e.sha256); assert.equal([...e.text].length, e.end - e.start); refs++;
  }
  for (const proof of row.countermodels) {
    const parent = source.semantic_graph.parents[g.premises.find(key => source.semantic_graph.parents[key].knowledge_id === proof.parent_knowledge_id)];
    assert.ok(parent); assert.equal(proof.parent_sha256, parent.knowledge_sha256);
    const s = parent.complete_parent.semantic_frame.statements.find(s => s.statement_id === proof.statement_id);
    assert.ok(s.qualifiers.attributes.some(a => JSON.stringify(a) === JSON.stringify(proof.original_attribute)));
    const witness = proof.witness, [a, b] = witness.models;
    assert.equal(a.incremental_R2, b.incremental_R2); assert.equal(a.baseline_R2, b.baseline_R2); assert.equal(a.full_R2, b.full_R2);
    for (const model of witness.models) {
      equalSum([fraction(model.baseline_R2), fraction(model.fitted_added_variance), fraction(model.residual_variance)], [1n, 1n]);
      equalSum([fraction(model.baseline_R2), fraction(model.incremental_R2)], fraction(model.full_R2));
    }
    if (witness.requested_parameter === 'intercept') assert.notEqual(a.intercept, b.intercept);
    else assert.notEqual(a.added_coefficient, b.added_coefficient);
    assert.equal(witness.source_patient_data_reconstructed, false); assert.equal(witness.applies_to_full_source_prose, false); proofCount++;
  }
}
assert.deepEqual(routes, r.counts); assert.deepEqual(arities, r.arity_counts);
assert.equal(oversized, 21); assert.equal(proofCount, 14); assert.equal(r.counts.result_synthesis_requires_operator_license, 13);
assert.equal(r.counts.parameter_not_identified_by_fit_summary, 7); assert.equal(r.counts.interpretation_not_empirical_truth_label, 20);
assert.deepEqual(r.automatically_licensed_empirical_rules, []); assert.deepEqual(r.future_predictions, []);
assert.equal(r.scientific_success, false); assert.equal(r.graph_advantage_demonstrated, false); assert.equal(r.model_calls, 0);
const html = read('operator-eligibility-review-v1/report.html').toString('utf8');
assert.match(html, /<html lang='ru'>/); assert.match(html, /Подтверждённых новых прогнозов — 0/);
assert.doesNotMatch(html, /<script|<iframe|<img|https?:\/\/|src=/i);
for (const row of r.rows) assert.ok(html.includes("id='группа-" + row.group_id + "'"));
const receipt = { run_id: r.run_id, verifier_sha256: hash(readFileSync(import.meta.path)), report_sha256: hash(read('operator-eligibility-review-v1/report.html')),
  canonicalizer_sha256: hash(readFileSync(resolve(import.meta.dir, 'raw_json_fingerprint.mjs'))),
  groups: 676, transition_refs: refs, oversized_groups: oversized, fit_countermodels: proofCount, tests_passed: verification.tests_passed,
  scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false };
const path = resolve(root, 'operator-eligibility-review-v1/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(path, bytes, { flag: 'wx' }); } catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
