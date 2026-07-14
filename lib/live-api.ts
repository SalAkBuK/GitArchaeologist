import type { Artifact } from '@/lib/domain'

export type ModifiedFileStatus = 'added' | 'modified' | 'deleted' | 'renamed'

export interface EvidenceEdge {
  id: string
  fromArtifactId: string
  toArtifactId: string
  relationType: 'modifies'
  label: string
  explanation: string
  confidence: number
  direct: boolean
}

export interface EvidenceStatus {
  status: 'verified_evidence' | 'missing_context'
  label: string
  artifactIds: string[]
  edgeIds: string[]
}

export type MissingContextCode =
  | 'missing_pull_request'
  | 'missing_issue'
  | 'missing_human_rationale'
  | 'missing_modified_files'

export interface MissingContextWarning {
  code: MissingContextCode
  message: string
}

export interface CommitInvestigation {
  repositoryId: string
  commitSha: string
  selectedCommit: Artifact
  modifiedFiles: Artifact[]
  evidenceEdges: EvidenceEdge[]
  evidenceStatus: EvidenceStatus[]
  missingContextWarnings: MissingContextWarning[]
}

export interface IngestionResult {
  recordsInserted: number
  recordsUpdated: number
  recordsDeleted: number
  recordsSkippedAsDuplicates: number
  recordsRejected: number
  validationErrors: Array<{
    recordNumber: number
    message: string
    externalId: string | null
  }>
}

export class ApiResponseError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiResponseError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isArtifact(value: unknown): value is Artifact {
  if (!isRecord(value) || !isRecord(value.author) || !isRecord(value.metadata)) {
    return false
  }
  return (
    typeof value.id === 'string' &&
    typeof value.repositoryId === 'string' &&
    (value.sourceType === 'git_commit' || value.sourceType === 'modified_file') &&
    typeof value.externalId === 'string' &&
    typeof value.title === 'string' &&
    typeof value.summary === 'string' &&
    typeof value.body === 'string' &&
    typeof value.author.displayName === 'string' &&
    typeof value.occurredAt === 'string' &&
    !Number.isNaN(Date.parse(value.occurredAt)) &&
    typeof value.ingestedAt === 'string' &&
    !Number.isNaN(Date.parse(value.ingestedAt)) &&
    typeof value.confidence === 'number' &&
    isStringArray(value.tags)
  )
}

function modifiedFileStatus(value: unknown): value is ModifiedFileStatus {
  return value === 'added' || value === 'modified' || value === 'deleted' || value === 'renamed'
}

function isModifiedFileArtifact(value: unknown): value is Artifact {
  if (!isArtifact(value) || value.sourceType !== 'modified_file') {
    return false
  }
  const previousPath = value.metadata.previousPath
  return (
    typeof value.metadata.commitHash === 'string' &&
    typeof value.metadata.path === 'string' &&
    modifiedFileStatus(value.metadata.changeStatus) &&
    (previousPath === null || previousPath === undefined || typeof previousPath === 'string')
  )
}

function isEvidenceEdge(value: unknown): value is EvidenceEdge {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.fromArtifactId === 'string' &&
    typeof value.toArtifactId === 'string' &&
    value.relationType === 'modifies' &&
    typeof value.label === 'string' &&
    typeof value.explanation === 'string' &&
    typeof value.confidence === 'number' &&
    typeof value.direct === 'boolean'
  )
}

function isEvidenceStatus(value: unknown): value is EvidenceStatus {
  return (
    isRecord(value) &&
    (value.status === 'verified_evidence' || value.status === 'missing_context') &&
    typeof value.label === 'string' &&
    isStringArray(value.artifactIds) &&
    isStringArray(value.edgeIds)
  )
}

function isMissingContextWarning(value: unknown): value is MissingContextWarning {
  const codes: MissingContextCode[] = [
    'missing_pull_request',
    'missing_issue',
    'missing_human_rationale',
    'missing_modified_files',
  ]
  return (
    isRecord(value) &&
    typeof value.code === 'string' &&
    codes.includes(value.code as MissingContextCode) &&
    typeof value.message === 'string'
  )
}

