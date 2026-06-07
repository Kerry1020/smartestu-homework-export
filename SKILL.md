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

## Privacy and Safety
- This repository contains no live credentials, tokens, or session data.
- Any identifiers shown in examples must be fictional placeholders.
- Credentials should only be used for the current login session.
- Do not echo passwords or tokens into chat logs, issues, screenshots, or repository files.

## Core Workflow

### 1. Resolve school code
Call:
- `GET https://smartestu.cn/api/schools`

Match the school entry first.

Example placeholder form:
- `name = "<school_name>"`
- `code = "<school_code>"`

### 1.1 Verify response shape before parsing
Do not assume endpoint response structure from memory, older notes, or nearby APIs.

Hard requirements:
- before writing parsing logic for a Smartestu endpoint, inspect a real response sample from that exact endpoint
- record whether the top-level payload is an object, array, or nested `data` wrapper
- do not assume `/api/schools` returns a bare array; verify whether it is `{ "schools": [...] }` or another wrapper in the current environment
- do not reuse parsing assumptions from login or homework endpoints for school-list endpoints
- when a response shape is uncertain, print or inspect the first layer of keys before iterating fields

Failure pattern to avoid:
- writing `for item in response` before confirming whether `response` is the array itself or an object containing the array
- treating a successful `200` response as proof that parsing assumptions are correct
- “the endpoint exists” and “the parser is correct” are separate checks

Recommended guardrail:
- first validate the shape
- then extract the correct collection field
- only then search/match school entries or flatten homework arrays

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

### 4. Pick the latest unsubmitted homework
Flatten:
- `data.courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`

Then filter and sort:
- keep `submission_status == "not_submitted"`
- sort by `endTime` descending
- choose the newest item

### 5. Extract questions in display order
Use the homework object directly:
- `exercises[]`
- `exercises[].questions[]`

Recommended order:
1. iterate `exercises` in array order
2. iterate each `questions[]` in array order
3. join `question.content`
4. if question content is empty, fall back to the exercise title or name

Useful fields:
- `exercise.questionNum`
- `exercise.name`
- `exercise.questions[].content`
- `exercise.questions[].type`

### 5.1 Preserve structure, not just text
Do not flatten structured question content into plain text if structure carries meaning.

Required handling:
- preserve Markdown tables as real HTML tables before PDF export
- preserve explicit line breaks, list structure, and simple inline HTML such as `<br>` when present in source content
- if multiple tables appear in one question, render all of them
- if a structure cannot be rendered faithfully, treat the export as incomplete instead of silently degrading it to paragraph text

Structural verification targets:
- tabular content in source should become visible table elements in the rendered HTML/PDF
- probability/distribution tables must remain readable row/column layouts
- the output should read like the original homework handout, not a text dump with `|` separators

### 5.2 Anti-silent-degradation rules
These rules exist to stop “looks good enough” exports.

Hard requirements:
- source structure decides output structure; if the source contains tables, the final output must contain tables
- do not confuse math rendering success with overall render success; formulas can pass while tables still fail
- do not treat plain-text preservation as acceptable when the original layout carries semantic meaning
- do not claim success just because the PDF opens, has pages, or contains all characters
- do not silently ship a degraded file and explain the limitation afterward; detect the degradation first and continue fixing

Required source scan before export:
- inspect representative `question.content` samples, not just homework metadata
- explicitly check whether content contains Markdown tables, repeated `|`-delimited rows, `<br>`, list markers, or other structure-sensitive patterns
- if any such pattern appears in source, add a matching render step and a matching verification step before generating the final PDF

### 5.3 Failure gates for structured content
Treat any of the following as an export failure, not a cosmetic issue:
- raw Markdown table separators such as `|---|`, `| --- |`, or repeated pipe rows remain visible in final presentation
- a question that should contain a table is rendered as a paragraph with pipes
- line breaks collapse and change the meaning or readability of the problem
- multiple tables in one question collapse into one block of text
- inline HTML needed for meaning is escaped away instead of rendered safely

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
  - when source contains tables, rendered `<table>` nodes are present in the final verified HTML
  - raw Markdown table separators like `|---|` are no longer visible as the final presentation for those questions
- never treat HTML generation or PDF generation alone as success
- never claim the export is correct until the runtime checks above have passed
- do not trust `file://` preview/export when external math assets are required unless runtime verification proves those assets actually loaded
- if math stays as raw `$...$`, treat the export as failed and switch asset host, local asset strategy, or rendering path before continuing
- if tables stay as raw Markdown, treat the export as failed and add a structure-aware rendering step before continuing
- if you copy or move the verified HTML, re-check every relative asset path from the final delivery file location
- the file you verify in the browser must be the same path you later export or send; a working sibling file does not prove the final deliverable works

### 6.1 Verification checklist before sending
Do not send the file until all applicable checks below pass.

Minimum runtime checks:
- `window.katex === true` or equivalent positive availability check
- `renderMathInElement` exists
- rendered `.katex` node count is greater than zero when formulas exist in source
- rendered `<table>` node count is greater than zero when tables exist in source
- raw `$...$` is not visible in final rendered text for formula-bearing questions
- raw Markdown table separators are not the final visible presentation for table-bearing questions

Minimum visual checks:
- inspect at least one formula-heavy question
- inspect at least one table-heavy question when tables exist
- confirm table borders/cells are readable and row/column grouping still makes sense
- confirm one-question-per-page layout did not cut tables into unreadable fragments

Artifact checks:
- regenerate the PDF after the last HTML fix
- verify PDF timestamp/size changed after regeneration
- send the exact file generated from the exact verified HTML path

### 6.2 Explicit anti-stupidity reminders
If you are tempted to say any of these, stop and keep fixing:
- “公式都渲染了，应该差不多了”
- “表格只是样式问题，不影响内容”
- “PDF 能打开就算成功”
- “用户如果发现表格有问题我再修”
- “HTML 看起来差不多，先发再说”

Reality:
- formula pass does not imply structure pass
- table loss is content loss, not just style loss
- opening successfully is not correctness
- post-send repair is failure, not acceptable default behavior

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
- Assuming response shape from memory instead of checking the real top-level payload first
- Treating a `200` response as if it proves the parser is correct
- Picking the first unsubmitted homework instead of sorting by `endTime`
- Exporting raw text or screenshots and losing formulas
- Repeating credentials in chat history
- Verifying one HTML file and sending a different copied/moved file with broken relative asset paths
- Fixing the HTML but forgetting to regenerate the PDF, then accidentally sending a stale older PDF
- Claiming success from DOM/runtime checks alone without checking that the final delivered artifact was rebuilt from that verified state

## Output Pattern
Preferred deliverables:
- ordered question content
- one merged PDF
- one-question-per-page PDF when direct answering is useful
- optional metadata summary with homework id, course, question count, and export paths
