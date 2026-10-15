// Независимая проверка источникового отсева, координат Unicode и неизменного бюджета.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/analogy-protocol-reconciliation-v1');
const read = path => readFileSync(resolve(root, path));
const json = path => JSON.parse(read(path));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
const fp = v => hash(Buffer.from(JSON.stringify(canonical(v))));
// Точная лексема 1.0 сохраняется при проверке Python-печатей родительского артефакта.
function rawFingerprint(bytes) {
  const text = bytes.toString('utf8'); let i = 0;
  const space = () => { while (i < text.length && /\s/.test(text[i])) i++; };
  function string() {
    const begin = i++; let escaped = false;
    while (i < text.length) {
      const ch = text[i++];
      if (ch === '"' && !escaped) return JSON.stringify(JSON.parse(text.slice(begin, i)));
      if (ch === '\\' && !escaped) escaped = true; else escaped = false;
    }
    throw Error('Незавершённая строка JSON');
  }
  function value() {
    space();
    if (text[i] === '"') return string();
    if (text[i] === '[') {
      i++; space(); const rows = [];
      if (text[i] !== ']') while (true) { rows.push(value()); space(); if (text[i] !== ',') break; i++; }
      assert.equal(text[i++], ']'); return '[' + rows.join(',') + ']';
    }
    if (text[i] === '{') {
      i++; space(); const rows = [];
      if (text[i] !== '}') while (true) {
        space(); const key = string(); space(); assert.equal(text[i++], ':');
        rows.push([JSON.parse(key), key, value()]); space(); if (text[i] !== ',') break; i++;
      }
      assert.equal(text[i++], '}'); rows.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
      return '{' + rows.map(r => r[1] + ':' + r[2]).join(',') + '}';
    }
    const regex = /true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y; regex.lastIndex = i;
    const match = regex.exec(text); assert.ok(match); i += match[0].length; return match[0];
  }
  const out = value(); space(); assert.equal(i, text.length); return hash(Buffer.from(out));
}

