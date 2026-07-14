import {
  Database,
  GitCommitVertical,
  GitPullRequest,
  FileCode2,
  MessagesSquare,
  Ticket,
  type LucideIcon,
} from 'lucide-react'
import sampleInvestigation from '@/sample-data/investigation-001.json'
import type {
  Artifact,
  ArtifactSourceType,
  EvidenceGraph,
  FollowUpQuestion,
  Investigation,
} from './domain'

export type SourceTone = 'amber' | 'cyan' | 'green' | 'violet' | 'neutral'

export interface SourcePresentation {
  label: string
  icon: LucideIcon
  tone: SourceTone
}

export interface RepositoryOption {
  id: string
  name: string
}

export interface IntegrationStatus {
  id: string
  name: string
  provider: 'github' | 'jira' | 'slack'
  status: string
}

export interface ExampleQuery {
  id: string
  question: string
}

interface SourceTypeSample {
  label: string
  tone: SourceTone
}

interface InvestigationSampleData {
  sourceTypes: Record<string, SourceTypeSample>
  repositories: RepositoryOption[]
  integrations: IntegrationStatus[]
  exampleQueries: ExampleQuery[]
  investigation: Investigation
  artifacts: Artifact[]
  evidenceGraph: EvidenceGraph
  followUpQuestions: FollowUpQuestion[]
}

const data = sampleInvestigation as InvestigationSampleData

const sourceIcons: Record<ArtifactSourceType, LucideIcon> = {
  slack_message: MessagesSquare,
  jira_ticket: Ticket,
  github_pull_request: GitPullRequest,
  git_commit: GitCommitVertical,
  modified_file: FileCode2,
  deployment: Database,
  service: Database,
  metric: Database,
  document: Database,
}

const shortMonths = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

const longMonths = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

function readUtcDate(iso: string) {
  const date = new Date(iso)
  return {
    day: date.getUTCDate(),
    month: date.getUTCMonth(),
    year: date.getUTCFullYear(),
    hour: String(date.getUTCHours()).padStart(2, '0'),
    minute: String(date.getUTCMinutes()).padStart(2, '0'),
  }
}

export function formatArtifactDate(iso: string) {
  const date = readUtcDate(iso)
  return `${longMonths[date.month]} ${date.day}, ${date.year}`
}

export function formatGraphTimestamp(iso: string) {
  const date = readUtcDate(iso)
  return `${shortMonths[date.month]} ${date.day}, ${date.year} · ${date.hour}:${date.minute}`
}

export function getSourceMeta() {
  return Object.fromEntries(
    Object.entries(data.sourceTypes).map(([sourceType, meta]) => [
      sourceType,
      {
        ...meta,
        icon: sourceIcons[sourceType as ArtifactSourceType] ?? Database,
      },
    ]),
  ) as Record<ArtifactSourceType, SourcePresentation>
}

export function getInvestigationDashboardData() {
  return {
    repositories: data.repositories,
    activeRepository: data.repositories.find(
      (repository) => repository.id === data.investigation.repositoryId,
    ),
    integrations: data.integrations,
    exampleQueries: data.exampleQueries,
    investigation: data.investigation,
    artifacts: data.artifacts,
    evidenceGraph: data.evidenceGraph,
    followUpQuestions: data.followUpQuestions,
    sourceMeta: getSourceMeta(),
  }
}
