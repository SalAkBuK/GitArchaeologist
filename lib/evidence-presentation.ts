import type { Artifact } from '@/lib/domain'
import type {
  CommitInvestigation,
  MissingContextWarning,
  ModifiedFileStatus,
  PullRequestEvidence,
  RepositoryImportWarning,
  UnresolvedCommitReference,
} from '@/lib/live-api'

export const NO_LINKED_PULL_REQUEST_MESSAGE =
  'No imported pull request contains this commit.'
export const NO_MODIFIED_FILES_MESSAGE =
  'No modified-file evidence was imported for this commit.'
export const NO_RELATIONSHIPS_MESSAGE =
  'No verified evidence relationships were returned for this commit.'
export const UNRESOLVED_REFERENCE_MESSAGE =
  'This pull request references a commit that was not available in the imported repository history.'

export interface SelectedCommitPresentation {
  repositoryId: string
  shortSha: string
  fullSha: string
  subject: string
  message: string
  authorName: string
  authorEmail: string | null
  occurredAt: string
  occurredAtLabel: string
}

export interface LinkedPullRequestPresentation {
  pullRequest: PullRequestEvidence
  relationText: string
  body: string | null
  navigableCommitShas: string[]
}

export interface ModifiedFilePresentation {
  artifact: Artifact
  path: string
  previousPath: string | null
  status: ModifiedFileStatus
  statusLabel: string
}

export interface EvidenceRelationshipPresentation {
  edgeId: string
  relationType: 'contains' | 'modifies'
  sourceArtifactId: string
  targetArtifactId: string
  sourceLabel: string
  targetLabel: string
  explanation: string
}

export interface UnresolvedReferencePresentation {
  reference: UnresolvedCommitReference
  shortSha: string
  message: string
  boundedHistoryNote: string | null
}

export interface EvidencePresentation {
  selectedCommit: SelectedCommitPresentation
  linkedPullRequests: LinkedPullRequestPresentation[]
  modifiedFiles: ModifiedFilePresentation[]
  relationships: EvidenceRelationshipPresentation[]
  warnings: MissingContextWarning[]
  unresolvedReferences: UnresolvedReferencePresentation[]
  evidenceStatusLabels: string[]
  pullRequestImportWasBounded: boolean
}

export function shortCommitSha(sha: string): string {
  return sha.slice(0, 7)
}

export function formatEvidenceTimestamp(value: string): string {
  if (Number.isNaN(Date.parse(value))) return value
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(new Date(value))
}

function filePath(artifact: Artifact): string {
  const path = artifact.metadata.path
  return typeof path === 'string' ? path : artifact.title
}

function fileStatus(artifact: Artifact): ModifiedFileStatus {
  const status = artifact.metadata.changeStatus
  return status === 'added' ||
    status === 'modified' ||
    status === 'deleted' ||
    status === 'renamed'
    ? status
    : 'modified'
}

function relationshipPresentations(
  investigation: CommitInvestigation,
): EvidenceRelationshipPresentation[] {
  const seenEdgeIds = new Set<string>()
  const relationships: EvidenceRelationshipPresentation[] = []

  for (const edge of investigation.evidenceEdges) {
    if (!edge.direct || seenEdgeIds.has(edge.id)) continue
    seenEdgeIds.add(edge.id)

    if (edge.relationType === 'contains') {
      const pullRequest = investigation.linkedPullRequests.find(
        (item) => item.id === edge.fromArtifactId,
      )
      if (!pullRequest || edge.toArtifactId !== investigation.selectedCommit.id) continue
      relationships.push({
        edgeId: edge.id,
        relationType: 'contains',
        sourceArtifactId: pullRequest.id,
        targetArtifactId: investigation.selectedCommit.id,
        sourceLabel: `PR #${pullRequest.number}`,
        targetLabel: `Commit ${shortCommitSha(investigation.commitSha)}`,
        explanation: edge.explanation,
      })
      continue
    }

    if (edge.relationType === 'modifies') {
      const modifiedFile = investigation.modifiedFiles.find(
        (item) => item.id === edge.toArtifactId,
      )
      if (!modifiedFile || edge.fromArtifactId !== investigation.selectedCommit.id) continue
      relationships.push({
        edgeId: edge.id,
        relationType: 'modifies',
        sourceArtifactId: investigation.selectedCommit.id,
        targetArtifactId: modifiedFile.id,
        sourceLabel: `Commit ${shortCommitSha(investigation.commitSha)}`,
        targetLabel: filePath(modifiedFile),
        explanation: edge.explanation,
      })
    }
  }

  return relationships
}

