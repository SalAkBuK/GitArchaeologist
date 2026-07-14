# GitArchaeologist AI Architecture Plan

## Current State

This project now has one live vertical slice backed by FastAPI: Git-log upload, persisted commit and modified-file artifacts, a commit investigation endpoint, and a Next.js dashboard that loads real backend data. The preserved design fixture lives in `sample-data/investigation-001.json`.

The immediate goal is still narrow: keep the live commit investigation honest while adding missing deterministic evidence sources one at a time.

## Hardcoded Data Structures Currently Rendered

### `sample-data/investigation-001.json`

| Structure | Current role | Should become |
| --- | --- | --- |
| `SourceType` | Union of source identifiers: `slack`, `jira`, `pr`, `commit`, `redis`. | Shared domain enum for artifact source types. Rename `redis` to a more general service or runtime source type unless Redis is truly a first-class integration. |
| `sourceMeta` | UI metadata for source labels, icons, and color tones. | Frontend presentation metadata keyed by backend source type. Keep client-side unless labels must be tenant-configurable. |
| `summary` | Active investigation headline, query, repository, root cause, confidence, evidence count. | `Investigation` response summary. |
| `correlationBadges` | Rendered badges under the reasoning chain. | Derived correlation signals returned with the investigation or evidence graph. |
| `reasoningChain` | Ordered list of AI reasoning steps. | Ordered reasoning steps tied to artifact IDs and edge IDs. |
| `graphNodes` | Evidence graph nodes. Duplicates artifact-like fields but lacks artifact IDs and edge linkage. | `EvidenceGraph.nodes`, ideally derived from `Artifact` records. |
| `artifacts` | Excavation trail cards with title, source, timestamp, author, confidence, body, detail. | `Artifact[]` from API. |
| `hypotheses` | Primary and secondary explanations with confidence values. | `Investigation.hypotheses`. |
| `analytics` | Footer metrics: commits indexed, conversations analyzed, tickets linked, graph confidence, time to insight. | Repository or investigation analytics endpoint. |
| `exampleQueries` | Sidebar investigation prompt examples. | Static config at first, later API-backed suggested prompts per repository. |
| `followUps` | Suggested follow-up strings. | `FollowUpQuestion[]` returned from the investigation engine. |
| `dataSources` | Connected integrations list. | Integration status endpoint. |

### Component-local hardcoding

| Component | Hardcoded values | Required change |
| --- | --- | --- |
| `components/dashboard/evidence-graph.tsx` | `positions` map, `order` array, graph edge construction by sequential order, fixed canvas height. | Replace with `EvidenceGraph.edges` and optional server/client layout data. The current graph is not a real graph because relationships are inferred from array order. |
| `components/dashboard/sidebar.tsx` | Brand text, repository selector value `acme-platform`, source icon map keyed by display names, search placeholder, section labels. | Repository selector and data sources should be dynamic. Brand and labels can stay static. |
| `components/dashboard/top-bar.tsx` | Active investigation label, `#128`, command hint, notification indicator, user initials `SJ`. | Investigation ID, notification state, and signed-in user should come from app/session state. |
| `components/dashboard/footer-analytics.tsx` | Metric icons are matched to `analytics` by array index. | Metrics should have stable IDs or types so icons are not position-dependent. |
| `app/page.tsx` | Always renders one active investigation with no route, no query state, and no loading/error states. | Add route-driven investigation loading and app shell state. |

## Components That Should Become Dynamic

1. `Page`
   - Load repositories, selected repository, active investigation, integration status, analytics, and user/session state.
   - Move from a single static dashboard to route-backed pages such as `/investigations/[id]`.

2. `Sidebar`
   - Repository selector should load real repositories.
   - Evidence search should query indexed artifacts.
   - Example investigations should come from config or a prompt suggestion endpoint.
   - Data sources should show actual integration connection, sync, error, and indexing status.
   - Follow-ups should render typed follow-up question objects, not raw strings.

3. `TopBar`
   - Active investigation ID should come from the loaded investigation.
   - User initials should come from auth/session.
   - Notification indicator should reflect real events such as completed indexing, failed sync, or finished investigation.

4. `InvestigationPanel`
   - Summary, root cause, metrics, reasoning chain, correlation signals, and graph should be loaded from an `Investigation`.
   - Add empty, loading, failed, running, and stale-result states.

5. `EvidenceGraph`
   - Nodes should come from artifacts or graph nodes.
   - Edges must come from `EvidenceEdge[]`.
   - Layout should be deterministic. Either store layout coordinates from the backend graph engine or compute them client-side from graph topology.

6. `ExcavationTrail`
   - Artifact cards should render API artifacts with source links and stable IDs.
   - Expand state can remain local, but source opening must use real `sourceUrl`.
   - Alternative explanations should come from investigation hypotheses.

7. `FooterAnalytics`
   - Metrics should be typed and keyed, not positional.
   - Some metrics are repository-level while others are investigation-level. Do not mix them without labels and scopes.

