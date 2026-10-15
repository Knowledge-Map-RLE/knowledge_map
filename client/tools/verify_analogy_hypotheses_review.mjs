// Проверяем неизменность посылок и автономный русский отчёт по направленным гипотезам.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root = path.resolve(process.argv[2]);
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
const data = read(path.join(root, 'data.json'));
const v = data.verification;
const folder = path.resolve(root, '../runs', v.run_id);
const result = read(path.join(folder, 'predictions.json'));
const baseline = read(path.join(folder, 'forecast.json'));
const audit = read(path.join(folder, 'protocol-audit.json'));
assert.equal(v.hypotheses, 4); assert.equal(v.python_tests_passed, 139);
assert.equal(v.confirmed_predictions, 0); assert.equal(v.future_results_scored, 0);
assert.equal(v.accuracy, null); assert.equal(v.graph_advantage_demonstrated, false);
assert.equal(result.canonical_blocks_searched, 812); assert.equal(result.native_statements_searched, 1593);
assert.deepEqual(result.hypotheses, data.hypotheses);
assert.equal(result.ablation.same_proposal_ids, true);
assert.equal(hash(fs.readFileSync(path.resolve(root, '../test-results-v1.xml'))), v.test_results_sha256);
const html = fs.readFileSync(path.join(root, 'report.html'), 'utf8');
assert.ok(html.includes('lang="ru"')); assert.ok(!/<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i.test(html));
for (const h of result.hypotheses) {
  const c = baseline.transport_tasks.find(c => c.id === h.analogy_candidate_id);
  assert.ok(c); assert.ok(html.includes(`data-hypothesis="${h.id}"`));
  assert.deepEqual(h.unmodified_analogy_frame, c.proposed_qualitative_frame);
  assert.deepEqual(h.witnesses, c.witnesses); assert.deepEqual(h.transport_obligations, c.transport_obligations);
  const review = audit.candidate_reviews.find(r => r.candidate_id === c.id);
  assert.deepEqual(h.unknown_dimensions, review.unresolved);
  assert.equal(h.knowledge_status, 'hypothesis'); assert.equal(h.confirmed, false);
  assert.equal(h.probability, null); assert.equal(h.predicted_p_value, null);
  assert.equal(h.effect_size, null); assert.equal(h.logical_entailment, false);
  assert.ok(h.frame.statements[0].scope.modality.includes('hypothesis'));
}
for (const [name, digest] of Object.entries(result.binding.implementation)) assert.equal(hash(fs.readFileSync(path.join(folder, 'implementation', name))), digest);
const receipt = {hypotheses: 4, confirmed: 0, complete_witnesses: true, unknown_context_retained: true,
  python_tests: 139, report_sha256: hash(html), external_resources: 0, visual_inspection: false};
const output = path.join(root, 'html-verification.json'); const raw = JSON.stringify(receipt, null, 2) + '\n';
if (fs.existsSync(output)) assert.equal(fs.readFileSync(output, 'utf8'), raw); else fs.writeFileSync(output, raw, {flag: 'wx'});
console.log(JSON.stringify(receipt));
