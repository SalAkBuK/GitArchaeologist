'use client'

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  GitCommitVertical,
  GitPullRequest,
  Lightbulb,
  LoaderCircle,
  Search,
  Send,
  X,
} from 'lucide-react'
import type { Artifact } from '@/lib/domain'
import {
  searchImportedEvidence,
  selectedCommitSearchResult,
  type EvidenceSearchResult,
} from '@/lib/evidence-search'
import {
  ApiResponseError,
  createExplanationRunner,
  requestGroundedExplanation,
  validateExplanationQuestion,
  type CitedExplanationStatement,
  type CommitInvestigation,
  type ExplanationRunner,
  type GroundedExplanation,
  type RepositoryImportWarning,
} from '@/lib/live-api'
import { isAbortError } from '@/lib/repository-import'

interface GroundedExplanationProps {
  apiBaseUrl: string
  investigation: CommitInvestigation
  commits: Artifact[]
  importWarnings: RepositoryImportWarning[]
  onSelectCommit: (commitSha: string) => void
}

const TYPE_LABELS = {
  git_commit: 'Commit',
  github_pull_request: 'Pull request',
  modified_file: 'File',
}

const CONFIDENCE_MEANING = {
  high: 'Broad direct evidence and imported rationale are available.',
  medium: 'Direct evidence and some rationale are available, with known gaps.',
  low: 'Direct rationale is limited or important context is missing.',
}

function ResultIcon({ type }: { type: EvidenceSearchResult['artifactType'] }) {
  if (type === 'github_pull_request') {
    return <GitPullRequest className="size-4" aria-hidden="true" />
  }
  if (type === 'modified_file') return <FileCode2 className="size-4" aria-hidden="true" />
  return <GitCommitVertical className="size-4" aria-hidden="true" />
}

function StatementEvidence({
  statement,
  explanation,
  onNavigate,
}: {
  statement: CitedExplanationStatement
  explanation: GroundedExplanation
  onNavigate: (artifactId: string) => void
}) {
  const artifacts = statement.supportingArtifactIds.flatMap((id) => {
    const artifact = explanation.supportingArtifacts.find((item) => item.id === id)
    return artifact ? [artifact] : []
  })
  const edges = statement.supportingEdgeIds.flatMap((id) => {
    const edge = explanation.supportingEdges.find((item) => item.id === id)
    return edge ? [edge] : []
  })

  return (
    <div className="mt-2 flex flex-wrap gap-2" aria-label="Supporting evidence">
      {artifacts.map((artifact) => (
        <button
          key={artifact.id}
          type="button"
          onClick={() => onNavigate(artifact.id)}
          className="rounded-md border border-border px-2 py-1 font-mono text-[11px] text-primary hover:border-primary/40"
        >
          {artifact.label}
        </button>
      ))}
      {edges.map((edge) => (
        <span
          key={edge.id}
          className="rounded-md border border-border px-2 py-1 font-mono text-[11px] text-muted-foreground"
        >
          {edge.sourceLabel} {edge.relationType} {edge.targetLabel}
        </span>
      ))}
    </div>
  )
}

