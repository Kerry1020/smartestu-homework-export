# smartestu-homework-export

[简体中文](./README.zh-CN.md)

`smartestu-homework-export` is a reusable skill for exporting homework from smartestu.cn / 数你最灵 into a cleaner, reusable study format. It focuses on one practical path: find the latest unsubmitted homework, keep the original question order, preserve math formulas, and produce a readable PDF deliverable.

## What this project is

This repository packages a focused skill for one specific platform workflow:

1. identify the latest unsubmitted Smartestu homework
2. extract the questions in display order
3. preserve formulas during export
4. generate a PDF that is actually usable for reading or answering

It is not a generic LMS scraper and does not try to support every education platform.

## What the skill does

The skill is designed around Smartestu's real homework workflow.

- resolves the school code first
- logs in with the expected Smartestu payload shape
- queries the homework list
- selects the latest unsubmitted assignment
- extracts ordered question content from the homework object itself
- exports the result through an HTML + KaTeX rendering path
- produces a printable PDF deliverable

## Key features

- API-first workflow instead of fragile browser scraping
- question extraction in original display order
- formula-preserving HTML export with KaTeX
- PDF export standards that require real math rendering verification
- one-question-per-page output for answer-friendly handouts
- privacy-aware examples with placeholders instead of real account data

## Why API-first

For this platform, API-first is more reliable than browser-first.

Browser automation is still useful for visual verification, but it should not be the primary extraction path when the underlying homework data can already be read from the API response. That keeps the workflow more stable and makes the exported output easier to control.

## Smartestu workflow summary

The skill follows this sequence:

1. `GET /api/schools`
2. `POST /api/auth/login`
3. `POST /api/homework/student/mark/queryHomeworks`
4. flatten `courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`
5. filter `submission_status == "not_submitted"`
6. sort by `endTime` descending
7. extract `exercises[].questions[]` in array order
8. render formulas through HTML + KaTeX
9. export a readable PDF

This repository keeps those platform-specific details because they are the whole point of the skill.

## PDF rendering standards

The PDF path is treated as part of the product, not as an afterthought.

The expected standard is:

- formulas must render as math, not raw `$...$`
- server-side (Node.js) KaTeX pre-rendering is the verified method — Chrome headless `--print-to-pdf` does NOT execute JavaScript
- the default handout style should be readable instead of a continuous webpage dump
- prefer one question per page when the user wants to answer directly below each problem
- always HTML-escape `<`, `>`, `&` in question text before rendering (LaTeX formulas like `$P\{1<X<3\}$` contain raw `<` that browsers interpret as HTML tags)

## Installation

Place the skill directory where your skills are loaded.

A typical local layout is:

```text
<your-skills-root>/smartestu-homework-export/
├── SKILL.md
├── README.md
└── README.zh-CN.md
```

If your environment uses a different skill discovery path, copy `SKILL.md` into the corresponding skills directory and keep the README files alongside it for maintenance.

## Usage

Typical requests that should trigger this skill:

- "Export my latest unsubmitted Smartestu homework"
- "Get the newest 数你最灵 homework and package it for me"
- "Make this Smartestu homework into a PDF with formulas preserved"
- "Export the homework one question per page so I can answer below it"

The user will still need to provide live credentials during their own session when authentication is required. Those credentials should never be committed, documented in examples, or pasted into public issue threads.

## Example placeholder payloads

```json
{
  "schoolCode": "<school_code>",
  "schoolUserLocalId": "<student_local_id>",
  "schoolUserId": "<school_user_id>",
  "password": "<password>"
}
```

```json
{
  "studentId": "<school_user_id>"
}
```

These are placeholders only. This repository intentionally includes no real school, student, password, token, or session values.

## Privacy and security notes

- no live credentials, tokens, or session data are stored in this repository
- all examples should remain fictional placeholders
- credentials should be used only for the current session
- do not copy secrets into repository files, screenshots, GitHub issues, or chat logs
- if you fork or adapt this skill, keep the same sanitization standard

## Repository structure

```text
smartestu-homework-export/
├── SKILL.md
├── references/
│   └── workflow.md
├── scripts/
│   ├── export_homework_pdf.py
│   └── render_katex.js
├── README.md
├── README.zh-CN.md
└── LICENSE
```

## Maintenance notes

When updating the skill, keep these rules aligned:

- preserve the API-first workflow unless the platform itself changes
- update both English and Chinese READMEs together
- keep all examples sanitized
- keep the PDF rendering standard explicit
- verify that any new export path still preserves formulas correctly

## License

This project is released under the GNU General Public License v3.0. See [LICENSE](./LICENSE).
