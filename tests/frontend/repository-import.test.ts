import assert from 'node:assert/strict'
import test from 'node:test'
import type { RepositoryImportResult } from '../../lib/live-api'

const liveApiUrl = new URL('../../lib/live-api.ts', import.meta.url).href
const repositoryImportUrl = new URL('../../lib/repository-import.ts', import.meta.url).href
const liveApiPromise = import(liveApiUrl) as Promise<typeof import('../../lib/live-api')>
const repositoryImportPromise = import(repositoryImportUrl) as Promise<
  typeof import('../../lib/repository-import')
>

const SHA = 'a'.repeat(40)

function importResult(
  overrides: Partial<RepositoryImportResult> = {},
): RepositoryImportResult {
  return {
    repositoryId: 'openai/example',
    repositoryUrl: 'https://github.com/openai/example',
    selectedCommitSha: SHA,
    gitIngestion: {
      repositoryId: 'openai/example',
      recordsParsed: 15,
      recordsInserted: 12,
      recordsUpdated: 1,
      recordsDeleted: 0,
      recordsSkippedAsDuplicates: 2,
      recordsRejected: 0,
      validationErrors: [],
    },
    pullRequestIngestion: {
      repositoryId: 'openai/example',
      recordsReceived: 5,
      recordsInserted: 4,
      recordsUpdated: 0,
      recordsSkippedAsDuplicates: 1,
      recordsRejected: 0,
      explicitCommitReferencesResolved: 8,
      explicitCommitReferencesUnresolved: 1,
      validationErrors: [],
    },
    warnings: [],
    limits: {
      maxCommits: 500,
      maxPullRequests: 100,
      maxCommitsPerPullRequest: 250,
      maxRepositoryBytes: 104857600,
    },
    ...overrides,
  }
}

test('posts the entered repositoryUrl to the repository import endpoint', async () => {
  const { importPublicRepository } = await liveApiPromise
  let capturedUrl = ''
  let capturedInit: RequestInit | undefined
  const controller = new AbortController()

  const result = await importPublicRepository({
    apiBaseUrl: 'http://127.0.0.1:8000',
    repositoryUrl: 'https://github.com/openai/example',
    signal: controller.signal,
    fetchImplementation: async (input, init) => {
      capturedUrl = String(input)
      capturedInit = init
      return Response.json(importResult())
    },
  })

  assert.equal(capturedUrl, 'http://127.0.0.1:8000/api/repositories/import')
  assert.equal(capturedInit?.method, 'POST')
  assert.deepEqual(JSON.parse(String(capturedInit?.body)), {
    repositoryUrl: 'https://github.com/openai/example',
  })
  assert.equal((capturedInit?.headers as Record<string, string>)['Content-Type'], 'application/json')
  assert.equal(capturedInit?.signal, controller.signal)
  assert.equal(result.selectedCommitSha, SHA)
})

test('performs only lightweight public GitHub HTTPS URL validation', async () => {
  const { validatePublicGithubRepositoryUrl } = await repositoryImportPromise

  assert.equal(validatePublicGithubRepositoryUrl('https://github.com/openai/example'), null)
  assert.match(validatePublicGithubRepositoryUrl('') ?? '', /Enter a public GitHub/)
  assert.match(validatePublicGithubRepositoryUrl('not a url') ?? '', /valid repository URL/)
  assert.match(validatePublicGithubRepositoryUrl('http://github.com/openai/example') ?? '', /HTTPS/)
  assert.match(validatePublicGithubRepositoryUrl('https://gitlab.com/openai/example') ?? '', /github.com/)
})

test('rejects malformed nested ingestion counts', async () => {
  const { parseRepositoryImportResult } = await liveApiPromise

  assert.throws(
    () =>
      parseRepositoryImportResult(
        importResult({
          gitIngestion: {
            ...importResult().gitIngestion,
            recordsInserted: -1,
          },
        }),
      ),
    /invalid ingestion counts/,
  )
  assert.throws(
    () =>
      parseRepositoryImportResult({
        ...importResult(),
        gitIngestion: {
          ...importResult().gitIngestion,
          recordsParsed: '15',
        },
      }),
    /invalid ingestion counts/,
  )
  assert.throws(
    () =>
      parseRepositoryImportResult(
        importResult({
          pullRequestIngestion: {
            ...importResult().pullRequestIngestion,
            recordsReceived: Number.NaN,
          },
        }),
      ),
    /invalid pull request ingestion counts/,
  )
})

