// Независимая проверка конечных списков: десятичные сравнения выполняются через BigInt.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/finite-test-synthesis-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p));
const hash = v => createHash('sha256').update(v).digest('hex');
const v = json('review-v2/verification.json');
for (const [p, h] of Object.entries(v.inputs)) assert.equal(hash(read(p)), h);
for (const [p, h] of Object.entries(v.files)) assert.equal(hash(read('review-v2/' + p)), h);
assert.equal(hash(read('build_review_v2.py')), v.builder_sha256);
const folder = 'runs/' + v.run_id, result = json(folder + '/predictions.json');
const source = json(folder + '/inputs/predictions.json'), g = source.semantic_graph;
assert.equal(rawJsonFingerprint(read(folder + '/predictions.json')), json(folder + '/seal.json').prediction_sha256);
assert.equal(rawJsonFingerprint(read(folder + '/inputs/predictions.json')), result.binding.source_artifact_sha256);
assert.equal(rawJsonFingerprint(Buffer.from(JSON.stringify(result.binding))), result.run_id);
assert.equal(result.binding.source_artifact_sha256, json(folder + '/inputs/seal.json').prediction_sha256);
for (const [p, h] of Object.entries(result.binding.implementation)) assert.equal(hash(read(folder + '/implementation/' + p)), h);
const reads = json(folder + '/reads.json');
assert.equal(reads.network_disabled, true); assert.equal(reads.other_maps_read, false); assert.equal(reads.model_calls, 0);
assert.equal(source.target_read, false); assert.equal(result.target_read, false);
assert.equal(result.canonical_blocks, 890); assert.equal(result.native_statements, 1797);
assert.equal(result.author_groups.length, 676); assert.equal(Object.keys(source.argument_circuits.groups).length, 676);
assert.equal(new Set(result.author_groups.map(r => r.group_id)).size, 676);

