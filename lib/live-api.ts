import type { Artifact } from '@/lib/domain'

export const MAX_PULL_REQUEST_FIXTURE_BYTES = 5 * 1024 * 1024
export const PULL_REQUEST_FIXTURE_ACCEPT = '.json,application/json'

export type ModifiedFileStatus = 'added' | 'modified' | 'deleted' | 'renamed'
export type PullRequestState = 'open' | 'closed' | 'merged'

export interface PullRequestEvidence {
  id: string
  repositoryId: string
  number: number
  title: string
  body: string | null
  state: PullRequestState
  author: { login: string }
  createdAt: string
  updatedAt: string
  mergedAt: string | null
  url: string | null
  baseBranch: string
  headBranch: string
  commitShas: string[]
}

export interface EvidenceEdge {
  id: string
  fromArtifactId: string
  toArtifactId: string
  relationType: 'contains' | 'modifies'
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
  | 'missing_pull_request_body'
  | 'missing_issue'
  | 'missing_human_rationale'
  | 'missing_modified_files'
  | 'unresolved_pull_request_commit'

export interface MissingContextWarning {
  code: MissingContextCode
  message: string
}

export interface UnresolvedCommitReference {
  pullRequestId: string
  pullRequestNumber: number
  commitSha: string
}

export interface CommitInvestigation {
  repositoryId: string
  commitSha: string
  selectedCommit: Artifact
  linkedPullRequests: PullRequestEvidence[]
  modifiedFiles: Artifact[]
  evidenceEdges: EvidenceEdge[]
  evidenceStatus: EvidenceStatus[]
  missingContextWarnings: MissingContextWarning[]
  unresolvedCommitReferences: UnresolvedCommitReference[]
}

export interface IngestionValidationError {
  recordNumber: number
  message: string
  externalId: string | null
}

export interface IngestionResult {
  repositoryId: string
  recordsParsed: number
  recordsInserted: number
  recordsUpdated: number
  recordsDeleted: number
  recordsSkippedAsDuplicates: number
  recordsRejected: number
  validationErrors: IngestionValidationError[]
}

export interface PullRequestIngestionResult {
  repositoryId: string
  recordsReceived: number
  recordsInserted: number
  recordsUpdated: number
  recordsSkippedAsDuplicates: number
  recordsRejected: number
  explicitCommitReferencesResolved: number
  explicitCommitReferencesUnresolved: number
  validationErrors: IngestionValidationError[]
}

export type RepositoryImportWarningCode =
  | 'git_history_truncated'
  | 'pull_requests_truncated'
  | 'pull_request_commits_truncated'

export interface RepositoryImportWarning {
  code: RepositoryImportWarningCode
  message: string
}

export interface RepositoryImportLimits {
  maxCommits: number
  maxPullRequests: number
  maxCommitsPerPullRequest: number
  maxRepositoryBytes: number
}

export interface RepositoryImportResult {
  repositoryId: string
  repositoryUrl: string
  selectedCommitSha: string
  gitIngestion: IngestionResult
  pullRequestIngestion: PullRequestIngestionResult
  warnings: RepositoryImportWarning[]
  limits: RepositoryImportLimits
}

export class ApiResponseError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(status: number, message: string, code: string | null = null) {
    super(message)
    this.name = 'ApiResponseError'
    this.status = status
    this.code = code
  }
}

export class PullRequestFixtureClientError extends Error {
  readonly code: 'wrong_extension' | 'file_too_large'

  constructor(code: 'wrong_extension' | 'file_too_large', message: string) {
    super(message)
    this.name = 'PullRequestFixtureClientError'
    this.code = code
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value))
}

function isNullableTimestamp(value: unknown): value is string | null {
  return value === null || isTimestamp(value)
}

