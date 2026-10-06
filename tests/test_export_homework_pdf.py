import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import export_homework_pdf as ehp
from export_homework_pdf import ExportError


def fake_renderer(calls=None):
    """Renders each formula as <m d=0|1>tex</m> with the TeX HTML-escaped."""
    def render(formulas):
        if calls is not None:
            calls.append(list(formulas))
        import html
        return ['<m d=%d>%s</m>' % (int(d), html.escape(t)) for t, d in formulas], '/*css*/'
    return render


# --- API parsing ---------------------------------------------------------

@pytest.mark.parametrize('data', [
    {'schools': [{'name': 'A', 'code': 'a'}]},
    {'data': {'schools': [{'name': 'A', 'code': 'a'}]}},
    {'data': [{'name': 'A', 'code': 'a'}]},
    [{'name': 'A', 'code': 'a'}],
])
def test_parse_schools_shapes(data):
    assert ehp.parse_schools(data) == [{'name': 'A', 'code': 'a'}]


def test_parse_schools_bad_shape():
    with pytest.raises(ExportError) as e:
        ehp.parse_schools({'oops': 1})
    assert e.value.exit_code == ehp.EXIT_API


SCHOOLS = [{'name': '示例大学', 'code': 'sl'}, {'name': '示例理工大学', 'code': 'slg'},
           {'name': '另一学院', 'code': 'other'}]


def test_find_school_code_exact_name_code_and_partial():
    assert ehp.find_school_code(SCHOOLS, '示例大学') == 'sl'
    assert ehp.find_school_code(SCHOOLS, 'slg') == 'slg'
    assert ehp.find_school_code(SCHOOLS, '另一') == 'other'


def test_find_school_code_ambiguous_and_missing():
    with pytest.raises(ExportError, match='ambiguous'):
        ehp.find_school_code(SCHOOLS, '示例')
    with pytest.raises(ExportError, match='not found') as e:
        ehp.find_school_code(SCHOOLS, 'nowhere')
    assert e.value.exit_code == ehp.EXIT_USAGE


def test_extract_token():
    assert ehp.extract_token({'token': 'abc'}) == 'abc'
    assert ehp.extract_token({'data': {'token': 'nested'}}) == 'nested'
    with pytest.raises(ExportError, match='wrong password'):
        ehp.extract_token({'message': 'wrong password'})
    with pytest.raises(ExportError, match='no token'):
        ehp.extract_token({})


def homework_response():
    return {'data': {'courseHomeworkDTOList': [
        {'courseName': '概率论', 'studentCourseHomeworkDTOList': [
            {'name': 'hw1', 'submission_status': 'submitted', 'status': 1, 'endTime': '2026-01-01'},
            {'name': 'hw2', 'submission_status': 'not_submitted', 'endTime': '2026-03-01'},
        ]},
        {'courseName': '线代', 'studentCourseHomeworkDTOList': [
            {'name': 'hw3', 'status': 0, 'endTime': '2026-05-01'},
            {'name': 'hw4', 'status': 0, 'endTime': None},
        ]},
        {'courseName': '空课', 'studentCourseHomeworkDTOList': None},
    ]}}


def test_flatten_and_select():
    homeworks, courses = ehp.flatten_homeworks(homework_response())
    assert courses == ['概率论', '线代', '空课']
    assert len(homeworks) == 4
    assert homeworks[0]['courseName'] == '概率论'
    selected = ehp.select_unsubmitted(homeworks)
    # None endTime must not crash sorting and sorts last.
    assert [h['name'] for h in selected] == ['hw3', 'hw2', 'hw4']


def test_flatten_rejects_missing_data():
    with pytest.raises(ExportError, match='token expired'):
        ehp.flatten_homeworks({'data': None, 'message': 'token expired'})


# --- question extraction -------------------------------------------------

def test_extract_questions_uses_all_structure_entries_and_subs():
    ex = {'questionStructure': [
        {'mainQuestion': {'questionMd': 'Main 1'}, 'subQuestions': [
            {'questionMd': 'a'}, {'questionMd': ''}, {'questionMd': 'b'}]},
        {'mainQuestion': {'questionMd': 'Main 2'}},
    ], 'questions': [{'content': 'ignored'}]}
    assert ehp.extract_questions(ex) == [
        {'main': 'Main 1', 'subs': ['a', 'b']}, {'main': 'Main 2', 'subs': []}]


def test_extract_questions_fallbacks():
    assert ehp.extract_questions({'questionStructure': [{'mainQuestion': {}}],
                                  'questions': [{'content': 'Q'}]}) == [{'main': 'Q', 'subs': []}]
    assert ehp.extract_questions({'name': 'Only name'}) == [{'main': 'Only name', 'subs': []}]
    assert ehp.extract_questions({}) == []


