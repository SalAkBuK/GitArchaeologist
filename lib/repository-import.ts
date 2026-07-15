import type { RepositoryImportResult } from './live-api'

export interface RepositoryImportErrorPresentation {
  title: string
  message: string
  code?: string
}

export interface RepositoryImportSummaryItem {
  label: string
  value: number
}

export interface RepositoryImportSummary {
  git: RepositoryImportSummaryItem[]
  pullRequests: RepositoryImportSummaryItem[]
  limits: RepositoryImportSummaryItem[]
}

export interface RepositoryImportRunner {
  isActive(): boolean
  cancel(): void
  run(
    task: () => Promise<RepositoryImportResult>,
    onSuccess: (result: RepositoryImportResult) => void | Promise<void>,
  ): Promise<{ started: boolean; result?: RepositoryImportResult; error?: unknown }>
}

const KNOWN_IMPORT_ERRORS: Record<
  string,
  Omit<RepositoryImportErrorPresentation, 'code'>
> = {
  invalid_repository_url: {
    title: 'Invalid repository URL',
    message: 'Enter a valid public GitHub HTTPS repository URL.',
  },
  unsupported_repository_host: {
    title: 'Unsupported repository host',
    message: 'Only public repositories hosted on github.com are supported.',
  },
  repository_not_found_or_inaccessible: {
    title: 'Repository unavailable',
    message: 'The repository was not found, is private, or cannot be accessed publicly.',
  },
  git_timeout: {
    title: 'Git import timed out',
    message: 'The repository could not be cloned within the configured time limit.',
  },
  repository_too_large: {
    title: 'Repository too large',
    message: 'The repository exceeds the configured import size limit.',
  },
  git_command_failed: {
    title: 'Git import failed',
    message: 'Git could not import this public repository.',
  },
  github_api_timeout: {
    title: 'GitHub request timed out',
    message: 'GitHub did not respond within the configured time limit.',
  },
  github_api_rate_limited: {
    title: 'GitHub rate limit reached',
    message: 'GitHub is temporarily refusing additional unauthenticated API requests.',
  },
  malformed_github_response: {
    title: 'Invalid GitHub response',
    message: 'GitHub returned data that could not be safely imported.',
  },
  github_api_unavailable: {
    title: 'GitHub unavailable',
    message: 'The GitHub API could not be reached.',
  },
  github_api_failure: {
    title: 'GitHub request failed',
    message: 'GitHub rejected the repository data request.',
  },
  git_unavailable: {
    title: 'Git unavailable',
    message: 'The backend cannot run Git repository imports.',
  },
  empty_repository: {
    title: 'Empty repository',
    message: 'The repository does not contain a commit that can be investigated.',
  },
  git_output_invalid: {
    title: 'Invalid Git history',
    message: 'The imported Git history could not be normalized.',
  },
  repository_import_failed: {
    title: 'Repository import failed',
    message: 'The backend could not complete the repository import.',
  },
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

export function validatePublicGithubRepositoryUrl(value: string): string | null {
  const candidate = value.trim()
  if (!candidate) return 'Enter a public GitHub repository URL.'

  let url: URL
  try {
    url = new URL(candidate)
  } catch {
    return 'Enter a valid repository URL.'
  }
  if (url.protocol !== 'https:') return 'Use an HTTPS repository URL.'
  if (url.hostname.toLowerCase() !== 'github.com') {
    return 'Only github.com repository URLs are supported.'
  }
  return null
}

export function repositoryImportSummary(result: RepositoryImportResult): RepositoryImportSummary {
  return {
    git: [
      { label: 'Parsed', value: result.gitIngestion.recordsParsed },
      { label: 'Inserted', value: result.gitIngestion.recordsInserted },
      { label: 'Updated', value: result.gitIngestion.recordsUpdated },
      { label: 'Deleted', value: result.gitIngestion.recordsDeleted },
      { label: 'Skipped', value: result.gitIngestion.recordsSkippedAsDuplicates },
      { label: 'Rejected', value: result.gitIngestion.recordsRejected },
    ],
    pullRequests: [
      { label: 'Received', value: result.pullRequestIngestion.recordsReceived },
      { label: 'Inserted', value: result.pullRequestIngestion.recordsInserted },
      { label: 'Updated', value: result.pullRequestIngestion.recordsUpdated },
      {
        label: 'Duplicates',
        value: result.pullRequestIngestion.recordsSkippedAsDuplicates,
      },
      { label: 'Rejected', value: result.pullRequestIngestion.recordsRejected },
      {
        label: 'References resolved',
        value: result.pullRequestIngestion.explicitCommitReferencesResolved,
      },
      {
        label: 'References unresolved',
        value: result.pullRequestIngestion.explicitCommitReferencesUnresolved,
      },
    ],
    limits: [
      { label: 'Commits', value: result.limits.maxCommits },
      { label: 'Pull requests', value: result.limits.maxPullRequests },
      { label: 'Commits per PR', value: result.limits.maxCommitsPerPullRequest },
      { label: 'Repository bytes', value: result.limits.maxRepositoryBytes },
    ],
  }
}

export function createRepositoryImportRunner(
  onLoadingChange: (loading: boolean) => void,
): RepositoryImportRunner {
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
      } catch (error) {
        if (requestGeneration !== generation) return { started: true }
        return { started: true, error }
      } finally {
        if (requestGeneration === generation) {
          active = false
          onLoadingChange(false)
        }
      }
    },
  }
}

export function presentRepositoryImportError(
  error: unknown,
): RepositoryImportErrorPresentation {
  if (
    error instanceof Error &&
    error.name === 'ApiResponseError' &&
    'status' in error &&
    typeof error.status === 'number'
  ) {
    const code = 'code' in error && typeof error.code === 'string' ? error.code : null
    const presentation = code ? KNOWN_IMPORT_ERRORS[code] : undefined
    return {
      ...(presentation ?? {
        title: 'Repository import failed',
        message: 'The backend could not complete the repository import.',
      }),
      ...(code ? { code } : {}),
    }
  }
  if (error instanceof Error && error.message.startsWith('Backend returned')) {
    return {
      title: 'Invalid backend response',
      message: 'The repository import response did not match the expected contract.',
    }
  }
  return {
    title: 'Network failure',
    message: 'The backend could not be reached. Check that it is running and try again.',
  }
}