export function parseArtifactList(value: unknown): Artifact[] {
  if (!Array.isArray(value) || !value.every(isArtifact)) {
    throw new Error('Backend returned an invalid artifact list')
  }
  if (value.some((artifact) => artifact.sourceType !== 'git_commit')) {
    throw new Error('Backend returned a non-commit artifact in the commit list')
  }
  return value
}

export function parseCommitInvestigation(value: unknown): CommitInvestigation {
  if (!isRecord(value)) {
    throw new Error('Backend returned an invalid commit investigation')
  }
  const selectedCommit = value.selectedCommit
  const modifiedFiles = value.modifiedFiles
  const evidenceEdges = value.evidenceEdges
  const evidenceStatus = value.evidenceStatus
  const missingContextWarnings = value.missingContextWarnings
  if (
    typeof value.repositoryId !== 'string' ||
    typeof value.commitSha !== 'string' ||
    !isArtifact(selectedCommit) ||
    selectedCommit.sourceType !== 'git_commit' ||
    !Array.isArray(modifiedFiles) ||
    !modifiedFiles.every(isModifiedFileArtifact) ||
    !Array.isArray(evidenceEdges) ||
    !evidenceEdges.every(isEvidenceEdge) ||
    !Array.isArray(evidenceStatus) ||
    !evidenceStatus.every(isEvidenceStatus) ||
    !Array.isArray(missingContextWarnings) ||
    !missingContextWarnings.every(isMissingContextWarning)
  ) {
    throw new Error('Backend returned an invalid commit investigation')
  }

  const fileIds = new Set(modifiedFiles.map((artifact) => artifact.id))
  if (
    selectedCommit.repositoryId !== value.repositoryId ||
    selectedCommit.externalId !== value.commitSha ||
    modifiedFiles.some(
      (artifact) =>
        artifact.repositoryId !== value.repositoryId ||
        artifact.metadata.commitHash !== value.commitSha,
    ) ||
    evidenceEdges.some(
      (edge) => edge.fromArtifactId !== selectedCommit.id || !fileIds.has(edge.toArtifactId),
    )
  ) {
    throw new Error('Backend returned inconsistent investigation relationships')
  }

  return {
    repositoryId: value.repositoryId,
    commitSha: value.commitSha,
    selectedCommit,
    modifiedFiles,
    evidenceEdges,
    evidenceStatus,
    missingContextWarnings,
  }
}

export function parseIngestionResult(value: unknown): IngestionResult {
  if (!isRecord(value)) {
    throw new Error('Backend returned an invalid ingestion result')
  }
  const numberFields = [
    'recordsInserted',
    'recordsUpdated',
    'recordsDeleted',
    'recordsSkippedAsDuplicates',
    'recordsRejected',
  ] as const
  if (numberFields.some((field) => !Number.isInteger(value[field]) || Number(value[field]) < 0)) {
    throw new Error('Backend returned invalid ingestion counts')
  }
  if (
    !Array.isArray(value.validationErrors) ||
    !value.validationErrors.every(
      (item) =>
        isRecord(item) &&
        Number.isInteger(item.recordNumber) &&
        typeof item.message === 'string' &&
        (item.externalId === null || item.externalId === undefined || typeof item.externalId === 'string'),
    )
  ) {
    throw new Error('Backend returned invalid ingestion validation errors')
  }
  return value as unknown as IngestionResult
}

export async function apiErrorFromResponse(response: Response): Promise<ApiResponseError> {
  let message = `Backend returned ${response.status}`
  try {
    const body: unknown = await response.json()
    if (isRecord(body)) {
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (Array.isArray(body.detail)) {
        const messages = body.detail
          .filter(isRecord)
          .map((item) => {
            const field =
              Array.isArray(item.loc) && typeof item.loc.at(-1) === 'string'
                ? `${item.loc.at(-1)}: `
                : ''
            return typeof item.msg === 'string' ? `${field}${item.msg}` : undefined
          })
          .filter((item): item is string => typeof item === 'string')
        if (messages.length > 0) {
          message = messages.join('; ')
        }
      }
    }
  } catch {
    // Keep the status-based fallback for non-JSON responses.
  }
  return new ApiResponseError(response.status, message)
}
