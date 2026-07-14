# GitArchaeologist AI

GitArchaeologist currently implements one deterministic vertical slice:

`Git log upload -> commit artifacts -> modified-file artifacts -> commit investigation API -> Next.js dashboard`

It does not ingest GitHub Issues, pull requests, Slack, Jira, embeddings, or LLM output.

## Supported Git-log input

Use the repository's deterministic format: full commit hash, author, ISO timestamp,
indented commit message, then optional tab-separated `--name-status` file records.

Generate compatible input with:

```powershell
git log --date=iso-strict --name-status --pretty=format:'commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n'
```

Supported file statuses:

- `A<TAB>path`
- `M<TAB>path`
- `D<TAB>path`
- `R<score><TAB>previous-path<TAB>path`

Malformed file records are reported as validation errors. Valid commit records and valid file records in the same upload are still ingested.

## Backend

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

If the virtual environment does not exist yet:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The default database is `backend/git_archaeologist.db`. Set `DATABASE_URL` to override it.

Upload a Git log:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/ingestions/git `
  -F "repositoryId=acme/platform" `
  -F "file=@sample-data/git_log.txt;type=text/plain"
```

Investigate a full commit SHA:

```powershell
curl.exe "http://127.0.0.1:8000/api/investigations/commits/1111111111111111111111111111111111111111?repositoryId=acme%2Fplatform"
```

## Frontend

From the repository root:

```powershell
npm.cmd run dev
```

The frontend calls `NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL`, defaulting to `http://127.0.0.1:8000`.

Optional local defaults:

```powershell
$env:NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_GIT_ARCHAEOLOGIST_REPOSITORY_ID = "acme/platform"
npm.cmd run dev
```

## Current limitations

- Full commit SHAs are required for investigations.
- Evidence edges are only deterministic `git_commit -> modified_file` edges.
- Edges are generated from persisted artifact metadata at read time, not stored in an edge table.
- Missing pull request, issue, and rationale context is reported explicitly.
- The preserved `sample-data/investigation-001.json` file is a design fixture, not live evidence.
