// Независимая проверка условий, получательской группы, источников и фиксированного бюджета.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/analogy-protocol-reconciliation-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p).toString('utf8'));
const hash = b => createHash('sha256').update(b).digest('hex');
const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
const fp = v => hash(Buffer.from(JSON.stringify(canonical(v))));
// Лексемы чисел сохраняются: исходный Python 1.0 не заменяется JavaScript 1.
function rawFingerprint(bytes, collectProofs = false) {
  const s = bytes.toString('utf8'); let pos = 0; const proofs = new Map();
  const space = () => { while (pos < s.length && /\s/.test(s[pos])) pos++; };
  function string() {
    const start = pos++; let escaped = false;
    while (pos < s.length) { const ch = s[pos++];
      if (ch === '"' && !escaped) return JSON.stringify(JSON.parse(s.slice(start, pos)));
      if (ch === '\\' && !escaped) escaped = true; else escaped = false;
    } throw Error('Незавершённая JSON-строка');
  }
  function value(path) {
    space(); let out;
    if (s[pos] === '"') out = string();
    else if (s[pos] === '[') {
      pos++; space(); const rows = [];
      if (s[pos] !== ']') while (true) { rows.push(value([...path, rows.length])); space(); if (s[pos] !== ',') break; pos++; }
      assert.equal(s[pos++], ']'); out = '[' + rows.join(',') + ']';
    } else if (s[pos] === '{') {
      pos++; space(); const rows = [];
      if (s[pos] !== '}') while (true) {
        space(); const key = string(); space(); assert.equal(s[pos++], ':');
        rows.push([JSON.parse(key), key, value([...path, JSON.parse(key)])]); space(); if (s[pos] !== ',') break; pos++;
      }
      assert.equal(s[pos++], '}'); rows.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
      out = '{' + rows.map(r => r[1] + ':' + r[2]).join(',') + '}';
    } else {
      const regex = /true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y; regex.lastIndex = pos;
      const match = regex.exec(s); assert.ok(match, 'Недопустимый токен'); pos += match[0].length; out = match[0];
    }
    if (collectProofs && path.length === 2 && path[0] === 'proof_registry') proofs.set(path[1], hash(Buffer.from(out)));
    return out;
  }
  const result = value([]); space(); assert.equal(pos, s.length); return { hash: hash(Buffer.from(result)), proofs };
}
const verify = json('review-v1/verification.json');
for (const [p, h] of Object.entries(verify.files)) assert.equal(hash(read('review-v1/' + p)), h);
for (const [p, h] of Object.entries(verify.inputs)) assert.equal(hash(read(p)), h);
assert.equal(hash(read('build_review.py')), verify.builder_sha256);
for (const t of verify.tests) assert.equal(hash(read(t.name)), t.sha256);
assert.deepEqual(verify.tests.map(t => t.passed), [133, 25]);
const folder = 'runs/' + verify.run_id;
const r = json(folder + '/predictions.json'), f = json(folder + '/inputs/forecast/predictions.json');
const args = json(folder + '/inputs/arguments.json'), graph = args.semantic_graph;
const audit = json(folder + '/inputs/annotation.json');
assert.equal(rawFingerprint(read(folder + '/predictions.json')).hash, json(folder + '/seal.json').prediction_sha256);
assert.equal(fp(r.binding), r.run_id);
const fh = rawFingerprint(read(folder + '/inputs/forecast/predictions.json'), true);
assert.equal(fh.hash, r.binding.forecast_sha256);
assert.equal(fh.hash, json(folder + '/inputs/forecast/seal.json').prediction_sha256);
assert.equal(rawFingerprint(read(folder + '/inputs/arguments.json')).hash, r.binding.arguments_artifact_sha256);
assert.equal(r.binding.arguments_artifact_sha256, f.binding.arguments_artifact_sha256);
assert.equal(fp(audit), r.binding.annotation_sha256);
assert.equal(fp(audit), fp(r.context_annotation));
assert.equal(f.model_calls, 0); assert.equal(f.target_read, false); assert.equal(f.question, null);
assert.equal(r.model_calls, 0); assert.equal(r.target_read, false); assert.equal(r.new_confirmed_predictions, 0);
assert.equal(r.scientific_success, false); assert.equal(r.graph_advantage_demonstrated, false);
assert.equal(verify.without_visible_dependencies_equal, true);
assert.equal(verify.complete_result_reproduced, true);
const rows = new Map(audit.contexts.map(c => [c.projection_proof_id, c]));
const designs = new Map(audit.recipient_designs.map(c => [c.projection_proof_id, c]));
const used = new Set(f.all_candidates.flatMap(c => c.witnesses.flatMap(w => w.premises.map(p => p.projection_proof_id))));
assert.deepEqual([...used].sort(), [...rows.keys()].sort()); assert.equal(rows.size, 33);
let quotationChecks = 0;
for (const [key, row] of rows) {
  const proof = f.proof_registry[key];
  assert.deepEqual(row.parent_key, proof.parent_key); assert.equal(row.native_statement_id, proof.native_statement_id);
  assert.equal(row.projection_proof_sha256, fh.proofs.get(key));
  for (const dimension of Object.values(row.dimensions)) {
    if (dimension.status === 'unknown') { assert.equal(dimension.value, null); assert.deepEqual(dimension.evidence, []); continue; }
    assert.equal(dimension.status, 'source_stated'); assert.ok(dimension.evidence.length);
    for (const ref of dimension.evidence) {
      const unit = graph.source_units[ref.source_unit]; assert.ok(unit);
      assert.equal(unit.article_id, row.parent_key[0]); assert.equal(unit.source_sha256, ref.source_sha256);
      assert.equal(hash(Buffer.from(unit.text)), ref.unit_sha256); assert.equal(unit.sha256, ref.unit_sha256);
      assert.equal([...unit.text].length, unit.end - unit.start); assert.ok(ref.quote && unit.text.includes(ref.quote)); quotationChecks++;
    }
  }
}
const candidateById = new Map(f.all_candidates.map(c => [c.id, c]));
assert.equal(candidateById.size, r.candidate_reviews.length); assert.equal(r.candidate_reviews.length, 35);
let witnessCount = 0, protocolCount = 0;
for (const review of r.candidate_reviews) {
  const candidate = candidateById.get(review.candidate_id); assert.ok(candidate);
  assert.deepEqual(review.original_frame, candidate.frame); assert.equal(review.witness_reviews.length, candidate.witnesses.length);
  for (let i = 0; i < review.witness_reviews.length; i++) {
    witnessCount++; const w = review.witness_reviews[i], original = candidate.witnesses[i];
    assert.deepEqual(w.premise_context_keys, original.premises.map(p => p.projection_proof_id));
    const [a, b, q] = w.premise_context_keys.map(k => rows.get(k).dimensions);
    const mixed = ['species', 'disease_model', 'challenge_anchor'].some(k =>
      new Set([a[k].value, b[k].value, q[k].value].map(fp)).size > 1);
    if (mixed) { assert.equal(w.status, 'blocked_context_mixture'); assert.equal(w.proposed_protocol, null); continue; }
    assert.equal(w.status, 'testable_design_hypothesis_not_confirmed'); protocolCount++;
    const plan = w.proposed_protocol, design = designs.get(w.premise_context_keys[1]).design;
    assert.deepEqual(plan.recipe, b.recipe.value); assert.deepEqual(plan.recipe, design.recipe);
    assert.deepEqual(plan.target_mechanism, b.target_mechanism.value);
    assert.equal(plan.target_mechanism.target_species, plan.target_mechanism.expressed_receptor_species);
    assert.equal(plan.target_mechanism.mouse_TNFR1_crossreactivity, false);
    assert.equal(plan.observed_recipient_response, false); assert.equal(plan.condition_on_predicted_response, false);
    assert.equal(plan.is_original_unique_dose_established, false); assert.equal(plan.scope_equivalence_established, false);
    assert.equal(plan.demographic_registration_required, true); assert.equal(plan.population.age, null); assert.equal(plan.population.sex, null);
    assert.deepEqual(plan.population.genotype, b.genotype.value); assert.equal(plan.population.species, b.species.value);
    assert.deepEqual(plan.measurement.assessment, q.assessment.value); assert.deepEqual(plan.measurement.tissue, q.tissue.value);
    assert.equal(plan.measurement.assessment.elapsed, 6); assert.equal(plan.measurement.assessment.unit, 'hour');
    assert.equal(plan.measurement.assessment_from_donor_is_design_choice, true);
    assert.deepEqual(plan.measurement.endpoint_roles, original.premises[2].frame.statements[0].roles.filter(role =>
      !['intervention', 'exposure', 'factor', 'population', 'cohort', 'tissue', 'model', 'challenge', 'phase', 'species', 'genotype'].includes(role.role)));
    assert.equal(plan.source_conditions_not_declared_recipient_facts, true);
  }
}
assert.equal(witnessCount, 57); assert.equal(protocolCount, 13);
assert.deepEqual(r.original_budget_slots.map(c => c.candidate_id), f.ranked_candidates.map(c => c.id));
assert.equal(r.original_budget_slots.filter(c => c.status === 'testable_design_hypothesis_not_confirmed').length, 9);
assert.equal(r.outside_budget_promoted, false); assert.equal(r.original_budget_preserved, true);
const html = read('review-v1/report.html').toString('utf8');
assert.match(html, /<html lang='ru'>/); assert.match(html, /Подтверждённых новых прогнозов — 0/);
assert.match(html, /Четыре проекта вне бюджета/); assert.doesNotMatch(html, /<script|<iframe|<img|https?:\/\/|src=/i);
for (const c of r.candidate_reviews) assert.ok(html.includes("id='кандидат-" + c.candidate_id + "'"));
const receipt = { verifier_sha256: hash(readFileSync(import.meta.path)), report_sha256: hash(read('review-v1/report.html')),
  run_id: r.run_id, quotation_checks: quotationChecks, contexts: rows.size, candidates: 35, witness_groups: witnessCount,
  proposed_witnesses: protocolCount, within_budget_proposals: 9, scientific_success: false,
  graph_advantage_demonstrated: false, visual_inspection: false, expert_validated: false };
const path = resolve(root, 'review-v1/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(path, bytes, { flag: 'wx' }); } catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