export function createEvidencePresentation(
  investigation: CommitInvestigation,
  options: {
    availableCommitShas?: string[]
    importWarnings?: RepositoryImportWarning[]
  } = {},
): EvidencePresentation {
  const availableCommitShas = new Set(
    (options.availableCommitShas ?? []).map((sha) => sha.toLowerCase()),
  )
  const relationships = relationshipPresentations(investigation)
  const linkedPullRequestIds = new Set(
    relationships
      .filter((item) => item.relationType === 'contains')
      .map((item) => item.sourceArtifactId),
  )
  const modifiedFileIds = new Set(
    relationships
      .filter((item) => item.relationType === 'modifies')
      .map((item) => item.targetArtifactId),
  )
  const historyWasTruncated = (options.importWarnings ?? []).some(
    (warning) => warning.code === 'git_history_truncated',
  )
  const pullRequestImportWasBounded = (options.importWarnings ?? []).some(
    (warning) =>
      warning.code === 'pull_requests_truncated' ||
      warning.code === 'pull_request_commits_truncated',
  )

  const selectedCommit = investigation.selectedCommit
  const message = selectedCommit.body?.trim() || selectedCommit.title
  const authorEmail = selectedCommit.author?.email?.trim() || null

  return {
    selectedCommit: {
      repositoryId: investigation.repositoryId,
      shortSha: shortCommitSha(investigation.commitSha),
      fullSha: investigation.commitSha,
      subject: selectedCommit.title,
      message,
      authorName: selectedCommit.author?.displayName || 'Unknown author',
      authorEmail,
      occurredAt: selectedCommit.occurredAt,
      occurredAtLabel: formatEvidenceTimestamp(selectedCommit.occurredAt),
    },
    linkedPullRequests: investigation.linkedPullRequests
      .filter((pullRequest) => linkedPullRequestIds.has(pullRequest.id))
      .map((pullRequest) => ({
        pullRequest,
        relationText: `PR #${pullRequest.number} contains commit ${shortCommitSha(investigation.commitSha)}`,
        body: pullRequest.body?.trim() ? pullRequest.body : null,
        navigableCommitShas: Array.from(
          new Set(
            pullRequest.commitShas
              .map((sha) => sha.toLowerCase())
              .filter(
                (sha) =>
                  sha !== investigation.commitSha && availableCommitShas.has(sha),
              ),
          ),
        ),
      })),
    modifiedFiles: investigation.modifiedFiles
      .filter((artifact) => modifiedFileIds.has(artifact.id))
      .map((artifact) => {
        const status = fileStatus(artifact)
        return {
          artifact,
          path: filePath(artifact),
          previousPath:
            typeof artifact.metadata.previousPath === 'string'
              ? artifact.metadata.previousPath
              : null,
          status,
          statusLabel: status[0].toUpperCase() + status.slice(1),
        }
      }),
    relationships,
    warnings: investigation.missingContextWarnings,
    unresolvedReferences: investigation.unresolvedCommitReferences.map((reference) => ({
      reference,
      shortSha: shortCommitSha(reference.commitSha),
      message: UNRESOLVED_REFERENCE_MESSAGE,
      boundedHistoryNote: historyWasTruncated
        ? 'The imported Git history was bounded, so the referenced commit may be outside the loaded history.'
        : null,
    })),
    evidenceStatusLabels: investigation.evidenceStatus
      .filter((item) => item.status === 'verified_evidence')
      .map((item) => item.label),
    pullRequestImportWasBounded,
  }
}
