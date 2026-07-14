# GitArchaeologist AI

GitArchaeologist currently implements one deterministic vertical slice:

`Git log upload -> commit and modified-file artifacts -> SQLite -> investigation API -> Next.js dashboard`

It does not ingest GitHub Issues, pull requests, Slack, Jira, embeddings, or LLM output.

## Install

Install frontend dependencies from the repository root:

```powershell
npm.cmd install
```

Create the backend environment from `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On Bash/Zsh, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

## Generate a Git log

Have Git write the file directly. This preserves Git's UTF-8 bytes and avoids PowerShell 5.1 `>` redirection, which writes UTF-16, and shell newline conversion.

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

Inputs must be UTF-8 or UTF-8 with BOM. LF, CRLF, and CR newlines are accepted. UTF-16 and corrupted UTF-8 are rejected with a validation response. Git's default quoted path format is also accepted, but `core.quotepath=false` keeps Unicode filenames readable.

Supported name-status records are:

- `A<TAB>path`
- `M<TAB>path`
- `D<TAB>path`
- `R<score><TAB>previous-path<TAB>path`

Copy records (`C<score>`) are rejected explicitly; they are not treated as renames.

## Run locally

Start FastAPI from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Start Next.js from the repository root in another terminal:

```powershell
$env:NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_GIT_ARCHAEOLOGIST_REPOSITORY_ID = "acme/platform"
npm.cmd run dev
```

The URL variable is optional and defaults to `http://127.0.0.1:8000`.

To upload from the browser, open `http://127.0.0.1:3000`, enter the repository ID used to generate the log, select `git_log.txt`, and choose **Upload**. The newest commit is selected automatically; selecting another commit loads its persisted investigation.

From the repository root, the equivalent API calls are:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/ingestions/git `
  -F "repositoryId=acme/platform" `
  -F "file=@sample-data/git_log.txt;type=text/plain"

curl.exe "http://127.0.0.1:8000/api/artifacts?repositoryId=acme%2Fplatform&sourceType=git_commit"

curl.exe "http://127.0.0.1:8000/api/investigations/commits/1111111111111111111111111111111111111111?repositoryId=acme%2Fplatform"
```

## Reingestion

An uploaded commit record is the current snapshot for that repository and full SHA. Reingestion updates changed commit content, adds new file records, removes obsolete file records, and leaves other commits and repositories untouched. The response reports inserted, updated, deleted, unchanged/skipped, and rejected artifact counts.

## Disposable demo database

The default database is `backend/git_archaeologist.db`. For an isolated PowerShell demo, set a temporary database before starting FastAPI:

```powershell
$databasePath = (Join-Path $env:TEMP "git-archaeologist-demo.db").Replace("\", "/")
$env:DATABASE_URL = "sqlite:///$databasePath"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Stop FastAPI and remove that file to reset the demo. On Bash/Zsh, an equivalent URL is `sqlite:////tmp/git-archaeologist-demo.db`.

## Current limitations and trust model

- Investigations require a full SHA-1 or SHA-256 commit hash.
- Evidence is limited to uploaded Git commits and deterministic `commit -> modified_file` edges.
- Pull request, issue, and human rationale context is reported as missing; it is not inferred.
- Uploads are limited to 5 MiB and `.txt` filenames.
- This is a local hackathon tool with local-origin CORS and no authentication. Do not expose it as a public or multi-tenant service.
- ESLint is not configured. Type safety is enforced with standalone `tsc` and the production build.
