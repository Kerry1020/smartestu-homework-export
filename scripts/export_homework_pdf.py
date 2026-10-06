#!/usr/bin/env python3
"""Export unsubmitted homework from smartestu.cn (数你最灵) as KaTeX-rendered PDFs.

Pipeline:
  1. API: resolve school code -> login -> query homeworks -> pick unsubmitted
  2. Extract questions (questionStructure main/sub questions, with fallbacks)
  3. Render formulas server-side with Node.js KaTeX (scripts/render_katex.js)
     and build a self-contained HTML file (no JavaScript)
  4. Print the HTML to PDF with Chrome/Chromium headless

Chrome headless --print-to-pdf does NOT execute page JavaScript, so all KaTeX
rendering happens before the HTML is written.

Password sources (first match wins): --password-stdin, $SMARTESTU_PASSWORD,
--keychain (macOS Keychain, service "smartestu.cn", account = student id),
--password (discouraged: visible in the process list and shell history).

Exit codes:
  0  success (including "no unsubmitted homework")
  1  unexpected error
  2  usage error / missing password / bad input file
  3  network, authentication or API response error
  4  formula rendering failed (Node.js / katex)
  5  PDF export failed (Chrome not found or produced no PDF)

Requires Python 3.9+.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

BASE_URL = 'https://smartestu.cn'
SCHOOLS_API = BASE_URL + '/api/schools'
LOGIN_API = BASE_URL + '/api/auth/login'
QUERY_HOMEWORKS_API = BASE_URL + '/api/homework/student/mark/queryHomeworks'
KEYCHAIN_SERVICE = 'smartestu.cn'

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER_SCRIPT = Path(__file__).resolve().parent / 'render_katex.js'

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_API = 3
EXIT_RENDER = 4
EXIT_PDF = 5

CHROME_CANDIDATES = (
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    'google-chrome',
    'google-chrome-stable',
    'chromium',
    'chromium-browser',
    'chrome',
    'msedge',
)

# (formulas: [(tex, display_mode)]) -> (rendered_html_list, katex_css)
Renderer = Callable[[List[Tuple[str, bool]]], Tuple[List[str], str]]


class ExportError(Exception):
    """An expected failure that maps to a specific exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# API response parsing (pure functions)
# ---------------------------------------------------------------------------

def parse_schools(data: Any) -> List[Dict[str, Any]]:
    """Return the school list from a /api/schools response of any known shape."""
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    if isinstance(data, dict):
        inner = data.get('data')
        candidates = [data.get('schools'), inner]
        if isinstance(inner, dict):
            candidates.insert(1, inner.get('schools'))
        for candidate in candidates:
            if isinstance(candidate, list):
                return [s for s in candidate if isinstance(s, dict)]
    raise ExportError('Unexpected /api/schools response shape', EXIT_API)


def find_school_code(schools: Sequence[Dict[str, Any]], school: str) -> str:
    """Match by exact name or code first, then by unique substring of the name."""
    wanted = school.strip()
    for s in schools:
        if wanted in (s.get('name'), s.get('code')) and s.get('code'):
            return s['code']
    partial = [s for s in schools if wanted and wanted in (s.get('name') or '') and s.get('code')]
    if len(partial) == 1:
        return partial[0]['code']
    if partial:
        names = ', '.join(s.get('name', '?') for s in partial)
        raise ExportError('School name "%s" is ambiguous: %s' % (school, names), EXIT_USAGE)
    raise ExportError('School not found: "%s" (%d schools listed by the API; '
                      'pass the exact Chinese name or --school-code)' % (school, len(schools)),
                      EXIT_USAGE)


def extract_token(login_response: Any) -> str:
    """The login token is at the TOP LEVEL (response['token']); fall back to data.token."""
    if isinstance(login_response, dict):
        token = login_response.get('token')
        if not token and isinstance(login_response.get('data'), dict):
            token = login_response['data'].get('token')
        if isinstance(token, str) and token:
            return token
        msg = login_response.get('message') or login_response.get('msg')
        if msg:
            raise ExportError('Login failed: %s' % msg, EXIT_API)
    raise ExportError('Login failed: no token in response (check school, student id and password)',
                      EXIT_API)


