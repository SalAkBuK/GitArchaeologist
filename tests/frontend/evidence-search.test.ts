import assert from 'node:assert/strict'
import test from 'node:test'
import type { Artifact } from '../../lib/domain'
import type { CommitInvestigation } from '../../lib/live-api'

const searchUrl = new URL('../../lib/evidence-search.ts', import.meta.url).href
const searchPromise = import(searchUrl) as Promise<typeof import('../../lib/evidence-search')>

const SHA = 'a'.repeat(40)
const OTHER_SHA = 'b'.repeat(40)

function artifact(overrides: Partial<Artifact>): Artifact {
  return {
    id: 'commit-1',
    repositoryId: 'acme/platform',
    sourceType: 'git_commit',
    externalId: SHA,
    title: 'Add repository importing',
    summary: '',
    body: 'Add repository importing with bounded history.',
    occurredAt: '2026-07-15T10:00:00Z',
    ingestedAt: '2026-07-15T10:01:00Z',
    confidence: 1,
    tags: [],
    metadata: {},
    ...overrides,
  }
}

function investigation(): CommitInvestigation {
  return {
    repositoryId: 'acme/platform',
    commitSha: SHA,
    selectedCommit: artifact({}),
    linkedPullRequests: [
      {
        id: 'pr-connected',
        repositoryId: 'acme/platform',
        number: 4,
        title: 'Public repository import',
        body: 'Rationale',
        state: 'merged',
        author: { login: 'developer' },
        createdAt: '2026-07-15T09:00:00Z',
        updatedAt: '2026-07-15T10:00:00Z',
        mergedAt: '2026-07-15T10:00:00Z',
        url: 'https://github.com/acme/platform/pull/4',
        baseBranch: 'main',
        headBranch: 'repository-import',
        commitShas: [SHA],
      },
      {
        id: 'pr-without-edge',
        repositoryId: 'acme/platform',
        number: 9,
        title: 'Matching text but no edge',
        body: null,
        state: 'open',
        author: { login: 'developer' },
        createdAt: '2026-07-15T09:00:00Z',
        updatedAt: '2026-07-15T10:00:00Z',
        mergedAt: null,
        url: null,
        baseBranch: 'main',
        headBranch: 'unrelated',
        commitShas: [],
      },
    ],
    modifiedFiles: [
      artifact({
        id: 'file-connected',
        sourceType: 'modified_file',
        externalId: `${SHA}:backend/app/services/repository_import.py`,
        title: 'backend/app/services/repository_import.py',
        body: '',
        metadata: {
          commitHash: SHA,
          path: 'backend/app/services/repository_import.py',
          changeStatus: 'added',
        },
      }),
      artifact({
        id: 'file-without-edge',
        sourceType: 'modified_file',
        externalId: `${SHA}:unrelated.py`,
        title: 'unrelated.py',
        body: '',
        metadata: { commitHash: SHA, path: 'unrelated.py', changeStatus: 'modified' },
      }),
    ],
    evidenceEdges: [
      {
        id: 'contains-4',
        fromArtifactId: 'pr-connected',
        toArtifactId: 'commit-1',
        relationType: 'contains',
        label: 'contains',
        explanation: 'explicit SHA',
        confidence: 1,
        direct: true,
      },
      {
        id: 'modifies-file',
        fromArtifactId: 'commit-1',
        toArtifactId: 'file-connected',
        relationType: 'modifies',
        label: 'modifies',
        explanation: 'name status',
        confidence: 1,
        direct: true,
      },
    ],
    evidenceStatus: [],
    missingContextWarnings: [],
    unresolvedCommitReferences: [],
  }
}

test('searches loaded commits by SHA and message', async () => {
  const { searchImportedEvidence } = await searchPromise
  const commits = [
    artifact({}),
    artifact({ id: 'commit-2', externalId: OTHER_SHA, title: 'Unrelated cleanup' }),
  ]

  assert.deepEqual(
    searchImportedEvidence({ query: SHA.slice(0, 12), commits, investigation: investigation() }).map(
      (result) => result.artifactId,
    ),
    ['commit-1'],
  )
  assert.equal(
    searchImportedEvidence({ query: 'repository importing', commits, investigation: investigation() })[0]
      .commitSha,
    SHA,
  )
})

test('returns typed PR and file results only through matching direct edges', async () => {
  const { searchImportedEvidence } = await searchPromise
  const source = investigation()

  const pullRequest = searchImportedEvidence({ query: '#4', commits: [], investigation: source })
  const file = searchImportedEvidence({ query: 'repository_import.py', commits: [], investigation: source })
  const unconnectedPr = searchImportedEvidence({ query: 'matching text', commits: [], investigation: source })
  const unconnectedFile = searchImportedEvidence({ query: 'unrelated.py', commits: [], investigation: source })

  assert.deepEqual(pullRequest, [
    {
      artifactId: 'pr-connected',
      artifactType: 'github_pull_request',
      label: 'PR #4',
      detail: 'Public repository import',
      commitSha: SHA,
    },
  ])
  assert.equal(file[0].artifactType, 'modified_file')
  assert.equal(file[0].artifactId, 'file-connected')
  assert.deepEqual(unconnectedPr, [])
  assert.deepEqual(unconnectedFile, [])
})

test('empty filters return no synthetic results', async () => {
  const { searchImportedEvidence, selectedCommitSearchResult } = await searchPromise
  const source = investigation()

  assert.deepEqual(searchImportedEvidence({ query: '   ', commits: [], investigation: source }), [])
  assert.deepEqual(selectedCommitSearchResult(source), {
    artifactId: 'commit-1',
    artifactType: 'git_commit',
    label: `Commit ${SHA.slice(0, 7)}`,
    detail: 'Add repository importing',
    commitSha: SHA,
  })
})
