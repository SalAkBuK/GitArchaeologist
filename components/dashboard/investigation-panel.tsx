import { Layers, ShieldCheck, Target, Waypoints } from 'lucide-react'
import type { EvidenceGraph as EvidenceGraphData, Investigation } from '@/lib/domain'
import type { SourcePresentation } from '@/lib/investigation-adapter'
import { EvidenceGraph } from './evidence-graph'

function MetricPill({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: typeof Layers
  label: string
  value: string
  accent?: boolean
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-background/40 px-3.5 py-3">
      <div
        className={`flex size-9 items-center justify-center rounded-lg ${
          accent ? 'bg-primary/15 text-primary' : 'bg-secondary text-foreground/70'
        }`}
      >
        <Icon className="size-4.5" aria-hidden="true" />
      </div>
      <div className="leading-tight">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {label}
        </p>
        <p className="text-sm font-semibold">{value}</p>
      </div>
    </div>
  )
}

export function InvestigationPanel({
  evidenceGraph,
  investigation,
  sourceMeta,
}: {
  evidenceGraph: EvidenceGraphData
  investigation: Investigation
  sourceMeta: Record<string, SourcePresentation>
}) {
  const confidenceLabel =
    investigation.confidenceLevel.charAt(0).toUpperCase() +
    investigation.confidenceLevel.slice(1)

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-primary/15 px-2 py-0.5 font-mono text-xs font-medium text-primary">
            Investigation {investigation.displayId}
          </span>
          <span className="font-mono text-xs text-muted-foreground">
            repo: {investigation.repositoryName}
          </span>
        </div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-balance md:text-3xl">
          Query: &ldquo;{investigation.query}&rdquo;
        </h1>
      </div>

      {/* Executive summary card */}
      <section className="glass relative overflow-hidden rounded-2xl border border-border p-5 shadow-2xl shadow-black/20">
        <div className="pointer-events-none absolute -right-24 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="flex items-center gap-2">
          <Target className="size-4 text-primary" aria-hidden="true" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Root Cause Summary
          </h2>
        </div>
        <p className="mt-3 max-w-2xl text-pretty text-lg leading-relaxed">
          {investigation.rootCauseSummary}
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricPill
            icon={Target}
            label="Intent Alignment"
            value={`${investigation.intentAlignmentScore}/100`}
            accent
          />
          <MetricPill icon={ShieldCheck} label="Confidence" value={confidenceLabel} />
          <MetricPill
            icon={Layers}
            label="Evidence Nodes"
            value={String(investigation.evidenceNodeCount)}
          />
          <MetricPill icon={Waypoints} label="Repository" value={investigation.repositoryName} />
        </div>
      </section>

      {/* Reasoning chain */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <Waypoints className="size-4 text-accent" aria-hidden="true" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            AI Reasoning Chain
          </h2>
        </div>

        <ol className="mt-4 flex flex-col gap-0">
          {investigation.reasoningChain.map((step, i) => (
            <li key={step.id} className="relative flex gap-4 pb-5 last:pb-0">
              {i < investigation.reasoningChain.length - 1 && (
                <span
                  className="absolute left-[15px] top-8 h-full w-px bg-gradient-to-b from-primary/40 to-border"
                  aria-hidden="true"
                />
              )}
              <span className="z-10 flex size-8 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 font-mono text-xs font-semibold text-primary">
                {i + 1}
              </span>
              <p className="pt-1 text-pretty text-sm leading-relaxed text-foreground/90">
                {step.text}
              </p>
            </li>
          ))}
        </ol>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
          {investigation.correlationSignals.map((b) => (
            <span
              key={b}
              className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 font-mono text-[11px] text-accent"
            >
              {b}
            </span>
          ))}
        </div>
      </section>

      {/* Evidence graph */}
      <EvidenceGraph evidenceGraph={evidenceGraph} sourceMeta={sourceMeta} />
    </div>
  )
}