## Backend APIs Required

The first backend should be API-first and boring: predictable JSON endpoints, background jobs for indexing, and a separate investigation execution pipeline. Do not hide long-running work behind a single synchronous request.

### Repository and integration APIs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/repositories` | List repositories available to the signed-in user. |
| `GET` | `/api/repositories/:repositoryId` | Fetch repository metadata and indexing state. |
| `POST` | `/api/repositories/:repositoryId/index` | Start or resume indexing for commits, PRs, tickets, conversations, and runtime artifacts. |
| `GET` | `/api/repositories/:repositoryId/analytics` | Return footer-style repository metrics. |
| `GET` | `/api/integrations` | List configured integrations and connection status. |
| `POST` | `/api/integrations/:provider/connect` | Start OAuth or credential connection flow. |
| `POST` | `/api/integrations/:provider/sync` | Trigger a manual sync. |

### Investigation APIs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/investigations` | Create an investigation from `{ repositoryId, query }`. Returns an investigation ID immediately. |
| `GET` | `/api/investigations` | List recent investigations for a repository or user. |
| `GET` | `/api/investigations/:id` | Fetch full investigation summary, hypotheses, reasoning chain, graph, artifacts, and follow-ups. |
| `GET` | `/api/investigations/:id/status` | Poll execution state: queued, running, completed, failed. |
| `GET` | `/api/investigations/:id/events` | Server-sent events stream for progress updates. |
| `POST` | `/api/investigations/:id/follow-ups` | Ask a follow-up question scoped to an existing investigation. |

### Artifact and evidence APIs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/investigations/:id/artifacts` | Paginated artifacts for the excavation trail. |
| `GET` | `/api/artifacts/:artifactId` | Fetch one artifact with full body, metadata, and source link. |
| `GET` | `/api/investigations/:id/graph` | Fetch evidence graph nodes, edges, and optional layout. |
| `GET` | `/api/repositories/:repositoryId/search` | Search indexed evidence across commits, PRs, tickets, and conversations. |

### Question suggestion APIs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/repositories/:repositoryId/example-queries` | Suggested starting investigations for a repository. |
| `GET` | `/api/investigations/:id/follow-ups` | Suggested follow-up questions for the current result. |

## TypeScript Domain Interfaces

These interfaces should live in a shared package or in `frontend/src/types/domain.ts` until the backend package exists. The names below are intentionally domain-oriented rather than UI-oriented.

### Artifact

```ts
export type ArtifactSourceType =
  | 'slack_message'
  | 'jira_ticket'
  | 'github_pull_request'
  | 'git_commit'
  | 'deployment'
  | 'service'
  | 'metric'
  | 'document';

export type ConfidenceLevel = 'low' | 'medium' | 'high';

export interface ActorRef {
  id?: string;
  displayName: string;
  email?: string;
  provider?: string;
}

export interface Artifact {
  id: string;
  investigationId?: string;
  repositoryId: string;
  sourceType: ArtifactSourceType;
  externalId?: string;
  sourceUrl?: string;
  title: string;
  summary: string;
  body?: string;
  detail?: string;
  author?: ActorRef;
  occurredAt: string;
  ingestedAt: string;
  confidence: number;
  confidenceLevel?: ConfidenceLevel;
  tags: string[];
  metadata: Record<string, unknown>;
}
```

### Edge

```ts
export type EvidenceRelationType =
  | 'references'
  | 'precedes'
  | 'causes'
  | 'implements'
  | 'deploys'
  | 'discusses'
  | 'mentions'
  | 'correlates_with'
  | 'contradicts';

export interface EvidenceEdge {
  id: string;
  investigationId: string;
  fromArtifactId: string;
  toArtifactId: string;
  relationType: EvidenceRelationType;
  label: string;
  explanation: string;
  confidence: number;
  signalTypes: string[];
  createdAt: string;
}
```

### Investigation

```ts
export type InvestigationStatus =
  | 'queued'
  | 'indexing'
  | 'analyzing'
  | 'completed'
  | 'failed';

export interface ReasoningStep {
  id: string;
  order: number;
  text: string;
  artifactIds: string[];
  edgeIds: string[];
}

export interface InvestigationHypothesis {
  id: string;
  label: string;
  text: string;
  confidence: number;
  primary: boolean;
  supportingArtifactIds: string[];
  contradictingArtifactIds: string[];
}

export interface InvestigationMetric {
  id: string;
  label: string;
  value: string | number;
  scope: 'repository' | 'investigation';
}

export interface Investigation {
  id: string;
  displayId: string;
  repositoryId: string;
  repositoryName: string;
  query: string;
  status: InvestigationStatus;
  rootCauseSummary?: string;
  confidenceScore: number;
  confidenceLevel: ConfidenceLevel;
  intentAlignmentScore?: number;
  evidenceNodeCount: number;
  correlationSignals: string[];
  reasoningChain: ReasoningStep[];
  hypotheses: InvestigationHypothesis[];
  metrics: InvestigationMetric[];
  createdBy: ActorRef;
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
  errorMessage?: string;
}
```