function isNullableAbsoluteHttpUrl(value: unknown): value is string | null {
  if (value === null) return true
  if (typeof value !== 'string') return false
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

function isFullCommitSha(value: unknown): value is string {
  return typeof value === 'string' && /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(value)
}

function isAbsoluteHttpsGithubUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  try {
    const url = new URL(value)
    const pathParts = url.pathname.split('/').filter(Boolean)
    return (
      url.protocol === 'https:' &&
      url.hostname.toLowerCase() === 'github.com' &&
      !url.username &&
      !url.password &&
      !url.port &&
      !url.search &&
      !url.hash &&
      pathParts.length === 2 &&
      url.pathname === `/${pathParts[0]}/${pathParts[1]}`
    )
  } catch {
    return false
  }
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
    isTimestamp(value.occurredAt) &&
    isTimestamp(value.ingestedAt) &&
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

function isPullRequestEvidence(value: unknown): value is PullRequestEvidence {
  if (!isRecord(value) || !isRecord(value.author)) return false
  return (
    typeof value.id === 'string' &&
    typeof value.repositoryId === 'string' &&
    Number.isInteger(value.number) &&
    Number(value.number) > 0 &&
    typeof value.title === 'string' &&
    (value.body === null || typeof value.body === 'string') &&
    (value.state === 'open' || value.state === 'closed' || value.state === 'merged') &&
    typeof value.author.login === 'string' &&
    isTimestamp(value.createdAt) &&
    isTimestamp(value.updatedAt) &&
    isNullableTimestamp(value.mergedAt) &&
    isNullableAbsoluteHttpUrl(value.url) &&
    typeof value.baseBranch === 'string' &&
    typeof value.headBranch === 'string' &&
    Array.isArray(value.commitShas) &&
    value.commitShas.every(isFullCommitSha)
  )
}

function isEvidenceEdge(value: unknown): value is EvidenceEdge {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.fromArtifactId === 'string' &&
    typeof value.toArtifactId === 'string' &&
    (value.relationType === 'contains' || value.relationType === 'modifies') &&
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
    'missing_pull_request_body',
    'missing_issue',
    'missing_human_rationale',
    'missing_modified_files',
    'unresolved_pull_request_commit',
  ]
  return (
    isRecord(value) &&
    typeof value.code === 'string' &&
    codes.includes(value.code as MissingContextCode) &&
    typeof value.message === 'string'
  )
}

function isUnresolvedCommitReference(value: unknown): value is UnresolvedCommitReference {
  return (
    isRecord(value) &&
    typeof value.pullRequestId === 'string' &&
    Number.isInteger(value.pullRequestNumber) &&
    Number(value.pullRequestNumber) > 0 &&
    isFullCommitSha(value.commitSha)
  )
}

