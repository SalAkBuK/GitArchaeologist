# GitArchaeologist AI

GitArchaeologist imports bounded Git and GitHub pull-request evidence and turns it into a deterministic investigation graph.

It is built around a simple evidence chain:

```text
Public GitHub repository URL
        |
        v
Bounded Git history and public pull requests
        |
        v
Pull-request, commit, and modified-file artifacts
        |
        v
Deterministic evidence edges
        |
        v
SQLite persistence
        |
        v
Investigation API
        |
        v
Next.js dashboard
```

The core relationship model is:

```text
Pull Request
    contains
        Commit
            modifies
                File
```

GitArchaeologist does not guess these relationships. A pull request is linked to a commit only when GitHub provides an exact full commit SHA for the same repository. Missing context is reported as missing instead of being invented.

## What It Does

- Imports a public GitHub repository from its HTTPS URL.
- Clones a bounded slice of the repository's default-branch history.
- Fetches bounded public pull-request metadata and pull-request commit SHAs.
- Normalizes repositories, pull requests, commits, and modified files.
- Creates deterministic `pull_request -> contains -> git_commit` evidence edges.
- Creates deterministic `git_commit -> modifies -> modified_file` evidence edges.
- Persists imported evidence in SQLite.
- Reconciles repeated imports without duplicating existing artifacts.
- Keeps repositories isolated even when PR numbers or external identifiers overlap.
- Displays unresolved commit references and missing-context warnings.
- Supports deterministic Git-log and pull-request fixture ingestion for development, testing, and offline demos.

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

On Bash or Zsh, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

## Run Locally

Start FastAPI from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The backend runs at:

```text
http://127.0.0.1:8000
```

Start Next.js from the repository root in another terminal:

```powershell
$env:NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL = "http://127.0.0.1:8000"
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:3000
```

`NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL` is optional and defaults to `http://127.0.0.1:8000`.

## Import a GitHub Repository

Use the repository import endpoint to import Git and pull-request evidence from a public GitHub repository.

```http
POST /api/repositories/import
Content-Type: application/json
```

Example request:

```json
{
  "repositoryUrl": "https://github.com/owner/repository"
}
```

PowerShell example:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/repositories/import `
  -H "Content-Type: application/json" `
  -d "{\"repositoryUrl\":\"https://github.com/owner/repository\"}"
```

The response includes:

- `repositoryId`
- canonical `repositoryUrl`
- `selectedCommitSha`
- Git ingestion counts
- pull-request ingestion counts
- import warnings
- effective import limits

`selectedCommitSha` identifies the initial commit investigation that the frontend can load after import.

### Supported Repository URLs

GitArchaeologist accepts standard public GitHub HTTPS repository URLs:

```text
https://github.com/owner/repository
https://github.com/owner/repository/
https://github.com/owner/repository.git
```

Owner and repository names are normalized consistently for internal repository identity.

## Import Bounds

Repository importing is intentionally bounded so imports stay predictable and safe for local development.

Default bounds:

| Resource | Default |
| --- | ---: |
| Git commits | 100 |
| Pull requests | 10 |
| Commits per pull request | 50 |
| GitHub network timeout | 15 seconds |
| Git command timeout | 60 seconds |
| Temporary repository size | 100 MiB |
| Generated Git-log output | 10 MiB |

When the importer reaches a configured bound, it returns stable warnings such as:

- `git_history_truncated`
- `pull_requests_truncated`
- `pull_request_commits_truncated`

## Import Safety

GitArchaeologist runs Git through subprocess argument arrays with shell execution disabled. Repository values provided by users are never interpolated into a shell command.

The importer uses a bounded clone strategy similar to:

```text
git [safe configuration options] clone
  --depth 101
  --single-branch
  --no-tags
  --filter=blob:none
  --no-checkout
