#!/usr/bin/env node
/**
 * Server-side KaTeX renderer for smartestu homework.
 *
 * Reads exercises JSON from stdin or file, outputs pre-rendered HTML
 * where all $...$ and $$...$$ formulas are already converted to KaTeX spans.
 *
 * Usage:
 *   node render_katex.js --input exercises.json --output homework.html --title "15周概率作业"
 *   cat exercises.json | node render_katex.js --title "作业" > homework.html
 *
 * The output HTML has NO JavaScript — all formulas are pre-rendered HTML spans.
 * This is critical because Chrome headless --print-to-pdf does NOT execute JS.
 */
const katex = require('katex');
const fs = require('fs');
const path = require('path');
const https = require('https');

// --- Helpers ---

function htmlEscape(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderFormulas(text) {
  // $$...$$ (display mode) first
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (match, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false });
    } catch (e) { return match; }
  });
  // $...$ (inline mode)
  text = text.replace(/\$([^\$\n]+?)\$/g, (match, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false });
    } catch (e) { return match; }
  });
  return text;
}

function processQuestionText(text) {
  // Escape HTML first (fixes $P\{1<X<3\}$ truncation), then render formulas
  return renderFormulas(htmlEscape(text));
}

// --- KaTeX CSS & Fonts ---

const KATEX_VERSION = '0.16.9';
const KATEX_CDN = `https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist`;
const FONT_CACHE_DIR = path.join(os_tmpdir(), 'katex-fonts');

const os = require('os');
function os_tmpdir() { return os.tmpdir(); }

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (resp) => {
      if (resp.statusCode === 302 || resp.statusCode === 301) {
        downloadFile(resp.headers.location, dest).then(resolve).catch(reject);
        return;
      }
      resp.pipe(file);
      file.on('finish', () => { file.close(resolve); });
    }).on('error', reject);
  });
}

async function ensureKatexAssets(workDir) {
  // Download KaTeX CSS
  const cssPath = path.join(workDir, 'katex.min.css');
  if (!fs.existsSync(cssPath)) {
    await downloadFile(`${KATEX_CDN}/katex.min.css`, cssPath);
  }

  // Download font files (only once)
  fs.mkdirSync(FONT_CACHE_DIR, { recursive: true });
  let css = fs.readFileSync(cssPath, 'utf-8');
  const fontNames = [...new Set([...css.matchAll(/url\(fonts\/([^)]+)\)/g)].map(m => m[1]))];

  for (const font of fontNames) {
    const dest = path.join(FONT_CACHE_DIR, font);
    if (!fs.existsSync(dest)) {
      await downloadFile(`${KATEX_CDN}/fonts/${font}`, dest);
    }
  }

  // Rewrite CSS font paths to absolute file:// URLs
  css = css.replace(/url\(fonts\//g, `url(file://${FONT_CACHE_DIR}/`);
  return css;
}

// --- Main ---

async function main() {
  const args = process.argv.slice(2);
  let title = '作业';
  let inputPath = null;
  let outputPath = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--title' && args[i + 1]) { title = args[++i]; }
    else if (args[i] === '--input' && args[i + 1]) { inputPath = args[++i]; }
    else if (args[i] === '--output' && args[i + 1]) { outputPath = args[++i]; }
  }

  // Read exercises JSON
  let exercises;
  if (inputPath) {
    exercises = JSON.parse(fs.readFileSync(inputPath, 'utf-8'));
  } else {
    exercises = JSON.parse(fs.readFileSync(0, 'utf-8')); // stdin
  }

  // Ensure KaTeX assets
  const workDir = path.dirname(outputPath || __dirname);
  fs.mkdirSync(workDir, { recursive: true });
  const katexCSS = await ensureKatexAssets(workDir);

  // Build HTML body
  let body = '';
  for (let i = 0; i < exercises.length; i++) {
    const ex = exercises[i];
    body += '<div class="exercise">\n';
    body += `<div class="ex-header">第 ${i + 1} 题`;
    if (ex.questionNum) body += `（${ex.questionNum}）`;
    body += '</div>\n<div class="ex-body">\n';

    const qs = ex.questionStructure || [];
    if (qs.length > 0) {
      const main = qs[0].mainQuestion || {};
      if (main.questionMd) {
        body += `<p>${processQuestionText(main.questionMd)}</p>\n`;
      }
      const subs = qs[0].subQuestions || [];
      for (let j = 0; j < subs.length; j++) {
        if (subs[j].questionMd) {
          body += `<p class="sub-q">（${j + 1}）${processQuestionText(subs[j].questionMd)}</p>\n`;
        }
      }
    } else {
      // Fallback to questions[].content
      for (const q of (ex.questions || [])) {
        if (q.content) body += `<p>${processQuestionText(q.content)}</p>\n`;
      }
    }

    body += '</div>\n<div class="answer-space"></div>\n</div>\n';
  }

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>${title}</title>
<style>
${katexCSS}

@page { size: A4; margin: 2cm; }
body { font-family: "PingFang SC", "Microsoft YaHei", serif; line-height: 1.8; color: #222; }
.hw-title { font-size: 20px; font-weight: bold; text-align: center; margin-bottom: 20px; }
.exercise { page-break-after: always; margin-bottom: 30px; }
.exercise:last-child { page-break-after: auto; }
.ex-header { font-size: 16px; font-weight: bold; margin-bottom: 12px; }
.ex-body { font-size: 15px; margin-bottom: 15px; }
.sub-q { margin-left: 2em; margin-bottom: 8px; }
.answer-space { border-bottom: 1px dashed #ccc; height: 250px; margin-top: 10px; }
</style>
</head>
<body>
<div class="hw-title">${title}</div>
${body}
</body>
</html>`;

  const formulaCount = (html.match(/class="katex"/g) || []).length;

  if (outputPath) {
    fs.writeFileSync(outputPath, html);
    process.stderr.write(`Pre-rendered HTML: ${outputPath} (${formulaCount} formulas)\n`);
  } else {
    process.stdout.write(html);
    process.stderr.write(`Pre-rendered HTML: stdout (${formulaCount} formulas)\n`);
  }
}

main().catch(err => { console.error(err); process.exit(1); });
