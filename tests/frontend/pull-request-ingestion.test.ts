import assert from 'node:assert/strict'
import test from 'node:test'
import type { PullRequestIngestionResult } from '../../lib/live-api'

const liveApiUrl = new URL('../../lib/live-api.ts', import.meta.url).href
const liveApiPromise = import(liveApiUrl) as Promise<typeof import('../../lib/live-api')>

const SHA = '1'.repeat(40)

function ingestionResult(
  overrides: Partial<PullRequestIngestionResult> = {},
): PullRequestIngestionResult {
  return {
    repositoryId: 'acme/platform',
    recordsReceived: 2,
    recordsInserted: 1,
    recordsUpdated: 0,
    recordsSkippedAsDuplicates: 0,
    recordsRejected: 1,
    explicitCommitReferencesResolved: 1,
    explicitCommitReferencesUnresolved: 0,
    validationErrors: [
      { recordNumber: 2, message: 'title: Field required', externalId: null },
    ],
    ...overrides,
  }
}

test('accepts .json selection and constructs the documented multipart request', async () => {
  const { PULL_REQUEST_FIXTURE_ACCEPT, uploadPullRequestFixture } = await liveApiPromise
  assert.equal(PULL_REQUEST_FIXTURE_ACCEPT, '.json,application/json')
  const file = new File(['{"schemaVersion":1}'], 'pull_requests.JSON', {
    type: 'application/json',
  })
  let capturedUrl = ''
  let capturedBody: FormData | undefined
  const fetchImplementation: typeof fetch = async (input, init) => {
    capturedUrl = String(input)
    capturedBody = init?.body as FormData
    return Response.json(ingestionResult())
  }

  const result = await uploadPullRequestFixture({
    apiBaseUrl: 'http://127.0.0.1:8000',
    repositoryId: 'acme/platform',
    file,
    fetchImplementation,
  })

  assert.equal(capturedUrl, 'http://127.0.0.1:8000/api/ingestions/github/pull-requests')
  assert.equal(capturedBody?.get('repositoryId'), 'acme/platform')
  assert.equal((capturedBody?.get('file') as File).name, 'pull_requests.JSON')
  assert.equal(result.recordsReceived, 2)
})

test('rejects non-json and greater-than-5-MiB files before fetch', async () => {
  const {
    MAX_PULL_REQUEST_FIXTURE_BYTES,
    PullRequestFixtureClientError,
    validatePullRequestFixtureFile,
  } = await liveApiPromise
  assert.throws(
    () => validatePullRequestFixtureFile(new File(['x'], 'fixture.txt')),
    (error) =>
      error instanceof PullRequestFixtureClientError && error.code === 'wrong_extension',
  )
  const oversized = new File(
    [new Uint8Array(MAX_PULL_REQUEST_FIXTURE_BYTES + 1)],
    'fixture.json',
  )
  assert.throws(
    () => validatePullRequestFixtureFile(oversized),
    (error) =>
      error instanceof PullRequestFixtureClientError && error.code === 'file_too_large',
  )
})

test('submission runner exposes loading, prevents duplicates, and refreshes after success', async () => {
  const { createPullRequestUploadRunner } = await liveApiPromise
  const loadingStates: boolean[] = []
  let release: ((value: PullRequestIngestionResult) => void) | undefined
  const pending = new Promise<PullRequestIngestionResult>((resolve) => {
    release = resolve
  })
  let refreshes = 0
  const runner = createPullRequestUploadRunner((loading) => loadingStates.push(loading))

  const first = runner.run(() => pending, () => {
    refreshes += 1
  })
  assert.equal(runner.isActive(), true)
  const duplicate = await runner.run(
    async () => ingestionResult(),
    () => {
      refreshes += 1
    },
  )
  assert.deepEqual(duplicate, { started: false })

  release?.(ingestionResult())
  await first
  assert.deepEqual(loadingStates, [true, false])
  assert.equal(runner.isActive(), false)
  assert.equal(refreshes, 1)
})

test('cancelled stale upload cannot refresh a newly selected repository', async () => {
  const { createPullRequestUploadRunner } = await liveApiPromise
  const loadingStates: boolean[] = []
  let releaseOld: ((value: PullRequestIngestionResult) => void) | undefined
  const oldRequest = new Promise<PullRequestIngestionResult>((resolve) => {
    releaseOld = resolve
  })
  const refreshedRepositories: string[] = []
  const runner = createPullRequestUploadRunner((loading) => loadingStates.push(loading))

  const stale = runner.run(() => oldRequest, (result) => {
    refreshedRepositories.push(result.repositoryId)
  })
  runner.cancel()
  await runner.run(
    async () => ingestionResult({ repositoryId: 'acme/new' }),
    (result) => {
      refreshedRepositories.push(result.repositoryId)
    },
  )
  releaseOld?.(ingestionResult({ repositoryId: 'acme/old' }))
  await stale

  assert.deepEqual(refreshedRepositories, ['acme/new'])
  assert.deepEqual(loadingStates, [true, false, true, false])
})

