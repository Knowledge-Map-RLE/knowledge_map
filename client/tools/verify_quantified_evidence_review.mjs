// Проверка русского автономного отчёта и сохранности числовых операндов и составных блоков.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/quantified-evidence-operations-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p).toString('utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const v = json('review-v1/verification.json');
for (const [file, digest] of Object.entries(v.files)) assert.equal(hash(read(`review-v1/${file}`)), digest);
for (const [file, digest] of Object.entries(v.inputs)) assert.equal(hash(read(file)), digest);
assert.equal(hash(read('build_review.py')), v.builder_sha256);
assert.equal(hash(read('test-results-v2.xml')), v.tests_sha256);
assert.equal(v.domain_seals_checked, true); assert.equal(v.full_parent_proofs_checked, 60);
assert.equal(v.printed_operands_checked, 180); assert.equal(v.canonical_coverage_checked, 890);
assert.equal(v.without_dependencies_equal, true); assert.equal(v.tests_passed, 87);
const data = json('review-v1/data.json');
assert.equal(data.sources, 10); assert.equal(data.canonical_blocks, 890);
assert.equal(data.printed_comparisons, 180); assert.equal(data.interpreted_parents, 60);
assert.equal(data.counts.below, 3); assert.equal(data.counts.not_below, 177);
assert.equal(data.new_empirical_predictions, 0); assert.equal(data.future_results_scored, 0);
assert.equal(data.model_calls, 0); assert.equal(data.target_read, false);
assert.equal(data.scientific_success, false); assert.equal(data.graph_advantage_demonstrated, false);
assert.equal(data.without_dependencies_equal, true);
assert.deepEqual(data.by_source, { PMC6218168: 60 });
const source = json(`runs/${data.run_id}/inputs/predictions.json`);
let operations = 0, below = 0, reportedBounds = 0;
for (const proof of data.proofs) {
  assert.deepEqual(proof.complete_parent, source.semantic_graph.parents[proof.parent].complete_parent);
  assert.equal(proof.parent_logic, proof.complete_parent.semantic_frame.logic);
  assert.equal(proof.new_measurement, false); assert.equal(proof.new_empirical_prediction, false);
  assert.equal(proof.parts_asserted_as_independent_facts, false); assert.equal(proof.graph_dependencies_used, false);
  for (const op of proof.operations) {
    operations++;
    const native = proof.complete_parent.semantic_frame.statements[op.statement_position];
    assert.equal(native.statement_id, op.statement_id);
    assert.equal(native.qualifiers.attributes[op.operand_positions.p].value, op.operation.reported_p);
    assert.equal(native.qualifiers.attributes[op.operand_positions.alpha].value, op.operation.reported_alpha);
    assert.equal(op.operation.unrounded_p_decision_established, false);
    assert.equal(op.operation.biological_effect_or_absence_established, false);
    // Число и явно напечатанная граница сохраняют разные значения.
    const operand = /^(<=|>=|<|>|≤|≥)?\s*((?:\d+(?:\.\d+)?|\.\d+))$/.exec(op.operation.reported_p);
    assert.ok(operand);
    assert.match(op.operation.reported_alpha, /^(?:\d+(?:\.\d+)?|\.\d+)$/);
    const relation = ({ '≤': '<=', '≥': '>=' })[operand[1]] || operand[1], value = Number(operand[2]), alpha = Number(op.operation.reported_alpha);
    let expected;
    if (!relation) expected = value < alpha ? 'below' : 'not_below';
    else if (relation === '<' || relation === '<=') expected = value < alpha || (value === alpha && relation === '<') ? 'below' : 'undetermined';
    else expected = value >= alpha ? 'not_below' : 'undetermined';
    if (relation) reportedBounds++;
    assert.equal(op.operation.decision, expected); if (expected === 'below') below++;
    for (const e of op.evidence) {
      assert.equal(Array.from(e.text).length, e.end - e.start);
      assert.equal(hash(Buffer.from(e.text)), e.sha256);
      assert.deepEqual(source.semantic_graph.source_units[e.id], e);
    }
  }
}
assert.equal(operations, 180); assert.equal(below, 3);
assert.equal(data.coverage.length, 890);
assert.equal(data.coverage.reduce((sum, r) => sum + r.all_statement_decisions.length, 0), data.statement_count);
assert.deepEqual(data.below.map(r => r.statement_id).sort(), ['K105S1', 'K84S1', 'K84S2']);
const html = read('review-v1/report.html').toString('utf8');
assert.match(html, /<html lang="ru">/);
assert.match(html, /Новых эмпирических прогнозов: 0/);
assert.match(html, /Это не три новых предсказания/);
assert.equal([...html.matchAll(/<details>/g)].length, 60);
assert.doesNotMatch(html, /<(?:script|iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
const receipt = { проверка: 'успешна', знаний: 890, частей: data.statement_count, полных_родителей: 60,
  сравнений: 180, ниже_порога: 3, новых_эмпирических_прогнозов: 0, тестов: 87,
  явно_напечатанных_границ: reportedBounds,
  контроль_без_зависимостей_совпадает: true, визуальная_проверка: false,
  файл_проверки_sha256: hash(readFileSync(import.meta.path)), отчёт_sha256: hash(read('review-v1/report.html')) };
const target = resolve(root, 'review-v1/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(target, bytes, { flag: 'wx' }); }
catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(target), bytes); }
console.log(JSON.stringify(receipt));
