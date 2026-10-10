# Smartestu Homework Export: Workflow Reference

Background for `scripts/export_homework_pdf.py`. All examples use placeholders.

## API

Base URL: `https://smartestu.cn`. TLS certificates are valid; keep verification on.

### 1. School lookup: `GET /api/schools`

Response: `{"schools": [{"_id": "...", "code": "<school_code>", "name": "<school_name>", "status": "enabled"}, ...]}`

The script matches the exact name or code first, then a unique substring of the
name. `--school-code` skips this call.

### 2. Login: `POST /api/auth/login`

Send `X-Auth-Protocol: cookie-v1` and this JSON body:

```json
{
  "schoolCode": "<school_code>",
  "schoolUserLocalId": "<student_local_id>",
  "schoolUserId": "<school_code>-<student_local_id>",
  "password": "<password>"
}
```

`schoolUserId` must be `${schoolCode}-${schoolUserLocalId}`. A raw student id
alone does not work. A successful current-protocol response sets the auth cookie
and returns a `sessionContext` value.

Some older deployments return a bearer token instead. The exporter retains that
legacy flow: when login returns a token without `sessionContext`, it sends
`Authorization: Bearer <token>` and queries with
`{"studentId": "<school_code>-<student_local_id>"}`. A transitional response
containing both values uses cookie-v1.

### 3. Session metadata: `GET /api/auth/session`

Send these headers after cookie login:

```text
X-Auth-Protocol: cookie-v1
X-Session-Context: <login sessionContext>
```

The response supplies the current context, CSRF token and authenticated user.
Student courses are found at:

```text
user.capabilityProfile.studentCourses[]
  courseId
  courseName
```

Use this list for `courses_checked`, including courses with no homework. Do not
infer the student's courses from the homework response.

### 4. Paginated homework list: `POST /api/homework/student/mark/queryHomeworks`

Send the cookie plus the current session headers:

```text
X-Auth-Protocol: cookie-v1
X-Session-Context: <current sessionContext>
X-CSRF-Token: <csrfToken>
```

Body:

```json
{
  "courseIds": [101, 102],
  "scene": "homework",
  "pageNo": 1,
  "pageSize": 100
}
```

Follow `data.pageTotal` until every page has been fetched, then merge each
course's `studentCourseHomeworkDTOList`. The list response contains homework
metadata but no longer includes full exercise data.

### 5. Exercise details: `POST /api/homework/student/mark/queryExercisesByHomeworkId`

For each unsubmitted homework, send the same cookie/session/CSRF headers and:

```json
{ "homeworkId": 123 }
```

Questions are in `data.exercises`. Fetch details only after filtering the list;
submitted homework does not need an extra request.

A saved legacy or augmented `queryHomeworks` response whose homework entries
already contain `exercises` can be replayed offline with `--from-json FILE`.
The current list endpoint response by itself is not sufficient for offline PDF
rendering because exercise details are returned separately.

## Homework selection

1. Flatten `data.courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`.
2. Keep items with `submission_status == "not_submitted"` (snake_case is more
   reliable than `submissionStatus`) or `status == 0`.
3. Sort by `endTime` descending. Return all of them.
4. Fetch `data.exercises` for every selected homework in the cookie-v1 flow.

In the cookie-v1 flow, always report `courses_checked` from the authenticated
session so a user can spot a missing enrollment even when no course has
homework. The legacy bearer response has no separate enrollment lookup, so its
`courses_checked` value contains only courses returned by `queryHomeworks`.

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
   `$$..$$`, `\[...\]` (display), `$..$`, `\(...\)` (inline). `\$` is a literal dollar sign.
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