function parseValidationErrors(value: unknown): IngestionValidationError[] {
  if (
    !Array.isArray(value) ||
    !value.every(
      (item) =>
        isRecord(item) &&
        Number.isInteger(item.recordNumber) &&
        Number(item.recordNumber) > 0 &&
        typeof item.message === 'string' &&
        (item.externalId === null ||
          item.externalId === undefined ||
          typeof item.externalId === 'string'),
    )
  ) {
    throw new Error('Backend returned invalid ingestion validation errors')
  }
  return value.map((item) => ({
    recordNumber: item.recordNumber as number,
    message: item.message as string,
    externalId: typeof item.externalId === 'string' ? item.externalId : null,
  }))
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
  const linkedPullRequests = value.linkedPullRequests
  const modifiedFiles = value.modifiedFiles
  const evidenceEdges = value.evidenceEdges
  const evidenceStatus = value.evidenceStatus
  const missingContextWarnings = value.missingContextWarnings
  const unresolvedCommitReferences = value.unresolvedCommitReferences
  if (
    typeof value.repositoryId !== 'string' ||
    !isFullCommitSha(value.commitSha) ||
    !isArtifact(selectedCommit) ||
    selectedCommit.sourceType !== 'git_commit' ||
    !Array.isArray(linkedPullRequests) ||
    !linkedPullRequests.every(isPullRequestEvidence) ||
    !Array.isArray(modifiedFiles) ||
    !modifiedFiles.every(isModifiedFileArtifact) ||
    !Array.isArray(evidenceEdges) ||
    !evidenceEdges.every(isEvidenceEdge) ||
    !Array.isArray(evidenceStatus) ||
    !evidenceStatus.every(isEvidenceStatus) ||
    !Array.isArray(missingContextWarnings) ||
    !missingContextWarnings.every(isMissingContextWarning) ||
    !Array.isArray(unresolvedCommitReferences) ||
    !unresolvedCommitReferences.every(isUnresolvedCommitReference)
  ) {
    throw new Error('Backend returned an invalid commit investigation')
  }

  const pullRequestIds = new Set(linkedPullRequests.map((item) => item.id))
  const fileIds = new Set(modifiedFiles.map((artifact) => artifact.id))
  const edgeIds = new Set(evidenceEdges.map((edge) => edge.id))
  const artifactIds = new Set([selectedCommit.id, ...pullRequestIds, ...fileIds])
  if (
    selectedCommit.repositoryId !== value.repositoryId ||
    selectedCommit.externalId !== value.commitSha ||
    linkedPullRequests.some((item) => item.repositoryId !== value.repositoryId) ||
    modifiedFiles.some(
      (artifact) =>
        artifact.repositoryId !== value.repositoryId ||
        artifact.metadata.commitHash !== value.commitSha,
    ) ||
    evidenceEdges.some((edge) =>
      edge.relationType === 'contains'
        ? !pullRequestIds.has(edge.fromArtifactId) || edge.toArtifactId !== selectedCommit.id
        : edge.fromArtifactId !== selectedCommit.id || !fileIds.has(edge.toArtifactId),
    ) ||
    evidenceStatus.some(
      (status) =>
        status.artifactIds.some((id) => !artifactIds.has(id)) ||
        status.edgeIds.some((id) => !edgeIds.has(id)),
    ) ||
    unresolvedCommitReferences.some((reference) => !pullRequestIds.has(reference.pullRequestId))
  ) {
    throw new Error('Backend returned inconsistent investigation relationships')
  }

  return {
    repositoryId: value.repositoryId,
    commitSha: value.commitSha,
    selectedCommit,
    linkedPullRequests,
    modifiedFiles,
    evidenceEdges,
    evidenceStatus,
    missingContextWarnings,
    unresolvedCommitReferences,
  }
}

export function parseIngestionResult(value: unknown): IngestionResult {
  if (!isRecord(value) || typeof value.repositoryId !== 'string' || !value.repositoryId.trim()) {
    throw new Error('Backend returned an invalid ingestion result')
  }
  const numberFields = [
    'recordsParsed',
    'recordsInserted',
    'recordsUpdated',
    'recordsDeleted',
    'recordsSkippedAsDuplicates',
    'recordsRejected',
  ] as const
  if (numberFields.some((field) => !isNonNegativeInteger(value[field]))) {
    throw new Error('Backend returned invalid ingestion counts')
  }
  return {
    repositoryId: value.repositoryId,
    recordsParsed: value.recordsParsed as number,
    recordsInserted: value.recordsInserted as number,
    recordsUpdated: value.recordsUpdated as number,
    recordsDeleted: value.recordsDeleted as number,
    recordsSkippedAsDuplicates: value.recordsSkippedAsDuplicates as number,
    recordsRejected: value.recordsRejected as number,
    validationErrors: parseValidationErrors(value.validationErrors),
  }
}

