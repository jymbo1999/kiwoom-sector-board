
# AGENTS.md

This repository is a local Streamlit dashboard project for Korean stock market sector/theme monitoring.

Use this AGENTS.md and the active request file under requests/ as the source of truth.

## Core rules

1. Follow the active request file under `requests/`.
2. This is currently a Streamlit app, not a Flask app.
3. Main entrypoint is `app.py`.
4. Main UI layer is `src/dashboard_components.py`.
5. Data/ranking logic is under `src/theme_loader.py`, `src/market_data.py`, and `src/sector_ranker.py`.
6. Touch only files directly relevant to the request.
7. Prefer small, safe, compatibility-preserving changes.
8. Do not remove existing features, fallbacks, TODOs, defensive code, or user data.
9. Do not run `git add .`.
10. If the folder is not a Git repository, do not attempt commits; report that Git is unavailable.

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

## DB rule

This project currently should not add a database unless explicitly requested.

If a change proposes DB tables, migrations, PostgreSQL, SQLite schema, or persistent storage changes, stop and report first.

## Verification baseline

Use only relevant checks for this Streamlit project.

Python syntax:

```bash
python -m py_compile app.py src/*.py

Tests:

pytest -q

Streamlit smoke check:

streamlit run app.py

Render start command:

streamlit run app.py --server.address 0.0.0.0 --server.port $PORT

Diff hygiene:

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