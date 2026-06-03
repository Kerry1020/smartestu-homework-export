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
- Known config: school_code=`heu` (Harbin Engineering University), student_local_id=`2025089104`
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

### 6. Preserve formulas with HTML + KaTeX
Do not rely on screenshots if formulas matter.

Reliable render approach:
- write a temporary HTML file
- prefer KaTeX assets from `unpkg.com` for this workflow
- if remote KaTeX assets do not actually load in the browser/runtime, switch to a local mirrored KaTeX asset bundle before continuing
- support these delimiters:
  - `$$ ... $$`
  - `$ ... $`
  - `\( ... \)`
  - `\[ ... \]`
- if a PDF is the deliverable, verify the page runtime before export:
  - `window.katex` exists
  - `renderMathInElement` exists
  - rendered `.katex` nodes are present
  - raw `$...$` is no longer visible in the rendered text
- never treat HTML generation or PDF generation alone as success
- never claim the export is correct until the runtime checks above have passed
- do not trust `file://` preview/export when external math assets are required unless runtime verification proves those assets actually loaded
- if math stays as raw `$...$`, treat the export as failed and switch asset host, local asset strategy, or rendering path before continuing
- if you copy or move the verified HTML, re-check every relative asset path from the final delivery file location
- the file you verify in the browser must be the same path you later export or send; a working sibling file does not prove the final deliverable works

### 7. Export PDF
Reliable local pattern:
1. write `rendered.html`
2. open the local page in an available browser tool
3. wait for math assets to load and confirm formulas are actually rendered
4. export the PDF from that exact verified file path
5. check the output PDF timestamp/size so you know you are sending the newly regenerated file, not an older stale artifact

PDF rendering standard:
- default deliverable should be readable as a homework handout, not a continuous webpage dump
- prefer `one question per page` so the user can answer directly under each problem
- keep formulas rendered, not raw LaTeX source
- visually verify at least one preview or screenshot before claiming success
- this visual check is required but not sufficient; the runtime KaTeX checks above are a hard gate
- if a compact all-in-one PDF is also useful, send both variants
- if the user wants PDF only, do not send ZIP/HTML as the final handoff
- before sending the PDF, verify that the final file corresponds to the verified HTML revision and was regenerated after the last HTML fix

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
- Exporting raw text or screenshots and losing formulas
- Repeating credentials in chat history
- Verifying one HTML file and sending a different copied/moved file with broken relative asset paths
- Fixing the HTML but forgetting to regenerate the PDF, then accidentally sending a stale older PDF
- Claiming success from DOM/runtime checks alone without checking that the final delivered artifact was rebuilt from that verified state
- **Forgetting sub-questions**: exercises with `questionStructure[].subQuestions[]` must render each sub-question separately, not just the main question

## Output Pattern
Preferred deliverables:
- ordered question content
- one merged PDF
- one-question-per-page PDF when direct answering is useful
- optional metadata summary with homework id, course, question count, and export paths