function decimal(raw) {
  const m = /^\s*(<=|>=|<|>|≤|≥)?\s*((?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,3})?)\s*$/.exec(raw);
  assert.ok(m); const [base, exp = '0'] = m[2].toLowerCase().split('e');
  const [integer, fraction = ''] = base.split('.'); let n = BigInt((integer || '0') + fraction), d = 10n ** BigInt(fraction.length);
  const e = Number(exp); if (e > 0) n *= 10n ** BigInt(e); else d *= 10n ** BigInt(-e);
  assert.ok(n >= 0n && n <= d); return { op: ({ '≤': '<=', '≥': '>=' })[m[1]] || m[1], n, d };
}
function decision(p, alpha) {
  const a = decimal(p), b = decimal(alpha); assert.equal(b.op, undefined); assert.ok(b.n > 0n);
  const cmp = a.n * b.d - b.n * a.d;
  if (!a.op) return cmp < 0n ? 'below' : 'not_below';
  if (a.op === '<' || a.op === '<=') return cmp < 0n || cmp === 0n && a.op === '<' ? 'below' : 'undetermined';
  return cmp >= 0n ? 'not_below' : 'undetermined';
}
let refs = 0, derivedTests = 0;
function checkEvidence(e, article) {
  assert.equal(e.article_id, article); assert.equal(hash(Buffer.from(e.text)), e.sha256);
  assert.equal([...e.text].length, e.end - e.start); assert.deepEqual(e, g.source_units[e.id]); refs++;
}
function checkSummary(s, members) {
  assert.deepEqual(s.members, [...members].sort()); assert.equal(s.finite_set_only, true);
  assert.equal(s.independent_tests_assumed, false); assert.equal(s.new_empirical_prediction, false);
  assert.equal(s.biological_effect_or_absence_established, false); assert.equal(s.compound_parts_asserted_as_independent_facts, false);
  const counts = { below: 0, not_below: 0, undetermined: 0 }, testIds = new Set(), measuredParents = new Set();
  for (const p of members) assert.deepEqual(s.whole_parents[p], g.parents[p]);
  for (const t of s.tests) {
    assert.ok(members.includes(t.parent)); measuredParents.add(t.parent);
    const parent = g.parents[t.parent], native = parent.complete_parent.semantic_frame.statements.find(n => n.statement_id === t.statement_id);
    assert.deepEqual(t.original_statement, native); assert.equal(parent.article_id, s.article_id);
    const ps = native.qualifiers.attributes.filter(a => a.name === 'p'), as = native.qualifiers.attributes.filter(a => a.name === 'alpha');
    assert.equal(ps.length, 1); assert.equal(as.length, 1); assert.equal(ps[0].unit, 'dimensionless'); assert.equal(as[0].unit, 'dimensionless');
    const op = t.operation.operation; assert.equal(op.reported_p, ps[0].value); assert.equal(op.reported_alpha, as[0].value);
    assert.equal(op.decision, decision(ps[0].value, as[0].value)); counts[op.decision]++;
    const cutoff = decimal(s.cutoff), alpha = decimal(as[0].value); assert.equal(cutoff.n * alpha.d, alpha.n * cutoff.d);
    assert.equal(t.cohort, s.cohort); assert.equal(op.biological_effect_or_absence_established, false);
    const part = Object.values(g.statements).find(n => n.parent === t.parent && n.statement_id === t.statement_id);
    assert.deepEqual(t.operation.roles, part.roles); assert.deepEqual(t.operation.scope, part.scope);
    assert.equal(part.roles.filter(r => r.role === 'cohort').length, 1);
    assert.equal(part.roles.find(r => r.role === 'cohort').target, s.cohort);
    assert.equal(part.unknown_context, false); assert.equal(part.negated, false); assert.equal(part.scope.modality, null);
    for (const e of t.operation.evidence) checkEvidence(e, s.article_id);
    const id = t.parent + ':' + t.statement_id; assert.ok(!testIds.has(id)); testIds.add(id); derivedTests++;
  }
  for (const p of measuredParents) {
    assert.equal(s.tests.filter(t => t.parent === p).length, g.parents[p].complete_parent.semantic_frame.statements.length);
  }
  for (const d of s.threshold_definitions) {
    assert.ok(members.includes(d.parent)); assert.equal(d.cohort, s.cohort);
    const native = g.parents[d.parent].complete_parent.semantic_frame.statements.find(n => n.statement_id === d.statement_id);
    assert.equal(native.predicate, 'define multiplicity threshold');
    assert.equal(native.qualifiers.attributes.find(a => a.name === 'comparison').value, 'strict p<alpha');
    for (const e of d.evidence) checkEvidence(e, s.article_id);
  }
  const p = s.profile; assert.equal(p.listed_tests, s.tests.length);
  for (const [k, n] of Object.entries(counts)) assert.equal(p[k], n);
  assert.equal(p.passing_count_lower_bound, counts.below); assert.equal(p.passing_count_upper_bound, counts.below + counts.undetermined);
  assert.equal(p.none_of_listed_tests_below, counts.below === 0 && counts.undetermined === 0);
  assert.equal(p.all_of_listed_tests_below, counts.below === s.tests.length);
  assert.equal(p.at_least_one_listed_test_below, counts.below > 0);
}
const statuses = {}, profiles = [];
for (const row of result.author_groups) {
  const group = source.argument_circuits.groups[row.group_id]; assert.ok(group);
  assert.deepEqual(row.members, group.premises); assert.equal(row.arity, group.premises.length);
  assert.equal(row.head_reference_for_navigation_only, group.head); assert.equal(row.head_content_used_as_operand, false);
  assert.equal(row.alternative_groups_merged, false); assert.equal(row.same_members_without_arrows_identical, true);
  assert.equal(row.member_audit.length, row.arity);
  for (const e of row.transition_evidence) checkEvidence(e, row.article_id);
  statuses[row.status] = (statuses[row.status] || 0) + 1;
  if (row.summary) {
    checkSummary(row.summary, row.members); profiles.push(row.summary.profile);
  } else {
    assert.ok(row.member_audit.some(m => m.kind === 'unsupported_full_parent'));
  }
}
assert.deepEqual(statuses, result.counts); assert.equal(profiles.length, 3);
assert.ok(profiles.some(p => p.listed_tests === 60 && p.below === 0));
assert.ok(profiles.some(p => p.listed_tests === 3 && p.below === 2));
assert.ok(profiles.some(p => p.listed_tests === 3 && p.below === 1));
const eligible = new Map(result.quantitative.proofs.filter(p => p.all_statement_decisions.every(s => s.status === 'printed_comparison_computed')).map(p => [p.parent, p]));
const bucketed = new Set();
for (const b of result.semantic_sets_without_author_groups) {
  assert.equal(b.membership_origin, 'statement_semantics_without_author_groups');
  checkSummary(b.summary, b.summary.members);
  for (const p of b.summary.members) { assert.ok(eligible.has(p)); assert.ok(!bucketed.has(p)); bucketed.add(p); }
  for (const t of b.summary.tests) {
    assert.deepEqual(b.grouping_key, [g.parents[t.parent].article_id, t.predicate, t.cohort, t.cutoff]);
  }
}
assert.equal(bucketed.size, eligible.size); assert.equal(result.semantic_sets_without_author_groups.length, 3);
assert.equal(result.baseline_parent_coverage.length + bucketed.size, result.canonical_blocks);
assert.equal(result.exact_test_sets_also_found_without_groups, 1);
assert.deepEqual(result.new_predictions, []); assert.equal(result.scientific_success, false); assert.equal(result.graph_advantage_demonstrated, false);
const html = read('review-v2/report.html').toString('utf8'); assert.match(html, /<html lang='ru'>/);
assert.doesNotMatch(html, /<script|<iframe|<img|https?:\/\/|src=/i);
for (const r of result.author_groups) assert.ok(html.includes("id='группа-" + r.group_id + "'"));
assert.match(html, /Новых научных прогнозов — 0/);
const receipt = { run_id: result.run_id, verifier_sha256: hash(readFileSync(import.meta.path)),
  canonicalizer_sha256: hash(readFileSync(resolve(import.meta.dir, 'raw_json_fingerprint.mjs'))),
  report_sha256: hash(read('review-v2/report.html')), groups: 676, profiles: 3, checked_test_uses: derivedTests,
  checked_source_refs: refs, tests_passed: v.tests_passed, scientific_success: false,
  graph_advantage_demonstrated: false, visual_inspection: false };
const path = resolve(root, 'review-v2/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(path, bytes, { flag: 'wx' }); } catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
