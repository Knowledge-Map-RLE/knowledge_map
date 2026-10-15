// Канонизация сохраняет числовые лексемы Python и лексикографический порядок ключей.
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

export function rawJsonFingerprint(bytes) {
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
      i++; space(); const rows = []; const keys = new Set();
      if (text[i] !== '}') while (true) {
        space(); const key = string(), name = JSON.parse(key); space(); assert.equal(text[i++], ':');
        assert.ok(!keys.has(name), 'Дублирующий ключ JSON'); keys.add(name);
        rows.push([name, key, value()]); space(); if (text[i] !== ',') break; i++;
      }
      assert.equal(text[i++], '}'); rows.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
      return '{' + rows.map(r => r[1] + ':' + r[2]).join(',') + '}';
    }
    const regex = /true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y; regex.lastIndex = i;
    const match = regex.exec(text); assert.ok(match, 'Недопустимый токен JSON'); i += match[0].length; return match[0];
  }
  const out = value(); space(); assert.equal(i, text.length);
  return createHash('sha256').update(out).digest('hex');
}
