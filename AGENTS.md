# AGENTS.md

This repository uses `AGENTS.md` as the main long-form instruction file.  
Keep this file short because agents read it every run.

## Core rules

1. Read `AGENTS.md` first.
2. Follow the active request file under `requests/`.
3. Touch only files directly relevant to the request.
4. Prefer small, safe, compatibility-preserving changes.
5. Do not remove existing features, fallbacks, TODOs, defensive code, or user data.
6. Do not run `git add .`.
7. Stage only related files explicitly.
8. Do not commit generated zips, runtime DBs, backups, `.env`, virtualenvs, build artifacts, local settings, or untracked user files.
9. If scope is unclear or risky, stop and report instead of guessing.

## Request file rule

- If the user already provides a specific `requests/*.md` file, use it as the active request.
- Do not create a duplicate request file for an already-defined task.
- If no request file exists and the task is non-trivial, create one under `requests/`.
- Trivial typo, label, or one-line style fixes do not require a request file unless asked.

## Work sequence

Use this order:

1. Analyze relevant files only.
2. Identify affected routes, templates, services, models, JS, CSS, storage, auth, and deployment risks.
3. Implement only the minimal scope defined in the active request.
4. Review the diff for regressions, duplicated UI, route/template mismatch, and compatibility issues.
5. Run relevant verification.
6. Fix only issues directly found by verification.
7. Report clearly.

## Safety stops

Stop and report before continuing if any of these are required:

- destructive DB migration
- deleting user data, uploads, storage objects, local DBs, or untracked files
- unknown auth/owner behavior
- large refactor outside the request
- production schema uncertainty
- missing critical dependencies preventing verification

## DB / Render PostgreSQL rule

Render production may use `DISABLE_STARTUP_SCHEMA=1`.

Agents must not assume production DB schema is auto-patched at startup.

If a change touches models, DB columns, DB tables, relationships, or queries expecting new schema:

1. Check whether production DB migration is needed.
2. Use only non-destructive SQL unless explicitly approved.
3. Prefer:

```sql
ALTER TABLE table_name ADD COLUMN IF NOT EXISTS column_name TYPE;
```

4. Do not use `DROP`, `DELETE`, `TRUNCATE`, destructive rename, or data-loss migration without explicit approval.
5. Final report must include:

```text
Production DB migration needed: YES/NO
```

If YES, include safe SQL, verification SQL, reason it is safe, and post-deploy checks.

## Verification baseline

Use only relevant checks.

Python:

```bash
uv run python -m py_compile apps/__init__.py apps/models.py apps/home/routes.py
```

Service files when touched:

```bash
uv run python -m py_compile apps/services/ai.py apps/services/rag.py apps/services/curriculum_gpt.py apps/services/review_export.py
```

Templates when touched:

```bash
uv run python - <<'PY'
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("templates"))
for t in ["home/child_detail.html", "includes/sidebar.html", "home/duty_schedule.html"]:
    env.get_template(t)
    print("OK", t)
PY
```

Render startup when app init/schema/deployment changed:

```bash
RENDER=1 uv run python - <<'PY'
from apps import create_app
app = create_app()
print("app ok", app.name)
PY
```

Diff hygiene:

```bash
git diff --check
git status --short
git diff --stat
```

## Commit policy

- Commit each logical fix separately when possible.
- Commit only related files.
- Keep request markdown files committed unless explicitly told not to.
- Do not commit unrelated formatting churn.

## Final report format

Include:

1. 원인
2. 수정한 파일
3. 기능별 변경 요약
4. 실행한 검증 명령
5. 검증 결과
6. git diff 요약
7. 커밋 해시
8. git status --short
9. 사용자가 직접 확인할 화면/동작
10. 남은 리스크
11. Production DB migration needed: YES/NO

Clearly separate automated checks actually run from browser/UI checks the user must confirm manually.