export function GroundedExplanationPanel({
  apiBaseUrl,
  investigation,
  commits,
  importWarnings,
  onSelectCommit,
}: GroundedExplanationProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [context, setContext] = useState<EvidenceSearchResult>(() =>
    selectedCommitSearchResult(investigation),
  )
  const [question, setQuestion] = useState('')
  const [questionError, setQuestionError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [explanation, setExplanation] = useState<GroundedExplanation | null>(null)
  const [error, setError] = useState<{ code: string | null; message: string } | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const runnerRef = useRef<ExplanationRunner | null>(null)
  if (runnerRef.current === null) {
    runnerRef.current = createExplanationRunner(setLoading)
  }

  const searchResults = useMemo(
    () => searchImportedEvidence({ query: searchQuery, commits, investigation }),
    [commits, investigation, searchQuery],
  )

  useEffect(() => {
    controllerRef.current?.abort()
    runnerRef.current?.cancel()
    setContext(selectedCommitSearchResult(investigation))
    setSearchQuery('')
    setExplanation(null)
    setError(null)
    setQuestionError(null)
  }, [investigation])

  useEffect(
    () => () => {
      controllerRef.current?.abort()
      runnerRef.current?.cancel()
    },
    [],
  )

  function selectResult(result: EvidenceSearchResult) {
    controllerRef.current?.abort()
    runnerRef.current?.cancel()
    setExplanation(null)
    setError(null)
    setQuestionError(null)
    setSearchQuery('')
    if (
      result.artifactType === 'git_commit' &&
      result.commitSha &&
      result.commitSha !== investigation.commitSha
    ) {
      onSelectCommit(result.commitSha)
      return
    }
    setContext(result)
  }

  function navigateToSupportingArtifact(artifactId: string) {
    const commit = commits.find((item) => item.id === artifactId)
    if (commit?.externalId) {
      if (commit.externalId !== investigation.commitSha) {
        onSelectCommit(commit.externalId)
      } else {
        document.getElementById('selected-commit-heading')?.scrollIntoView({ behavior: 'smooth' })
      }
      return
    }
    const pullRequest = investigation.linkedPullRequests.find((item) => item.id === artifactId)
    if (pullRequest) {
      document.getElementById('context-heading')?.scrollIntoView({ behavior: 'smooth' })
      return
    }
    const file = investigation.modifiedFiles.find((item) => item.id === artifactId)
    if (file) {
      document.getElementById('changes-heading')?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (runnerRef.current?.isActive()) return
    const validationError = validateExplanationQuestion(question)
    setQuestionError(validationError)
    if (validationError) return

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setError(null)
    try {
      await runnerRef.current?.run(
        () =>
          requestGroundedExplanation({
            apiBaseUrl,
            repositoryId: investigation.repositoryId,
            selectedArtifactId: context.artifactId,
            question,
            importWarningCodes: importWarnings.map((warning) => warning.code),
            signal: controller.signal,
          }),
        (result) => setExplanation(result),
      )
    } catch (requestError) {
      if (!isAbortError(requestError)) {
        setError({
          code: requestError instanceof ApiResponseError ? requestError.code : null,
          message:
            requestError instanceof Error
              ? requestError.message
              : 'Grounded explanation generation failed.',
        })
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }

  function cancelQuestion() {
    controllerRef.current?.abort()
    controllerRef.current = null
    runnerRef.current?.cancel()
  }

  return (
    <section aria-labelledby="grounded-explanation-heading" className="border border-border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="grounded-explanation-heading" className="text-lg font-semibold">
            Grounded explanation
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Deterministic local explanation from imported evidence only.
          </p>
        </div>
        <span className="rounded-md border border-border px-2 py-1 font-mono text-[11px] text-muted-foreground">
          No external model
        </span>
      </div>

      <div className="mt-5">
        <label htmlFor="evidence-search" className="text-sm font-medium">
          Find imported evidence
        </label>
        <div className="relative mt-2">
          <Search
            className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            id="evidence-search"
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Commit SHA, message, PR number, title, or file path"
            className="h-9 w-full border border-border bg-background pl-9 pr-3 text-sm outline-none focus:border-primary"
          />
        </div>
        {searchQuery.trim() && (
          <div className="mt-2 border border-border bg-background" aria-live="polite">
            {searchResults.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                No loaded evidence matches this filter.
              </p>
            ) : (
              <ul className="max-h-64 overflow-y-auto">
                {searchResults.map((result) => (
                  <li key={`${result.artifactType}:${result.artifactId}`}>
                    <button
                      type="button"
                      onClick={() => selectResult(result)}
                      className="flex w-full items-start gap-3 border-b border-border px-3 py-2 text-left last:border-b-0 hover:bg-secondary/60"
                    >
                      <span className="mt-0.5 text-primary">
                        <ResultIcon type={result.artifactType} />
                      </span>
                      <span className="min-w-0">
                        <span className="block font-mono text-[10px] uppercase text-muted-foreground">
                          {TYPE_LABELS[result.artifactType]}
                        </span>
                        <span className="mt-0.5 block break-all text-sm font-medium">
                          {result.label}
                        </span>
                        <span className="mt-0.5 block break-words text-xs text-muted-foreground">
                          {result.detail}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <form onSubmit={submitQuestion} className="mt-5 border-t border-border pt-5">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Question context:</span>
          <span className="rounded-md border border-primary/35 bg-primary/10 px-2 py-1 font-mono text-xs text-primary">
            {TYPE_LABELS[context.artifactType]}: {context.label}
          </span>
        </div>
        <label htmlFor="evidence-question" className="mt-4 block text-sm font-medium">
          Ask about this evidence
        </label>
        <textarea
          id="evidence-question"
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value)
            if (questionError) setQuestionError(null)
          }}
          rows={3}
          maxLength={500}
          placeholder="Why was this changed?"
          aria-invalid={questionError ? true : undefined}
          aria-describedby={questionError ? 'evidence-question-error' : undefined}
          className="mt-2 w-full resize-y border border-border bg-background p-3 text-sm outline-none focus:border-primary"
        />
        {questionError && (
          <p id="evidence-question-error" className="mt-2 text-xs text-destructive">
            {questionError}
          </p>
        )}
        <div className="mt-3 flex items-center gap-2">
          <button
            type="submit"
            disabled={loading}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="size-4" aria-hidden="true" />
            )}
            {loading ? 'Generating' : 'Generate explanation'}
          </button>
          {loading && (
            <button
              type="button"
              onClick={cancelQuestion}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm"
            >
              <X className="size-4" aria-hidden="true" />
              Cancel
            </button>
          )}
        </div>
      </form>

      {error && (
        <div className="mt-5 border border-destructive/40 bg-destructive/10 p-4" role="alert">
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-4" aria-hidden="true" />
            <h3 className="text-sm font-semibold">Explanation unavailable</h3>
          </div>
          {error.code && <p className="mt-2 font-mono text-[11px]">{error.code}</p>}
          <p className="mt-2 text-sm text-muted-foreground">{error.message}</p>
        </div>
      )}

      {explanation && (
        <div className="mt-6 border-t border-border pt-5" aria-live="polite">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase text-muted-foreground">Question</p>
              <p className="mt-1 text-sm font-medium">{explanation.question}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-[10px] uppercase text-muted-foreground">Confidence</p>
              <p className="mt-1 text-sm font-semibold capitalize">{explanation.confidence}</p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                {CONFIDENCE_MEANING[explanation.confidence]}
              </p>
            </div>
          </div>

          <div className="mt-5">
            <h3 className="text-sm font-semibold">Summary</h3>
            <p className="mt-2 text-sm leading-relaxed">{explanation.summary.text}</p>
            <StatementEvidence
              statement={explanation.summary}
              explanation={explanation}
              onNavigate={navigateToSupportingArtifact}
            />
          </div>

          <div className="mt-6 border-t border-border pt-5">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-primary" aria-hidden="true" />
              <h3 className="text-sm font-semibold">Verified evidence</h3>
            </div>
            <ul className="mt-3 space-y-4">
              {explanation.verifiedFacts.map((fact, index) => (
                <li key={`${fact.text}:${index}`}>
                  <p className="text-sm leading-relaxed">{fact.text}</p>
                  <StatementEvidence
                    statement={fact}
                    explanation={explanation}
                    onNavigate={navigateToSupportingArtifact}
                  />
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-6 border-t border-border pt-5">
            <div className="flex items-center gap-2">
              <Lightbulb className="size-4 text-amber-300" aria-hidden="true" />
              <h3 className="text-sm font-semibold">Interpretation</h3>
            </div>
            <ul className="mt-3 space-y-4">
              {explanation.interpretations.map((interpretation, index) => (
                <li key={`${interpretation.text}:${index}`}>
                  <p className="text-sm leading-relaxed">{interpretation.text}</p>
                  <StatementEvidence
                    statement={interpretation}
                    explanation={explanation}
                    onNavigate={navigateToSupportingArtifact}
                  />
                </li>
              ))}
            </ul>
          </div>

          {explanation.missingContext.length > 0 && (
            <div className="mt-6 border-t border-border pt-5">
              <div className="flex items-center gap-2">
                <AlertTriangle className="size-4 text-amber-300" aria-hidden="true" />
                <h3 className="text-sm font-semibold">Missing context</h3>
              </div>
              <ul className="mt-3 space-y-3">
                {explanation.missingContext.map((item) => (
                  <li key={item.id} className="border-l-2 border-amber-400 pl-3">
                    <p className="font-mono text-[11px] text-amber-300">{item.code}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{item.message}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {item.supportingArtifactIds.map((artifactId) => {
                        const artifact = explanation.supportingArtifacts.find(
                          (candidate) => candidate.id === artifactId,
                        )
                        return artifact ? (
                          <button
                            key={artifact.id}
                            type="button"
                            onClick={() => navigateToSupportingArtifact(artifact.id)}
                            className="rounded-md border border-border px-2 py-1 font-mono text-[11px] text-primary"
                          >
                            {artifact.label}
                          </button>
                        ) : null
                      })}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
