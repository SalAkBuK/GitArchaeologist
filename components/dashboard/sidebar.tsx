'use client'

import {
  ChevronDown,
  GitBranch,
  MessagesSquare,
  ScanSearch,
  Search,
  Sparkles,
  Ticket,
} from 'lucide-react'
import type {
  ExampleQuery,
  IntegrationStatus,
  RepositoryOption,
} from '@/lib/investigation-adapter'
import type { FollowUpQuestion } from '@/lib/domain'

const sourceIcons = {
  github: GitBranch,
  jira: Ticket,
  slack: MessagesSquare,
} as const

export function Sidebar({
  activeRepository,
  dataSources,
  exampleQueries,
  followUps,
}: {
  activeRepository?: RepositoryOption
  dataSources: IntegrationStatus[]
  exampleQueries: ExampleQuery[]
  followUps: FollowUpQuestion[]
}) {
  return (
    <aside className="flex h-full w-full flex-col gap-6 overflow-y-auto p-4">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-1">
        <div className="flex size-9 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/30">
          <ScanSearch className="size-5 text-primary" aria-hidden="true" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold tracking-tight">GitArchaeologist</p>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Code Time Machine
          </p>
        </div>
      </div>

      {/* Repository selector */}
      <div>
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Repository
        </label>
        <button className="flex w-full items-center justify-between rounded-lg border border-border bg-card px-3 py-2.5 text-left text-sm transition-colors hover:border-primary/40">
          <span className="flex items-center gap-2">
            <GitBranch className="size-4 text-muted-foreground" aria-hidden="true" />
            {activeRepository?.name}
          </span>
          <ChevronDown className="size-4 text-muted-foreground" aria-hidden="true" />
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          placeholder="Search evidence..."
          aria-label="Search evidence"
          className="w-full rounded-lg border border-border bg-card py-2.5 pl-9 pr-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
        />
      </div>

      {/* Example queries */}
      <div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Example Investigations
        </p>
        <ul className="flex flex-col gap-1.5">
          {exampleQueries.map((q) => (
            <li key={q.id}>
              <button className="group flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-foreground/80 transition-colors hover:bg-secondary hover:text-foreground">
                <Sparkles
                  className="mt-0.5 size-3.5 shrink-0 text-primary/70 transition-colors group-hover:text-primary"
                  aria-hidden="true"
                />
                <span className="text-pretty leading-snug">{q.question}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Data sources */}
      <div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Data Sources
        </p>
        <ul className="flex flex-col gap-1.5">
          {dataSources.map((s) => {
            const Icon = sourceIcons[s.provider]
            return (
              <li
                key={s.id}
                className="flex items-center justify-between rounded-lg border border-border bg-card/60 px-3 py-2"
              >
                <span className="flex items-center gap-2 text-sm">
                  <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
                  {s.name}
                </span>
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400/60" />
                    <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
                  </span>
                  {s.status}
                </span>
              </li>
            )
          })}
        </ul>
      </div>

      {/* Suggested follow-ups */}
      <div className="mt-auto">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Suggested Follow-ups
        </p>
        <ul className="flex flex-col gap-1.5">
          {followUps.map((q) => (
            <li key={q.id}>
              <button className="w-full rounded-lg border border-dashed border-border px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
                {q.question}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
