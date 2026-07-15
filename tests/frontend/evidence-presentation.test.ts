import assert from 'node:assert/strict'
import test from 'node:test'
import type { Artifact } from '../../lib/domain'
import type { CommitInvestigation, EvidenceEdge } from '../../lib/live-api'

const presentationUrl = new URL('../../lib/evidence-presentation.ts', import.meta.url).href
const presentationPromise = import(presentationUrl) as Promise<
  typeof import('../../lib/evidence-presentation')
>

const SHA = '1'.repeat(40)
const LINKED_SHA = '2'.repeat(40)
const UNAVAILABLE_SHA = '3'.repeat(40)

function artifact(
  id: string,
  sourceType: Artifact['sourceType'],
  overrides: Partial<Artifact> = {},
): Artifact {
  return {
    id,
    repositoryId: 'acme/platform',
    sourceType,
    title: id,
    summary: '',
    occurredAt: '2026-07-14T12:30:00Z',
    ingestedAt: '2026-07-14T12:31:00Z',
    confidence: 1,
    tags: [],
    metadata: {},
    ...overrides,
  }
}

function edge(
  id: string,
  relationType: EvidenceEdge['relationType'],
  fromArtifactId: string,
  toArtifactId: string,
): EvidenceEdge {
  return {
    id,
    relationType,
    fromArtifactId,
    toArtifactId,
    label: relationType,
    explanation: `${fromArtifactId} ${relationType} ${toArtifactId}`,
    confidence: 1,
    direct: true,
  }
}

function investigation(overrides: Partial<CommitInvestigation> = {}): CommitInvestigation {
  return {
    repositoryId: 'acme/platform',
    commitSha: SHA,
    selectedCommit: artifact('commit-1', 'git_commit', {
      externalId: SHA,
      title: 'Preserve evidence direction',
      body: 'Full commit message\n\nWith supporting detail.',
      author: { displayName: 'Ada Lovelace', email: 'ada@example.com' },
    }),
    linkedPullRequests: [
      {
        id: 'pr-7',
        repositoryId: 'acme/platform',
        number: 7,
        title: 'Add evidence browser',
        body: 'Pull request rationale.',
        state: 'merged',
        author: { login: 'ada' },
        createdAt: '2026-07-13T10:00:00Z',
        updatedAt: '2026-07-14T11:00:00Z',
        mergedAt: '2026-07-14T11:30:00Z',
        url: 'https://github.com/acme/platform/pull/7',
        baseBranch: 'main',
        headBranch: 'evidence-browser',
        commitShas: [SHA, LINKED_SHA, UNAVAILABLE_SHA, LINKED_SHA],
      },
    ],
    modifiedFiles: [
      artifact('file-added', 'modified_file', {
        title: 'added.ts',
        metadata: { path: 'src/added.ts', changeStatus: 'added' },
      }),
      artifact('file-modified', 'modified_file', {
        title: 'modified.ts',
        metadata: { path: 'src/modified.ts', changeStatus: 'modified' },
      }),
      artifact('file-deleted', 'modified_file', {
        title: 'deleted.ts',
        metadata: { path: 'src/deleted.ts', changeStatus: 'deleted' },
      }),
      artifact('file-renamed', 'modified_file', {
        title: 'current.ts',
        metadata: {
          path: 'src/current.ts',
          previousPath: 'src/previous.ts',
          changeStatus: 'renamed',
        },
      }),
      artifact('file-without-edge', 'modified_file', {
        metadata: { path: 'src/not-evidence.ts', changeStatus: 'modified' },
      }),
    ],
    evidenceEdges: [
      edge('contains-7', 'contains', 'pr-7', 'commit-1'),
      edge('modifies-added', 'modifies', 'commit-1', 'file-added'),
      edge('modifies-modified', 'modifies', 'commit-1', 'file-modified'),
      edge('modifies-deleted', 'modifies', 'commit-1', 'file-deleted'),
      edge('modifies-renamed', 'modifies', 'commit-1', 'file-renamed'),
    ],
    evidenceStatus: [
      {
        status: 'verified_evidence',
        label: 'Commit metadata was imported from Git.',
        artifactIds: ['commit-1'],
        edgeIds: [],
      },
      {
        status: 'missing_context',
        label: 'Human rationale is unavailable.',
        artifactIds: ['commit-1'],
        edgeIds: [],
      },
    ],
    missingContextWarnings: [
      { code: 'missing_issue', message: 'No issue reference was imported.' },
    ],
    unresolvedCommitReferences: [
      { pullRequestId: 'pr-7', pullRequestNumber: 7, commitSha: UNAVAILABLE_SHA },
    ],
    ...overrides,
  }
}