def flatten_homeworks(data: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Flatten data.courseHomeworkDTOList[].studentCourseHomeworkDTOList[].

    Returns (homeworks, course_names). Each homework dict gets a 'courseName'.
    """
    if not isinstance(data, dict):
        raise ExportError('Unexpected queryHomeworks response shape', EXIT_API)
    payload = data.get('data')
    if not isinstance(payload, dict):
        raise ExportError('queryHomeworks response has no "data" object: %s'
                          % (data.get('message') or data.get('msg') or 'unknown error'), EXIT_API)
    homeworks = []
    courses = []
    for course in payload.get('courseHomeworkDTOList') or []:
        if not isinstance(course, dict):
            continue
        name = course.get('courseName') or '?'
        courses.append(name)
        for hw in course.get('studentCourseHomeworkDTOList') or []:
            if isinstance(hw, dict):
                item = dict(hw)
                item['courseName'] = course.get('courseName')
                homeworks.append(item)
    return homeworks, courses


def is_unsubmitted(hw: Dict[str, Any]) -> bool:
    return hw.get('submission_status') == 'not_submitted' or hw.get('status') == 0


def select_unsubmitted(homeworks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep unsubmitted homework, newest deadline (endTime) first."""
    items = [h for h in homeworks if is_unsubmitted(h)]
    items.sort(key=lambda h: str(h.get('endTime') or ''), reverse=True)
    return items


# ---------------------------------------------------------------------------
# Question extraction and HTML building (pure functions)
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def extract_questions(exercise: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return [{'main': str, 'subs': [str]}] for one exercise.

    Priority: every questionStructure[] entry (mainQuestion.questionMd +
    subQuestions[].questionMd) -> questions[].content -> exercise.name.
    """
    blocks = []
    for entry in exercise.get('questionStructure') or []:
        if not isinstance(entry, dict):
            continue
        main = _text((entry.get('mainQuestion') or {}).get('questionMd'))
        subs = [_text(s.get('questionMd')) for s in entry.get('subQuestions') or []
                if isinstance(s, dict) and _text(s.get('questionMd'))]
        if main or subs:
            blocks.append({'main': main, 'subs': subs})
    if blocks:
        return blocks
    for q in exercise.get('questions') or []:
        if isinstance(q, dict) and _text(q.get('content')):
            blocks.append({'main': _text(q['content']), 'subs': []})
    if blocks:
        return blocks
    name = _text(exercise.get('name'))
    return [{'main': name, 'subs': []}] if name else []


# $$..$$, \[..\], \(..\), then inline $..$ (not preceded by a backslash).
MATH_RE = re.compile(
    r'\$\$(?P<dd>[\s\S]+?)\$\$'
    r'|\\\[(?P<bd>[\s\S]+?)\\\]'
    r'|\\\((?P<bi>[\s\S]+?)\\\)'
    r'|(?<!\\)\$(?P<di>[^$\n]+?)(?<!\\)\$'
)
IMAGE_RE = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+"[^"]*")?\)')


def split_math(text: str) -> List[Tuple[str, str, bool]]:
    """Split text into [('text', s, False) | ('math', tex, display)] segments.

    TeX is returned raw (not HTML-escaped): escaping must only be applied to
    the text segments, otherwise KaTeX sees '&lt;' and fails to parse.
    """
    segments = []
    pos = 0
    for m in MATH_RE.finditer(text):
        if m.start() > pos:
            segments.append(('text', text[pos:m.start()], False))
        if m.group('dd') is not None:
            segments.append(('math', m.group('dd').strip(), True))
        elif m.group('bd') is not None:
            segments.append(('math', m.group('bd').strip(), True))
        elif m.group('bi') is not None:
            segments.append(('math', m.group('bi').strip(), False))
        else:
            segments.append(('math', m.group('di').strip(), False))
        pos = m.end()
    if pos < len(text):
        segments.append(('text', text[pos:], False))
    return segments


def text_to_html(text: str) -> str:
    """Escape a non-math text segment; support markdown images and line breaks."""
    out = []
    pos = 0
    for m in IMAGE_RE.finditer(text):
        out.append(_escape_text(text[pos:m.start()]))
        url = m.group('url')
        if re.match(r'^(https?:|data:image/)', url, re.I):
            out.append('<img src="%s" alt="%s">' % (html.escape(url, quote=True),
                                                    html.escape(m.group('alt'), quote=True)))
        else:
            out.append(_escape_text(m.group(0)))
        pos = m.end()
    out.append(_escape_text(text[pos:]))
    return ''.join(out)


def _escape_text(s: str) -> str:
    return html.escape(s.replace('\\$', '$'), quote=False).replace('\n', '<br>\n')


def collect_formulas(texts: Iterable[str]) -> List[Tuple[str, bool]]:
    formulas = []
    for t in texts:
        formulas.extend((tex, display) for kind, tex, display in split_math(t) if kind == 'math')
    return formulas


def render_rich_text(text: str, rendered: Iterable[str]) -> str:
    """Join escaped text segments with pre-rendered formula HTML (consumed in order)."""
    it = iter(rendered)
    parts = []
    for kind, value, _display in split_math(text):
        parts.append(next(it) if kind == 'math' else text_to_html(value))
    return ''.join(parts)


PAGE_CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", serif;
       line-height: 1.8; color: #222; }
.hw-title { font-size: 20px; font-weight: bold; text-align: center; margin-bottom: 4px; }
.hw-meta { font-size: 13px; color: #666; text-align: center; margin-bottom: 20px; }
.exercise { page-break-after: always; margin-bottom: 30px; }
.exercise:last-child { page-break-after: auto; }
.ex-header { font-size: 16px; font-weight: bold; margin-bottom: 12px; }
.ex-body { font-size: 15px; margin-bottom: 15px; }
.ex-body img { max-width: 100%; }
.sub-q { margin-left: 2em; margin-bottom: 8px; }
.answer-space { border-bottom: 1px dashed #ccc; height: 250px; margin-top: 10px; }
"""


def build_homework_html(title: str, exercises: Sequence[Dict[str, Any]], renderer: Renderer,
                        meta: str = '') -> Tuple[str, int]:
    """Build a self-contained, JavaScript-free HTML document.

    Returns (html, formula_count). `renderer` turns [(tex, display)] into
    rendered HTML strings plus the KaTeX CSS; it is injected for testability.
    """
    structured = [(ex, extract_questions(ex)) for ex in exercises if isinstance(ex, dict)]
    texts = []
    for _ex, blocks in structured:
        for b in blocks:
            texts.append(b['main'])
            texts.extend(b['subs'])
    formulas = collect_formulas(texts)
    if formulas:
        rendered, css = renderer(formulas)
        if len(rendered) != len(formulas):
            raise ExportError('Renderer returned %d results for %d formulas'
                              % (len(rendered), len(formulas)), EXIT_RENDER)
    else:
        rendered, css = [], ''
    it = iter(rendered)

    body = []
    for i, (ex, blocks) in enumerate(structured, 1):
        header = '第 %d 题' % i
        if ex.get('questionNum') not in (None, ''):
            header += '（%s）' % html.escape(str(ex['questionNum']))
        if ex.get('score') not in (None, ''):
            header += ' <span class="score">[%s 分]</span>' % html.escape(str(ex['score']))
        body.append('<div class="exercise">\n<div class="ex-header">%s</div>\n<div class="ex-body">'
                    % header)
        for b in blocks:
            if b['main']:
                body.append('<p>%s</p>' % render_rich_text(b['main'], it))
            for j, sub in enumerate(b['subs'], 1):
                body.append('<p class="sub-q">（%d）%s</p>' % (j, render_rich_text(sub, it)))
        body.append('</div>\n<div class="answer-space"></div>\n</div>')

    safe_title = html.escape(title)
    doc = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
           '<title>%s</title>\n<style>\n%s\n%s\n</style>\n</head>\n<body>\n'
           '<div class="hw-title">%s</div>\n%s%s\n</body>\n</html>\n') % (
        safe_title, css, PAGE_CSS, safe_title,
        '<div class="hw-meta">%s</div>\n' % html.escape(meta) if meta else '',
        '\n'.join(body))
    return doc, len(formulas)


_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_filename(name: str, used: Optional[set] = None, max_len: int = 80) -> str:
    """Make a filesystem-safe, non-empty, unique (within `used`) base name."""
    base = _UNSAFE_FILENAME.sub('_', name or '').strip().replace(' ', '_').strip('._')
    base = base[:max_len] or 'homework'
    if used is None:
        return base
    candidate, n = base, 2
    while candidate in used:
        candidate = '%s_%d' % (base, n)
        n += 1
    used.add(candidate)
    return candidate


# ---------------------------------------------------------------------------
# Side-effecting helpers (network, keychain, node, chrome)
# ---------------------------------------------------------------------------

def _request_json(session, method: str, url: str, verify: bool, timeout: int, **kwargs) -> Any:
    import requests  # imported lazily so pure functions work without it

    try:
        resp = session.request(method, url, verify=verify, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise ExportError('Network error calling %s: %s' % (url, exc), EXIT_API)
    if resp.status_code in (401, 403):
        raise ExportError('Authentication failed (HTTP %d) at %s' % (resp.status_code, url), EXIT_API)
    if resp.status_code >= 400:
        raise ExportError('HTTP %d from %s' % (resp.status_code, url), EXIT_API)
    try:
        return resp.json()
    except ValueError:
        raise ExportError('Non-JSON response from %s' % url, EXIT_API)


def fetch_unsubmitted(session, school: Optional[str], school_code: Optional[str],
                      student_id: str, password: str, verify: bool = True):
    """Run the API workflow. Returns (school_code, unsubmitted, courses)."""
    if not school_code:
        schools = parse_schools(_request_json(session, 'GET', SCHOOLS_API, verify, 30))
        school_code = find_school_code(schools, school or '')
    school_user_id = '%s-%s' % (school_code, student_id)
    login_resp = _request_json(session, 'POST', LOGIN_API, verify, 30, json={
        'schoolCode': school_code,
        'schoolUserLocalId': student_id,
        'schoolUserId': school_user_id,
        'password': password,
    })
    token = extract_token(login_resp)
    data = _request_json(session, 'POST', QUERY_HOMEWORKS_API, verify, 120,
                         headers={'Authorization': 'Bearer ' + token},
                         json={'studentId': school_user_id})
    homeworks, courses = flatten_homeworks(data)
    return school_code, select_unsubmitted(homeworks), courses


def keychain_password(account: str) -> str:
    if sys.platform != 'darwin' or not shutil.which('security'):
        raise ExportError('--keychain is only supported on macOS', EXIT_USAGE)
    result = subprocess.run(['security', 'find-generic-password', '-a', account,
                             '-s', KEYCHAIN_SERVICE, '-w'], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ExportError('No Keychain item for account "%s" service "%s". Add one with:\n'
                          '  security add-generic-password -a "%s" -s "%s" -w'
                          % (account, KEYCHAIN_SERVICE, account, KEYCHAIN_SERVICE), EXIT_USAGE)
    return result.stdout.rstrip('\n')


def resolve_password(args: argparse.Namespace, stdin=None, environ=None) -> str:
    environ = os.environ if environ is None else environ
    if args.password_stdin:
        pw = (stdin or sys.stdin).readline().rstrip('\r\n')
    elif environ.get('SMARTESTU_PASSWORD'):
        pw = environ['SMARTESTU_PASSWORD']
    elif args.keychain:
        pw = keychain_password(args.student_id)
    else:
        pw = args.password or ''
    if not pw:
        raise ExportError('No password given. Use --password-stdin, $SMARTESTU_PASSWORD, '
                          '--keychain or --password.', EXIT_USAGE)
    return pw


def ensure_katex_installed(install: bool = True) -> None:
    if (REPO_ROOT / 'node_modules' / 'katex' / 'package.json').exists():
        return
    npm = shutil.which('npm')
    if not install or not npm:
        raise ExportError('The katex npm package is not installed. Run "npm ci" in %s' % REPO_ROOT,
                          EXIT_RENDER)
    print('Installing katex (npm ci) in %s ...' % REPO_ROOT, file=sys.stderr)
    cmd = [npm, 'ci'] if (REPO_ROOT / 'package-lock.json').exists() else [npm, 'install']
    result = subprocess.run(cmd + ['--no-audit', '--no-fund'], cwd=str(REPO_ROOT),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise ExportError('npm failed:\n%s' % result.stderr.strip(), EXIT_RENDER)


def make_node_renderer(node: str = 'node', script: Path = RENDER_SCRIPT,
                       timeout: int = 120) -> Renderer:
    """Return a Renderer that calls render_katex.js once per batch of formulas."""
    def render(formulas: List[Tuple[str, bool]]) -> Tuple[List[str], str]:
        request = json.dumps({'formulas': [{'tex': t, 'display': d} for t, d in formulas]},
                             ensure_ascii=False)
        try:
            result = subprocess.run([node, str(script)], input=request, capture_output=True,
                                    text=True, timeout=timeout, encoding='utf-8')
        except FileNotFoundError:
            raise ExportError('Node.js not found (%s). Install Node.js 18+.' % node, EXIT_RENDER)
        except subprocess.TimeoutExpired:
            raise ExportError('render_katex.js timed out after %ds' % timeout, EXIT_RENDER)
        if result.returncode != 0:
            raise ExportError('render_katex.js failed: %s' % result.stderr.strip(), EXIT_RENDER)
        try:
            data = json.loads(result.stdout)
            return list(data['html']), str(data['css'])
        except (ValueError, KeyError, TypeError):
            raise ExportError('render_katex.js returned invalid JSON', EXIT_RENDER)
    return render


def find_chrome(explicit: Optional[str] = None, environ=None) -> Optional[str]:
    environ = os.environ if environ is None else environ
    for candidate in (explicit, environ.get('CHROME_PATH')) + CHROME_CANDIDATES:
        if not candidate:
            continue
        if os.path.isabs(candidate):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found
    return None


def export_pdf(chrome: str, html_path: Path, pdf_path: Path, timeout: int = 120) -> None:
    """Print pre-rendered HTML to PDF and verify a fresh, valid PDF was written."""
    if pdf_path.exists():
        pdf_path.unlink()  # never mistake a stale PDF from an earlier run for success
    # Note: do not pass a fresh --user-data-dir; on macOS that makes Chrome hang after printing.
    cmd = [chrome, '--headless', '--disable-gpu', '--no-pdf-header-footer',
           '--print-to-pdf-no-header', '--print-to-pdf=%s' % pdf_path, html_path.resolve().as_uri()]
    try:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ExportError('Chrome timed out after %ds printing %s' % (timeout, html_path), EXIT_PDF)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise ExportError('Chrome did not produce %s: %s' % (pdf_path, result.stderr.strip()[-500:]),
                          EXIT_PDF)
    with pdf_path.open('rb') as fh:
        if fh.read(5) != b'%PDF-':
            raise ExportError('%s is not a valid PDF' % pdf_path, EXIT_PDF)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='export_homework_pdf.py',
        description='Export unsubmitted smartestu.cn (数你最灵) homework to KaTeX-rendered PDFs.',
        epilog='Exit codes: 0 ok, 1 unexpected error, 2 usage, 3 network/auth/API, '
               '4 formula rendering, 5 PDF export.',
    )
    src = p.add_argument_group('homework source')
    src.add_argument('--school-name', help='School name as listed by /api/schools (e.g. the Chinese name)')
    src.add_argument('--school-code', help='School code; skips the /api/schools lookup')
    src.add_argument('--student-id', help='Student local id (without the school prefix)')
    src.add_argument('--from-json', type=Path, metavar='FILE',
                     help='Offline mode: read a saved queryHomeworks response instead of logging in')
    pw = p.add_argument_group('password (first match wins)')
    pw.add_argument('--password-stdin', action='store_true', help='Read the password from stdin')
    pw.add_argument('--keychain', action='store_true',
                    help='Read the password from macOS Keychain (service "smartestu.cn", account = student id)')
    pw.add_argument('--password', help='Password on the command line (discouraged); '
                                       '$SMARTESTU_PASSWORD is also honoured')
    out = p.add_argument_group('output')
    out.add_argument('--out-dir', type=Path,
                     default=Path(tempfile.gettempdir()) / 'smartestu-export',
                     help='Output directory (default: %(default)s)')
    out.add_argument('--latest-only', action='store_true',
                     help='Export only the unsubmitted homework with the latest deadline')
    out.add_argument('--no-pdf', action='store_true', help='Write HTML only, skip Chrome')
    out.add_argument('--chrome', help='Path to Chrome/Chromium (default: auto-detect, or $CHROME_PATH)')
    out.add_argument('--node', default='node', help='Node.js executable (default: %(default)s)')
    out.add_argument('--no-install', action='store_true',
                     help='Do not run "npm ci" automatically if katex is missing')
    p.add_argument('--insecure', action='store_true', help='Disable TLS certificate verification')
    return p


def run(args: argparse.Namespace, session=None, renderer: Optional[Renderer] = None) -> Dict[str, Any]:
    if args.from_json:
        try:
            data = json.loads(args.from_json.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ExportError('Cannot read %s: %s' % (args.from_json, exc), EXIT_USAGE)
        homeworks, courses = flatten_homeworks(data)
        unsubmitted = select_unsubmitted(homeworks)
        school_code = args.school_code
    else:
        if not args.student_id or not (args.school_name or args.school_code):
            raise ExportError('--student-id and one of --school-name/--school-code are required '
                              '(or use --from-json)', EXIT_USAGE)
        password = resolve_password(args)
        if session is None:
            import requests
            session = requests.Session()
        if args.insecure:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        school_code, unsubmitted, courses = fetch_unsubmitted(
            session, args.school_name, args.school_code, args.student_id, password,
            verify=not args.insecure)

    summary = {
        'status': 'ok' if unsubmitted else 'no_unsubmitted',
        'school_code': school_code,
        'unsubmitted_count': len(unsubmitted),
        'courses_checked': courses,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'homeworks': [],
    }
    if not unsubmitted:
        return summary
    if args.latest_only:
        unsubmitted = unsubmitted[:1]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if renderer is None:
        ensure_katex_installed(install=not args.no_install)
        renderer = make_node_renderer(args.node)
    chrome = None
    if not args.no_pdf:
        chrome = find_chrome(args.chrome)
        if not chrome:
            raise ExportError('Chrome/Chromium not found. Install it, pass --chrome PATH, '
                              'set $CHROME_PATH, or use --no-pdf.', EXIT_PDF)

    used = set()
    for hw in unsubmitted:
        name = str(hw.get('name') or 'homework')
        base = safe_filename(name, used)
        html_path = args.out_dir / (base + '.html')
        pdf_path = args.out_dir / (base + '.pdf')
        exercises = [e for e in hw.get('exercises') or [] if isinstance(e, dict)]
        meta = ' · '.join(x for x in (str(hw.get('courseName') or ''),
                                      ('截止 %s' % hw['endTime']) if hw.get('endTime') else '') if x)
        doc, formula_count = build_homework_html(name, exercises, renderer, meta=meta)
        html_path.write_text(doc, encoding='utf-8')
        if chrome:
            export_pdf(chrome, html_path, pdf_path)
        summary['homeworks'].append({
            'homework_name': name,
            'course': hw.get('courseName') or '',
            'endTime': hw.get('endTime') or '',
            'exercise_count': len(exercises),
            'formula_count': formula_count,
            'html': str(html_path),
            'pdf': str(pdf_path) if chrome else None,
            'pdf_size': pdf_path.stat().st_size if chrome else None,
        })

    (args.out_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run(args)
    except ExportError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
