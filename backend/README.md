# GitArchaeologist AI backend

The backend implements the deterministic commit-investigation slice:

`git_log.txt -> parser -> commit/file artifacts -> SQLite -> FastAPI investigation response`

It does not ingest Issues, pull requests, Slack, Jira, or model-generated evidence.

## Install and run

From `backend/` on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Use `.venv/bin/python` on Bash/Zsh. The default database is `backend/git_archaeologist.db`; `DATABASE_URL` can select a disposable SQLite file.

From `backend/`, upload the tracked sample and query it with:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/ingestions/git `
  -F "repositoryId=acme/platform" `
  -F "file=@../sample-data/git_log.txt;type=text/plain"

curl.exe "http://127.0.0.1:8000/api/artifacts?repositoryId=acme%2Fplatform&sourceType=git_commit"

curl.exe "http://127.0.0.1:8000/api/investigations/commits/1111111111111111111111111111111111111111?repositoryId=acme%2Fplatform"
```

Run tests from `backend/` with:

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

## Generate accepted input

Use Git's `--output` option instead of shell redirection. PowerShell 5.1 `>` writes UTF-16 and is intentionally rejected.

PowerShell:

```powershell
git -c core.quotepath=false log `
  --date=iso-strict `
  --name-status `
  --pretty=format:"commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n" `
  --output=git_log.txt
```

Bash/Zsh:

```bash
git -c core.quotepath=false log \
  --date=iso-strict \
  --name-status \
  --pretty=format:'commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n' \
  --output=git_log.txt
```

The upload boundary accepts strict UTF-8 with an optional BOM. The parser normalizes LF, CRLF, and CR. It supports added (`A`), modified (`M`), deleted (`D`), and renamed (`R<score>`) records. Git C-style quoted paths are decoded strictly, including UTF-8 octal bytes. Copy records are rejected with a record-level validation error.

Empty commit messages are valid. They retain an empty body and use `Commit <short-sha>` only as the display title.

## Snapshot reconciliation

Each valid incoming commit record is authoritative for its repository and SHA. In one database transaction, ingestion:

1. Inserts a new commit or updates changed normalized commit content.
2. Inserts newly present modified-file artifacts.
3. Updates a same-identity file artifact when mutable metadata changes.
4. Removes obsolete file artifacts for that commit only.
5. Leaves other commits and repositories untouched.

The response preserves `recordsInserted` and `recordsSkippedAsDuplicates`, and adds `recordsUpdated` and `recordsDeleted`. Rejected parser records remain in `validationErrors`. A reconciliation failure rolls the transaction back.

## Contracts and limits

Repository-specific endpoints require a trimmed, non-empty `repositoryId` of at most 255 characters. Investigations require a full 40- or 64-character hexadecimal SHA. Uploads require a `.txt` filename, are limited to 5 MiB, and never write the uploaded filename or file contents to the local filesystem.

Artifacts use deterministic UUIDv5 IDs scoped by repository. Modified files store `commitHash`, `path`, `previousPath`, `changeStatus`, and `rawStatus`. Investigation edges are generated from that persisted metadata at read time.

`Database.create_schema()` uses `create_all()` for local development. It creates fresh tables but is not a migration system. The current slice remains compatible with the earlier SQLite table because generated external IDs fit its existing column declaration.

The service trusts local users and permits only `localhost:3000` and `127.0.0.1:3000` browser origins. It has no authentication and must not be exposed as a public multi-tenant API.
