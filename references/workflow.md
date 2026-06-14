# Smartestu Homework Export Workflow Reference

## Confirmed Working API Path

### 1. School lookup
- `GET /api/schools`
- Use to resolve school code from the human-readable school name.

For Harbin Engineering University:
- `code: heu`
- `name: 哈尔滨工程大学`

### 2. Login
- `POST /api/auth/login`

Working fields:
- `schoolCode`
- `schoolUserLocalId`
- `schoolUserId` — format: `${schoolCode}-${schoolUserLocalId}`
- `password`

Example payload:

```json
{
  "schoolCode": "heu",
  "schoolUserLocalId": "2025089104",
  "schoolUserId": "heu-2025089104",
  "password": "..."
}
```

**Token location:** The login response returns the token at the **TOP LEVEL**, not nested under `data`:
```json
{
  "token": "eyJ...",
  "user": { "_id": "...", "schoolUserId": "heu-2025089104", "name": "..." }
}
```
Extract as `response['token']`, NOT `response['data']['token']`.

### 3. Query homework list
- `POST /api/homework/student/mark/queryHomeworks`

Working payload:

```json
{
  "studentId": "heu-2025089104"
}
```

**Key insight:** This API response **already contains full exercise data inline** — including `questionStructure[].mainQuestion.questionMd` and `questionStructure[].subQuestions[].questionMd`. No separate API call is needed to get question content. The response is ~1MB+ for a student with multiple courses.

## Homework Selection Rule

Flatten:
- `data.courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`

Then filter:
- `submission_status == "not_submitted"` (snake_case field — `submissionStatus` camelCase also exists but snake_case is more reliable)
- OR `status == 0` as backup check

Sort by `endTime` descending. **Return ALL unsubmitted items.**

## Question Extraction Priority

1. `questionStructure[].mainQuestion.questionMd` (preferred — preserves LaTeX formulas)
2. `questionStructure[].subQuestions[].questionMd` (sub-questions — MUST render separately)
3. Fallback: `questions[].content`
4. Last resort: `exercise.name`

**Critical:** Exercises with `subQuestions[]` must render each sub-question separately with its own number. Missing sub-questions is a silent data loss bug.

## Rendering Pipeline (CORRECTED)

### The Problem

**Chrome headless `--print-to-pdf` does NOT execute JavaScript.** This was verified extensively:
- `--virtual-time-budget=10000` does not help
- `--headless=new` does not help
- CDP `Page.printToPDF` after waiting also does not help
- Browser-side KaTeX (`renderMathInElement` in a `<script>` tag) produces raw `$...$` text in the PDF, not rendered formulas

### The Solution: Server-Side KaTeX Pre-Rendering

Use Node.js katex module to render all `$...$` and `$$...$$` formulas into HTML spans BEFORE writing the HTML file.

1. `npm install katex@0.16.9` in working directory
2. Run `scripts/render_katex.js` — reads exercises JSON, outputs self-contained HTML with:
   - All formulas pre-rendered as KaTeX HTML spans
   - KaTeX CSS inlined with font paths pointing to local `file:///` URLs
   - **No JavaScript** in the output
3. Feed the pre-rendered HTML to Chrome headless `--print-to-pdf`

See `scripts/render_katex.js` for the verified working renderer.

### HTML Escaping (CRITICAL)

Question text from the API contains raw `<` and `>` inside LaTeX formulas (e.g. `$P\{1<X<3\}$`). These are interpreted as HTML tags by the browser, causing **silent content truncation** — everything after `<X` disappears.

**Always HTML-escape `<`, `>`, and `&` in question text BEFORE inserting into HTML**, then render KaTeX on the escaped text:

```javascript
function htmlEscape(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
// Escape first, then render formulas
renderFormulas(htmlEscape(questionMd));
```

### Font Files

KaTeX CSS references ~60 font files (woff2, ttf, woff). For Chrome headless PDF to render formulas correctly, these must be available locally. `render_katex.js` handles this automatically by downloading fonts to `$TMPDIR/katex-fonts/` and rewriting CSS paths to `file:///` URLs.

## PDF Export: Chrome Headless

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu \
  --print-to-pdf=/tmp/output.pdf \
  --print-to-pdf-no-header \
  "file:///path/to/prerendered.html"
```

**The input MUST be the server-side pre-rendered HTML, not the browser-side KaTeX HTML.**

**Verification checklist:**
- Output file size > 50KB (not empty)
- Formula count > 0 (check `class="katex"` occurrences in the HTML before PDF)
- No raw `$...$` or `\(...\)` visible in PDF
- Regenerate PDF after any HTML change — don't send a stale PDF
