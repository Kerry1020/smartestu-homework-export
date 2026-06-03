#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path
from datetime import datetime

import requests

SCHOOLS_API = 'https://smartestu.cn/api/schools'
LOGIN_API = 'https://smartestu.cn/api/auth/login'
QUERY_HOMEWORKS_API = 'https://smartestu.cn/api/homework/student/mark/queryHomeworks'


def get_school_code(session: requests.Session, school_name: str) -> str:
    data = session.get(SCHOOLS_API, verify=False, timeout=30).json()
    for school in data.get('schools', []):
        if school.get('name') == school_name:
            return school.get('code')
    raise SystemExit(f'School not found: {school_name}')


def login(session: requests.Session, school_code: str, student_local_id: str, password: str):
    payload = {
        'schoolCode': school_code,
        'schoolUserLocalId': student_local_id,
        'schoolUserId': f'{school_code}-{student_local_id}',
        'password': password,
    }
    resp = session.post(LOGIN_API, json=payload, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_latest_unsubmitted(session: requests.Session, token: str, school_code: str, student_local_id: str):
    headers = {'Authorization': f'Bearer {token}'}
    payload = {'studentId': f'{school_code}-{student_local_id}'}
    resp = session.post(QUERY_HOMEWORKS_API, headers=headers, json=payload, verify=False, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    homeworks = []
    for course in data.get('data', {}).get('courseHomeworkDTOList', []):
        for hw in course.get('studentCourseHomeworkDTOList', []):
            item = dict(hw)
            item['courseName'] = course.get('courseName')
            homeworks.append(item)
    unsubmitted = [h for h in homeworks if h.get('submission_status') == 'not_submitted']
    if not unsubmitted:
        raise SystemExit('No unsubmitted homework found')
    unsubmitted.sort(key=lambda x: x.get('endTime', ''), reverse=True)
    return unsubmitted[0]


def build_rendered_html(homework: dict) -> str:
    blocks = []
    for idx, ex in enumerate(homework.get('exercises', []), start=1):
        questions = ex.get('questions') or [{'type': 'text', 'content': ex.get('name', '(无题目内容)')}]
        content = '\n\n'.join([
            str(q.get('content', '')).strip()
            for q in questions
            if str(q.get('content', '')).strip()
        ])
        if not content:
            content = ex.get('name', '(无题目内容)')
        safe = html.escape(content).replace('\n', '<br>').replace('&amp;nbsp;', '&nbsp;')
        blocks.append(
            '<section class="question-card">\n'
            f'  <div class="q-head">题目 {idx} <span class="q-sub">小题编号：{html.escape(str(ex.get("questionNum", "")))}</span></div>\n'
            f'  <div class="q-body">{safe}</div>\n'
            '</section>'
        )

    homework_name = html.escape(str(homework.get('name', '')))
    course_name = html.escape(str(homework.get('courseName', '')))
    exercise_count = len(homework.get('exercises', []))
    html_doc = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>未提交作业题目（公式渲染版）</title>
  <script>
    window.__math_ready = false;
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
      }},
      svg: {{ fontCache: 'global' }},
      startup: {{
        pageReady: () => {{
          return MathJax.startup.defaultPageReady().then(() => {{
            window.__math_ready = true;
          }});
        }}
      }}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif; background:#f6f7fb; color:#111; margin:0; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 40px 24px 80px; }}
    .title {{ font-size: 32px; font-weight: 700; margin-bottom: 10px; }}
    .meta {{ color:#555; font-size: 16px; margin-bottom: 28px; }}
    .question-card {{ background:#fff; border-radius:16px; box-shadow:0 6px 24px rgba(0,0,0,.06); padding:24px 28px; margin-bottom:20px; page-break-inside: avoid; }}
    .q-head {{ font-size:22px; font-weight:700; margin-bottom:16px; }}
    .q-sub {{ font-size:14px; color:#666; font-weight:500; margin-left:12px; }}
    .q-body {{ font-size:20px; line-height:1.85; word-break:break-word; color:#111; }}
    .q-body mjx-container, .q-body svg, .q-body path, .q-body use {{ color:#111 !important; fill:#111 !important; stroke:#111 !important; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">未提交作业题目（公式渲染版）</div>
    <div class="meta">作业：{homework_name} ｜ 课程：{course_name} ｜ 共 {exercise_count} 题</div>
    {''.join(blocks)}
  </div>
</body>
</html>'''
    return html_doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--school-name', required=True)
    parser.add_argument('--student-id', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--out-dir', default='/tmp/openclaw/smartestu-export')
    args = parser.parse_args()

    session = requests.Session()
    school_code = get_school_code(session, args.school_name)
    login_data = login(session, school_code, args.student_id, args.password)
    homework = get_latest_unsubmitted(session, login_data['token'], school_code, args.student_id)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered = build_rendered_html(homework)
    (out_dir / 'rendered.html').write_text(rendered, encoding='utf-8')
    (out_dir / 'homework.json').write_text(json.dumps(homework, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {
        'school_code': school_code,
        'homework_id': homework.get('id'),
        'homework_name': homework.get('name'),
        'course_name': homework.get('courseName'),
        'exercise_count': len(homework.get('exercises', [])),
        'generated_at': datetime.now().isoformat(),
        'rendered_html': str(out_dir / 'rendered.html'),
        'raw_json': str(out_dir / 'homework.json'),
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
