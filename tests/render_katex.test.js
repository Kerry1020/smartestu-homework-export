'use strict';
const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const { spawnSync } = require('child_process');
const r = require('../scripts/render_katex.js');

const SCRIPT = path.join(__dirname, '..', 'scripts', 'render_katex.js');

test('renders raw TeX containing < without parse errors', () => {
  const res = r.renderRequest({ formulas: [{ tex: 'P\\{1<X<3\\}', display: false },
                                            { tex: '\\sum_i x_i', display: true }] });
  assert.strictEqual(res.html.length, 2);
  assert.match(res.html[0], /class="katex"/);
  assert.doesNotMatch(res.html[0], /katex-error/);
  assert.match(res.html[1], /katex-display/);
  assert.match(res.css, /url\(file:\/\//);
});

test('invalid TeX yields an error span, not an exception', () => {
  const res = r.renderRequest({ formulas: [{ tex: '\\frac{', display: false }] });
  assert.match(res.html[0], /katex-error/);
});

test('validates input', () => {
  assert.throws(() => r.validateRequest({}), /formulas/);
  assert.throws(() => r.validateRequest({ formulas: [{ tex: 1 }] }), /tex must be a string/);
});

test('CLI: stdin JSON in, JSON out; exit codes', () => {
  const ok = spawnSync('node', [SCRIPT], { input: JSON.stringify({ formulas: [{ tex: 'x^2' }] }) });
  assert.strictEqual(ok.status, 0);
  assert.strictEqual(JSON.parse(ok.stdout).html.length, 1);
  assert.strictEqual(spawnSync('node', [SCRIPT], { input: 'not json' }).status, 2);
  assert.strictEqual(spawnSync('node', [SCRIPT, '--bogus']).status, 2);
  assert.strictEqual(spawnSync('node', [SCRIPT, '--help']).status, 0);
});