export function parsePullRequestIngestionResult(value: unknown): PullRequestIngestionResult {
  if (!isRecord(value) || typeof value.repositoryId !== 'string') {
    throw new Error('Backend returned an invalid pull request ingestion result')
  }
  const numberFields = [
    'recordsReceived',
    'recordsInserted',
    'recordsUpdated',
    'recordsSkippedAsDuplicates',
    'recordsRejected',
    'explicitCommitReferencesResolved',
    'explicitCommitReferencesUnresolved',
  ] as const
  if (numberFields.some((field) => !isNonNegativeInteger(value[field]))) {
    throw new Error('Backend returned invalid pull request ingestion counts')
  }
  if (Number(value.recordsRejected) > Number(value.recordsReceived)) {
    throw new Error('Backend returned inconsistent pull request ingestion counts')
  }
  return {
    repositoryId: value.repositoryId,
    recordsReceived: value.recordsReceived as number,
    recordsInserted: value.recordsInserted as number,
    recordsUpdated: value.recordsUpdated as number,
    recordsSkippedAsDuplicates: value.recordsSkippedAsDuplicates as number,
    recordsRejected: value.recordsRejected as number,
    explicitCommitReferencesResolved: value.explicitCommitReferencesResolved as number,
    explicitCommitReferencesUnresolved: value.explicitCommitReferencesUnresolved as number,
    validationErrors: parseValidationErrors(value.validationErrors),
  }
}

export function parseRepositoryImportResult(value: unknown): RepositoryImportResult {
  if (
    !isRecord(value) ||
    typeof value.repositoryId !== 'string' ||
    !value.repositoryId.trim() ||
    !isAbsoluteHttpsGithubUrl(value.repositoryUrl) ||
    !isFullCommitSha(value.selectedCommitSha)
  ) {
    throw new Error('Backend returned an invalid repository import result')
  }

  const gitIngestion = parseIngestionResult(value.gitIngestion)
  const pullRequestIngestion = parsePullRequestIngestionResult(value.pullRequestIngestion)
  if (
    gitIngestion.repositoryId !== value.repositoryId ||
    pullRequestIngestion.repositoryId !== value.repositoryId
  ) {
    throw new Error('Backend returned repository import data for different repositories')
  }

  const warningCodes: RepositoryImportWarningCode[] = [
    'git_history_truncated',
    'pull_requests_truncated',
    'pull_request_commits_truncated',
  ]
  if (
    !Array.isArray(value.warnings) ||
    !value.warnings.every(
      (warning) =>
        isRecord(warning) &&
        typeof warning.code === 'string' &&
        warningCodes.includes(warning.code as RepositoryImportWarningCode) &&
        typeof warning.message === 'string',
    )
  ) {
    throw new Error('Backend returned invalid repository import warnings')
  }

  if (!isRecord(value.limits)) {
    throw new Error('Backend returned invalid repository import limits')
  }
  const limits = value.limits
  const limitFields = [
    'maxCommits',
    'maxPullRequests',
    'maxCommitsPerPullRequest',
    'maxRepositoryBytes',
  ] as const
  if (
    limitFields.some(
      (field) => !isNonNegativeInteger(limits[field]) || Number(limits[field]) === 0,
    )
  ) {
    throw new Error('Backend returned invalid repository import limits')
  }

  return {
    repositoryId: value.repositoryId,
    repositoryUrl: value.repositoryUrl,
    selectedCommitSha: value.selectedCommitSha,
    gitIngestion,
    pullRequestIngestion,
    warnings: value.warnings as RepositoryImportWarning[],
    limits: {
      maxCommits: limits.maxCommits as number,
      maxPullRequests: limits.maxPullRequests as number,
      maxCommitsPerPullRequest: limits.maxCommitsPerPullRequest as number,
      maxRepositoryBytes: limits.maxRepositoryBytes as number,
    },
  }
}

export async function importPublicRepository(options: {
  apiBaseUrl: string
  repositoryUrl: string
  signal?: AbortSignal
  fetchImplementation?: typeof fetch
}): Promise<RepositoryImportResult> {
  const response = await (options.fetchImplementation ?? fetch)(
    `${options.apiBaseUrl}/api/repositories/import`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repositoryUrl: options.repositoryUrl }),
      signal: options.signal,
    },
  )
  if (!response.ok) {
    throw await apiErrorFromResponse(response)
  }
  return parseRepositoryImportResult(await response.json())
}

