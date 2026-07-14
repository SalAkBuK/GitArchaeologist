'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  GitBranch,
  GitCommitVertical,
  Network,
  RefreshCw,
  Upload,
} from 'lucide-react'
import type { Artifact } from '@/lib/domain'

interface EvidenceEdge {
  id: string
  fromArtifactId: string
  toArtifactId: string
  relationType: 'modifies'
  label: string
  explanation: string
  confidence: number
  direct: boolean
}

interface EvidenceStatus {
  status: 'verified_evidence' | 'missing_context'
  label: string
  artifactIds: string[]
  edgeIds: string[]
}

interface MissingContextWarning {
  code:
    | 'missing_pull_request'
    | 'missing_issue'
    | 'missing_human_rationale'
    | 'missing_modified_files'
  message: string
}

interface CommitInvestigation {
  repositoryId: string
  commitSha: string
  selectedCommit: Artifact
  modifiedFiles: Artifact[]
  evidenceEdges: EvidenceEdge[]
  evidenceStatus: EvidenceStatus[]
  missingContextWarnings: MissingContextWarning[]
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

export default function Page() {
  const [repositoryId, setRepositoryId] = useState(DEFAULT_REPOSITORY_ID)
  const [commits, setCommits] = useState<Artifact[]>([])
  const [selectedSha, setSelectedSha] = useState<string | null>(null)
  const [investigation, setInvestigation] = useState<CommitInvestigation | null>(null)
  const [loadingCommits, setLoadingCommits] = useState(true)
  const [loadingInvestigation, setLoadingInvestigation] = useState(false)
  const [backendError, setBackendError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const normalizedRepositoryId = repositoryId.trim()

  useEffect(() => {
    let cancelled = false

    async function loadCommits() {
      if (!normalizedRepositoryId) {
        setCommits([])
        setSelectedSha(null)
        setLoadingCommits(false)
        return
      }

      setLoadingCommits(true)
      setBackendError(null)
      setUploadMessage(null)
      try {
        const params = new URLSearchParams({
          repositoryId: normalizedRepositoryId,
          sourceType: 'git_commit',
        })
        const response = await fetch(`${API_BASE_URL}/api/artifacts?${params}`)
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`)
        }
        const data = (await response.json()) as Artifact[]
        if (cancelled) {
          return
        }
        setCommits(data)
        setSelectedSha((current) => {
          if (current && data.some((commit) => commit.externalId === current)) {
            return current
          }
          return data[0]?.externalId ?? null
        })
      } catch (error) {
        if (!cancelled) {
          setBackendError(
            error instanceof Error ? error.message : 'Backend request failed',
          )
          setCommits([])
          setSelectedSha(null)
        }
      } finally {
        if (!cancelled) {
          setLoadingCommits(false)
        }
      }
    }

    loadCommits()
    return () => {
      cancelled = true
    }
  }, [normalizedRepositoryId])

  useEffect(() => {
    let cancelled = false

    async function loadInvestigation() {
      if (!selectedSha || !normalizedRepositoryId) {
        setInvestigation(null)
        setNotFound(false)
        return
      }

      setLoadingInvestigation(true)
      setBackendError(null)
      setNotFound(false)
      try {
        const params = new URLSearchParams({ repositoryId: normalizedRepositoryId })
        const response = await fetch(
          `${API_BASE_URL}/api/investigations/commits/${selectedSha}?${params}`,
        )
        if (response.status === 404) {
          if (!cancelled) {
            setInvestigation(null)
            setNotFound(true)
          }
          return
        }
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`)
        }
        const data = (await response.json()) as CommitInvestigation
        if (!cancelled) {
          setInvestigation(data)
        }
      } catch (error) {
        if (!cancelled) {
          setBackendError(
            error instanceof Error ? error.message : 'Backend request failed',
          )
          setInvestigation(null)
        }
      } finally {
        if (!cancelled) {
          setLoadingInvestigation(false)
        }
      }
    }

    loadInvestigation()
    return () => {
      cancelled = true
    }
  }, [normalizedRepositoryId, selectedSha])

