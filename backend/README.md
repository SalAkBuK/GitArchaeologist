# GitArchaeologist AI backend

This backend implements the first deterministic vertical slice:

`git_log.txt -> deterministic Git parser -> normalized commit/file artifacts -> SQLite -> FastAPI investigation response`

It does not parse Jira, Slack, GitHub Issues, pull requests, call an LLM, or infer semantic relationships.

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

curl.exe "http://127.0.0.1:8000/api/investigations/commits/1111111111111111111111111111111111111111?repositoryId=acme%2Fplatform"
```

Run tests from `backend/`:

```powershell
python -m pytest
```

## Accepted Git log format

Each record must use a full SHA-1 or SHA-256 hash, an author name/email, a timezone-aware ISO 8601 date, an indented commit message, and optional tab-separated file records from Git name-status output:

```text
commit <full hash>
Author: Name <email@example.com>
Date: 2026-07-14T10:30:00+05:00

    Subject line
    Optional multiline body

A	path/to/new-file.ts
M	path/to/changed-file.ts
D	path/to/deleted-file.ts
R100	path/to/old-name.ts	path/to/new-name.ts
```

Generate compatible input with:

```powershell
git log --date=iso-strict --name-status --pretty=format:'commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n'
```

Supported file statuses are added (`A`), modified (`M`), deleted (`D`), and renamed (`R<score>`). The parser handles records independently. `recordsParsed` counts successfully normalized artifacts; `recordsRejected` and `validationErrors` describe malformed commit or file records. Valid records in a partially malformed upload are still inserted.

## Artifact contract

Database columns use snake_case. API responses use the camelCase names from `lib/domain.ts`. `author_name` and `author_email` are flattened in SQLite but returned as the TypeScript-compatible `author` object. Git commit and modified-file artifacts have confidence `1.0` because the uploaded Git log is direct evidence. Optional URL, detail, and confidence-level fields are omitted because ingestion cannot determine them honestly.

Modified-file artifacts use `sourceType=modified_file` and store `commitHash`, `path`, `previousPath`, `changeStatus`, and `rawStatus` in metadata.

The commit investigation endpoint returns deterministic `git_commit -> modified_file` edges. Those edges are generated from persisted artifact metadata at request time instead of being stored in a separate edge table. For this slice there is only one edge source, so persisting edges would add schema surface without preserving additional evidence.

## Frontend integration

Run the Next.js frontend from the repository root with:

```powershell
npm.cmd run dev
```

The frontend reads `NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL` and defaults to `http://127.0.0.1:8000`. It can upload a supported `.txt` Git log, list ingested commits for a repository, and load `GET /api/investigations/commits/{full_sha}?repositoryId=...`.

Current limitations are explicit in the API response: no linked pull request, no linked issue, no human rationale beyond the commit message, and no modified-file records when the upload omitted name-status lines.

IDs are UUIDv5 values derived from repository ID, `git_commit`, and the lowercase full commit hash. SQLite additionally enforces uniqueness across `(repository_id, source_type, external_id)`.

Ticket references and component mentions are extracted only by explicit regular expressions in `app/parsers/git_log.py`; no inferred tags are produced.

## Schema management tradeoff

`Database.create_schema()` uses SQLAlchemy `create_all()` because this phase owns one table and targets local development. This does not safely evolve an existing database. Add a migration tool such as Alembic before changing a deployed or shared schema.
