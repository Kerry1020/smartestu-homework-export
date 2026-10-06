# smartestu-homework-export

[![CI](https://github.com/Kerry1020/smartestu-homework-export/actions/workflows/ci.yml/badge.svg)](https://github.com/Kerry1020/smartestu-homework-export/actions/workflows/ci.yml)

[English](./README.md)

一个 Agent skill（Claude Code / Agent SDK 的 `SKILL.md` 格式），也可以作为独立命令行工具使用：把 **smartestu.cn（数你最灵）上未提交的作业** 导出为可打印的 PDF。每题单独一页，公式用 KaTeX 渲染。

- 直接调用 Smartestu API，不抓取浏览器页面
- 列出全部未提交作业，按截止时间倒序，并附上已检查的课程列表
- 按原顺序导出主问题和子问题
- 在打印前渲染好 KaTeX 公式，HTML 中不含 JavaScript，Chrome headless 能正确打印公式
- 每题下方留出 A4 作答空间

本工具不是通用 LMS 爬虫，也不会提交任何内容。

## 环境要求

- Python 3.9+
- Node.js 18+ 和 npm
- Google Chrome、Chromium 或 Microsoft Edge（仅生成 PDF 时需要）
- macOS 钥匙串（可选，用来保存密码最方便）

## 安装

```bash
git clone https://github.com/Kerry1020/smartestu-homework-export.git
cd smartestu-homework-export
npm ci                                    # 安装 katex 0.16.9（版本锁定在 package-lock.json）
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

作为 skill 使用时，把整个目录（不只是 `SKILL.md`）放到 agent 加载 skills 的位置，例如 `~/.claude/skills/smartestu-homework-export/`。之后可以直接说“把我数你最灵没交的作业导出成 PDF”。

## 使用

```bash
# 先保存一次密码（macOS）。-w 后面不写密码时会提示输入。
security add-generic-password -a "<student_id>" -s "smartestu.cn" -w

.venv/bin/python scripts/export_homework_pdf.py \
  --school-name "<学校名称>" --student-id "<student_id>" --keychain \
  --out-dir ~/Desktop/homework
```

其他传入密码的方式（按以下顺序取第一个）：`--password-stdin`、环境变量 `SMARTESTU_PASSWORD`、`--keychain`、`--password`。不建议用 `--password`，因为密码会出现在 `ps` 输出和 shell 历史记录里。

常用参数：

| 参数 | 作用 |
|---|---|
| `--school-code CODE` | 跳过按学校名称查询 |
| `--latest-only` | 只导出截止时间最晚的一份作业 |
| `--no-pdf` | 只生成 HTML |
| `--chrome PATH` | 指定浏览器路径（也可以设置 `CHROME_PATH`） |
| `--from-json FILE` | 离线模式：渲染之前保存的 `queryHomeworks` 响应 |
| `--insecure` | 关闭 TLS 证书校验（一般不需要） |

输出：每份作业生成一个 `<作业名>.html` 和一个 `<作业名>.pdf`，另有一个 `summary.json`，内容同时打印到 stdout。

退出码：`0` 成功（包括“没有未提交作业”）；`1` 未预期的错误；`2` 参数错误、找不到学校或缺少密码；`3` 网络、登录或 API 错误；`4` KaTeX 渲染失败；`5` PDF 导出失败。

## 常见问题

| 现象 | 处理方法 |
|---|---|
| `School not found` / `ambiguous` | 使用 smartestu 上显示的完整校名，或改用 `--school-code`（可以用 `curl https://smartestu.cn/api/schools` 查询） |
| `Login failed` / 退出码 3 | 检查学号（不要带学校前缀）和密码；用 `security find-generic-password -a <学号> -s smartestu.cn` 检查钥匙串条目 |
| `katex npm package is not installed` / 退出码 4 | 在仓库根目录运行 `npm ci` |
| `Chrome/Chromium not found` / 退出码 5 | 安装 Chrome，或用 `--chrome` / `CHROME_PATH` 指定路径；也可以用 `--no-pdf` |
| Chrome 超时 | 关闭 Chrome 弹出的配置对话框后重试；不要自己加 `--user-data-dir`（在 macOS 上会导致 Chrome 卡住） |
| PDF 中出现红色公式 | 说明源题目里这条 TeX 本身有错误，可以用 `grep katex-error *.html` 找到它 |
| 显示 0 份未提交，但实际应该有 | 查看 `courses_checked`：API 只返回在平台上布置了作业的课程 |

## 隐私

本仓库不包含任何账号、密码、token 或个人数据。所有示例都使用 `<school_code>`、`<student_id>` 这类占位符。请不要把真实信息贴到 issue、commit 或日志里。

## 开发

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest      # Python 测试（网络和 Chrome 都已 mock）
npm test                        # 渲染器测试（node:test）
```

CI 会在 Python 3.9 和 3.12 上运行这两套测试。API payload 的格式和渲染时容易踩的坑（HTML 转义和 TeX 的冲突、为什么必须在服务端渲染）见 [`references/workflow.md`](./references/workflow.md)。

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

## License

GPL-3.0，详见 [LICENSE](./LICENSE)。