```

Safety controls include:

- no shell execution
- no working-tree checkout
- no submodule initialization
- no Git hook execution
- no Git LFS smudging
- disabled interactive credential prompts
- disabled system and global Git configuration
- removal of dangerous inherited Git environment variables
- per-command timeouts
- repository-size checks
- generated Git-output limits
- isolated temporary directories
- cleanup after success or failure

The backend returns sanitized errors for invalid repository URLs, inaccessible repositories, clone failures, timeouts, rate limits, malformed upstream responses, and import failures. Local paths, subprocess details, stack traces, credentials, and raw upstream payloads are not exposed in API responses.

## Evidence Rules

### Pull Request to Commit

A `contains` edge is created only when:

- the pull request provides an exact full commit SHA
- that commit was imported
- the pull request and commit belong to the same repository

Direction:

```text
pull_request -> contains -> git_commit
```

Unknown, abbreviated, malformed, or cross-repository SHAs do not create evidence edges.

### Commit to Modified File

A `modifies` edge records that a Git commit changed a normalized file artifact.

Direction:

```text
git_commit -> modifies -> modified_file
```

## Investigation API

List imported commit artifacts:

```powershell
curl.exe "http://127.0.0.1:8000/api/artifacts?repositoryId=acme%2Fplatform&sourceType=git_commit"
```

Load an investigation for a selected commit:

```powershell
curl.exe "http://127.0.0.1:8000/api/investigations/commits/1111111111111111111111111111111111111111?repositoryId=acme%2Fplatform"
```

Investigations use full SHA-1 or SHA-256 commit hashes.

The investigation response can include:

- the selected commit
- modified-file artifacts
- linked pull requests
- `contains` evidence edges
- `modifies` evidence edges
- unresolved commit references
- missing-context warnings

## Manual Git-Log Ingestion

Git-log upload is available as a deterministic fallback and development tool.

Have Git write the file directly. This preserves Git's UTF-8 bytes and avoids PowerShell 5.1 `>` redirection, which writes UTF-16.

PowerShell:

```powershell
git -c core.quotepath=false log `
  --date=iso-strict `
  --name-status `
  --pretty=format:"commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n" `
  --output=git_log.txt
```

Bash or Zsh:

```bash
git -c core.quotepath=false log \
  --date=iso-strict \
  --name-status \
  --pretty=format:'commit %H%nAuthor: %an <%ae>%nDate: %aI%n%n%w(0,4,4)%B%n' \
  --output=git_log.txt
```

Inputs must be UTF-8 or UTF-8 with BOM. LF, CRLF, and CR newlines are accepted.

Supported name-status records:

```text
A<TAB>path
M<TAB>path
D<TAB>path
R<score><TAB>previous-path<TAB>path
```

Upload a Git log:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/ingestions/git `
  -F "repositoryId=acme/platform" `
  -F "file=@sample-data/git_log.txt;type=text/plain"
```

Git-log uploads use `.txt` files up to 5 MiB.

## Pull-Request Fixture Ingestion

Pull-request JSON upload is available for deterministic fixture-based workflows.

The fixture endpoint validates:

- `.json` filenames
- a 5 MiB maximum upload size
- UTF-8 or UTF-8-BOM decoding
- agreement between the request repository ID and fixture repository ID
- repository-scoped PR identities

The response reports:

- `repositoryId`
- `recordsReceived`
- `recordsInserted`
- `recordsUpdated`
- `recordsSkippedAsDuplicates`
- `recordsRejected`
- `explicitCommitReferencesResolved`
- `explicitCommitReferencesUnresolved`
- bounded validation errors

Included pull requests are partial upserts. Pull requests omitted from a fixture remain unchanged. For an included pull request, its explicit commit SHA set is replaced authoritatively.

## Reimport and Reconciliation

A Git commit is identified by repository and full commit SHA.

Reimporting a commit:

- updates changed commit content
- adds newly referenced files
- removes obsolete commit-to-file relationships
- leaves unrelated commits untouched
- leaves other repositories untouched

Pull requests are identified by repository and PR number.

Reimporting a pull request:

- updates included PR metadata
- replaces its explicit commit-reference set
- preserves omitted pull requests
- recreates valid same-repository evidence edges
- remains isolated from PRs with the same number in other repositories

Repeated imports reconcile existing state instead of creating duplicate artifacts.

## Disposable Demo Database

The default SQLite database is:

```text
backend/git_archaeologist.db
```

For an isolated PowerShell demo, set a temporary database before starting FastAPI:

```powershell
$databasePath = (Join-Path $env:TEMP "git-archaeologist-demo.db").Replace("\", "/")
$env:DATABASE_URL = "sqlite:///$databasePath"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Stop FastAPI and remove the temporary file to reset the demo.

On Bash or Zsh, an equivalent URL is:

```text
sqlite:////tmp/git-archaeologist-demo.db
```

## Verification

Backend checks from `backend/`:

```powershell
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pip check
```

Frontend checks from the repository root:

```powershell
npm.cmd run test:frontend
npm.cmd exec tsc -- --noEmit
npm.cmd run build
```
