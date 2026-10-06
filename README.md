# smartestu-homework-export

[![CI](https://github.com/Kerry1020/smartestu-homework-export/actions/workflows/ci.yml/badge.svg)](https://github.com/Kerry1020/smartestu-homework-export/actions/workflows/ci.yml)

[简体中文](./README.zh-CN.md)

An agent skill (Claude Code / Agent SDK `SKILL.md` format) and standalone CLI
that exports your **unsubmitted homework from smartestu.cn (数你最灵)** to
printable PDFs. Each question goes on its own page, with math rendered by KaTeX.

- Uses the Smartestu API directly instead of scraping pages in a browser
- Reports every unsubmitted assignment, newest deadline first, plus the list of courses it checked
- Includes main questions and sub-questions in their original order
- Renders KaTeX formulas before printing, so the HTML needs no JavaScript and Chrome headless prints the math correctly
- Leaves A4 answer space under each question

It is not a general-purpose LMS scraper and does not submit anything.

## Requirements

- Python 3.9+
- Node.js 18+ and npm
- Google Chrome, Chromium or Microsoft Edge (only for PDF output)
- macOS Keychain is optional. It is the most convenient way to store the password.

## Installation

```bash
git clone https://github.com/Kerry1020/smartestu-homework-export.git
cd smartestu-homework-export
npm ci                                    # katex 0.16.9 (pinned in package-lock.json)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

To use it as a skill, put the whole directory (not only `SKILL.md`) where your
agent loads skills, for example `~/.claude/skills/smartestu-homework-export/`.
Then ask for things like "export my unsubmitted 数你最灵 homework as PDF".

## Usage

```bash
# Store the password once (macOS). Omitting the value after -w makes it prompt.
security add-generic-password -a "<student_id>" -s "smartestu.cn" -w

.venv/bin/python scripts/export_homework_pdf.py \
  --school-name "<school_name>" --student-id "<student_id>" --keychain \
  --out-dir ~/Desktop/homework
```

Other ways to pass the password (first match wins): `--password-stdin`,
the `SMARTESTU_PASSWORD` environment variable, `--keychain`, or `--password`.
`--password` is discouraged because the value shows up in `ps` and in shell history.

Useful options:

| Option | Purpose |
|---|---|
| `--school-code CODE` | skip the school-name lookup |
| `--latest-only` | export only the homework with the latest deadline |
| `--no-pdf` | write HTML only |
| `--chrome PATH` | browser binary (or set `CHROME_PATH`) |
| `--from-json FILE` | offline: render a saved `queryHomeworks` response |
| `--insecure` | disable TLS verification (not normally needed) |

Output: one `<homework>.html` and one `<homework>.pdf` per assignment, plus a
`summary.json` file. The same summary is printed to stdout.

Exit codes: `0` ok (including "no unsubmitted homework"), `1` unexpected
error, `2` usage / school not found / no password, `3` network, login or API
error, `4` KaTeX rendering, `5` PDF export.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `School not found` / `ambiguous` | use the exact name shown on smartestu, or `--school-code` (see `curl https://smartestu.cn/api/schools`) |
| `Login failed` / exit 3 | check the student id (without the school prefix) and the password; check the Keychain item with `security find-generic-password -a <id> -s smartestu.cn` |
| `katex npm package is not installed` / exit 4 | run `npm ci` in the repository root |
| `Chrome/Chromium not found` / exit 5 | install Chrome, or pass `--chrome` / set `CHROME_PATH`; or use `--no-pdf` |
| Chrome timeout | close any Chrome profile dialogs and try again; never add a custom `--user-data-dir` (Chrome hangs on macOS) |
| red formula text in the PDF | that formula is invalid TeX in the source; `grep katex-error *.html` finds it |
| `0 unsubmitted` but you expected some | look at `courses_checked`: the API only lists courses that have homework on the platform |

## Privacy

This repository contains no credentials, tokens or personal data. All examples
use placeholders such as `<school_code>` and `<student_id>`. Do not paste real
values into issues, commits or logs.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest      # Python tests (network and Chrome are mocked)
npm test                        # renderer tests (node:test)
```

CI runs both suites on Python 3.9 and 3.12. See
[`references/workflow.md`](./references/workflow.md) for the API payloads and
the rendering pitfalls (HTML escaping vs. TeX, why rendering has to happen
server-side).

```text
smartestu-homework-export/
├── SKILL.md                    # skill entry point
├── references/workflow.md      # API + rendering reference
├── scripts/
│   ├── export_homework_pdf.py  # CLI
│   └── render_katex.js         # KaTeX renderer (JSON in/out)
├── tests/
├── package.json / package-lock.json
└── requirements.txt / requirements-dev.txt
```

When you change behaviour, update both READMEs.

## License

GPL-3.0. See [LICENSE](./LICENSE).