test('rejects malformed repository identity, canonical URL, and selected SHA fields', async () => {
  const { parseRepositoryImportResult } = await liveApiPromise

  assert.throws(
    () => parseRepositoryImportResult(importResult({ repositoryId: '  ' })),
    /invalid repository import result/,
  )
  assert.throws(
    () =>
      parseRepositoryImportResult(
        importResult({ repositoryUrl: 'https://github.com/openai/example/' }),
      ),
    /invalid repository import result/,
  )
  assert.throws(
    () => parseRepositoryImportResult(importResult({ selectedCommitSha: 'abc123' })),
    /invalid repository import result/,
  )
})

test('rejects malformed warnings and preserves stable warning codes', async () => {
  const { parseRepositoryImportResult } = await liveApiPromise
  const warnings = [
    { code: 'git_history_truncated', message: 'Git history was bounded.' },
    { code: 'pull_requests_truncated', message: 'Pull requests were bounded.' },
    { code: 'pull_request_commits_truncated', message: 'PR commits were bounded.' },
  ] as RepositoryImportResult['warnings']

  assert.deepEqual(parseRepositoryImportResult(importResult({ warnings })).warnings, warnings)
  assert.throws(
    () =>
      parseRepositoryImportResult({
        ...importResult(),
        warnings: [{ code: 'undocumented_warning', message: 'No contract.' }],
      }),
    /invalid repository import warnings/,
  )
  assert.throws(
    () =>
      parseRepositoryImportResult({
        ...importResult(),
        warnings: [{ code: 'git_history_truncated', message: 12 }],
      }),
    /invalid repository import warnings/,
  )
})

test('rejects malformed limits and cross-repository PR ingestion data', async () => {
  const { parseRepositoryImportResult } = await liveApiPromise

  assert.throws(
    () =>
      parseRepositoryImportResult({
        ...importResult(),
        limits: { ...importResult().limits, maxCommits: 0 },
      }),
    /invalid repository import limits/,
  )
  assert.throws(
    () =>
      parseRepositoryImportResult(
        importResult({
          pullRequestIngestion: {
            ...importResult().pullRequestIngestion,
            repositoryId: 'another/repository',
          },
        }),
      ),
    /different repositories/,
  )
  assert.throws(
    () =>
      parseRepositoryImportResult(
        importResult({
          gitIngestion: {
            ...importResult().gitIngestion,
            repositoryId: 'another/repository',
          },
        }),
      ),
    /different repositories/,
  )
})

test('runner exposes loading state and blocks duplicate submission', async () => {
  const { createRepositoryImportRunner } = await repositoryImportPromise
  const loadingStates: boolean[] = []
  let release: ((result: RepositoryImportResult) => void) | undefined
  const pending = new Promise<RepositoryImportResult>((resolve) => {
    release = resolve
  })
  let successes = 0
  const runner = createRepositoryImportRunner((loading) => loadingStates.push(loading))

  const first = runner.run(() => pending, () => {
    successes += 1
  })
  assert.equal(runner.isActive(), true)
  const duplicate = await runner.run(async () => importResult(), () => {
    successes += 1
  })
  assert.deepEqual(duplicate, { started: false })

  release?.(importResult())
  await first
  assert.deepEqual(loadingStates, [true, false])
  assert.equal(successes, 1)
})

