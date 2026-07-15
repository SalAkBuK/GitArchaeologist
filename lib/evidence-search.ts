import type { Artifact } from '@/lib/domain'
import type { CommitInvestigation, ExplanationArtifactType } from '@/lib/live-api'

export interface EvidenceSearchResult {
  artifactId: string
  artifactType: ExplanationArtifactType
  label: string
  detail: string
  commitSha: string | null
}

export function selectedCommitSearchResult(
  investigation: CommitInvestigation,
): EvidenceSearchResult {
  return {
    artifactId: investigation.selectedCommit.id,
    artifactType: 'git_commit',
    label: `Commit ${investigation.commitSha.slice(0, 7)}`,
    detail: investigation.selectedCommit.title,
    commitSha: investigation.commitSha,
  }
}

export function searchImportedEvidence(options: {
  query: string
  commits: Artifact[]
  investigation: CommitInvestigation
}): EvidenceSearchResult[] {
  const query = options.query.trim().toLowerCase()
  if (!query) return []

  const results: EvidenceSearchResult[] = []
  for (const commit of options.commits) {
    const sha = commit.externalId ?? ''
    const searchable = `${sha}\n${commit.title}\n${commit.body ?? ''}`.toLowerCase()
    if (commit.sourceType === 'git_commit' && searchable.includes(query)) {
      results.push({
        artifactId: commit.id,
        artifactType: 'git_commit',
        label: `Commit ${sha.slice(0, 7)}`,
        detail: commit.title,
        commitSha: sha,
      })
    }
  }

  const directContainsPrIds = new Set(
    options.investigation.evidenceEdges
      .filter(
        (edge) =>
          edge.direct &&
          edge.relationType === 'contains' &&
          edge.toArtifactId === options.investigation.selectedCommit.id,
      )
      .map((edge) => edge.fromArtifactId),
  )
  for (const pullRequest of options.investigation.linkedPullRequests) {
    const number = String(pullRequest.number)
    const searchable = `${number}\n#${number}\n${pullRequest.title}`.toLowerCase()
    if (directContainsPrIds.has(pullRequest.id) && searchable.includes(query)) {
      results.push({
        artifactId: pullRequest.id,
        artifactType: 'github_pull_request',
        label: `PR #${pullRequest.number}`,
        detail: pullRequest.title,
        commitSha: options.investigation.commitSha,
      })
    }
  }

  const directModifiedFileIds = new Set(
    options.investigation.evidenceEdges
      .filter(
        (edge) =>
          edge.direct &&
          edge.relationType === 'modifies' &&
          edge.fromArtifactId === options.investigation.selectedCommit.id,
      )
      .map((edge) => edge.toArtifactId),
  )
  for (const file of options.investigation.modifiedFiles) {
    const path = typeof file.metadata.path === 'string' ? file.metadata.path : file.title
    const previousPath =
      typeof file.metadata.previousPath === 'string' ? file.metadata.previousPath : ''
    if (
      directModifiedFileIds.has(file.id) &&
      `${path}\n${previousPath}`.toLowerCase().includes(query)
    ) {
      results.push({
        artifactId: file.id,
        artifactType: 'modified_file',
        label: path,
        detail: `Modified by commit ${options.investigation.commitSha.slice(0, 7)}`,
        commitSha: options.investigation.commitSha,
      })
    }
  }

  return results.slice(0, 30)
}
