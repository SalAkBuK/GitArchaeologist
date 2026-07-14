# GitArchaeologist AI backend

This backend implements the first ingestion slice only:

`git_log.txt -> deterministic Git parser -> normalized artifacts -> SQLite -> FastAPI`

It does not parse Jira, Slack, pull requests, build evidence edges, call an LLM, or integrate with the frontend.

## Run locally

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The default database is `backend/git_archaeologist.db`. Set `DATABASE_URL` to override it.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/ingestions/git `
  -F "repositoryId=acme/platform" `
  -F "file=@../sample-data/git_log.txt;type=text/plain"

curl.exe "http://127.0.0.1:8000/api/artifacts?repositoryId=acme%2Fplatform&sourceType=git_commit"
```

Run tests from `backend/`:

```powershell
python -m pytest
```

## Accepted Git log format

Each record must use a full SHA-1 or SHA-256 hash, an author name/email, and a timezone-aware ISO 8601 date:

```text
commit <full hash>
Author: Name <email@example.com>
Date: 2026-07-14T10:30:00+05:00

    Subject line
    Optional multiline body
```

Generate compatible input with:

```powershell
git log --date=iso-strict --pretty=format:'commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%B%n'
```

The parser handles records independently. `recordsParsed` counts successfully normalized records; `recordsRejected` and `validationErrors` describe malformed records. Valid records in a partially malformed upload are still inserted.

## Artifact contract

Database columns use snake_case. API responses use the camelCase names from `lib/domain.ts`. `author_name` and `author_email` are flattened in SQLite but returned as the TypeScript-compatible `author` object. A Git artifact has confidence `1.0` because the uploaded commit is direct evidence. Optional investigation, URL, detail, and confidence-level fields are omitted because ingestion cannot determine them honestly.

IDs are UUIDv5 values derived from repository ID, `git_commit`, and the lowercase full commit hash. SQLite additionally enforces uniqueness across `(repository_id, source_type, external_id)`.

Ticket references and component mentions are extracted only by explicit regular expressions in `app/parsers/git_log.py`; no inferred tags are produced.

## Schema management tradeoff

`Database.create_schema()` uses SQLAlchemy `create_all()` because this phase owns one table and targets local development. This does not safely evolve an existing database. Add a migration tool such as Alembic before changing a deployed or shared schema.
