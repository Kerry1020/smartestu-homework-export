---
name: smartestu-homework-export
description: Export unsubmitted homework from smartestu.cn (数你最灵) to a printable PDF with math formulas rendered by KaTeX, one question per page. Use when the user mentions smartestu.cn or 数你最灵 and wants to list unsubmitted assignments, extract homework questions in order, or get a homework PDF/handout. Not for other learning platforms or for submitting answers.
---

# Smartestu Homework Export

Use the bundled script. It talks to the Smartestu API directly (no browser
scraping), follows the current cookie/CSRF and paginated homework workflow,
renders formulas server-side with KaTeX, and prints PDFs with Chrome headless.
Chrome's `--print-to-pdf` does not run page JavaScript, so never switch to
browser-side KaTeX.

## Prerequisites (once)

From the skill directory:

```bash
npm ci                                   # installs katex 0.16.9 (pinned)
python3 -m pip install -r requirements.txt
```

Also needed: Python 3.9+, Node.js 18+, Google Chrome / Chromium / Edge.

## Steps

1. **Get the inputs.** Ask for the school name (as shown on smartestu, e.g. its
   Chinese name) or school code, and the student id (without the school
   prefix). Never echo, log or commit the password.
2. **Provide the password safely.** Prefer the macOS Keychain:
   ```bash
   security find-generic-password -a "<student_id>" -s "smartestu.cn" -w >/dev/null \
     || security add-generic-password -a "<student_id>" -s "smartestu.cn" -w   # prompts
   ```
   Otherwise pipe it with `--password-stdin` or set `SMARTESTU_PASSWORD`.
3. **Run the export:**
   ```bash
   python3 scripts/export_homework_pdf.py \
     --school-name "<school_name>" --student-id "<student_id>" --keychain \
     --out-dir /tmp/smartestu-export
   ```
   Add `--latest-only` if the user only wants the newest assignment.
   Run `--help` for all options.
4. **Check the result.** The script prints a JSON summary (also saved as
   `summary.json`) and exits non-zero on failure:

   | Exit | Meaning | What to do |
   |---|---|---|
   | 0 | ok, or `"status": "no_unsubmitted"` | report results |
   | 2 | usage / school not found / no password | fix the inputs |
   | 3 | network, login or API error | check credentials; see `references/workflow.md` |
   | 4 | KaTeX rendering failed | run `npm ci`; check `node --version` |
   | 5 | Chrome missing or no PDF | pass `--chrome PATH` or use `--no-pdf` |

5. **Report back.** List every unsubmitted homework (name, course, deadline,
   PDF path). If none, say "0 unsubmitted across N courses" and show
   `courses_checked`, so the user can spot a missing course. Hand over the PDF
   files, not the HTML, unless the user asks for HTML.

## Rules

- Always report **all** unsubmitted homework, sorted by deadline, unless the
  user asked for only the latest.
- Send only PDFs the script regenerated in this run (it deletes stale PDFs
  first and checks the new file is a valid PDF).
- Use a browser only to visually double-check output, never as the extraction
  or PDF path.

## Files

- `scripts/export_homework_pdf.py`: CLI. API calls, homework selection,
  question extraction, HTML building, Chrome PDF export.
- `scripts/render_katex.js`: JSON-in / JSON-out KaTeX renderer called by the CLI.
- `references/workflow.md`: API endpoints, payload shapes, response fields,
  extraction order and rendering pitfalls. Read it when the API changes or
  something fails.