test('cancelled stale import cannot select over a newer repository context', async () => {
  const { createRepositoryImportRunner } = await repositoryImportPromise
  let releaseOld: ((result: RepositoryImportResult) => void) | undefined
  const oldRequest = new Promise<RepositoryImportResult>((resolve) => {
    releaseOld = resolve
  })
  const selected: Array<{ repositoryId: string; selectedCommitSha: string }> = []
  const runner = createRepositoryImportRunner(() => undefined)

  const stale = runner.run(() => oldRequest, (result) => {
    selected.push({
      repositoryId: result.repositoryId,
      selectedCommitSha: result.selectedCommitSha,
    })
  })
  runner.cancel()
  const nextSha = 'b'.repeat(40)
  await runner.run(
    async () =>
      importResult({
        repositoryId: 'openai/newer',
        repositoryUrl: 'https://github.com/openai/newer',
        selectedCommitSha: nextSha,
        gitIngestion: {
          ...importResult().gitIngestion,
          repositoryId: 'openai/newer',
        },
        pullRequestIngestion: {
          ...importResult().pullRequestIngestion,
          repositoryId: 'openai/newer',
        },
      }),
    (result) => {
      selected.push({
        repositoryId: result.repositoryId,
        selectedCommitSha: result.selectedCommitSha,
      })
    },
  )
  releaseOld?.(importResult())
  await stale

  assert.deepEqual(selected, [
    { repositoryId: 'openai/newer', selectedCommitSha: nextSha },
  ])
})

test('import cancellation stays independent from commit-evidence cancellation', async () => {
  const { createRepositoryImportRunner } = await repositoryImportPromise
  const evidenceController = new AbortController()
  const runner = createRepositoryImportRunner(() => undefined)

  runner.cancel()

  assert.equal(evidenceController.signal.aborted, false)
})

test('summary exposes actual Git, PR, and effective-limit fields', async () => {
  const { repositoryImportSummary } = await repositoryImportPromise
  const summary = repositoryImportSummary(importResult())

  assert.deepEqual(summary.git, [
    { label: 'Parsed', value: 15 },
    { label: 'Inserted', value: 12 },
    { label: 'Updated', value: 1 },
    { label: 'Deleted', value: 0 },
    { label: 'Skipped', value: 2 },
    { label: 'Rejected', value: 0 },
  ])
  assert.deepEqual(summary.pullRequests.at(-2), {
    label: 'References resolved',
    value: 8,
  })
  assert.deepEqual(summary.limits, [
    { label: 'Commits', value: 500 },
    { label: 'Pull requests', value: 100 },
    { label: 'Commits per PR', value: 250 },
    { label: 'Repository bytes', value: 104857600 },
  ])
})

test('preserves backend error codes and maps stable import failures safely', async () => {
  const { apiErrorFromResponse } = await liveApiPromise
  const { presentRepositoryImportError } = await repositoryImportPromise
  const cases = [
    ['invalid_repository_url', 'Invalid repository URL'],
    ['unsupported_repository_host', 'Unsupported repository host'],
    ['repository_not_found_or_inaccessible', 'Repository unavailable'],
    ['git_timeout', 'Git import timed out'],
    ['git_command_failed', 'Git import failed'],
    ['github_api_rate_limited', 'GitHub rate limit reached'],
    ['github_api_timeout', 'GitHub request timed out'],
    ['github_api_unavailable', 'GitHub unavailable'],
    ['malformed_github_response', 'Invalid GitHub response'],
    ['empty_repository', 'Empty repository'],
    ['repository_too_large', 'Repository too large'],
    ['repository_import_failed', 'Repository import failed'],
  ] as const

  for (const [code, title] of cases) {
    const error = await apiErrorFromResponse(
      Response.json({ detail: { code, message: 'Sanitized backend message' } }, { status: 422 }),
    )
    assert.equal(error.code, code)
    const presentation = presentRepositoryImportError(error)
    assert.equal(presentation.code, code)
    assert.equal(presentation.title, title)
    assert.notEqual(presentation.message, 'Sanitized backend message')
  }

  assert.deepEqual(presentRepositoryImportError(new TypeError('fetch failed')), {
    title: 'Network failure',
    message: 'The backend could not be reached. Check that it is running and try again.',
  })
})

test('an aborted import is identifiable and does not need failure presentation', async () => {
  const { isAbortError } = await repositoryImportPromise
  const aborted = new DOMException('The request was aborted', 'AbortError')

  assert.equal(isAbortError(aborted), true)
  assert.equal(isAbortError(new Error('network failed')), false)
})