export function validatePullRequestFixtureFile(file: Pick<File, 'name' | 'size'>): void {
  if (!file.name.toLowerCase().endsWith('.json')) {
    throw new PullRequestFixtureClientError(
      'wrong_extension',
      'Choose a pull request fixture with a .json extension.',
    )
  }
  if (file.size > MAX_PULL_REQUEST_FIXTURE_BYTES) {
    throw new PullRequestFixtureClientError(
      'file_too_large',
      'Pull request fixture exceeds the 5 MiB upload limit.',
    )
  }
}

export async function uploadPullRequestFixture(options: {
  apiBaseUrl: string
  repositoryId: string
  file: File
  signal?: AbortSignal
  fetchImplementation?: typeof fetch
}): Promise<PullRequestIngestionResult> {
  validatePullRequestFixtureFile(options.file)
  const payload = new FormData()
  payload.append('repositoryId', options.repositoryId)
  payload.append('file', options.file)
  const response = await (options.fetchImplementation ?? fetch)(
    `${options.apiBaseUrl}/api/ingestions/github/pull-requests`,
    {
      method: 'POST',
      body: payload,
      signal: options.signal,
    },
  )
  if (!response.ok) {
    throw await apiErrorFromResponse(response)
  }
  const result = parsePullRequestIngestionResult(await response.json())
  if (result.repositoryId !== options.repositoryId) {
    throw new Error('Backend returned a pull request ingestion result for another repository')
  }
  return result
}

export function pullRequestIngestionSummary(
  result: PullRequestIngestionResult,
): string[] {
  const lines = [
    `Received ${result.recordsReceived}; accepted ${result.recordsReceived - result.recordsRejected}; rejected ${result.recordsRejected}.`,
    `Inserted ${result.recordsInserted}; updated ${result.recordsUpdated}; unchanged ${result.recordsSkippedAsDuplicates}.`,
    `References resolved ${result.explicitCommitReferencesResolved}; unresolved ${result.explicitCommitReferencesUnresolved}.`,
  ]
  if (result.recordsRejected > 0) {
    lines.push(
      `Rejected ${result.recordsRejected} total; showing ${result.validationErrors.length} validation details.`,
    )
  }
  return lines
}

export interface PullRequestUploadRunner {
  isActive(): boolean
  cancel(): void
  run(
    task: () => Promise<PullRequestIngestionResult>,
    onSuccess: (result: PullRequestIngestionResult) => void | Promise<void>,
  ): Promise<{ started: boolean; result?: PullRequestIngestionResult }>
}

export function createPullRequestUploadRunner(
  onLoadingChange: (loading: boolean) => void,
): PullRequestUploadRunner {
  let active = false
  let generation = 0
  return {
    isActive: () => active,
    cancel() {
      generation += 1
      active = false
      onLoadingChange(false)
    },
    async run(task, onSuccess) {
      if (active) return { started: false }
      active = true
      const requestGeneration = ++generation
      onLoadingChange(true)
      try {
        const result = await task()
        if (requestGeneration !== generation) return { started: true }
        await onSuccess(result)
        return { started: true, result }
      } finally {
        if (requestGeneration === generation) {
          active = false
          onLoadingChange(false)
        }
      }
    },
  }
}

export async function apiErrorFromResponse(response: Response): Promise<ApiResponseError> {
  let message = `Backend returned ${response.status}`
  let code: string | null = null
  try {
    const body: unknown = await response.json()
    if (isRecord(body)) {
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (
        isRecord(body.detail) &&
        typeof body.detail.code === 'string' &&
        typeof body.detail.message === 'string'
      ) {
        code = body.detail.code
        message = body.detail.message
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
  return new ApiResponseError(response.status, message, code)
}