### Evidence Graph

```ts
export interface EvidenceGraphNode {
  id: string;
  artifactId: string;
  sourceType: ArtifactSourceType;
  title: string;
  subtitle?: string;
  author?: ActorRef;
  occurredAt: string;
  confidence: number;
  x?: number;
  y?: number;
}

export interface EvidenceGraph {
  investigationId: string;
  nodes: EvidenceGraphNode[];
  edges: EvidenceEdge[];
  layout?: {
    algorithm: 'manual' | 'dagre' | 'force' | 'timeline';
    width: number;
    height: number;
    generatedAt: string;
  };
  generatedAt: string;
}
```

### Follow-up Questions

```ts
export type FollowUpQuestionStatus =
  | 'suggested'
  | 'asked'
  | 'answered'
  | 'dismissed';

export interface FollowUpQuestion {
  id: string;
  investigationId: string;
  question: string;
  rationale?: string;
  priority: number;
  status: FollowUpQuestionStatus;
  generatedFromArtifactIds: string[];
  generatedFromEdgeIds: string[];
  answerInvestigationId?: string;
  createdAt: string;
}
```

## Historical Implementation Plan

The phased plan below predates the live commit-investigation slice and is retained only as design history. It is not current setup or execution guidance; use the root and backend READMEs for the implemented system.

### Phase 1 - Frontend normalization (completed)

The Next.js app remains at the repository root. Shared types live in `lib/domain.ts`, the preserved design fixture lives in `sample-data/investigation-001.json`, and fixture loading remains isolated in `lib/investigation-adapter.ts`. The active page now uses the FastAPI commit-investigation API instead of that fixture.

### Phase 2 - Normalize the mock data

1. Convert `summary`, `reasoningChain`, `hypotheses`, `analytics`, and `followUps` into one `Investigation` object.
2. Convert `artifacts` into `Artifact[]`.
3. Replace `graphNodes`, `positions`, and `order` with an `EvidenceGraph`.
4. Add explicit `EvidenceEdge[]` records instead of inferring graph relationships from array order.
5. Add `sourceUrl`, `externalId`, ISO timestamps, and repository IDs to all artifacts.

This is the most important frontend step. If the sample data is normalized correctly, the backend API can copy that contract later.

### Phase 3 - Route the frontend around investigations

1. Add `/investigations/[id]`.
2. Add a new investigation form that posts `{ repositoryId, query }`.
3. Add loading, failed, queued, analyzing, and completed states.
4. Make the repository selector update URL or app state.
5. Wire search input to a local sample-data search first, then to backend search later.

### Phase 4 - Backend contract and storage design

1. Define API schemas from the TypeScript interfaces.
2. Choose storage for investigations, artifacts, edges, repositories, integrations, and job state.
3. Add background jobs for ingestion and investigation execution.
4. Store raw source payloads separately from normalized artifacts.
5. Store model output with traceability: every summary claim should point back to artifact IDs and edge IDs.

This sequencing constraint has been satisfied for the current narrow contract: the implemented backend persists only Git commits and modified-file artifacts and returns explicit deterministic edges.

### Phase 5 - Real ingestion

1. Start with GitHub commits and pull requests because they are deterministic and easy to link.
2. Add Jira tickets next because ticket references often appear in PRs and commits.
3. Add Slack after the artifact and permission model is solid. Slack is noisier and creates more privacy and tenancy risk.
4. Add deployment/runtime artifacts only after the graph model supports non-human source nodes.

### Phase 6 - Investigation engine

1. Retrieve candidate artifacts from indexed evidence.
2. Rank artifacts by semantic similarity, temporal proximity, shared actors, explicit references, and repository component overlap.
3. Generate evidence edges with explanations and confidence scores.
4. Generate hypotheses and reasoning steps only from selected artifacts and edges.
5. Generate follow-up questions from low-confidence edges, missing links, contradictions, and unresolved ownership.

### Phase 7 - Production hardening

1. Add authentication and repository-level authorization before connecting real integrations.
2. Add pagination for artifacts and investigation history.
3. Add audit logs for source access and investigation runs.
4. Add rate limits and job cancellation for expensive investigations.
5. Add tests at the contract boundary: API schema tests, graph normalization tests, and UI rendering tests with sample data.

## Non-negotiable Architecture Decisions

1. Evidence edges must be first-class records. A graph without explicit edges is just a timeline drawing.
2. UI source metadata should not be mixed with backend evidence data.
3. AI summaries must cite artifact IDs and edge IDs. Free-floating explanations are not trustworthy enough for this product.
4. Follow-up questions should be typed objects, not strings, because they need provenance, status, and optional answer links.
5. Backend work should wait until the frontend consumes normalized sample data. That is the cheapest way to expose bad contracts early.
