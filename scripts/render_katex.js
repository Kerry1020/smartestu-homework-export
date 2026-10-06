#!/usr/bin/env node
/**
 * Server-side KaTeX formula renderer for smartestu-homework-export.
 *
 * Reads a JSON request on stdin (or --input FILE) and writes a JSON response
 * on stdout (or --output FILE):
 *
 *   request:  {"formulas": [{"tex": "x^2", "display": false}, ...]}
 *   response: {"katexVersion": "0.16.9",
 *              "html": ["<span class=\"katex\">...</span>", ...],
 *              "css": "<katex.min.css with font URLs rewritten to file:// URLs>"}
 *
 * The Python driver (export_homework_pdf.py) owns question extraction, HTML
 * escaping and page layout; this script only turns raw TeX into KaTeX HTML.
 * TeX must be passed UNESCAPED (e.g. "P\\{1<X<3\\}"): KaTeX escapes its own
 * output. Escaping "<" to "&lt;" before KaTeX causes parse errors.
 *
 * KaTeX CSS and fonts are read from the installed katex npm package
 * (node_modules/katex/dist), so no network access is needed at render time.
 * Chrome headless --print-to-pdf does not run page JavaScript, which is why
 * rendering happens here instead of in a <script> tag.
 *
 * Exit codes: 0 ok, 1 runtime error, 2 usage / invalid input.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const USAGE = `Usage: node render_katex.js [--input FILE] [--output FILE]

Reads {"formulas":[{"tex":"...","display":false}]} JSON (stdin by default)
and writes {"katexVersion","html":[...],"css"} JSON (stdout by default).`;

function loadKatex() {
  try {
    return require('katex');
  } catch (err) {
    const e = new Error(
      'Cannot load the "katex" npm package. Run "npm ci" in the repository root ' +
      '(next to package.json), or set NODE_PATH to a node_modules directory containing katex.'
    );
    e.exitCode = 1;
    throw e;
  }
}

function renderFormula(katex, tex, display) {
  // throwOnError:false makes KaTeX emit a red error span instead of throwing,
  // so one bad formula never aborts a whole homework export.
  return katex.renderToString(String(tex), {
    displayMode: Boolean(display),
    throwOnError: false,
    strict: 'ignore',
    output: 'html',
  });
}

function loadKatexCss() {
  const cssPath = require.resolve('katex/dist/katex.min.css');
  const fontsUrl = pathToFileURL(path.join(path.dirname(cssPath), 'fonts')).href;
  const css = fs.readFileSync(cssPath, 'utf-8');
  return css.replace(/url\(fonts\//g, `url(${fontsUrl}/`);
}

function validateRequest(req) {
  if (!req || typeof req !== 'object' || !Array.isArray(req.formulas)) {
    throw usageError('Input must be a JSON object with a "formulas" array.');
  }
  req.formulas.forEach((f, i) => {
    if (!f || typeof f.tex !== 'string') {
      throw usageError(`formulas[${i}].tex must be a string.`);
    }
  });
  return req;
}

function usageError(msg) {
  const e = new Error(msg);
  e.exitCode = 2;
  return e;
}

function parseArgs(argv) {
  const opts = { input: null, output: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') {
      opts.help = true;
    } else if (a === '--input' || a === '--output') {
      if (i + 1 >= argv.length) throw usageError(`${a} requires a value.\n${USAGE}`);
      opts[a.slice(2)] = argv[++i];
    } else {
      throw usageError(`Unknown argument: ${a}\n${USAGE}`);
    }
  }
  return opts;
}

function renderRequest(req, katex) {
  katex = katex || loadKatex();
  validateRequest(req);
  return {
    katexVersion: katex.version,
    html: req.formulas.map((f) => renderFormula(katex, f.tex, f.display)),
    css: loadKatexCss(),
  };
}

function main(argv) {
  const opts = parseArgs(argv);
  if (opts.help) {
    process.stdout.write(USAGE + '\n');
    return 0;
  }
  const raw = fs.readFileSync(opts.input || 0, 'utf-8');
  let req;
  try {
    req = JSON.parse(raw);
  } catch (err) {
    throw usageError(`Invalid JSON input: ${err.message}`);
  }
  const res = renderRequest(req);
  const out = JSON.stringify(res);
  if (opts.output) fs.writeFileSync(opts.output, out);
  else process.stdout.write(out);
  process.stderr.write(`render_katex: rendered ${res.html.length} formulas (KaTeX ${res.katexVersion})\n`);
  return 0;
}

module.exports = { renderFormula, renderRequest, loadKatexCss, parseArgs, validateRequest };

if (require.main === module) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (err) {
    process.stderr.write(`render_katex: ${err.message}\n`);
    process.exitCode = err.exitCode || 1;
  }
}