test('summary shows complete rejected count beside bounded validation details', async () => {
  const { parsePullRequestIngestionResult, pullRequestIngestionSummary } = await liveApiPromise
  const boundedErrors = Array.from({ length: 100 }, (_, index) => ({
    recordNumber: index + 1,
    message: 'number: Input should be greater than 0',
    externalId: null,
  }))
  const result = parsePullRequestIngestionResult(
    ingestionResult({
      recordsReceived: 106,
      recordsRejected: 105,
      validationErrors: boundedErrors,
    }),
  )

  assert.deepEqual(pullRequestIngestionSummary(result), [
    'Received 106; accepted 1; rejected 105.',
    'Inserted 1; updated 0; unchanged 0.',
    'References resolved 1; unresolved 0.',
    'Rejected 105 total; showing 100 validation details.',
  ])
})

test('repository mismatch preserves the backend status and message', async () => {
  const { ApiResponseError, uploadPullRequestFixture } = await liveApiPromise
  const file = new File(['{}'], 'fixture.json', { type: 'application/json' })
  await assert.rejects(
    uploadPullRequestFixture({
      apiBaseUrl: 'http://127.0.0.1:8000',
      repositoryId: 'acme/platform',
      file,
      fetchImplementation: async () =>
        Response.json(
          { detail: 'Fixture repositoryId does not match the request repositoryId' },
          { status: 422 },
        ),
    }),
    (error) => {
      assert.ok(error instanceof ApiResponseError)
      assert.equal(error.status, 422)
      assert.equal(error.message, 'Fixture repositoryId does not match the request repositoryId')
      return true
    },
  )
})

test('investigation validation preserves warning codes and exact contains direction', async () => {
  const { parseCommitInvestigation } = await liveApiPromise
  const commit = {
    id: 'commit-id',
    repositoryId: 'acme/platform',
    sourceType: 'git_commit',
    externalId: SHA,
    title: 'Commit title',
    summary: 'Commit title',
    body: 'Commit title',
    author: { displayName: 'Developer', email: 'dev@example.com', provider: 'git' },
    occurredAt: '2026-07-10T10:00:00Z',
    ingestedAt: '2026-07-10T10:01:00Z',
    confidence: 1,
    tags: [],
    metadata: {},
  }
  const pullRequest = {
    id: 'pr-id',
    repositoryId: 'acme/platform',
    number: 22,
    title: 'Explicit fixture evidence',
    body: null,
    state: 'merged',
    author: { login: 'developer' },
    createdAt: '2026-07-10T10:00:00Z',
    updatedAt: '2026-07-11T12:00:00Z',
    mergedAt: '2026-07-11T12:00:00Z',
    url: 'https://github.com/example/repository/pull/22',
    baseBranch: 'main',
    headBranch: 'feature/evidence',
    commitShas: [SHA],
  }
  const investigation = parseCommitInvestigation({
    repositoryId: 'acme/platform',
    commitSha: SHA,
    selectedCommit: commit,
    linkedPullRequests: [pullRequest],
    modifiedFiles: [],
    evidenceEdges: [
      {
        id: 'edge-id',
        fromArtifactId: 'pr-id',
        toArtifactId: 'commit-id',
        relationType: 'contains',
        label: 'Pull request contains commit',
        explanation: 'Explicit fixture SHA.',
        confidence: 1,
        direct: true,
      },
    ],
    evidenceStatus: [
      {
        status: 'verified_evidence',
        label: 'Explicit PR evidence.',
        artifactIds: ['pr-id'],
        edgeIds: ['edge-id'],
      },
    ],
    missingContextWarnings: [
      {
        code: 'missing_pull_request_body',
        message: 'The linked pull request does not include a description explaining the change.',
      },
      {
        code: 'missing_issue',
        message: 'No issue evidence has been imported for this investigation.',
      },
    ],
    unresolvedCommitReferences: [],
  })

  assert.equal(investigation.evidenceEdges[0].fromArtifactId, pullRequest.id)
  assert.equal(investigation.evidenceEdges[0].toArtifactId, commit.id)
  assert.deepEqual(investigation.missingContextWarnings, [
    {
      code: 'missing_pull_request_body',
      message: 'The linked pull request does not include a description explaining the change.',
    },
    {
      code: 'missing_issue',
      message: 'No issue evidence has been imported for this investigation.',
    },
  ])
  assert.throws(
    () =>
      parseCommitInvestigation({
        ...investigation,
        evidenceEdges: [
          {
            ...investigation.evidenceEdges[0],
            fromArtifactId: commit.id,
            toArtifactId: pullRequest.id,
          },
        ],
      }),
    /inconsistent investigation relationships/,
  )
})
