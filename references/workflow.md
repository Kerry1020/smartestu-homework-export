# Smartestu Homework Export: Workflow Reference

Background for `scripts/export_homework_pdf.py`. All examples use placeholders.

## API

Base URL: `https://smartestu.cn`. TLS certificates are valid; keep verification on.

### 1. School lookup: `GET /api/schools`

Response: `{"schools": [{"_id": "...", "code": "<school_code>", "name": "<school_name>", "status": "enabled"}, ...]}`

The script matches the exact name or code first, then a unique substring of the
name. `--school-code` skips this call.

### 2. Login: `POST /api/auth/login`

```json
{
  "schoolCode": "<school_code>",
  "schoolUserLocalId": "<student_local_id>",
  "schoolUserId": "<school_code>-<student_local_id>",
  "password": "<password>"
}
```

- `schoolUserId` must be `${schoolCode}-${schoolUserLocalId}`. A raw student id alone does not work.
- The token is at the **top level**: `response["token"]`, not `response["data"]["token"]`.

```json
{ "token": "eyJ...", "user": { "_id": "...", "schoolUserId": "<school_code>-<student_local_id>", "name": "..." } }
```

### 3. Homework list: `POST /api/homework/student/mark/queryHomeworks`

Header `Authorization: Bearer <token>`, body:

```json
{ "studentId": "<school_code>-<student_local_id>" }
```

- Use the school-style `schoolUserId`, not the Mongo `_id`.
- The response already contains full exercise data inline, so no extra call is
  needed. It can be over 1 MB.
- Save a response to a file and replay it offline with `--from-json FILE`.

## Homework selection

1. Flatten `data.courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`.
2. Keep items with `submission_status == "not_submitted"` (snake_case is more
   reliable than `submissionStatus`) or `status == 0`.
3. Sort by `endTime` descending. Return all of them.

The API may only list courses that have homework. Always report
`courses_checked` so the user can spot a missing course.

## Question extraction order (per exercise)

1. Every `questionStructure[]` entry:
   - `mainQuestion.questionMd`: main text (keeps LaTeX)
   - `subQuestions[].questionMd`: rendered separately as (1), (2), ...
     Dropping sub-questions loses data without any warning.
2. Fallback: `questions[].content` (plain text, may lose formatting)
3. Last resort: `exercise.name`

Header fields: `exercise.questionNum`, `exercise.score`.

## Rendering pipeline

1. Split each question into text and math segments. Supported delimiters:
   `$$..$$`, `\[..\]` (display), `$..$`, `\(..\)` (inline). `\$` is a literal dollar sign.
2. HTML-escape **text segments only**. Question text contains raw `<`/`>`
   (e.g. `$P\{1<X<3\}$`). Unescaped text gets truncated by the browser.
   Escaped TeX (`&lt;`) makes KaTeX fail to parse. So escape the text, and give
   KaTeX the raw TeX (its output is already safe HTML).
3. Send all formulas of a homework in one batch to `scripts/render_katex.js`
   (`{"formulas":[{"tex","display"}]}` on stdin, `{"html":[...],"css"}` on stdout).
4. The CSS comes from `node_modules/katex/dist/katex.min.css`, with font URLs
   rewritten to `file://` paths in `node_modules/katex/dist/fonts`, so nothing
   is downloaded at render time.
5. The resulting HTML contains no JavaScript. One exercise per page, with answer space.

### Why server-side

Chrome headless `--print-to-pdf` does not execute page JavaScript.
`--virtual-time-budget`, `--headless=new` and CDP `Page.printToPDF` after a wait
were all tried, and none of them fix it. Browser-side `renderMathInElement`
leaves raw `$...$` in the PDF.

## PDF export

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=/tmp/output.pdf "file:///path/to/prerendered.html"
```

- Do **not** add a fresh `--user-data-dir` on macOS. Chrome writes the PDF but
  then never exits.
- The script deletes any old PDF first and checks that the new file starts with `%PDF-`.

## Verification checklist

- `formula_count` in the summary > 0 for math homework
- no `katex-error` in the HTML (`grep -c katex-error file.html`)
- PDF regenerated in this run (check `pdf_size` / mtime)