# --- math splitting / escaping -------------------------------------------

def test_split_math_delimiters():
    segs = ehp.split_math(r'a $x<1$ b $$\sum$$ c \(y\) d \[z\] e')
    assert [s for s in segs if s[0] == 'math'] == [
        ('math', 'x<1', False), ('math', r'\sum', True),
        ('math', 'y', False), ('math', 'z', True)]


def test_split_math_ignores_escaped_dollar():
    assert ehp.split_math(r'costs \$5 and \$6') == [('text', r'costs \$5 and \$6', False)]


def test_tex_is_not_html_escaped_but_text_is():
    html_out = ehp.render_rich_text(r'1<2 & $P\{1<X<3\}$', iter(['<R>']))
    assert html_out == '1&lt;2 &amp; <R>'
    assert ehp.collect_formulas([r'$P\{1<X<3\}$']) == [(r'P\{1<X<3\}', False)]


def test_text_to_html_images_and_newlines():
    out = ehp.text_to_html('line1\nsee ![fig](https://x.test/a.png?a=1&b=2) <b>')
    assert '<br>' in out
    assert '<img src="https://x.test/a.png?a=1&amp;b=2" alt="fig">' in out
    assert '&lt;b&gt;' in out
    # non-http(s) image URLs are left as escaped text
    assert '<img' not in ehp.text_to_html('![x](javascript:alert(1))')


# --- HTML building -------------------------------------------------------

def test_build_homework_html():
    calls = []
    exercises = [
        {'questionNum': 1, 'score': 10, 'questionStructure': [
            {'mainQuestion': {'questionMd': '设 $X<Y$，求'}, 'subQuestions': [{'questionMd': '$$E[X]$$'}]}]},
        {'questions': [{'content': 'no math <here>'}]},
    ]
    doc, count = ehp.build_homework_html('作业 <1>', exercises, fake_renderer(calls), meta='概率论')
    assert count == 2
    assert calls == [[('X<Y', False), ('E[X]', True)]]  # one batched call, raw TeX
    assert '<title>作业 &lt;1&gt;</title>' in doc
    assert '<m d=0>X&lt;Y</m>' in doc and '<m d=1>E[X]</m>' in doc
    assert '（1）<m d=1>' in doc
    assert '第 1 题（1） <span class="score">[10 分]</span>' in doc
    assert 'no math &lt;here&gt;' in doc
    assert '/*css*/' in doc and '概率论' in doc
    assert '<script' not in doc
    assert doc.count('class="exercise"') == 2


def test_build_homework_html_skips_renderer_without_formulas():
    def boom(_):
        raise AssertionError('renderer should not be called')
    doc, count = ehp.build_homework_html('t', [{'name': 'plain'}], boom)
    assert count == 0 and 'plain' in doc


def test_build_homework_html_renderer_count_mismatch():
    with pytest.raises(ExportError) as e:
        ehp.build_homework_html('t', [{'name': '$a$ $b$'}], lambda f: (['x'], ''))
    assert e.value.exit_code == ehp.EXIT_RENDER


def test_safe_filename():
    used = set()
    assert ehp.safe_filename('第 15 周/作业:1?', used) == '第_15_周_作业_1'
    assert ehp.safe_filename('第 15 周/作业:1?', used) == '第_15_周_作业_1_2'
    assert ehp.safe_filename('..', None) == 'homework'
    assert len(ehp.safe_filename('x' * 300)) == 80


# --- password / chrome / renderer subprocess -----------------------------

def ns(**kw):
    base = dict(password_stdin=False, keychain=False, password=None, student_id='s1')
    base.update(kw)
    return SimpleNamespace(**base)


def test_resolve_password_priority():
    assert ehp.resolve_password(ns(password_stdin=True, password='cli'),
                                stdin=io.StringIO('fromstdin\n'), environ={}) == 'fromstdin'
    assert ehp.resolve_password(ns(password='cli'), environ={'SMARTESTU_PASSWORD': 'env'}) == 'env'
    assert ehp.resolve_password(ns(password='cli'), environ={}) == 'cli'
    with pytest.raises(ExportError) as e:
        ehp.resolve_password(ns(), environ={})
    assert e.value.exit_code == ehp.EXIT_USAGE


def test_find_chrome(tmp_path, monkeypatch):
    exe = tmp_path / 'chrome'
    exe.write_text('#!/bin/sh\n')
    exe.chmod(0o755)
    monkeypatch.setattr(ehp, 'CHROME_CANDIDATES', ())
    assert ehp.find_chrome(str(exe), environ={}) == str(exe)
    assert ehp.find_chrome(None, environ={'CHROME_PATH': str(exe)}) == str(exe)
    assert ehp.find_chrome(None, environ={}) is None


