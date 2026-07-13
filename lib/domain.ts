export type ArtifactSourceType =
  | 'slack_message'
  | 'jira_ticket'
  | 'github_pull_request'
  | 'git_commit'
  | 'deployment'
  | 'service'
  | 'metric'
  | 'document'

export type ConfidenceLevel = 'low' | 'medium' | 'high'

export interface ActorRef {
  id?: string
  displayName: string
  email?: string
  provider?: string
}

export interface Artifact {
  id: string
  investigationId?: string
  repositoryId: string
  sourceType: ArtifactSourceType
  externalId?: string
  sourceUrl?: string
  title: string
  summary: string
  body?: string
  detail?: string
  author?: ActorRef
  occurredAt: string
  ingestedAt: string
  confidence: number
  confidenceLevel?: ConfidenceLevel
  tags: string[]
  metadata: Record<string, unknown>
}

export type EvidenceRelationType =
  | 'references'
  | 'precedes'
  | 'causes'
  | 'implements'
  | 'deploys'
  | 'discusses'
  | 'mentions'
  | 'correlates_with'
  | 'contradicts'

export interface EvidenceEdge {
  id: string
  investigationId: string
  fromArtifactId: string
  toArtifactId: string
  relationType: EvidenceRelationType
  label: string
  explanation: string
  confidence: number
  signalTypes: string[]
  createdAt: string
}

export type InvestigationStatus =
  | 'queued'
  | 'indexing'
  | 'analyzing'
  | 'completed'
  | 'failed'

export interface ReasoningStep {
  id: string
  order: number
  text: string
  artifactIds: string[]
  edgeIds: string[]
}

export interface InvestigationHypothesis {
  id: string
  label: string
  text: string
  confidence: number
  primary: boolean
  supportingArtifactIds: string[]
  contradictingArtifactIds: string[]
}

export interface InvestigationMetric {
  id: string
  label: string
  value: string | number
  scope: 'repository' | 'investigation'
}

export interface Investigation {
  id: string
  displayId: string
  repositoryId: string
  repositoryName: string
  query: string
  status: InvestigationStatus
  rootCauseSummary?: string
  confidenceScore: number
  confidenceLevel: ConfidenceLevel
  intentAlignmentScore?: number
  evidenceNodeCount: number
  correlationSignals: string[]
  reasoningChain: ReasoningStep[]
  hypotheses: InvestigationHypothesis[]
  metrics: InvestigationMetric[]
  createdBy: ActorRef
  createdAt: string
  updatedAt: string
  completedAt?: string
  errorMessage?: string
}

export interface EvidenceGraphNode {
  id: string
  artifactId: string
  sourceType: ArtifactSourceType
  title: string
  subtitle?: string
  author?: ActorRef
  occurredAt: string
  confidence: number
  x?: number
  y?: number
}

export interface EvidenceGraph {
  investigationId: string
  nodes: EvidenceGraphNode[]
  edges: EvidenceEdge[]
  layout?: {
    algorithm: 'manual' | 'dagre' | 'force' | 'timeline'
    width: number
    height: number
    generatedAt: string
  }
  generatedAt: string
}

export type FollowUpQuestionStatus =
  | 'suggested'
  | 'asked'
  | 'answered'
  | 'dismissed'

export interface FollowUpQuestion {
  id: string
  investigationId: string
  question: string
  rationale?: string
  priority: number
  status: FollowUpQuestionStatus
  generatedFromArtifactIds: string[]
  generatedFromEdgeIds: string[]
  answerInvestigationId?: string
  createdAt: string
}