  const selectedCommit = useMemo(
    () => commits.find((commit) => commit.externalId === selectedSha),
    [commits, selectedSha],
  )

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const input = form.elements.namedItem('gitLog') as HTMLInputElement | null
    const file = input?.files?.[0]
    if (!file || !normalizedRepositoryId) {
      setUploadMessage('Choose a Git log file and repository ID first.')
      return
    }

    const payload = new FormData()
    payload.append('repositoryId', normalizedRepositoryId)
    payload.append('file', file)

    setUploading(true)
    setUploadMessage(null)
    setBackendError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/ingestions/git`, {
        method: 'POST',
        body: payload,
      })
      if (!response.ok) {
        throw new Error(`Upload failed with ${response.status}`)
      }
      const result = (await response.json()) as {
        recordsInserted: number
        recordsSkippedAsDuplicates: number
        recordsRejected: number
      }
      setUploadMessage(
        `Inserted ${result.recordsInserted}, skipped ${result.recordsSkippedAsDuplicates}, rejected ${result.recordsRejected}.`,
      )
      form.reset()
      setLoadingCommits(true)
      const params = new URLSearchParams({
        repositoryId: normalizedRepositoryId,
        sourceType: 'git_commit',
      })
      const listResponse = await fetch(`${API_BASE_URL}/api/artifacts?${params}`)
      if (!listResponse.ok) {
        throw new Error(`Backend returned ${listResponse.status}`)
      }
      const data = (await listResponse.json()) as Artifact[]
      setCommits(data)
      setSelectedSha(data[0]?.externalId ?? null)
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setUploading(false)
      setLoadingCommits(false)
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
                onChange={(event) => setRepositoryId(event.target.value)}
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
                        onClick={() => setSelectedSha(commit.externalId ?? null)}
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
            {backendError && (
              <section className="rounded-xl border border-destructive/40 bg-destructive/10 p-4">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertTriangle className="size-4" aria-hidden="true" />
                  <h2 className="text-sm font-semibold">Backend unavailable</h2>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{backendError}</p>
              </section>
            )}

            {!backendError && loadingInvestigation && (
              <section className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
                Loading commit investigation.
              </section>
            )}

            {!backendError && notFound && (
              <section className="rounded-xl border border-border bg-card p-5">
                <h1 className="text-lg font-semibold">Commit not found</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  The selected full SHA does not exist for repository {normalizedRepositoryId}.
                </p>
              </section>
            )}

            {!backendError && !loadingInvestigation && !investigation && !notFound && (
              <section className="rounded-xl border border-border bg-card p-5">
                <h1 className="text-lg font-semibold">No commit selected</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  Upload a supported Git log or select an ingested commit.
                </p>
              </section>
            )}

            {investigation && selectedCommit && (
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
                      No commit-to-file edges exist because no file records were ingested.
                    </p>
                  ) : (
                    <ul className="mt-4 flex flex-col gap-2">
                      {investigation.evidenceEdges.map((edge) => (
                        <li key={edge.id} className="rounded-lg border border-border p-3">
                          <p className="text-sm font-medium">
                            {shortSha(investigation.commitSha)} modifies{' '}
                            {filePath(
                              investigation.modifiedFiles.find(
                                (fileArtifact) => fileArtifact.id === edge.toArtifactId,
                              ) ?? investigation.modifiedFiles[0],
                            )}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {edge.explanation}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
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
              <ul className="flex flex-col gap-3">
                {investigation.missingContextWarnings.map((warning) => (
                  <li key={warning.code} className="rounded-xl border border-border bg-card p-3">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-primary">
                      {warning.code.replaceAll('_', ' ')}
                    </p>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {warning.message}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
                Missing-context warnings appear after a commit investigation loads.
              </p>
            )}
          </div>
        </aside>
      </div>

      <footer className="border-t border-border bg-background/70 px-4 py-2 font-mono text-[11px] text-muted-foreground">
        Verified evidence only: uploaded Git commit records and parsed name-status file records.
      </footer>
    </div>
  )
}
