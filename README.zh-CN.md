# smartestu-homework-export

[![CI](https://github.com/Kerry1020/smartestu-homework-export/actions/workflows/ci.yml/badge.svg)](https://github.com/Kerry1020/smartestu-homework-export/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

[English](README.md) | 简体中文

一个 Agent skill（Claude Code / Agent SDK 的 `SKILL.md` 格式），也可以当作独立命令行工具用：把 **smartestu.cn（数你最灵）上还没交的作业** 导出成可打印的 PDF，每题一页，公式用 KaTeX 渲染。

## 功能特性

- 直接调用 Smartestu API，不靠浏览器抓页面
- 使用当前 cookie/CSRF 会话协议，同时兼容旧版 bearer token 响应
- 读取当前学生的课程，遍历分页作业结果，并为每份未提交作业获取题目详情
- 列出全部未提交作业，按截止时间从晚到早排列，并附上检查过的课程列表
- 按原顺序导出主问题和子问题
- 打印前先渲染好 KaTeX 公式，HTML 里不含 JavaScript，Chrome headless 也能正确打印公式
- 每题下方留出 A4 作答空间
- 离线模式：不登录，直接渲染之前保存的、包含题目详情的 `queryHomeworks` 响应

本工具不是通用的 LMS 爬虫，也不会替你提交任何内容。

## 快速开始

环境要求：

- Python 3.9+
- Node.js 18+ 和 npm
- Google Chrome、Chromium 或 Microsoft Edge（只有生成 PDF 时需要）
- macOS 钥匙串（可选，用来存密码最省事）

```bash
git clone https://github.com/Kerry1020/smartestu-homework-export.git
cd smartestu-homework-export
npm ci                                    # 安装 katex 0.16.9（版本锁定在 package-lock.json）
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

没跑 `npm ci` 也没关系，脚本第一次运行时会自动执行（除非加了 `--no-install`）。

作为 skill 使用时，把整个目录（不只是 `SKILL.md`）放到 agent 加载 skills 的位置，例如 `~/.claude/skills/smartestu-homework-export/`。之后直接说“把我数你最灵没交的作业导出成 PDF”就行。

## 使用

```bash
# 先保存一次密码（macOS）。-w 后面不写密码时会提示输入。
security add-generic-password -a "<student_id>" -s "smartestu.cn" -w

.venv/bin/python scripts/export_homework_pdf.py \
  --school-name "<学校名称>" --student-id "<student_id>" --keychain \
  --out-dir ~/Desktop/homework
```

密码的其他传入方式（按顺序取第一个可用的）：`--password-stdin`、环境变量 `SMARTESTU_PASSWORD`、`--keychain`、`--password`。不建议用 `--password`，密码会出现在 `ps` 输出和 shell 历史里。

参数一览：

| 参数 | 作用 |
|---|---|
| `--school-name NAME` | 学校名称，与 `/api/schools` 中的一致（如中文校名） |
| `--school-code CODE` | 跳过按学校名称查询 |
| `--student-id ID` | 学号，不带学校前缀 |
| `--from-json FILE` | 离线模式：渲染之前保存的、包含题目详情的 `queryHomeworks` 响应 |
| `--password-stdin` / `--keychain` / `--password PW` | 密码来源（见上文） |
| `--out-dir DIR` | 输出目录（默认 `$TMPDIR/smartestu-export`） |
| `--latest-only` | 只导出截止时间最晚的一份作业 |
| `--no-pdf` | 只生成 HTML，不调用 Chrome |
| `--chrome PATH` | 浏览器路径（默认自动查找，或读取 `CHROME_PATH`） |
| `--node PATH` | Node.js 可执行文件（默认 `node`） |
| `--no-install` | 缺少 katex 时不自动运行 `npm ci` |
| `--insecure` | 关闭 TLS 证书校验（一般用不到） |

输出：每份作业生成一个 `<作业名>.html` 和一个 `<作业名>.pdf`，另有一个 `summary.json`，内容同时打印到 stdout。在支持 POSIX 权限的平台上，生成文件仅允许当前用户访问。

退出码：`0` 成功（包括“没有未提交作业”）；`1` 未预期的错误；`2` 参数错误、找不到学校、缺少密码或输入文件读不了；`3` 网络、登录或 API 错误；`4` KaTeX 渲染失败；`5` PDF 导出失败；`130` 被中断。

## 配置

| 名称 | 必需 | 敏感 | 默认值 | 说明 |
|---|---|---|---|---|
| `SMARTESTU_PASSWORD` | 否 | 是 | – | 密码；未指定 `--password-stdin` 时使用 |
| `CHROME_PATH` | 否 | 否 | 自动查找 | Chrome/Chromium/Edge 路径；`--chrome` 优先 |

钥匙串条目（`--keychain` 使用）：service 为 `smartestu.cn`，account 为学号。

## 常见问题

| 现象 | 处理方法 |
|---|---|
| `School not found` / `ambiguous` | 使用 smartestu 上显示的完整校名，或改用 `--school-code`（可以用 `curl https://smartestu.cn/api/schools` 查询） |
| `Login failed` / 退出码 3 | 检查学号（不要带学校前缀）和密码；用 `security find-generic-password -a <学号> -s smartestu.cn` 检查钥匙串条目 |
| `katex npm package is not installed` / 退出码 4 | 在仓库根目录运行 `npm ci`（或去掉 `--no-install`） |
| `Chrome/Chromium not found` / 退出码 5 | 安装 Chrome，或用 `--chrome` / `CHROME_PATH` 指定路径；也可以用 `--no-pdf` |
| Chrome 超时 | 关掉 Chrome 弹出的配置对话框后重试；不要自己加 `--user-data-dir`（在 macOS 上会让 Chrome 卡住） |
| PDF 里出现红色公式 | 说明题目源数据里这条 TeX 本身有错，可以用 `grep katex-error *.html` 定位 |
| 显示 0 份未提交，但实际应该有 | 新版 cookie-v1 流程中请检查 `courses_checked`：它来自当前账号的学生课程列表，缺少课程通常说明账号或选课信息异常；旧版 bearer 响应可能只列出作业接口返回的课程 |

## 隐私

本仓库不包含任何账号、密码、token 或个人数据。所有示例都使用 `<school_code>`、`<student_id>` 这类占位符。请不要把真实信息贴到 issue、commit 或日志里。

## 开发

```bash
npm ci
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest      # Python 测试（网络和 Chrome 都已 mock）
npm test                        # 渲染器测试（node:test）
```

CI 在 Python 3.9 和 3.12（Node.js 20）上运行这两套测试，外加一次 `--help` 冒烟测试。API payload 格式和渲染时容易踩的坑（HTML 转义与 TeX 的冲突、为什么必须在服务端渲染）见 [`references/workflow.md`](./references/workflow.md)。

```text
smartestu-homework-export/
├── SKILL.md                    # skill 入口
├── references/workflow.md      # API 与渲染参考
├── scripts/
│   ├── export_homework_pdf.py  # 命令行入口
│   └── render_katex.js         # KaTeX 渲染器（JSON 输入/输出）
├── tests/
├── package.json / package-lock.json
└── requirements.txt / requirements-dev.txt
```

修改功能时，请同时更新中英文 README。

## 许可证

[GNU 通用公共许可证 v3.0](LICENSE)。
