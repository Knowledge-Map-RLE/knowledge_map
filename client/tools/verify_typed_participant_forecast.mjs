// Независимое повторение подстановок: именованные участники не стирают ограничения.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { rawJsonFingerprint } from './raw_json_fingerprint.mjs';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/typed-participants-v1');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const read = path => readFileSync(path);
const json = path => JSON.parse(read(path));
function rawField(bytes, field) {
  const s = bytes.toString(), match = new RegExp('^  "' + field + '":\\s*', 'm').exec(s); assert.ok(match);
  const start = match.index + match[0].length; let depth = 0, quoted = false, escaped = false;
  for (let i = start; i < s.length; i++) {
    const c = s[i];
    if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; continue; }
    if (c === '"') { quoted = true; continue; }
    if (c === '{' || c === '[') depth++; else if (c === '}' || c === ']') depth--;
    if (!depth) return Buffer.from(s.slice(start, i + 1));
  }
  assert.fail('Незавершённое поле JSON');
}
function seal(folder) {
  const bytes = read(resolve(folder, 'predictions.json')), data = JSON.parse(bytes), proof = json(resolve(folder, 'seal.json'));
  assert.equal(rawJsonFingerprint(bytes), proof.prediction_sha256);
  assert.equal(rawJsonFingerprint(rawField(bytes, 'binding')), data.run_id);
  for (const [file, digest] of Object.entries(data.binding.implementation))
    assert.equal(hash(read(resolve(folder, 'implementation', file))), digest);
  assert.equal(data.model_calls, 0); return { bytes, data };
}
const review = resolve(root, 'review-v2'), receipt = json(resolve(review, 'verification.json'));
for (const [file, digest] of Object.entries(receipt.files)) assert.equal(hash(read(resolve(review, file))), digest);
assert.equal(hash(read(receipt.tests_path)), receipt.tests_sha256);
assert.equal(hash(read(resolve(import.meta.dir, '../../api/tools/render_typed_participant_forecast.py'))), receipt.builder_sha256);
assert.equal(hash(read(resolve(import.meta.dir, '../../api/tools/render_template_barrier_audit.py'))), receipt.render_helper_sha256);
const tests = new JSDOM(read(receipt.tests_path).toString(), { contentType: 'text/xml' }).window.document;
let testCount = 0;
for (const s of tests.querySelectorAll('testsuite')) {
  testCount += Number(s.getAttribute('tests'));
  for (const k of ['errors', 'failures', 'skipped']) assert.equal(Number(s.getAttribute(k)), 0);
}
assert.equal(testCount, 109); assert.equal(testCount, receipt.tests_passed);
const current = seal(receipt.run_path), source = seal(receipt.source_path), data = current.data, frozen = source.data;
assert.equal(rawJsonFingerprint(source.bytes), data.binding.source_sha256);
assert.deepEqual(data.binding.map_hashes, frozen.binding.map_hashes);
assert.equal(hash(read(resolve(receipt.source_path, 'origin-audit.json'))), frozen.binding.metadata.input_audit_file_sha256['origin-audit']);
assert.equal(rawJsonFingerprint(read(resolve(receipt.source_path, 'origin-audit.json'))), data.binding.origin_audit_sha256);
assert.equal(data.version, 'whole-map-typed-participant-forecast-3');
const index = json(resolve(receipt.source_path, 'inputs-manifest.json'));
let canonical = 0, statements = 0, provenance = 0, sources = 0;
const native = new Map();
for (const e of index.sources) {
  const bytes = read(resolve(receipt.source_path, e.map_path)); assert.equal(hash(bytes), e.map_file_sha256);
  const m = JSON.parse(bytes); sources++; assert.equal(m.graph.schema_version, 6);
  assert.equal(hash(Buffer.from(m.source.text)), m.source.sha256);
  assert.notEqual(m.source.sha256, 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8');
  if (e.coverage_path) assert.equal(hash(read(resolve(receipt.source_path, e.coverage_path))), e.coverage_sha256);
  const nodes = new Map(m.graph.nodes.map(n => [n.id, n])); assert.equal(nodes.size, m.graph.nodes.length);
  const degree = new Map([...nodes.keys()].map(k => [k, 0])), adjacent = new Map([...nodes.keys()].map(k => [k, []]));
  for (const edge of m.graph.edges) {
    assert.ok(nodes.has(edge.source) && nodes.has(edge.target)); degree.set(edge.target, degree.get(edge.target) + 1); adjacent.get(edge.source).push(edge.target);
  }
  const queue = [...nodes.keys()].filter(k => degree.get(k) === 0); let visited = 0;
  while (queue.length) { const k = queue.pop(); visited++; for (const t of adjacent.get(k)) { degree.set(t, degree.get(t) - 1); if (!degree.get(t)) queue.push(t); } }
  assert.equal(visited, nodes.size);
  const text = Array.from(m.source.text), units = new Map(m.source.units.map(u => [u.id, u]));
  for (const k of m.graph.knowledge) {
    canonical++; native.set(JSON.stringify([m.article_id, k.knowledge_id]), k);
    for (const s of k.semantic_frame.statements) {
      statements++;
      for (const id of s.provenance.unit_ids) { const u = units.get(id); assert.ok(u); assert.equal(text.slice(u.start, u.end).join(''), u.text); provenance++; }
    }
  }
}
assert.equal(sources, 11); assert.equal(canonical, 943); assert.equal(statements, 1897);
assert.equal(data.parent_coverage.length, canonical); assert.equal(data.licensed_parts, 910);
const views = new Map(frozen.part_views.map(v => [JSON.stringify(v.key), v])); assert.equal(views.size, 910);
const coverage = new Map(data.parent_coverage.map(c => [JSON.stringify(c.key), c.parts]));
let parts = 0, digitRoles = [];
for (const [key, v] of views) {
  assert.deepEqual(v.projection_proof.complete_native_knowledge, native.get(JSON.stringify(v.native_key)));
  assert.ok(coverage.get(JSON.stringify(v.native_key)).some(k => JSON.stringify(k) === key)); parts++;
  for (const r of v.frame.statements[0].roles)
    if (r.reference_kind === 'concept' && typeof r.value === 'string' && /\d/.test(r.value))
      digitRoles.push({ part_key: v.key, native_key: v.native_key, role: r.role, value: r.value,
        pure_numeric_literal: /^[+−-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+−-]?\d+)?$/.test(r.value.trim()) });
}
assert.equal(parts, 910); assert.deepEqual(digitRoles, data.digit_participants); assert.equal(digitRoles.length, 973);
// Все реальные подстановки воспроизводятся независимо от Python-генератора.
let replayed = 0;
function compare(pattern, actual, bindings, article, allowNew = true) {
  assert.equal(pattern.kind, actual.kind); assert.equal(pattern.action_status, actual.action_status); assert.equal(pattern.logic, actual.logic);
  for (let i = 0; i < pattern.statements.length; i++) {
    const p = pattern.statements[i], a = actual.statements[i];
    assert.equal(p.predicate, a.predicate); assert.equal(p.negated, a.negated);
    const roles = [...a.roles].sort((x, y) => x.role.localeCompare(y.role, 'en'));
    assert.equal(p.roles.length, roles.length);
    for (let j = 0; j < p.roles.length; j++) {
      const r = p.roles[j], observed = roles[j]; assert.equal(r.role, observed.role); assert.equal(r.reference_kind, observed.reference_kind);
      if ('variable' in r.value) {
        assert.ok(allowNew || bindings.has(r.value.variable), 'Заключение содержит непривязанного участника');
        if (bindings.has(r.value.variable)) assert.deepEqual(bindings.get(r.value.variable), observed.value);
        else bindings.set(r.value.variable, observed.value);
      } else assert.deepEqual(r.value.constant, observed.value);
    }
    const scope = structuredClone(p.scope);
    if (scope.study_group?.study_variable) scope.study_group = article;
    scope.conditions = scope.conditions.map(c => c?.source_local_report ? 'source-local report: ' + article : c).sort();
    assert.deepEqual(scope, { ...a.scope, conditions: [...a.scope.conditions].sort() });
    const attrs = structuredClone(p.attributes);
    assert.equal(attrs.length, a.attributes.length);
    for (let j = 0; j < attrs.length; j++) {
      const r = attrs[j], observed = a.attributes[j];
      if (r.value && typeof r.value === 'object' && 'protocol_variable' in r.value) {
        assert.equal(r.name, observed.name); assert.equal(r.unit, observed.unit);
        const name = r.value.protocol_variable;
        assert.ok(allowNew || bindings.has(name), 'Число заключения не связано с протоколом');
        if (bindings.has(name)) assert.deepEqual(bindings.get(name), observed.value); else bindings.set(name, observed.value);
        r.value = bindings.get(name);
      }
    }
    assert.deepEqual(attrs, a.attributes);
    if ('attribute_types' in p) assert.deepEqual(p.attribute_types, a.attribute_types);
  }
}
for (const [policy, modes] of Object.entries(data.policies)) {
  for (const [mode, row] of Object.entries(modes)) {
    assert.equal(row.predictions.length, 0);
    if (!row.learning) continue;
    assert.equal(row.rules.length, 0); assert.equal(row.guard_barriers.length, 0);
    if (policy === 'legacy_digits_constant') {
      assert.deepEqual(row.learning, frozen.learning_by_mode[mode].learning);
      assert.deepEqual(row.rules, frozen.learning_by_mode[mode].primary_supported_rules);
      assert.equal(data.baseline_learning_reproduced[mode], true);
    }
    for (const rule of [...row.rules, ...row.learning.unsupported_rules]) {
      for (const e of rule.examples) {
        const bindings = new Map();
        for (let i = 0; i < e.body.length; i++) {
          const v = views.get(JSON.stringify(e.body[i])); assert.ok(v); compare(rule.body[i], v.frame, bindings, v.key[0]);
        }
        const head = views.get(JSON.stringify(e.head)); assert.ok(head); compare(rule.head, head.frame, bindings, head.key[0], false); replayed++;
      }
    }
  }
}
assert.equal(data.scientific_success, false); assert.equal(data.graph_advantage_demonstrated, false); assert.equal(data.target_read, false);
const doc = new JSDOM(read(resolve(review, 'report.html')).toString()).window.document;
assert.equal(doc.documentElement.lang, 'ru'); assert.equal(doc.querySelectorAll('table').length, 2);
assert.equal(doc.querySelectorAll('[src],link[href],script').length, 0);
assert.match(doc.body.textContent, /Новых прогнозов — 0/);
const proof = { run_id: data.run_id, tests_passed: testCount, sources, canonical_blocks: canonical,
  semantic_statements: statements, licensed_parts: parts, source_provenance_uses: provenance,
  digit_roles: digitRoles.length, replayed_template_examples: replayed, baseline_learning_reproduced: true,
  new_hypotheses: 0, graph_advantage_demonstrated: false, model_calls: 0, visual_review_claimed: false,
  verifier_sha256: hash(read(import.meta.filename)), helper_sha256: hash(read(resolve(import.meta.dir, 'raw_json_fingerprint.mjs'))) };
const destination = resolve(review, 'bun-verification.json'), bytes = Buffer.from(JSON.stringify(proof, null, 2) + '\n');
if (existsSync(destination)) assert.deepEqual(read(destination), bytes); else writeFileSync(destination, bytes, { flag: 'wx' });
console.log(JSON.stringify(proof));
