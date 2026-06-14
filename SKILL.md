---
name: smartestu-homework-export
description: Use when the user asks to work with smartestu.cn / 数你最灵 homework, find the latest unsubmitted assignment, extract questions in order, preserve formulas, or export a readable PDF deliverable.
---

# Smartestu Homework Export

## Overview
For this site, API-first beats browser-first. Use browser automation for visual verification only after the homework data path is understood.

## When to Use
- User mentions `smartestu.cn` or 数你最灵
- Need latest unsubmitted homework
- Need ordered question extraction
- Formulas must survive export
- Need PDF delivery instead of screenshots

Do not use this skill for generic LMS scraping where the site and payloads are unknown.

## Credentials
- Password is stored in macOS Keychain: `security find-generic-password -a "<student_local_id>" -s "smartestu.cn" -w`
- If keychain lookup fails (needs user approval), ask the user for password once, then store it: `security add-generic-password -a "<student_local_id>" -s "smartestu.cn" -w "<password>"`
- Known config: school_code=`<school_code>` (resolved via `/api/schools`), student_local_id=`<student_local_id>`
- Do not echo passwords or tokens into chat logs, issues, screenshots, or repository files.

## Core Workflow

### 1. Resolve school code
Call:
- `GET https://smartestu.cn/api/schools`

Match the school entry first.

Example placeholder form:
- `name = "<school_name>"`
- `code = "<school_code>"`

### 2. Log in with the real payload shape
Use:
- `POST https://smartestu.cn/api/auth/login`

Working payload pattern:

```json
{
  "schoolCode": "<school_code>",
  "schoolUserLocalId": "<student_local_id>",
  "schoolUserId": "<school_user_id>",
  "password": "<password>"
}
```

Critical details:
- `schoolUserId` should be `${schoolCode}-${schoolUserLocalId}`
- guessing with only a raw student id is unreliable
- the bearer token returned by login is enough for downstream homework queries
- the login response returns token at the **TOP LEVEL** (`response['token']`), NOT nested under `response['data']['token']`
- the homework list API response **already contains full exercise data inline** (including `questionStructure[].mainQuestion.questionMd` and `subQuestions[].questionMd`) — no separate API call needed
- do not echo the user's password back into chat or logs

### 3. Query homework list
Use:
- `POST https://smartestu.cn/api/homework/student/mark/queryHomeworks`

Working payload pattern:

```json
{
  "studentId": "<school_user_id>"
}
```

Critical detail:
- this API expects the school-style `schoolUserId` string
- the internal Mongo-style `_id` is the wrong identifier here

### 4. Pick unsubmitted homework (ALL of them)
Flatten:
- `data.courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`

Then filter and sort:
- keep `submission_status == "not_submitted"` (also check `status == 0` as backup)
- sort by `endTime` descending
- **Return ALL unsubmitted items, not just the latest one**
- If no unsubmitted found, explicitly report "0 unsubmitted across N courses" so the user can verify

Important: the API may only return courses that have homework assigned. If the user expects a course that doesn't appear, that course may not be on this platform or may have no homework yet. Report the full course list so the user can spot gaps.

### 5. Extract questions (with sub-questions)
Use the homework object directly:
- `exercises[]` → each exercise has `questions[]` and optionally `questionStructure[]`

Recommended order:
1. iterate `exercises` in array order
2. For each exercise, check `questionStructure[]` first:
   - `questionStructure[].mainQuestion.questionMd` = main question text
   - `questionStructure[].subQuestions[]` = sub-parts with their own `questionMd`
3. Fallback: `questions[].content` if questionStructure is empty
4. If both empty, fall back to `exercise.name`

Useful fields:
- `exercise.questionNum`, `exercise.name`, `exercise.score`
- `exercise.questions[].content`, `exercise.questions[].type`
- `questionStructure[].mainQuestion.questionMd` (preferred for rendering)
- `questionStructure[].subQuestions[].questionMd`

### 6. Preserve formulas with Server-Side KaTeX Rendering

**CRITICAL: Chrome headless `--print-to-pdf` does NOT execute JavaScript.** Browser-side KaTeX rendering (via `renderMathInElement` in a `<script>` tag) will NOT appear in the PDF. The PDF will contain raw `$...$` text, not rendered formulas. This was verified extensively — `--virtual-time-budget` and `--headless=new` flags do not fix it.

**The correct approach is server-side (Node.js) KaTeX pre-rendering:**

1. `npm install katex@0.16.9` in a working directory
2. Use Node.js katex module to render all `$...$` and `$$...$$` formulas into HTML spans BEFORE writing the HTML file
3. Inline the KaTeX CSS into the HTML `<style>` block
4. Download KaTeX font files locally and use `file:///` absolute paths in the CSS
5. The resulting HTML has **no JavaScript** — all formulas are pre-rendered HTML
6. Chrome headless can then correctly print this pre-rendered HTML to PDF

