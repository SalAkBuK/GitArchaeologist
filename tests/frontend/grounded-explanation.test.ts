import assert from 'node:assert/strict'
import test from 'node:test'
import type { GroundedExplanation } from '../../lib/live-api'

const liveApiUrl = new URL('../../lib/live-api.ts', import.meta.url).href
const liveApiPromise = import(liveApiUrl) as Promise<typeof import('../../lib/live-api')>

function explanation(overrides: Partial<GroundedExplanation> = {}): GroundedExplanation {
  return {
    generator: 'deterministic_local',
    question: 'Why was this changed?',
    context: { artifactId: 'commit-1', artifactType: 'git_commit', label: 'Commit aaaaaaa' },
    summary: {
      text: 'Imported evidence connects one commit and one file.',
      supportingArtifactIds: ['commit-1'],
      supportingEdgeIds: ['edge-1'],
    },
    verifiedFacts: [
      {
        text: 'Commit aaaaaaa modifies backend/app/main.py.',
        supportingArtifactIds: ['commit-1', 'file-1'],
        supportingEdgeIds: ['edge-1'],
      },
    ],
    interpretations: [
      {
        text: 'The commit message suggests the change intended to add importing.',
        supportingArtifactIds: ['commit-1'],
        supportingEdgeIds: [],
      },
    ],
    missingContext: [
      {
        id: 'warning:1',
        code: 'missing_issue',
        message: 'No issue evidence was imported.',
        supportingArtifactIds: ['commit-1'],
        warningIds: ['warning:1'],
        unresolvedReferenceIds: [],
      },
    ],
    supportingArtifacts: [
      { id: 'commit-1', sourceType: 'git_commit', label: 'Commit aaaaaaa' },
      { id: 'file-1', sourceType: 'modified_file', label: 'backend/app/main.py' },
    ],
    supportingEdges: [
      {
        id: 'edge-1',
        relationType: 'modifies',
        fromArtifactId: 'commit-1',
        toArtifactId: 'file-1',
        sourceLabel: 'Commit aaaaaaa',
        targetLabel: 'backend/app/main.py',
      },
    ],
    confidence: 'low',
    ...overrides,
  }
}

test('posts bounded question context and validates the structured explanation', async () => {
  const { requestGroundedExplanation } = await liveApiPromise
  let capturedUrl = ''
  let capturedBody: unknown
  const result = await requestGroundedExplanation({
    apiBaseUrl: 'http://127.0.0.1:8000',
    repositoryId: 'acme/platform',
    selectedArtifactId: 'commit-1',
    question: '  Why was this changed?  ',
    importWarningCodes: ['git_history_truncated'],
    fetchImplementation: async (input, init) => {
      capturedUrl = String(input)
      capturedBody = JSON.parse(String(init?.body))
      return Response.json(explanation())
    },
  })

  assert.equal(capturedUrl, 'http://127.0.0.1:8000/api/explanations')
  assert.deepEqual(capturedBody, {
    repositoryId: 'acme/platform',
    selectedArtifactId: 'commit-1',
    question: 'Why was this changed?',
    importWarningCodes: ['git_history_truncated'],
  })
  assert.equal(result.verifiedFacts[0].supportingEdgeIds[0], 'edge-1')
  assert.equal(result.interpretations.length, 1)
  assert.equal(result.missingContext[0].code, 'missing_issue')
})

test('rejects malformed claims and citations outside supporting evidence', async () => {
  const { parseGroundedExplanation } = await liveApiPromise
  assert.throws(
    () =>
      parseGroundedExplanation(
        explanation({
          verifiedFacts: [{ text: 'Unsupported fact', supportingArtifactIds: [], supportingEdgeIds: [] }],
        }),
      ),
    /invalid grounded explanation/,
  )
  assert.throws(
    () =>
      parseGroundedExplanation(
        explanation({
          interpretations: [
            {
              text: 'Unsupported interpretation',
              supportingArtifactIds: ['artifact-outside-bundle'],
              supportingEdgeIds: [],
            },
          ],
        }),
      ),
    /inconsistent explanation citations/,
  )
})

test('validates empty and overlong questions before fetch', async () => {
  const { MAX_EXPLANATION_QUESTION_LENGTH, validateExplanationQuestion } = await liveApiPromise
  assert.match(validateExplanationQuestion('   ') ?? '', /Enter a question/)
  assert.match(
    validateExplanationQuestion('x'.repeat(MAX_EXPLANATION_QUESTION_LENGTH + 1)) ?? '',
    /500 characters/,
  )
  assert.equal(validateExplanationQuestion('Which files changed?'), null)
})

test('runner prevents duplicates and ignores cancelled stale responses', async () => {
  const { createExplanationRunner } = await liveApiPromise
  const loadingStates: boolean[] = []
  const accepted: string[] = []
  let resolveFirst: ((value: GroundedExplanation) => void) | undefined
  const firstResult = new Promise<GroundedExplanation>((resolve) => {
    resolveFirst = resolve
  })
  const runner = createExplanationRunner((loading) => loadingStates.push(loading))

  const first = runner.run(() => firstResult, (result) => {
    accepted.push(result.question)
  })
  const duplicate = await runner.run(
    async () => explanation({ question: 'duplicate' }),
    (result) => {
      accepted.push(result.question)
    },
  )
  runner.cancel()
  resolveFirst?.(explanation({ question: 'stale' }))
  await first

  assert.deepEqual(duplicate, { started: false })
  assert.deepEqual(accepted, [])
  assert.deepEqual(loadingStates, [true, false])
})

test('failed generation does not replace previously accepted evidence', async () => {
  const { createExplanationRunner } = await liveApiPromise
  let current = explanation({ question: 'existing evidence' })
  const runner = createExplanationRunner(() => undefined)

  await assert.rejects(
    runner.run(
      async () => {
        throw new Error('generation failed')
      },
      (result) => {
        current = result
      },
    ),
    /generation failed/,
  )
  assert.equal(current.question, 'existing evidence')
})
