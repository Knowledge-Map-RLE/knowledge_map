// Проверка полного русского отчёта, вложенных И/ИЛИ-групп и автономных элементов управления.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dir, '../../eval/whole_map_forecast/author-argument-circuits-v1');
const read = p => readFileSync(resolve(root, p));
const json = p => JSON.parse(read(p).toString('utf8'));
const hash = x => createHash('sha256').update(x).digest('hex');
const v = json('review-v1/verification.json');
for (const [name, digest] of Object.entries(v.files)) assert.equal(hash(read(`review-v1/${name}`)), digest);
for (const [name, digest] of Object.entries(v.input_files)) assert.equal(hash(read(name)), digest);
assert.equal(hash(read('build_review.py')), v.builder_sha256);
assert.equal(hash(read('test-results-v2.xml')), v.tests_sha256);
assert.equal(v.tests_passed, 102);
assert.equal(v.all_native_parents_checked, 890);
assert.equal(v.source_transitions_checked, 676);
assert.equal(v.source_maps_checked, 10);
assert.equal(v.domain_seal_validated, true);
assert.equal(v.complete_visible_dag_checked, true);
const d = json('review-v1/data.json'), html = read('review-v1/report.html').toString('utf8');
assert.match(html, /<html lang="ru">/);
assert.match(html, /Новых прогнозов: 0/);
assert.doesNotMatch(html, /<(?:iframe|link)\b|(?:src|href)\s*=\s*["'](?:https?:|\/\/)/i);
assert.equal(d.canonical_blocks, 890); assert.equal(d.visible_occurrences, 890);
assert.equal(d.maximum_depth, 13); assert.equal(d.groups, 676);
assert.equal(d.sources.length, 10); assert.equal(d.transition_evidence_incomplete, 0);
assert.equal(d.new_predictions, 0); assert.equal(d.future_results_scored, 0);
assert.equal(d.scientific_success, false); assert.equal(d.graph_advantage_demonstrated, false);
assert.equal(d.model_calls, 0); assert.equal(d.target_read, false);
assert.deepEqual(d.counts, { has_content_basis_to_review: 537, no_expanded_content_basis: 219, procedure_only_basis: 134 });
assert.deepEqual(d.transition_forms, { state_to_state: 427, action_to_state: 495, state_to_action: 94, action_to_action: 66 });
assert.equal(d.roots.length, Object.keys(d.nodes).length);
for (const r of d.roots) {
  assert.equal(r.depth_truncated, false); assert.equal(r.new_knowledge_or_rule_created, false);
  assert.equal(r.union_of_leaves_is_not_a_joint_premise_group, true);
  assert.equal(d.nodes[r.root].parent, r.parent);
}
for (const g of Object.values(d.argument_groups)) {
  assert.equal(g.connective, 'all_members_required_by_this_author_group');
  assert.equal(g.alternative_groups_are_jointly_required, false);
  assert.equal(g.deductive_rule, false); assert.equal(g.causal_rule, false);
  assert.equal(g.transition_evidence_complete, true);
  for (const e of g.evidence) {
    assert.equal(Array.from(e.text).length, e.end - e.start);
    assert.equal(hash(Buffer.from(e.text)), e.sha256);
  }
}
const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 2);
const embedded = JSON.parse(scripts[0][2]); assert.deepEqual(embedded, d);
assert.doesNotMatch(scripts[1][2], /\b(?:fetch|XMLHttpRequest|WebSocket|eval)\s*\(/);
function element() {
  return { value: '', textContent: '', children: [], listeners: {},
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren(...children) { this.children = children; },
    addEventListener(name, callback) { this.listeners[name] = callback; } };
}
const elements = Object.fromEntries(['data', 'article', 'category', 'choice', 'detail'].map(k => [k, element()]));
elements.data.textContent = scripts[0][2];
const document = { getElementById: id => elements[id], createElement: () => element() };
runInNewContext(scripts[1][2], { document }, { timeout: 5000 });
assert.equal(elements.article.children.length, 11); assert.equal(elements.category.children.length, 4);
assert.equal(elements.choice.children.length, 890);
const text = e => e.textContent + e.children.map(text).join('\n');
for (const rootNode of d.roots) {
  elements.choice.value = rootNode.root; elements.choice.listeners.change();
  const t = text(elements.detail); assert.match(t, /Глубина:/);
  assert.ok(t.includes(d.parents[rootNode.parent].complete_parent.display_text));
  assert.ok(!t.includes('undefined'));
}
elements.article.value = d.sources[0].article_id; elements.article.listeners.change();
assert.equal(elements.choice.children.length, d.sources[0].blocks);
elements.category.value = 'procedure_only_basis'; elements.category.listeners.change();
assert.equal(elements.choice.children.length, d.sources[0].classes.procedure_only_basis);
elements.article.value = ''; elements.category.value = 'has_content_basis_to_review'; elements.category.listeners.change();
const boxes = elements.detail.children.filter(e => e.children.some(c => c.listeners.click));
assert.ok(boxes.length > 0);
const button = boxes[0].children.find(e => e.listeners.click), label = button.textContent;
button.listeners.click(); assert.ok(text(elements.detail).includes(label.split(' · ')[0]));
elements.category.value = 'no-such-category'; elements.category.listeners.change();
assert.equal(elements.choice.children.length, 0); assert.match(text(elements.detail), /цепочек нет/);
const receipt = { проверка: 'успешна', источников: 10, знаний: 890, авторских_групп: 676,
  максимальная_глубина: 13, проверенных_вхождений_интерфейса: 890, прогнозов: 0, тестов: 102,
  визуальная_проверка: false, файл_проверки_sha256: hash(readFileSync(import.meta.path)), отчёт_sha256: hash(read('review-v1/report.html')) };
const path = resolve(root, 'review-v1/html-verification.json'), bytes = Buffer.from(JSON.stringify(receipt, null, 2) + '\n');
try { writeFileSync(path, bytes, { flag: 'wx' }); }
catch (e) { if (e.code !== 'EEXIST') throw e; assert.deepEqual(readFileSync(path), bytes); }
console.log(JSON.stringify(receipt));
