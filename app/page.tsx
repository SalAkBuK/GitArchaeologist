'use client'

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  GitBranch,
  GitCommitVertical,
  GitPullRequest,
  ExternalLink,
  Network,
  RefreshCw,
  Upload,
} from 'lucide-react'
import type { Artifact } from '@/lib/domain'
import {
  createRepositoryImportRunner,
  isAbortError,
  presentRepositoryImportError,
  repositoryImportSummary,
  validatePublicGithubRepositoryUrl,
  type RepositoryImportRunner,
} from '@/lib/repository-import'
import {
  ApiResponseError,
  PULL_REQUEST_FIXTURE_ACCEPT,
  PullRequestFixtureClientError,
  apiErrorFromResponse,
  createPullRequestUploadRunner,
  importPublicRepository,
  parseArtifactList,
  parseCommitInvestigation,
  parseIngestionResult,
  pullRequestIngestionSummary,
  uploadPullRequestFixture,
  type CommitInvestigation,
  type MissingContextWarning,
  type PullRequestIngestionResult,
  type PullRequestUploadRunner,
  type RepositoryImportResult,
} from '@/lib/live-api'

interface ApplicationError {
  title: string
  message: string
  code?: string
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_GIT_ARCHAEOLOGIST_API_URL ?? 'http://127.0.0.1:8000'

const DEFAULT_REPOSITORY_ID =
  process.env.NEXT_PUBLIC_GIT_ARCHAEOLOGIST_REPOSITORY_ID ?? 'acme/platform'

function shortSha(sha?: string) {
  return sha ? sha.slice(0, 7) : ''
}

function formatDate(iso: string) {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(new Date(iso))
}

function changeLabel(artifact: Artifact) {
  const value = artifact.metadata.changeStatus
  return typeof value === 'string' ? value.replace('_', ' ') : 'changed'
}

function filePath(artifact: Artifact) {
  const path = artifact.metadata.path
  return typeof path === 'string' ? path : artifact.title
}

function presentError(error: unknown, operation: 'list' | 'investigation' | 'upload'): ApplicationError {
  if (error instanceof ApiResponseError) {
    if (error.status === 422) {
      return {
        title:
          operation !== 'upload' || error.message.toLowerCase().includes('repositoryid')
            ? 'Invalid repository'
            : 'Invalid uploaded file',
        message: error.message,
      }
    }
    if (operation === 'upload' && (error.status === 400 || error.status === 413)) {
      return { title: 'Invalid Git log', message: error.message }
    }
    return { title: 'Backend request failed', message: error.message }
  }
  if (error instanceof Error && error.message.startsWith('Backend returned')) {
    return { title: 'Invalid backend response', message: error.message }
  }
  return {
    title: 'Backend unavailable',
    message: error instanceof Error ? error.message : 'The backend request failed',
  }
}

function presentPullRequestUploadError(error: unknown): ApplicationError {
  if (error instanceof PullRequestFixtureClientError) {
    return {
      title: error.code === 'wrong_extension' ? 'Wrong file type' : 'Fixture too large',
      message: error.message,
    }
  }
  if (error instanceof ApiResponseError) {
    const message = error.message.toLowerCase()
    if (error.status === 413) return { title: 'Fixture too large', message: error.message }
    if (message.includes('repositoryid') && message.includes('match')) {
      return { title: 'Repository mismatch', message: error.message }
    }
    if (message.includes('utf-8') || message.includes('utf-16')) {
      return { title: 'Unsupported encoding', message: error.message }
    }
    if (message.includes('malformed json')) return { title: 'Malformed JSON', message: error.message }
    if (error.status === 400 || error.status === 422) {
      return { title: 'Invalid pull request fixture', message: error.message }
    }
    return { title: 'Backend request failed', message: error.message }
  }
  return presentError(error, 'upload')
}

function MissingContextList({ warnings }: { warnings: MissingContextWarning[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {warnings.map((warning) => (
        <li key={warning.code} className="rounded-xl border border-border bg-card p-3">
          <p className="font-mono text-[10px] uppercase tracking-widest text-primary">
            {warning.code}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{warning.message}</p>
        </li>
      ))}
    </ul>
  )
}

export default function Page() {
  const [repositoryUrl, setRepositoryUrl] = useState('')
  const [repositoryUrlError, setRepositoryUrlError] = useState<string | null>(null)
  const [repositoryImporting, setRepositoryImporting] = useState(false)
  const [repositoryImportResult, setRepositoryImportResult] =
    useState<RepositoryImportResult | null>(null)
  const [repositoryImportError, setRepositoryImportError] =
    useState<ApplicationError | null>(null)
  const [repositoryId, setRepositoryId] = useState(DEFAULT_REPOSITORY_ID)
  const [commits, setCommits] = useState<Artifact[]>([])
  const [selectedSha, setSelectedSha] = useState<string | null>(null)
  const [investigation, setInvestigation] = useState<CommitInvestigation | null>(null)
  const [loadingCommits, setLoadingCommits] = useState(true)
  const [loadingInvestigation, setLoadingInvestigation] = useState(false)
  const [applicationError, setApplicationError] = useState<ApplicationError | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [pullRequestUploading, setPullRequestUploading] = useState(false)
  const [pullRequestUploadResult, setPullRequestUploadResult] =
    useState<PullRequestIngestionResult | null>(null)
  const [pullRequestUploadError, setPullRequestUploadError] =
    useState<ApplicationError | null>(null)
  const [investigationRevision, setInvestigationRevision] = useState(0)
  const [commitListRevision, setCommitListRevision] = useState(0)
  const repositoryImportController = useRef<AbortController | null>(null)
  const repositoryImportRunner = useRef<RepositoryImportRunner | null>(null)
  const preferredCommitSha = useRef<string | null>(null)
  if (repositoryImportRunner.current === null) {
    repositoryImportRunner.current = createRepositoryImportRunner(setRepositoryImporting)
  }
  const commitListController = useRef<AbortController | null>(null)
  const investigationController = useRef<AbortController | null>(null)
  const uploadController = useRef<AbortController | null>(null)
  const pullRequestUploadController = useRef<AbortController | null>(null)
  const pullRequestUploadRunner = useRef<PullRequestUploadRunner | null>(null)
  if (pullRequestUploadRunner.current === null) {
    pullRequestUploadRunner.current = createPullRequestUploadRunner(setPullRequestUploading)
  }
  const commitListRequestId = useRef(0)
  const investigationRequestId = useRef(0)
  const uploadRequestId = useRef(0)

  const normalizedRepositoryId = repositoryId.trim()
  const activeRepositoryId = useRef(normalizedRepositoryId)
  activeRepositoryId.current = normalizedRepositoryId

  useEffect(() => {
    commitListController.current?.abort()
    const controller = new AbortController()
    commitListController.current = controller
    const requestId = ++commitListRequestId.current

    setCommits([])
    setSelectedSha(null)
    setInvestigation(null)
    setNotFound(false)

    async function loadCommits() {
      if (!normalizedRepositoryId) {
        setLoadingCommits(false)
        return
      }

      setLoadingCommits(true)
      setApplicationError(null)
      setUploadMessage(null)
      try {
        const params = new URLSearchParams({
          repositoryId: normalizedRepositoryId,
          sourceType: 'git_commit',
        })
        const response = await fetch(`${API_BASE_URL}/api/artifacts?${params}`, {
          signal: controller.signal,
        })
        if (!response.ok) {
          throw await apiErrorFromResponse(response)
        }
        const data = parseArtifactList(await response.json())
        if (requestId !== commitListRequestId.current || controller.signal.aborted) {
          return
        }
        setCommits(data)
        const importedSha = preferredCommitSha.current
        const nextSha = importedSha ?? data[0]?.externalId ?? null
        preferredCommitSha.current = null
        setSelectedSha(nextSha)
      } catch (error) {
        if (
          !isAbortError(error) &&
          requestId === commitListRequestId.current &&
          !controller.signal.aborted
        ) {
          setApplicationError(presentError(error, 'list'))
          setCommits([])
          setSelectedSha(null)
        }
      } finally {
        if (requestId === commitListRequestId.current) {
          setLoadingCommits(false)
        }
      }
    }

    loadCommits()
    return () => {
      controller.abort()
    }
  }, [commitListRevision, normalizedRepositoryId])

  useEffect(() => {
    investigationController.current?.abort()
    const controller = new AbortController()
    investigationController.current = controller
    const requestId = ++investigationRequestId.current
    setInvestigation(null)
    setNotFound(false)

    async function loadInvestigation() {
      if (!selectedSha || !normalizedRepositoryId) {
        setLoadingInvestigation(false)
        return
      }

      setLoadingInvestigation(true)
      setApplicationError(null)
      try {
        const params = new URLSearchParams({ repositoryId: normalizedRepositoryId })
        const response = await fetch(
          `${API_BASE_URL}/api/investigations/commits/${selectedSha}?${params}`,
          { signal: controller.signal },
        )
        if (response.status === 404) {
          if (requestId === investigationRequestId.current && !controller.signal.aborted) {
            setNotFound(true)
          }
          return
        }
        if (!response.ok) {
          throw await apiErrorFromResponse(response)
        }
        const data = parseCommitInvestigation(await response.json())
        if (requestId === investigationRequestId.current && !controller.signal.aborted) {
          setInvestigation(data)
        }
      } catch (error) {
        if (
          !isAbortError(error) &&
          requestId === investigationRequestId.current &&
          !controller.signal.aborted
        ) {
          setApplicationError(presentError(error, 'investigation'))
        }
      } finally {
        if (requestId === investigationRequestId.current) {
          setLoadingInvestigation(false)
        }
      }
    }

    loadInvestigation()
    return () => {
      controller.abort()
    }
  }, [investigationRevision, normalizedRepositoryId, selectedSha])

  const importSummary = useMemo(
    () =>
      repositoryImportResult ? repositoryImportSummary(repositoryImportResult) : null,
    [repositoryImportResult],
  )

  function handleRepositoryChange(event: ChangeEvent<HTMLInputElement>) {
    repositoryImportController.current?.abort()
    repositoryImportRunner.current?.cancel()
    commitListController.current?.abort()
    investigationController.current?.abort()
    uploadController.current?.abort()
    pullRequestUploadController.current?.abort()
    pullRequestUploadRunner.current?.cancel()
    commitListRequestId.current += 1
    investigationRequestId.current += 1
    uploadRequestId.current += 1
    preferredCommitSha.current = null
    setRepositoryImportResult(null)
    setRepositoryImportError(null)
    setCommits([])
    setSelectedSha(null)
    setInvestigation(null)
    setNotFound(false)
    setLoadingCommits(false)
    setLoadingInvestigation(false)
    setUploading(false)
    setPullRequestUploadResult(null)
    setPullRequestUploadError(null)
    setApplicationError(null)
    setUploadMessage(null)
    setRepositoryId(event.target.value)
  }

  async function handleRepositoryImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (repositoryImportRunner.current?.isActive()) return

    const candidate = repositoryUrl.trim()
    const validationError = validatePublicGithubRepositoryUrl(candidate)
    setRepositoryUrlError(validationError)
    if (validationError) return

    repositoryImportController.current?.abort()
    const controller = new AbortController()
    repositoryImportController.current = controller
    const startingRepositoryId = activeRepositoryId.current
    setRepositoryImportError(null)
    setRepositoryImportResult(null)
    setApplicationError(null)

    const outcome = await repositoryImportRunner.current?.run(
      () =>
        importPublicRepository({
          apiBaseUrl: API_BASE_URL,
          repositoryUrl: candidate,
          signal: controller.signal,
        }),
      (result) => {
        if (
          controller.signal.aborted ||
          activeRepositoryId.current !== startingRepositoryId
        ) {
          return
        }

        preferredCommitSha.current = result.selectedCommitSha
        commitListController.current?.abort()
        commitListRequestId.current += 1
        setRepositoryImportResult(result)
        setRepositoryImportError(null)
        setApplicationError(null)
        setRepositoryUrl(result.repositoryUrl)
        activeRepositoryId.current = result.repositoryId
        if (result.repositoryId === normalizedRepositoryId) {
          setCommitListRevision((revision) => revision + 1)
        } else {
          setRepositoryId(result.repositoryId)
        }
      },
    )

    if (outcome?.error && !isAbortError(outcome.error) && !controller.signal.aborted) {
      setRepositoryImportError(presentRepositoryImportError(outcome.error))
    }
  }

  function handleCommitSelection(commitSha: string) {
    investigationController.current?.abort()
    investigationRequestId.current += 1
    setInvestigation(null)
    setNotFound(false)
    setSelectedSha(commitSha)
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const input = form.elements.namedItem('gitLog') as HTMLInputElement | null
    const file = input?.files?.[0]
    if (!file || !normalizedRepositoryId) {
      setUploadMessage('Choose a Git log file and repository ID first.')
      return
    }

    const targetRepositoryId = normalizedRepositoryId
    const payload = new FormData()
    payload.append('repositoryId', targetRepositoryId)
    payload.append('file', file)

    uploadController.current?.abort()
    const controller = new AbortController()
    uploadController.current = controller
    const requestId = ++uploadRequestId.current
    setUploading(true)
    setUploadMessage(null)
    setApplicationError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/ingestions/git`, {
        method: 'POST',
        body: payload,
        signal: controller.signal,
      })
      if (!response.ok) {
        throw await apiErrorFromResponse(response)
      }
      const result = parseIngestionResult(await response.json())
      if (
        requestId !== uploadRequestId.current ||
        controller.signal.aborted ||
        activeRepositoryId.current !== targetRepositoryId
      ) {
        return
      }
      const countSummary = `Inserted ${result.recordsInserted}, updated ${result.recordsUpdated}, removed ${result.recordsDeleted}, skipped ${result.recordsSkippedAsDuplicates}, rejected ${result.recordsRejected}.`
      const validationSummary = result.validationErrors[0]?.message
      setUploadMessage(
        validationSummary
          ? `${countSummary} Malformed record: ${validationSummary}`
          : countSummary,
      )
      form.reset()

      commitListController.current?.abort()
      const listRequestId = ++commitListRequestId.current
      setLoadingCommits(true)
      const params = new URLSearchParams({
        repositoryId: targetRepositoryId,
        sourceType: 'git_commit',
      })
      const listResponse = await fetch(`${API_BASE_URL}/api/artifacts?${params}`, {
        signal: controller.signal,
      })
      if (!listResponse.ok) {
        throw await apiErrorFromResponse(listResponse)
      }
      const data = parseArtifactList(await listResponse.json())
      if (
        requestId !== uploadRequestId.current ||
        listRequestId !== commitListRequestId.current ||
        controller.signal.aborted ||
        activeRepositoryId.current !== targetRepositoryId
      ) {
        return
      }
      setCommits(data)
      setSelectedSha(data[0]?.externalId ?? null)
    } catch (error) {
      if (
        !isAbortError(error) &&
        requestId === uploadRequestId.current &&
        !controller.signal.aborted
      ) {
        setApplicationError(presentError(error, 'upload'))
      }
    } finally {
      if (requestId === uploadRequestId.current) {
        setUploading(false)
        setLoadingCommits(false)
      }
    }
  }

  async function handlePullRequestUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const input = form.elements.namedItem('pullRequestFixture') as HTMLInputElement | null
    const file = input?.files?.[0]
    if (!file || !normalizedRepositoryId) {
      setPullRequestUploadError({
        title: 'Fixture required',
        message: 'Choose a pull request JSON fixture and repository ID first.',
      })
      return
    }

    const targetRepositoryId = normalizedRepositoryId
    setPullRequestUploadError(null)
    setPullRequestUploadResult(null)
    try {
      await pullRequestUploadRunner.current?.run(
        async () => {
          const controller = new AbortController()
          pullRequestUploadController.current = controller
          return uploadPullRequestFixture({
            apiBaseUrl: API_BASE_URL,
            repositoryId: targetRepositoryId,
            file,
            signal: controller.signal,
          })
        },
        (result) => {
          if (activeRepositoryId.current !== targetRepositoryId) return
          setPullRequestUploadResult(result)
          form.reset()
          setInvestigationRevision((revision) => revision + 1)
        },
      )
    } catch (error) {
      if (!isAbortError(error) && activeRepositoryId.current === targetRepositoryId) {
        setPullRequestUploadError(presentPullRequestUploadError(error))
      }
    }
  }

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <header className="flex items-center justify-between gap-4 border-b border-border bg-background/70 px-4 py-3 backdrop-blur">
        <div className="flex items-center gap-2">
          <GitBranch className="size-4 text-primary" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold">GitArchaeologist</p>
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Commit Evidence Slice
            </p>
          </div>
        </div>
        <span className="hidden font-mono text-xs text-muted-foreground md:inline">
          {API_BASE_URL}
        </span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="max-h-[45dvh] w-full shrink-0 border-b border-border bg-sidebar lg:max-h-none lg:w-72 lg:border-b-0 lg:border-r xl:w-80">
          <aside className="flex h-full flex-col gap-5 overflow-y-auto p-4">
            <div>
              <label className="mb-2 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Repository ID
              </label>
              <input
                value={repositoryId}
                onChange={handleRepositoryChange}
                className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none focus:border-primary/50"
              />
            </div>

            <form onSubmit={handleUpload} className="rounded-xl border border-border bg-card p-3">
              <div className="mb-3 flex items-center gap-2">
                <Upload className="size-4 text-primary" aria-hidden="true" />
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Ingest Git Log
                </p>
              </div>
              <input
                name="gitLog"
                type="file"
                accept=".txt,text/plain"
                className="w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-2 file:py-1.5 file:text-xs file:text-foreground"
              />
              <button
                type="submit"
                disabled={uploading}
                className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                <Upload className="size-4" aria-hidden="true" />
                {uploading ? 'Uploading' : 'Upload'}
              </button>
              {uploadMessage && (
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  {uploadMessage}
                </p>
              )}
            </form>

            <details className="rounded-xl border border-border bg-card p-3">
              <summary className="flex cursor-pointer list-none items-center gap-2">
                <GitPullRequest className="size-4 text-primary" aria-hidden="true" />
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Advanced: PR Fixture
                </p>
              </summary>
              <form onSubmit={handlePullRequestUpload} className="mt-3 border-t border-border pt-3">
                <input
                  name="pullRequestFixture"
                  type="file"
                  accept={PULL_REQUEST_FIXTURE_ACCEPT}
                  disabled={pullRequestUploading}
                  className="w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-2 file:py-1.5 file:text-xs file:text-foreground disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={pullRequestUploading}
                  className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Upload className="size-4" aria-hidden="true" />
                  {pullRequestUploading ? 'Uploading fixture' : 'Upload PR fixture'}
                </button>

                {pullRequestUploadError && (
                  <div className="mt-3 rounded-lg border border-destructive/40 bg-destructive/10 p-2.5">
                    <p className="text-xs font-medium text-destructive">
                      {pullRequestUploadError.title}
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {pullRequestUploadError.message}
                    </p>
                  </div>
                )}

                {pullRequestUploadResult && (
                  <div className="mt-3 space-y-1 border-t border-border pt-3 font-mono text-[11px] text-muted-foreground">
                    {pullRequestIngestionSummary(pullRequestUploadResult).map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                    {pullRequestUploadResult.recordsRejected > 0 && (
                      <div className="pt-2 font-sans">
                        <ul className="mt-2 max-h-40 space-y-2 overflow-y-auto pr-1">
                          {pullRequestUploadResult.validationErrors.map((error) => (
                            <li
                              key={`${error.recordNumber}:${error.externalId ?? ''}:${error.message}`}
                              className="rounded-md border border-border bg-background/40 p-2 text-xs"
                            >
                              <span className="font-mono text-primary">Record {error.recordNumber}</span>{' '}
                              <span className="text-muted-foreground">{error.message}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </form>
            </details>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Ingested Commits
                </p>
                <RefreshCw
                  className={`size-3.5 text-muted-foreground ${
                    loadingCommits ? 'animate-spin' : ''
                  }`}
                  aria-hidden="true"
                />
              </div>
              {loadingCommits ? (
                <p className="rounded-lg border border-border bg-card p-3 text-sm text-muted-foreground">
                  Loading commits from backend.
                </p>
              ) : commits.length === 0 ? (
                <p className="rounded-lg border border-border bg-card p-3 text-sm text-muted-foreground">
                  No ingested commits for this repository.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {commits.map((commit) => (
                    <li key={commit.id}>
                      <button
                        type="button"
                        onClick={() => {
                          if (commit.externalId) {
                            handleCommitSelection(commit.externalId)
                          }
                        }}
                        className={`w-full rounded-lg border p-3 text-left transition-colors ${
                          selectedSha === commit.externalId
                            ? 'border-primary/50 bg-primary/10'
                            : 'border-border bg-card hover:border-primary/30'
                        }`}
                      >
                        <span className="font-mono text-[11px] text-primary">
                          {shortSha(commit.externalId)}
                        </span>
                        <span className="mt-1 block text-sm font-medium leading-snug">
                          {commit.title}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {commit.author?.displayName} - {formatDate(commit.occurredAt)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>

        <main className="min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto flex max-w-4xl flex-col gap-5">
            <section className="border border-primary/35 bg-card p-4 md:p-5">
              <div className="flex items-start gap-3">
                <GitBranch className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
                <div>
                  <h1 className="text-base font-semibold">Import a public GitHub repository</h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Enter a public github.com repository URL to import its commit and pull request
                    evidence.
                  </p>
                </div>
              </div>
              <form onSubmit={handleRepositoryImport} className="mt-4" noValidate>
                <label htmlFor="repository-url" className="text-sm font-medium">
                  Repository URL
                </label>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <input
                    id="repository-url"
                    name="repositoryUrl"
                    type="url"
                    value={repositoryUrl}
                    onChange={(event) => {
                      setRepositoryUrl(event.target.value)
                      setRepositoryUrlError(null)
                    }}
                    placeholder="https://github.com/owner/repository"
                    autoCapitalize="none"
                    autoComplete="url"
                    spellCheck={false}
                    aria-describedby="repository-url-help repository-url-error"
                    aria-invalid={repositoryUrlError ? true : undefined}
                    disabled={repositoryImporting}
                    className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary/60 disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <button
                    type="submit"
                    disabled={repositoryImporting}
                    className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {repositoryImporting ? (
                      <RefreshCw className="size-4 animate-spin" aria-hidden="true" />
                    ) : (
                      <GitBranch className="size-4" aria-hidden="true" />
                    )}
                    {repositoryImporting ? 'Importing' : 'Import repository'}
                  </button>
                </div>
                <p id="repository-url-help" className="mt-2 text-xs text-muted-foreground">
                  Only public GitHub repositories over HTTPS are supported.
                </p>
                {repositoryUrlError && (
                  <p id="repository-url-error" className="mt-2 text-xs text-destructive">
                    {repositoryUrlError}
                  </p>
                )}
              </form>
            </section>

            {repositoryImportError && (
              <section className="border border-destructive/40 bg-destructive/10 p-4" role="alert">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertTriangle className="size-4" aria-hidden="true" />
                  <h2 className="text-sm font-semibold">{repositoryImportError.title}</h2>
                </div>
                {repositoryImportError.code && (
                  <p className="mt-2 font-mono text-[11px] text-destructive">
                    {repositoryImportError.code}
                  </p>
                )}
                <p className="mt-2 text-sm text-muted-foreground">
                  {repositoryImportError.message}
                </p>
              </section>
            )}

            {repositoryImportResult && importSummary && (
              <section className="border border-primary/35 bg-primary/5 p-4" aria-live="polite">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-primary">
                      {repositoryImportResult.warnings.length > 0 ? (
                        <AlertTriangle className="size-4" aria-hidden="true" />
                      ) : (
                        <CheckCircle2 className="size-4" aria-hidden="true" />
                      )}
                      <h2 className="text-sm font-semibold">
                        {repositoryImportResult.warnings.length > 0
                          ? 'Import succeeded with limits'
                          : 'Import succeeded'}
                      </h2>
                    </div>
                    <a
                      href={repositoryImportResult.repositoryUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex items-center gap-1 break-all text-sm text-primary hover:underline"
                    >
                      {repositoryImportResult.repositoryUrl}
                      <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
                    </a>
                  </div>
                  <div className="text-right font-mono text-[11px] text-muted-foreground">
                    <p>{repositoryImportResult.repositoryId}</p>
                    <p className="mt-1">commit {shortSha(repositoryImportResult.selectedCommitSha)}</p>
                  </div>
                </div>

                <div className="mt-4 grid gap-4 border-t border-primary/20 pt-4 md:grid-cols-3">
                  {(
                    [
                      ['Git ingestion', importSummary.git],
                      ['Pull request ingestion', importSummary.pullRequests],
                      ['Effective limits', importSummary.limits],
                    ] as const
                  ).map(([title, items]) => (
                    <div key={title}>
                      <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        {title}
                      </h3>
                      <dl className="mt-2 space-y-1 text-xs">
                        {items.map((item) => (
                          <div key={item.label} className="flex items-baseline justify-between gap-3">
                            <dt className="text-muted-foreground">{item.label}</dt>
                            <dd className="font-mono text-foreground">
                              {item.value.toLocaleString('en')}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ))}
                </div>

                {repositoryImportResult.warnings.length > 0 && (
                  <div className="mt-4 border-t border-primary/20 pt-4">
                    <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      Import warnings
                    </h3>
                    <ul className="mt-2 space-y-2">
                      {repositoryImportResult.warnings.map((warning, index) => (
                        <li
                          key={`${warning.code}:${index}`}
                          className="border-l-2 border-primary pl-3 text-sm"
                        >
                          <span className="font-mono text-[11px] text-primary">
                            {warning.code}
                          </span>
                          <p className="mt-1 text-muted-foreground">{warning.message}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}

            {applicationError && (
              <section className="rounded-xl border border-destructive/40 bg-destructive/10 p-4">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertTriangle className="size-4" aria-hidden="true" />
                  <h2 className="text-sm font-semibold">{applicationError.title}</h2>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{applicationError.message}</p>
              </section>
            )}

            {!applicationError && loadingInvestigation && (
              <section className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
                Loading commit investigation.
              </section>
            )}

            {!applicationError && notFound && (
              <section className="rounded-xl border border-border bg-card p-5">
                <h1 className="text-lg font-semibold">Commit not found</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  The selected full SHA does not exist for repository {normalizedRepositoryId}.
                </p>
              </section>
            )}

            {!applicationError && !loadingInvestigation && !investigation && !notFound && (
              <section className="rounded-xl border border-border bg-card p-5">
                <h1 className="text-lg font-semibold">No commit selected</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  Upload a supported Git log or select an ingested commit.
                </p>
              </section>
            )}

            {investigation && (
              <>
                <section className="glass rounded-2xl border border-border p-5 shadow-2xl shadow-black/20">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-primary/15 px-2 py-0.5 font-mono text-xs text-primary">
                      {shortSha(investigation.commitSha)}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">
                      repo: {investigation.repositoryId}
                    </span>
                  </div>
                  <h1 className="mt-3 text-2xl font-semibold tracking-tight">
                    {investigation.selectedCommit.title}
                  </h1>
                  <p className="mt-3 max-w-3xl whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">
                    {investigation.selectedCommit.body}
                  </p>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    <div className="rounded-xl border border-border bg-background/40 p-3">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Author
                      </p>
                      <p className="mt-1 text-sm font-medium">
                        {investigation.selectedCommit.author?.displayName}
                      </p>
                    </div>
                    <div className="rounded-xl border border-border bg-background/40 p-3">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Date
                      </p>
                      <p className="mt-1 text-sm font-medium">
                        {formatDate(investigation.selectedCommit.occurredAt)}
                      </p>
                    </div>
                    <div className="rounded-xl border border-border bg-background/40 p-3">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Files
                      </p>
                      <p className="mt-1 text-sm font-medium">
                        {investigation.modifiedFiles.length}
                      </p>
                    </div>
                  </div>
                </section>

                {investigation.linkedPullRequests.length > 0 && (
                  <section className="rounded-2xl border border-border bg-card p-5">
                    <div className="flex items-center gap-2">
                      <GitPullRequest className="size-4 text-primary" aria-hidden="true" />
                      <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                        Linked Pull Requests
                      </h2>
                    </div>
                    <ul className="mt-4 flex flex-col gap-3">
                      {investigation.linkedPullRequests.map((pullRequest) => (
                        <li key={pullRequest.id} className="rounded-xl border border-border p-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-primary">
                              PR #{pullRequest.number}
                            </span>
                            <span className="rounded-md bg-secondary px-2 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">
                              {pullRequest.state}
                            </span>
                            {pullRequest.url && (
                              <a
                                href={pullRequest.url}
                                target="_blank"
                                rel="noreferrer"
                                className="ml-auto inline-flex items-center gap-1 text-xs text-primary hover:underline"
                              >
                                Open source
                                <ExternalLink className="size-3" aria-hidden="true" />
                              </a>
                            )}
                          </div>
                          <h3 className="mt-2 text-sm font-semibold">{pullRequest.title}</h3>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {pullRequest.author.login} -{' '}
                            {formatDate(pullRequest.mergedAt ?? pullRequest.createdAt)}
                          </p>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">
                            {pullRequest.body?.trim()
                              ? pullRequest.body
                              : 'No pull request description was imported.'}
                          </p>
                          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
                            Explicitly contains commit {shortSha(investigation.commitSha)}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                <section className="rounded-2xl border border-border bg-card p-5">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="size-4 text-primary" aria-hidden="true" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      Verified Evidence
                    </h2>
                  </div>
                  <ul className="mt-4 flex flex-col gap-2">
                    {investigation.evidenceStatus.map((item) => (
                      <li
                        key={item.label}
                        className="rounded-lg border border-primary/25 bg-primary/5 p-3 text-sm"
                      >
                        {item.label}
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="rounded-2xl border border-border bg-card p-5">
                  <div className="flex items-center gap-2">
                    <FileCode2 className="size-4 text-accent" aria-hidden="true" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      Modified Files
                    </h2>
                  </div>
                  {investigation.modifiedFiles.length === 0 ? (
                    <p className="mt-4 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                      This commit was ingested without modified-file records.
                    </p>
                  ) : (
                    <ul className="mt-4 grid gap-3 md:grid-cols-2">
                      {investigation.modifiedFiles.map((artifact) => (
                        <li key={artifact.id} className="rounded-xl border border-border p-3">
                          <span className="rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[10px] uppercase text-accent">
                            {changeLabel(artifact)}
                          </span>
                          <p className="mt-2 break-all font-mono text-sm">{filePath(artifact)}</p>
                          {typeof artifact.metadata.previousPath === 'string' && (
                            <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                              from {artifact.metadata.previousPath}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="rounded-2xl border border-border bg-card p-5">
                  <div className="flex items-center gap-2">
                    <Network className="size-4 text-primary" aria-hidden="true" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      Explicit Evidence Edges
                    </h2>
                  </div>
                  {investigation.evidenceEdges.length === 0 ? (
                    <p className="mt-4 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                      No explicit evidence edges exist for this commit.
                    </p>
                  ) : (
                    <ul className="mt-4 flex flex-col gap-2">
                      {investigation.evidenceEdges.map((edge) => {
                        const pullRequest = investigation.linkedPullRequests.find(
                          (item) => item.id === edge.fromArtifactId,
                        )
                        const modifiedFile = investigation.modifiedFiles.find(
                          (item) => item.id === edge.toArtifactId,
                        )
                        return (
                          <li key={edge.id} className="rounded-lg border border-border p-3">
                            <p className="text-sm font-medium">
                              {edge.relationType === 'contains' && pullRequest
                                ? `PR #${pullRequest.number} contains ${shortSha(investigation.commitSha)}`
                                : `${shortSha(investigation.commitSha)} modifies ${modifiedFile ? filePath(modifiedFile) : ''}`}
                            </p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {edge.explanation}
                            </p>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </section>

                <section className="rounded-2xl border border-border bg-sidebar p-5 xl:hidden">
                  <div className="mb-4 flex items-center gap-2">
                    <AlertTriangle className="size-4 text-primary" aria-hidden="true" />
                    <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      Missing Context
                    </h2>
                  </div>
                  <MissingContextList warnings={investigation.missingContextWarnings} />
                </section>
              </>
            )}
          </div>
        </main>

        <aside className="hidden w-80 shrink-0 border-l border-border bg-sidebar p-4 xl:block 2xl:w-96">
          <div className="flex h-full flex-col gap-4 overflow-y-auto">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-primary" aria-hidden="true" />
              <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Missing Context
              </h2>
            </div>
            {investigation ? (
              <MissingContextList warnings={investigation.missingContextWarnings} />
            ) : (
              <p className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
                Missing-context warnings appear after a commit investigation loads.
              </p>
            )}
          </div>
        </aside>
      </div>

      <footer className="border-t border-border bg-background/70 px-4 py-2 font-mono text-[11px] text-muted-foreground">
        Verified evidence only: imported pull request references, Git commits, and name-status files.
      </footer>
    </div>
  )
}
