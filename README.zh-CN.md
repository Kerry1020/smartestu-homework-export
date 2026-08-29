# smartestu-homework-export

[English](./README.md)

`smartestu-homework-export` 是一个面向 smartestu.cn / 数你最灵 场景的可复用 skill，用来把平台里的作业导出成更清晰、可复用、可打印的学习材料。它聚焦一条很具体的流程：找到最新未提交作业，按原顺序提取题目，保留数学公式，并生成真正可用的 PDF。

## 这个项目是做什么的

这个仓库打包的是一个面向单一平台流程的 skill，目标很明确：

1. 找到 Smartestu 上最新未提交的作业
2. 按页面展示顺序提取题目
3. 在导出过程中保留公式
4. 输出适合阅读或直接作答的 PDF

它不是一个通用 LMS 爬虫，也不追求支持所有教学平台。

## 这个 skill 会做什么

这个 skill 围绕 Smartestu 的真实作业流程设计：

- 先解析 school code
- 按 Smartestu 需要的 payload 形状登录
- 查询作业列表
- 选出最新未提交作业
- 直接从 homework 对象中按顺序提取题目内容
- 通过 HTML + KaTeX 路径保留公式
- 生成可打印、可交付的 PDF

## 核心特性

- API-first，而不是脆弱的浏览器页面抓取
- 题目按原始展示顺序提取
- 用 KaTeX 保留数学公式
- PDF 导出前强制验证公式是否真实渲染
- 支持“一题一页”输出，方便直接在题目下作答
- 所有示例都使用占位符，不包含真实账号数据

## 为什么采用 API-first

对这个平台来说，API-first 比 browser-first 更稳。

浏览器自动化仍然有价值，但更适合做视觉验证，而不是主提取路径。只要底层作业数据本来就能从 API 响应里拿到，就应该优先走 API，这样流程更稳定，导出的格式也更容易控制。

## Smartestu 工作流概览

这个 skill 走的是下面这条链路：

1. `GET /api/schools`
2. `POST /api/auth/login`
3. `POST /api/homework/student/mark/queryHomeworks`
4. 展平 `courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`
5. 过滤 `submission_status == "not_submitted"`
6. 按 `endTime` 倒序
7. 按数组顺序提取 `exercises[].questions[]`
8. 通过 HTML + KaTeX 渲染公式
9. 导出可读 PDF

仓库保留这些 Smartestu 专用细节，因为它们正是这个 skill 的核心价值。

## PDF 渲染标准

这个项目把 PDF 产出视为产品的一部分，而不是最后随手导一下。

标准包括：

- 公式必须渲染成数学排版，而不是原始 `$...$`
- 服务端（Node.js）KaTeX 预渲染是已验证的方案——Chrome headless `--print-to-pdf` 不执行 JavaScript
- 默认导出结果应当像作业讲义，而不是一整页连续网页内容
- 当用户想直接作答时，优先一题一页
- 渲染前必须对题目文本中的 `<`、`>`、`&` 做 HTML 转义（LaTeX 公式如 `$P\{1<X<3\}$` 中的原始 `<` 会被浏览器当作 HTML 标签，导致内容被静默截断）

## 安装方式

把这个 skill 目录放到你的 skills 加载路径中。

一个常见的本地结构是：

```text
<your-skills-root>/smartestu-homework-export/
├── SKILL.md
├── README.md
└── README.zh-CN.md
```

如果你的环境使用别的技能发现路径，就把 `SKILL.md` 放到对应目录里，并把 README 一起保留，方便后续维护。

## 使用方式

下面这类请求通常就适合触发这个 skill：

- “把我最新没写的数你最灵作业导出来”
- “导出最新未提交的 Smartestu 作业”
- “把这个数你最灵作业做成保留公式的 PDF”
- “按一题一页导出，这样我能直接在下面答题”

如果平台需要登录，用户仍然需要在自己的会话里提供真实凭据。但这些凭据不应该进入仓库文件、示例文本、公开 issue、截图或日志。

## 占位符示例 payload

```json
{
  "schoolCode": "<school_code>",
  "schoolUserLocalId": "<student_local_id>",
  "schoolUserId": "<school_user_id>",
  "password": "<password>"
}
```

```json
{
  "studentId": "<school_user_id>"
}
```

这些都是公开占位符，不代表真实学校、真实学号、真实密码、真实 token 或真实 session。

## 隐私与安全说明

- 本仓库不包含任何真实账号、密码、token 或 session 数据
- 所有示例都应保持为虚构占位符
- 凭据只应用于当前登录会话
- 不要把秘密信息写进仓库文件、截图、GitHub issue 或聊天记录
- 如果你 fork 或继续扩展这个 skill，也应保持同样的脱敏标准

## 仓库结构

```text
smartestu-homework-export/
├── SKILL.md
├── README.md
├── README.zh-CN.md
└── LICENSE
```

## 维护说明

后续更新这个 skill 时，建议始终保持这些约束：

- 除非平台本身发生变化，否则继续保持 API-first
- 中英文 README 同步更新
- 所有示例继续脱敏
- 把 PDF 渲染标准明确写出来，不要靠隐含经验
- 任何新的导出路径都要重新验证公式保留是否正确

## License

本项目采用 GPL-3.0 License，详见 [LICENSE](./LICENSE)。
