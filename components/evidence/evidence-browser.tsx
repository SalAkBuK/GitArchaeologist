'use client'

import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowDown,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileCode2,
  GitCommitVertical,
  GitPullRequest,
  Network,
} from 'lucide-react'
import {
  createEvidencePresentation,
  NO_LINKED_PULL_REQUEST_MESSAGE,
  NO_MODIFIED_FILES_MESSAGE,
  NO_RELATIONSHIPS_MESSAGE,
  formatEvidenceTimestamp,
} from '@/lib/evidence-presentation'
import type { CommitInvestigation, RepositoryImportWarning } from '@/lib/live-api'

interface EvidenceBrowserProps {
  investigation: CommitInvestigation
  availableCommitShas: string[]
  importWarnings: RepositoryImportWarning[]
  onSelectCommit: (commitSha: string) => void
}

const STATUS_CLASSES = {
  added: 'border-emerald-500/35 bg-emerald-500/10 text-emerald-300',
  modified: 'border-primary/35 bg-primary/10 text-primary',
  deleted: 'border-destructive/35 bg-destructive/10 text-destructive',
  renamed: 'border-amber-500/35 bg-amber-500/10 text-amber-300',
}

export function EvidenceBrowser({
  investigation,
  availableCommitShas,
  importWarnings,
  onSelectCommit,
}: EvidenceBrowserProps) {
  const [copied, setCopied] = useState(false)
  const evidence = useMemo(
    () =>
      createEvidencePresentation(investigation, {
        availableCommitShas,
        importWarnings,
      }),
    [availableCommitShas, importWarnings, investigation],
  )

  async function copyFullSha() {
    try {
      await navigator.clipboard.writeText(evidence.selectedCommit.fullSha)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section
        aria-labelledby="selected-commit-heading"
        className="border border-primary/35 bg-card p-5 shadow-xl shadow-black/10"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-primary">
              <GitCommitVertical className="size-4" aria-hidden="true" />
              <h2
                id="selected-commit-heading"
                className="font-mono text-xs uppercase tracking-widest"
              >
                Selected commit
              </h2>
            </div>
            <h3 className="mt-3 max-w-3xl break-words text-xl font-semibold">
              {evidence.selectedCommit.subject}
            </h3>
          </div>
          <span className="rounded-md border border-primary/30 bg-primary/10 px-2 py-1 font-mono text-xs text-primary">
            {evidence.selectedCommit.shortSha}
          </span>
        </div>

        <p className="mt-4 max-h-64 overflow-y-auto whitespace-pre-wrap break-words pr-2 text-sm leading-relaxed text-foreground/85">
          {evidence.selectedCommit.message}
        </p>

        <div className="mt-5 border-t border-border pt-4">
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Full commit SHA
          </p>
          <div className="mt-2 flex items-start gap-2">
            <code className="min-w-0 flex-1 select-all break-all font-mono text-xs text-foreground">
              {evidence.selectedCommit.fullSha}
            </code>
            <button
              type="button"
              onClick={copyFullSha}
              aria-label="Copy full commit SHA"
              title="Copy full commit SHA"
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:border-primary/40 hover:text-primary"
            >
              <Copy className="size-3.5" aria-hidden="true" />
            </button>
          </div>
          {copied && <p className="mt-1 text-xs text-primary">Copied to clipboard.</p>}
        </div>

        <dl className="mt-5 grid gap-4 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Repository
            </dt>
            <dd className="mt-1 break-all text-sm font-medium">
              {evidence.selectedCommit.repositoryId}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Author
            </dt>
            <dd className="mt-1 break-words text-sm font-medium">
              {evidence.selectedCommit.authorName}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Author email
            </dt>
            <dd className="mt-1 break-all text-sm font-medium">
              {evidence.selectedCommit.authorEmail ?? 'Not available'}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Timestamp
            </dt>
            <dd className="mt-1 text-sm font-medium">
              <time dateTime={evidence.selectedCommit.occurredAt}>
                {evidence.selectedCommit.occurredAtLabel} UTC
              </time>
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="context-heading">
        <div className="flex items-center gap-2">
          <GitPullRequest className="size-4 text-primary" aria-hidden="true" />
          <h2 id="context-heading" className="text-lg font-semibold">
            Context
          </h2>
        </div>

        <div className="mt-4 border-t border-border pt-5">
          <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Linked pull requests
          </h3>
          {evidence.linkedPullRequests.length === 0 ? (
            <div className="mt-3 border border-dashed border-border p-4 text-sm text-muted-foreground">
              <p>{NO_LINKED_PULL_REQUEST_MESSAGE}</p>
              {evidence.pullRequestImportWasBounded && (
                <p className="mt-2">
                  Pull request evidence was imported with limits, so additional context may not
                  have been loaded.
                </p>
              )}
            </div>
          ) : (
            <ul className="mt-3 space-y-3">
              {evidence.linkedPullRequests.map(
                ({ pullRequest, relationText, body, navigableCommitShas }) => (
                  <li key={pullRequest.id} className="rounded-lg border border-border bg-card p-4">
                    <div className="flex flex-wrap items-start gap-2">
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
                          rel="noopener noreferrer"
                          aria-label={`Open PR #${pullRequest.number} on GitHub`}
                          className="ml-auto inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          Open on GitHub
                          <ExternalLink className="size-3" aria-hidden="true" />
                        </a>
                      )}
                    </div>
                    <h4 className="mt-2 break-words text-base font-semibold">
                      {pullRequest.title}
                    </h4>
                    <p className="mt-2 font-mono text-[11px] text-primary">{relationText}</p>
                    <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
                      <div>
                        <dt className="text-muted-foreground">Author</dt>
                        <dd className="mt-1 font-medium">{pullRequest.author.login}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Branches</dt>
                        <dd className="mt-1 break-all font-mono">
                          {pullRequest.headBranch} to {pullRequest.baseBranch}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Created</dt>
                        <dd className="mt-1">
                          <time dateTime={pullRequest.createdAt}>
                            {formatEvidenceTimestamp(pullRequest.createdAt)} UTC
                          </time>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Updated</dt>
                        <dd className="mt-1">
                          <time dateTime={pullRequest.updatedAt}>
                            {formatEvidenceTimestamp(pullRequest.updatedAt)} UTC
                          </time>
                        </dd>
                      </div>
                      {pullRequest.mergedAt && (
                        <div>
                          <dt className="text-muted-foreground">Merged</dt>
                          <dd className="mt-1">
                            <time dateTime={pullRequest.mergedAt}>
                              {formatEvidenceTimestamp(pullRequest.mergedAt)} UTC
                            </time>
                          </dd>
                        </div>
                      )}
                    </dl>
                    <div className="mt-4 border-t border-border pt-4">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Pull request context
                      </p>
                      {body ? (
                        <p className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap break-words pr-2 text-sm leading-relaxed text-foreground/85">
                          {body}
                        </p>
                      ) : (
                        <p className="mt-2 text-sm text-muted-foreground">
                          This pull request was imported without a description.
                        </p>
                      )}
                    </div>
                    {navigableCommitShas.length > 0 && (
                      <div className="mt-4 border-t border-border pt-4">
                        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                          Other imported commits in this PR
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {navigableCommitShas.map((sha) => (
                            <button
                              key={sha}
                              type="button"
                              onClick={() => onSelectCommit(sha)}
                              aria-label={`Select linked commit ${sha}`}
                              className="rounded-md border border-border px-2 py-1 font-mono text-xs text-primary hover:border-primary/40"
                            >
                              {sha.slice(0, 7)}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </li>
                ),
              )}
            </ul>
          )}
        </div>

        {evidence.evidenceStatusLabels.length > 0 && (
          <div className="mt-6 border-t border-border pt-5">
            <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Verified evidence status
            </h3>
            <ul className="mt-3 space-y-2">
              {evidence.evidenceStatusLabels.map((label) => (
                <li key={label} className="flex items-start gap-2 text-sm">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {evidence.warnings.length > 0 && (
          <div className="mt-6 border-t border-border pt-5">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-amber-300" aria-hidden="true" />
              <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Missing context
              </h3>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              These are investigation gaps, not repository import failures.
            </p>
            <ul className="mt-3 space-y-3">
              {evidence.warnings.map((warning, index) => (
                <li key={`${warning.code}:${index}`} className="border-l-2 border-amber-400 pl-3">
                  <p className="font-mono text-[11px] text-amber-300">{warning.code}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{warning.message}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {evidence.unresolvedReferences.length > 0 && (
          <div className="mt-6 border-t border-border pt-5">
            <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Unresolved commit references
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Explicit references are listed separately from verified relationships.
            </p>
            <ul className="mt-3 space-y-3">
              {evidence.unresolvedReferences.map(
                ({ reference, shortSha, message, boundedHistoryNote }) => (
                  <li
                    key={`${reference.pullRequestId}:${reference.commitSha}`}
                    className="rounded-lg border border-dashed border-border p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs text-primary">
                        PR #{reference.pullRequestNumber}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">{shortSha}</span>
                    </div>
                    <code className="mt-2 block select-all break-all font-mono text-xs">
                      {reference.commitSha}
                    </code>
                    <p className="mt-2 text-sm text-muted-foreground">{message}</p>
                    {boundedHistoryNote && (
                      <p className="mt-2 text-xs text-muted-foreground">{boundedHistoryNote}</p>
                    )}
                  </li>
                ),
              )}
            </ul>
          </div>
        )}
      </section>

      <section aria-labelledby="changes-heading">
        <div className="flex items-center gap-2">
          <FileCode2 className="size-4 text-primary" aria-hidden="true" />
          <h2 id="changes-heading" className="text-lg font-semibold">
            Changes
          </h2>
        </div>

        <div className="mt-4 border-t border-border pt-5">
          <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Modified files
          </h3>
          {evidence.modifiedFiles.length === 0 ? (
            <p className="mt-3 border border-dashed border-border p-4 text-sm text-muted-foreground">
              {NO_MODIFIED_FILES_MESSAGE}
            </p>
          ) : (
            <ul className="mt-3 grid gap-3 md:grid-cols-2">
              {evidence.modifiedFiles.map(({ artifact, path, previousPath, status, statusLabel }) => (
                <li key={artifact.id} className="rounded-lg border border-border bg-card p-4">
                  <span
                    className={`inline-flex rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase ${STATUS_CLASSES[status]}`}
                  >
                    {statusLabel}
                  </span>
                  {status === 'renamed' && previousPath ? (
                    <div className="mt-3 space-y-2 font-mono text-xs">
                      <div>
                        <p className="text-[10px] uppercase text-muted-foreground">Previous path</p>
                        <code className="mt-1 block break-all">{previousPath}</code>
                      </div>
                      <ArrowDown className="size-3.5 text-muted-foreground" aria-hidden="true" />
                      <div>
                        <p className="text-[10px] uppercase text-muted-foreground">Current path</p>
                        <code className="mt-1 block break-all">{path}</code>
                      </div>
                    </div>
                  ) : (
                    <code className="mt-3 block break-all font-mono text-sm">{path}</code>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-6 border-t border-border pt-5">
          <div className="flex items-center gap-2">
            <Network className="size-4 text-primary" aria-hidden="true" />
            <h3 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Evidence relationships
            </h3>
          </div>
          {evidence.relationships.length === 0 ? (
            <p className="mt-3 border border-dashed border-border p-4 text-sm text-muted-foreground">
              {NO_RELATIONSHIPS_MESSAGE}
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {evidence.relationships.map((relationship) => (
                <li key={relationship.edgeId} className="rounded-lg border border-border bg-card p-4">
                  <p className="break-words text-sm font-medium">{relationship.sourceLabel}</p>
                  <div className="my-2 flex items-center gap-2 pl-2 font-mono text-[11px] text-primary">
                    <ArrowDown className="size-3" aria-hidden="true" />
                    <span>{relationship.relationType}</span>
                  </div>
                  <p className="break-all text-sm font-medium">{relationship.targetLabel}</p>
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                    {relationship.explanation}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}