def test_node_renderer_parses_output(monkeypatch):
    seen = {}

    def fake_run(cmd, input, **kw):
        seen['req'] = json.loads(input)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({'html': ['<k>'], 'css': 'c'}), '')
    monkeypatch.setattr(ehp.subprocess, 'run', fake_run)
    assert ehp.make_node_renderer()([('x<1', False)]) == (['<k>'], 'c')
    assert seen['req'] == {'formulas': [{'tex': 'x<1', 'display': False}]}


def test_node_renderer_failure(monkeypatch):
    monkeypatch.setattr(ehp.subprocess, 'run',
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, '', 'boom'))
    with pytest.raises(ExportError, match='boom') as e:
        ehp.make_node_renderer()([('x', False)])
    assert e.value.exit_code == ehp.EXIT_RENDER


# --- end-to-end with mocked network --------------------------------------

class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, login=None):
        self.calls = []
        self.login = login if login is not None else {'token': 'T'}

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if url == ehp.SCHOOLS_API:
            return FakeResp({'schools': SCHOOLS})
        if url == ehp.LOGIN_API:
            return FakeResp(self.login)
        if url == ehp.QUERY_HOMEWORKS_API:
            return FakeResp(homework_response())
        raise AssertionError(url)


def cli_args(tmp_path, *extra):
    return ehp.build_parser().parse_args(
        ['--school-name', '示例大学', '--student-id', '123', '--password', 'pw',
         '--out-dir', str(tmp_path), '--no-pdf'] + list(extra))


def test_fetch_unsubmitted_payloads():
    s = FakeSession()
    code, unsub, courses = ehp.fetch_unsubmitted(s, '示例大学', None, '123', 'pw')
    assert code == 'sl' and len(unsub) == 3
    _, _, login_kw = s.calls[1]
    assert login_kw['json']['schoolUserId'] == 'sl-123'
    assert login_kw['verify'] is True
    _, _, query_kw = s.calls[2]
    assert query_kw['json'] == {'studentId': 'sl-123'}
    assert query_kw['headers']['Authorization'] == 'Bearer T'


def test_run_writes_html_and_summary(tmp_path):
    summary = ehp.run(cli_args(tmp_path), session=FakeSession(), renderer=fake_renderer())
    assert summary['status'] == 'ok' and summary['unsubmitted_count'] == 3
    assert [h['homework_name'] for h in summary['homeworks']] == ['hw3', 'hw2', 'hw4']
    assert Path(summary['homeworks'][0]['html']).exists()
    assert json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))['unsubmitted_count'] == 3


def test_run_latest_only(tmp_path):
    summary = ehp.run(cli_args(tmp_path, '--latest-only'), session=FakeSession(),
                      renderer=fake_renderer())
    assert [h['homework_name'] for h in summary['homeworks']] == ['hw3']


def test_run_from_json_offline(tmp_path):
    src = tmp_path / 'resp.json'
    src.write_text(json.dumps(homework_response()), encoding='utf-8')
    args = ehp.build_parser().parse_args(['--from-json', str(src), '--out-dir', str(tmp_path / 'o'),
                                          '--no-pdf'])
    summary = ehp.run(args, renderer=fake_renderer())
    assert summary['unsubmitted_count'] == 3


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('SMARTESTU_PASSWORD', raising=False)
    assert ehp.main(['--student-id', '1', '--school-code', 'x', '--out-dir', str(tmp_path)]) == ehp.EXIT_USAGE
    assert ehp.main(['--from-json', str(tmp_path / 'missing.json')]) == ehp.EXIT_USAGE
    with pytest.raises(SystemExit) as e:
        ehp.main(['--help'])
    assert e.value.code == 0
    assert 'Exit codes' in capsys.readouterr().out


def test_main_login_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ehp, 'run', lambda args: ehp.extract_token({'message': 'bad'}))
    assert ehp.main(['--from-json', 'x']) == ehp.EXIT_API


# --- real KaTeX (only when node + katex are installed) -------------------

KATEX_AVAILABLE = shutil.which('node') and (ehp.REPO_ROOT / 'node_modules' / 'katex').exists()


@pytest.mark.skipif(not KATEX_AVAILABLE, reason='node/katex not installed (run npm ci)')
def test_real_katex_renders_less_than_without_errors():
    doc, count = ehp.build_homework_html(
        't', [{'name': r'求 $P\{1<X<3\}$ 和 $$\int_0^1 x\,dx$$'}], ehp.make_node_renderer())
    assert count == 2
    assert doc.count('class="katex"') >= 1 and 'katex-display' in doc
    assert 'katex-error' not in doc
    assert 'file://' in doc  # fonts rewritten to local files