See `scripts/render_katex.js` for the verified working server-side renderer.

#### HTML escaping (CRITICAL)

Question text from the API contains raw `<` and `>` inside LaTeX formulas (e.g. `$P\{1<X<3\}$`). These are interpreted as HTML tags by the browser, causing **silent content truncation** — everything after `<X` disappears.

**Always HTML-escape `<`, `>`, and `&` in question text before inserting into HTML:**

```javascript
function htmlEscape(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
```

Apply escaping BEFORE KaTeX rendering (KaTeX will handle the escaped entities correctly within `$...$` delimiters).

#### Font files

KaTeX CSS references ~60 font files (woff2, ttf, woff). For Chrome headless PDF to render formulas correctly, these must be available locally:

```bash
mkdir -p /tmp/katex-fonts
# Extract font filenames from CSS and download each
grep -o 'fonts/[^)]*' katex.min.css | sort -u | while read f; do
  curl -s "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/$f" -o "/tmp/katex-fonts/$(basename $f)"
done
```

Then in the CSS, replace `url(fonts/` with `url(file:///tmp/katex-fonts/`.

#### Browser for verification only

The browser tool CAN render KaTeX (it executes JavaScript). Use it to verify formulas look correct, but do NOT use it for PDF export. The browser-verified HTML and the Chrome-headless-printed HTML are different files — always print from the server-side pre-rendered HTML.

### 7. Export PDF
Reliable local pattern:
1. Use `scripts/render_katex.js` to generate pre-rendered HTML (server-side KaTeX)
2. Print with Chrome headless:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --headless --disable-gpu --print-to-pdf-no-header \
     --print-to-pdf="output.pdf" \
     "file:///path/to/prerendered.html"
   ```
3. Check the output PDF timestamp/size so you know you are sending the newly regenerated file

PDF rendering standard:
- default deliverable should be readable as a homework handout, not a continuous webpage dump
- prefer `one question per page` so the user can answer directly under each problem
- keep formulas rendered (server-side), not raw LaTeX source
- **NEVER rely on browser-side JS rendering for PDF** — Chrome headless does not execute JavaScript. Use server-side KaTeX pre-rendering only (see Section 6).
- if the user wants PDF only, do not send ZIP/HTML as the final handoff
- before sending the PDF, verify that the final file was regenerated from the server-side pre-rendered HTML

## Browser Fallback
If visual verification is needed:
- use the browser to verify rendered output
- do not make browser login the primary path when the API path works
- typing the school name directly can help for manual checks

## Quick Reference
| Goal | Method |
|---|---|
| Find school code | `GET /api/schools` |
| Log in | `POST /api/auth/login` |
| Query homework list | `POST /api/homework/student/mark/queryHomeworks` |
| Identify target homework | flatten nested lists, filter `not_submitted`, sort by `endTime` |
| Preserve math | KaTeX-rendered HTML |
| Produce final deliverable | local HTML to PDF |

## Common Mistakes
- Using browser scraping first when the API path is known
- Sending only `studentId` without building `schoolUserId`
- Using internal `_id` instead of the school-style student identifier
- Picking the first unsubmitted homework instead of sorting by `endTime`
- **Returning only the latest unsubmitted instead of ALL unsubmitted** — always report the full list
- **Claiming "no unsubmitted" without showing the course list** — always show which courses were checked so the user can spot missing ones
- **NOT HTML-escaping `<` and `>` in question text before rendering** — LaTeX formulas like `$P\{1<X<3\}$` contain raw `<` that browsers interpret as HTML tags, silently truncating all content after the `<`. ALWAYS escape first.
- **Trusting Chrome headless `--print-to-pdf` to execute JavaScript** — it does NOT. Browser-side KaTeX rendering (`renderMathInElement` in a `<script>` tag) will NOT appear in the PDF. Use server-side Node.js katex pre-rendering instead (see Section 6).
- **Forgetting to download KaTeX font files locally** — without the actual woff2/ttf files, Chrome headless PDF shows formula boxes without proper glyphs. Download all ~60 font files and use `file:///` paths.
- Exporting raw text or screenshots and losing formulas
- Repeating credentials in chat history
- Verifying one HTML file and sending a different copied/moved file with broken relative asset paths
- Fixing the HTML but forgetting to regenerate the PDF, then accidentally sending a stale older PDF
- **Forgetting sub-questions**: exercises with `questionStructure[].subQuestions[]` must render each sub-question separately, not just the main question
- **Using `questions[].content` instead of `questionStructure[].mainQuestion.questionMd`**: the `questionStructure` path preserves LaTeX formulas properly; `questions[].content` is a plain-text fallback that may lose formatting
- **Extracting token from wrong level**: login response token is at `response['token']` (top level), NOT `response['data']['token']`

## Output Pattern
Preferred deliverables:
- ordered question content
- one merged PDF
- one-question-per-page PDF when direct answering is useful
- optional metadata summary with homework id, course, question count, and export paths