const verification = json('method-review-v1/verification.json');
for (const [p, h] of Object.entries(verification.inputs)) assert.equal(hash(read(p)), h);
for (const [p, h] of Object.entries(verification.files)) assert.equal(hash(read('method-review-v1/' + p)), h);
assert.equal(hash(read('build_method_review.py')), verification.builder_sha256);
assert.equal(verification.tests_passed, 65);
const folder = 'method-screen-runs/' + verification.run_id;
const result = json(folder + '/predictions.json'), seal = json(folder + '/seal.json');
assert.equal(rawFingerprint(read(folder + '/predictions.json')), seal.prediction_sha256);
assert.equal(fp(result.binding), result.run_id);
const source = json(folder + '/inputs/source_protocols/predictions.json');
const registration = json(folder + '/inputs/protocol.json');
assert.equal(rawFingerprint(read(folder + '/inputs/source_protocols/predictions.json')), registration.source_artifact_sha256);
assert.equal(fp(registration), result.binding.registration_sha256);
assert.deepEqual(registration.fixed_original_slots, source.original_budget_slots.map(r => r.candidate_id));
assert.deepEqual(result.original_slots, registration.fixed_original_slots); assert.equal(result.original_slots.length, 20);
const plan = json(folder + '/inputs/method-acquisition-plan-v2.json');
const annotation = json(folder + '/inputs/annotation.json'), disclosure = json(folder + '/inputs/disclosure.json');
assert.equal(fp(plan), result.binding.method_plan_sha256); assert.equal(fp(annotation), result.binding.annotation_sha256);
assert.equal(fp(disclosure), result.binding.disclosure_sha256);
const packets = {};
let quotationChecks = 0;
for (const control of annotation.controls) {
  const path = folder + '/inputs/methods/' + control.pmcid;
  const packet = json(path + '/packet.json'); packets[control.pmcid] = packet;
  assert.equal(hash(read(path + '/article.xml')), packet.raw_xml_sha256);
  assert.equal(packet.raw_xml_sha256, control.raw_xml_sha256); assert.equal(fp(packet), control.packet_sha256);
  assert.equal(packet.training_source, false); assert.equal(packet.generator_access, false);
  assert.equal(packet.results_section_included, false); assert.equal(packet.version, 'controlled-article-method-packet-2');
  const s = packet.method_source; assert.equal(hash(Buffer.from(s.text)), s.sha256);
  assert.equal(s.coordinate_space, 'selected_method_text'); assert.equal(s.offset_encoding, 'unicode_codepoints');
  assert.equal(s.units.map(u => u.text).join('\n\n'), s.text);
  for (const u of s.units) {
    assert.equal([...s.text].slice(u.start, u.end).join(''), u.text); assert.equal(hash(Buffer.from(u.text)), u.sha256);
  }
  for (const fact of Object.values(control.dimensions)) {
    if (fact.status === 'not_assessed') { assert.equal(fact.value, null); assert.deepEqual(fact.evidence, []); continue; }
    assert.equal(fact.status, 'codex_source_license');
    for (const ref of fact.evidence) {
      const unit = s.units.find(u => u.id === ref.unit_id); assert.ok(unit);
      assert.equal(unit.sha256, ref.unit_sha256); assert.equal([...s.text].slice(ref.start, ref.end).join(''), ref.quote);
      assert.ok(ref.start >= unit.start && ref.end <= unit.end); quotationChecks++;
    }
  }
}
assert.equal(fp(packets), result.binding.packets_sha256);
assert.equal(result.comparisons.length, 63); assert.equal(new Set(result.comparisons.map(c => c.candidate_id + ':' + c.pmcid)).size, 63);
const counts = {};
for (const row of result.comparisons) {
  assert.ok(registration.eligible_draft_ids.includes(row.candidate_id));
  const control = annotation.controls.find(c => c.pmcid === row.pmcid); const statuses = [];
  const designs = registration.source_protocols[row.candidate_id]; assert.equal(designs.length, row.design_alternatives.length);
  for (let i = 0; i < designs.length; i++) {
    const design = designs[i], expected = { species: design.population.species, disease_model: design.challenge.id };
    const unknown = [], different = [];
    for (const d of ['species', 'disease_model']) {
      if (control.dimensions[d].status === 'not_assessed') unknown.push(d);
      else if (expected[d] !== control.dimensions[d].value) different.push(d);
    }
    const status = different.length ? 'incompatible_shared_study_scope' : unknown.length
      ? 'insufficient_shared_study_scope' : 'shared_scope_candidate_requires_full_protocol_audit';
    statuses.push(status); assert.equal(row.design_alternatives[i].status, status);
    assert.deepEqual(row.design_alternatives[i].differences.map(r => r.dimension), different);
    assert.deepEqual(row.design_alternatives[i].unknown_dimensions, unknown);
  }
  const status = statuses.includes('shared_scope_candidate_requires_full_protocol_audit') ? 'shared_scope_candidate_requires_full_protocol_audit'
    : statuses.includes('insufficient_shared_study_scope') ? 'insufficient_shared_study_scope' : 'incompatible_shared_study_scope';
  assert.equal(row.status, status); counts[status] = (counts[status] || 0) + 1;
}
assert.deepEqual(counts, result.counts); assert.deepEqual(counts, { incompatible_shared_study_scope: 54, insufficient_shared_study_scope: 9 });
assert.equal(disclosure.controls.filter(r => r.partial_outcome_disclosure).length, 1);
assert.equal(disclosure.forecasts_changed, false); assert.equal(disclosure.results_scored, 0);
assert.equal(result.model_calls, 0); assert.equal(result.future_results_scored, 0); assert.equal(result.new_confirmed_predictions, 0);
assert.equal(result.accuracy, null); assert.equal(result.scientific_success, false); assert.equal(result.graph_advantage_demonstrated, false);
const html = read('method-review-v1/report.html').toString('utf8');
assert.match(html, /<html lang='ru'>/); assert.match(html, /Подтверждённых новых прогнозов — 0/);
assert.doesNotMatch(html, /<script|<iframe|<img|https?:\/\/|src=/i);
for (const c of annotation.controls) assert.ok(html.includes("id='контроль-" + c.pmcid + "'"));
const receipt = { run_id: result.run_id, verifier_sha256: hash(readFileSync(import.meta.path)),
  report_sha256: hash(read('method-review-v1/report.html')), controls: 7, comparisons: 63, quotation_checks: quotationChecks,
  outcomes_scored: 0, scientific_success: false, graph_advantage_demonstrated: false, visual_inspection: false };
const path = resolve(root, 'method-review-v1/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(path, bytes, { flag: 'wx' }); } catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
