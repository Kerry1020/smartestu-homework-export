#!/usr/bin/env python3
"""Export unsubmitted homework from smartestu.cn as KaTeX-rendered PDF.

Pipeline:
  1. API: login → query homeworks → extract unsubmitted
  2. Save exercises JSON
  3. Node.js katex (scripts/render_katex.js): server-side render formulas → self-contained HTML (no JS)
  4. Chrome headless --print-to-pdf: HTML → PDF

CRITICAL: Chrome headless --print-to-pdf does NOT execute JavaScript.
All KaTeX rendering must happen server-side (Step 3), NOT in a <script> tag.

Usage:
  python3 export_homework_pdf.py \\
    --school-name "<school_name>" \\
    --student-id "<student_local_id>" \\
    --password "$(security find-generic-password -a '<student_local_id>' -s 'smartestu.cn' -w)" \\
    --out-dir /tmp/smartestu-export
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import requests

SCHOOLS_API = 'https://smartestu.cn/api/schools'
LOGIN_API = 'https://smartestu.cn/api/auth/login'
QUERY_HOMEWORKS_API = 'https://smartestu.cn/api/homework/student/mark/queryHomeworks'

# Path to the server-side KaTeX renderer (lives next to this script)
RENDER_SCRIPT = Path(__file__).parent / 'render_katex.js'

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


def get_school_code(session, school_name):
    """Resolve school code from human-readable name."""
    data = session.get(SCHOOLS_API, verify=False, timeout=30).json()
    schools = data.get('schools', data.get('data', {}).get('schools', []))
    for school in schools:
        if school.get('name') == school_name:
            return school.get('code')
    # Fallback: print all schools so user can pick
    available = ', '.join(s.get('name', '?') for s in schools)
    raise SystemExit(f'School not found: {school_name}. Available: {available}')


def login(session, school_code, student_local_id, password):
    """Login and return full response. Token is at TOP LEVEL, not under 'data'."""
    payload = {
        'schoolCode': school_code,
        'schoolUserLocalId': student_local_id,
        'schoolUserId': f'{school_code}-{student_local_id}',
        'password': password,
    }
    resp = session.post(LOGIN_API, json=payload, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_all_unsubmitted(session, token, school_user_id):
    """Query homework list and return ALL unsubmitted items sorted by deadline."""
    headers = {'Authorization': f'Bearer {token}'}
    payload = {'studentId': school_user_id}
    resp = session.post(QUERY_HOMEWORKS_API, headers=headers, json=payload, verify=False, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    homeworks = []
    courses_seen = []
    for course in data.get('data', {}).get('courseHomeworkDTOList', []):
        courses_seen.append(course.get('courseName', '?'))
        for hw in course.get('studentCourseHomeworkDTOList', []):
            item = dict(hw)
            item['courseName'] = course.get('courseName')
            homeworks.append(item)

    unsubmitted = [
        h for h in homeworks
        if h.get('submission_status') == 'not_submitted' or h.get('status') == 0
    ]
    unsubmitted.sort(key=lambda x: x.get('endTime', ''), reverse=True)
    return unsubmitted, courses_seen


def render_html_server_side(exercises, title, output_path):
    """Use Node.js katex to pre-render all formulas into self-contained HTML.

    This is REQUIRED because Chrome headless --print-to-pdf does NOT execute JavaScript.
    Browser-side KaTeX (renderMathInElement in <script>) will NOT appear in the PDF.
    """
    # Save exercises JSON for Node
    exercises_path = str(output_path).replace('.html', '.exercises.json')
    Path(exercises_path).write_text(json.dumps(exercises, ensure_ascii=False), encoding='utf-8')

    # Run Node.js renderer
    result = subprocess.run(
        ['node', str(RENDER_SCRIPT),
         '--input', exercises_path,
         '--output', str(output_path),
         '--title', title],
        capture_output=True, text=True, timeout=30,
        cwd=str(Path(output_path).parent),  # node needs katex module installed here
    )
    if result.returncode != 0:
        print(f'render_katex.js failed: {result.stderr}', file=sys.stderr)
        raise SystemExit(1)
    print(result.stderr.strip(), file=sys.stderr)
    return output_path


def export_pdf(html_path, pdf_path):
    """Export pre-rendered HTML to PDF via Chrome headless."""
    if not Path(CHROME).exists():
        print(f'WARNING: Chrome not found at {CHROME}, skipping PDF export', file=sys.stderr)
        return False
    result = subprocess.run([
        CHROME, '--headless', '--disable-gpu',
        f'--print-to-pdf={pdf_path}',
        '--print-to-pdf-no-header',
        f'file://{html_path}'
    ], capture_output=True, timeout=30)
    return Path(pdf_path).exists()


def main():
    parser = argparse.ArgumentParser(description='Export smartestu homework to PDF')
    parser.add_argument('--school-name', required=True, help='School name (resolved via /api/schools)')
    parser.add_argument('--student-id', required=True, help='Student local ID')
    parser.add_argument('--password', required=True, help='Password (do not log this)')
    parser.add_argument('--out-dir', default='/tmp/smartestu-export', help='Output directory')
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ensure katex is installed for Node
    node_modules = out_dir / 'node_modules' / 'katex'
    if not node_modules.exists():
        print('Installing katex...', file=sys.stderr)
        subprocess.run(['npm', 'install', 'katex@0.16.9'], check=True, capture_output=True, cwd=str(out_dir))

    # API calls
    session = requests.Session()
    school_code = get_school_code(session, args.school_name)
    login_data = login(session, school_code, args.student_id, args.password)
    token = login_data['token']  # TOP LEVEL
    school_user_id = f'{school_code}-{args.student_id}'

    unsubmitted, courses_seen = get_all_unsubmitted(session, token, school_user_id)

    if not unsubmitted:
        print(json.dumps({
            'status': 'no_unsubmitted',
            'courses_checked': courses_seen,
        }, ensure_ascii=False, indent=2))
        return

    results = []
    for hw in unsubmitted:
        hw_name = hw.get('name', 'homework')
        safe_name = hw_name.replace('/', '_').replace(' ', '_')
        html_path = out_dir / f'{safe_name}.html'
        pdf_path = out_dir / f'{safe_name}.pdf'

        # Step 1: Server-side KaTeX rendering → self-contained HTML
        exercises = hw.get('exercises', [])
        render_html_server_side(exercises, hw_name, html_path)

        # Step 2: Chrome headless HTML → PDF
        pdf_ok = export_pdf(str(html_path), str(pdf_path))

        results.append({
            'homework_name': hw_name,
            'course': hw.get('courseName', ''),
            'endTime': hw.get('endTime', ''),
            'exercise_count': len(exercises),
            'html': str(html_path),
            'pdf': str(pdf_path) if pdf_ok else None,
            'pdf_exported': pdf_ok,
        })

    summary = {
        'school_code': school_code,
        'unsubmitted_count': len(unsubmitted),
        'courses_checked': courses_seen,
        'generated_at': datetime.now().isoformat(),
        'homeworks': results,
    }
    summary_path = out_dir / 'summary.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