test('presents the selected commit and only verified PR and file relationships', async () => {
  const { createEvidencePresentation } = await presentationPromise
  const evidence = createEvidencePresentation(investigation(), {
    availableCommitShas: [SHA, LINKED_SHA],
  })

  assert.deepEqual(evidence.selectedCommit, {
    repositoryId: 'acme/platform',
    shortSha: SHA.slice(0, 7),
    fullSha: SHA,
    subject: 'Preserve evidence direction',
    message: 'Full commit message\n\nWith supporting detail.',
    authorName: 'Ada Lovelace',
    authorEmail: 'ada@example.com',
    occurredAt: '2026-07-14T12:30:00Z',
    occurredAtLabel: 'Jul 14, 2026, 12:30',
  })
  assert.equal(evidence.linkedPullRequests.length, 1)
  assert.equal(evidence.linkedPullRequests[0].pullRequest.url, 'https://github.com/acme/platform/pull/7')
  assert.equal(evidence.linkedPullRequests[0].body, 'Pull request rationale.')
  assert.deepEqual(evidence.linkedPullRequests[0].navigableCommitShas, [LINKED_SHA])
  assert.deepEqual(
    evidence.modifiedFiles.map(({ path, status }) => [path, status]),
    [
      ['src/added.ts', 'added'],
      ['src/modified.ts', 'modified'],
      ['src/deleted.ts', 'deleted'],
      ['src/current.ts', 'renamed'],
    ],
  )
  assert.equal(evidence.modifiedFiles[3].previousPath, 'src/previous.ts')
  assert.deepEqual(evidence.relationships[0], {
    edgeId: 'contains-7',
    relationType: 'contains',
    sourceArtifactId: 'pr-7',
    targetArtifactId: 'commit-1',
    sourceLabel: 'PR #7',
    targetLabel: `Commit ${SHA.slice(0, 7)}`,
    explanation: 'pr-7 contains commit-1',
  })
  assert.deepEqual(evidence.evidenceStatusLabels, ['Commit metadata was imported from Git.'])
})

test('does not infer PRs or files from artifact arrays without matching direct edges', async () => {
  const {
    createEvidencePresentation,
    NO_LINKED_PULL_REQUEST_MESSAGE,
    NO_MODIFIED_FILES_MESSAGE,
    NO_RELATIONSHIPS_MESSAGE,
  } = await presentationPromise
  const source = investigation()
  const evidence = createEvidencePresentation(
    investigation({
      evidenceEdges: [
        { ...source.evidenceEdges[0], direct: false },
        edge('wrong-pr-direction', 'contains', 'commit-1', 'pr-7'),
        edge('wrong-file-direction', 'modifies', 'file-added', 'commit-1'),
      ],
    }),
  )

  assert.equal(evidence.linkedPullRequests.length, 0, NO_LINKED_PULL_REQUEST_MESSAGE)
  assert.equal(evidence.modifiedFiles.length, 0, NO_MODIFIED_FILES_MESSAGE)
  assert.equal(evidence.relationships.length, 0)
  assert.equal(NO_LINKED_PULL_REQUEST_MESSAGE, 'No imported pull request contains this commit.')
  assert.equal(NO_MODIFIED_FILES_MESSAGE, 'No modified-file evidence was imported for this commit.')
  assert.equal(
    NO_RELATIONSHIPS_MESSAGE,
    'No verified evidence relationships were returned for this commit.',
  )
})

test('keeps warnings and unresolved references separate from verified relationships', async () => {
  const { createEvidencePresentation, UNRESOLVED_REFERENCE_MESSAGE } = await presentationPromise
  const evidence = createEvidencePresentation(investigation(), {
    importWarnings: [
      { code: 'git_history_truncated', message: 'History limit reached.' },
      { code: 'pull_requests_truncated', message: 'Pull request limit reached.' },
    ],
  })

  assert.deepEqual(evidence.warnings, [
    { code: 'missing_issue', message: 'No issue reference was imported.' },
  ])
  assert.equal(evidence.unresolvedReferences[0].message, UNRESOLVED_REFERENCE_MESSAGE)
  assert.match(evidence.unresolvedReferences[0].boundedHistoryNote ?? '', /bounded/)
  assert.equal(evidence.pullRequestImportWasBounded, true)
  assert.equal(evidence.relationships.some((item) => item.targetArtifactId === UNAVAILABLE_SHA), false)

  const unbounded = createEvidencePresentation(investigation())
  assert.equal(unbounded.unresolvedReferences[0].boundedHistoryNote, null)
  assert.equal(unbounded.pullRequestImportWasBounded, false)
})

test('handles optional commit and PR fields without inventing values', async () => {
  const { createEvidencePresentation } = await presentationPromise
  const source = investigation()
  const evidence = createEvidencePresentation(
    investigation({
      selectedCommit: { ...source.selectedCommit, body: undefined, author: undefined },
      linkedPullRequests: [{ ...source.linkedPullRequests[0], body: '   ', url: null }],
      missingContextWarnings: [],
      unresolvedCommitReferences: [],
    }),
  )

  assert.equal(evidence.selectedCommit.message, source.selectedCommit.title)
  assert.equal(evidence.selectedCommit.authorName, 'Unknown author')
  assert.equal(evidence.selectedCommit.authorEmail, null)
  assert.equal(evidence.linkedPullRequests[0].body, null)
  assert.equal(evidence.linkedPullRequests[0].pullRequest.url, null)
  assert.deepEqual(evidence.warnings, [])
  assert.deepEqual(evidence.unresolvedReferences, [])
})

test('deduplicates edge IDs and ignores unknown relationship types safely', async () => {
  const { createEvidencePresentation } = await presentationPromise
  const source = investigation()
  const unknownEdge = {
    ...edge('unknown-edge', 'modifies', 'commit-1', 'file-added'),
    relationType: 'mentions',
  } as unknown as EvidenceEdge
  const evidence = createEvidencePresentation(
    investigation({
      evidenceEdges: [source.evidenceEdges[0], source.evidenceEdges[0], unknownEdge],
    }),
  )

  assert.deepEqual(evidence.relationships.map((item) => item.edgeId), ['contains-7'])
  assert.equal(evidence.linkedPullRequests.length, 1)
  assert.equal(evidence.modifiedFiles.length, 0)
})
