# Smartestu Homework Export Workflow Reference

## Confirmed Working API Path

### 1. School lookup
- `GET /api/schools`
- Use to resolve school code from the human-readable school name.

For Harbin Engineering University:
- `code: heu`
- `name: 哈尔滨工程大学`

### 2. Login
- `POST /api/auth/login`

Working fields:
- `schoolCode`
- `schoolUserLocalId`
- `schoolUserId`
- `password`

Example pattern:

```json
{
  "schoolCode": "heu",
  "schoolUserLocalId": "2025089104",
  "schoolUserId": "heu-2025089104",
  "password": "..."
}
```

### 3. Query homework list
- `POST /api/homework/student/mark/queryHomeworks`

Working payload pattern:

```json
{
  "studentId": "heu-2025089104"
}
```

## Homework Selection Rule

Flatten:
- `courseHomeworkDTOList[].studentCourseHomeworkDTOList[]`

Then choose:
- `submission_status == "not_submitted"`
- latest `endTime`

## Confirmed Homework Shape

A homework item typically includes:
- `id`
- `name`
- `courseName`
- `startTime`
- `endTime`
- `submission_status`
- `review_status`
- `exercise_status`
- `exercises[]`

Exercise objects commonly include:
- `id`
- `name`
- `questionNum`
- `questionType`
- `score`
- `questions[]`

Question objects commonly include:
- `type`
- `content`

## Rendering Notes

To produce formula-correct output:
- use KaTeX in a generated HTML page
- do not rely on plain text screenshots for math-heavy content

## PDF Notes

Reliable export path used in this workspace:
- generate `rendered.html`
- serve locally with Python http.server
- export through browser PDF
