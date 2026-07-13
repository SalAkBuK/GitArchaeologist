'use client'

import { useState } from 'react'
import { ChevronDown, Clock, ExternalLink, Layers, Scale } from 'lucide-react'
import type { Artifact, InvestigationHypothesis } from '@/lib/domain'
import {
  formatArtifactDate,
  type SourcePresentation,
} from '@/lib/investigation-adapter'

const toneText: Record<string, string> = {
  amber: 'text-primary',
  cyan: 'text-accent',
  green: 'text-emerald-400',
  violet: 'text-violet-300',
  neutral: 'text-foreground/70',
}
const toneBg: Record<string, string> = {
  amber: 'bg-primary/15 text-primary',
  cyan: 'bg-accent/15 text-accent',
  green: 'bg-emerald-400/15 text-emerald-400',
  violet: 'bg-violet-400/15 text-violet-300',
  neutral: 'bg-secondary text-foreground/70',
}

function ArtifactCard({
  artifact,
  sourceMeta,
}: {
  artifact: Artifact
  sourceMeta: Record<string, SourcePresentation>
}) {
  const [open, setOpen] = useState(false)
  const meta = sourceMeta[artifact.sourceType]
  const Icon = meta.icon
  return (
    <li className="relative pl-6">
      <span className="absolute left-0 top-2 flex size-3 -translate-x-1/2 items-center justify-center">
        <span className={`size-2 rounded-full ${toneText[meta.tone]} bg-current`} />
      </span>
      <div className="rounded-xl border border-border bg-card p-3.5 transition-colors hover:border-primary/30">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className={`flex size-7 items-center justify-center rounded-md ${toneBg[meta.tone]}`}>
              <Icon className="size-3.5" aria-hidden="true" />
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold">{artifact.title}</p>
              <p className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
                <Clock className="size-3" aria-hidden="true" />
                {formatArtifactDate(artifact.occurredAt)}
              </p>
            </div>
          </div>
          <span
            className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${toneBg[meta.tone]}`}
          >
            {meta.label}
          </span>
        </div>

        <p className="mt-2.5 text-pretty text-sm leading-snug text-foreground/85">
          {artifact.body ?? artifact.summary}
        </p>

        {open && artifact.detail && (
          <p className="mt-2 rounded-lg border border-border bg-background/50 p-2.5 text-xs leading-relaxed text-muted-foreground">
            {artifact.detail}
          </p>
        )}

        <div className="mt-3 flex items-center justify-between border-t border-border pt-2.5">
          <span className="font-mono text-[10px] text-muted-foreground">
            {artifact.author?.displayName} · <span className={toneText[meta.tone]}>{artifact.confidence}%</span>
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              {open ? 'Collapse' : 'Expand'}
              <ChevronDown
                className={`size-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            </button>
            <button
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label={`Open ${artifact.title} source`}
              type="button"
            >
              Source
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </li>
  )
}

export function ExcavationTrail({
  artifacts,
  hypotheses,
  sourceMeta,
}: {
  artifacts: Artifact[]
  hypotheses: InvestigationHypothesis[]
  sourceMeta: Record<string, SourcePresentation>
}) {
  return (
    <aside className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      {/* Timeline */}
      <section>
        <div className="mb-3 flex items-center gap-2">
          <Layers className="size-4 text-primary" aria-hidden="true" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Excavation Trail
          </h2>
        </div>
        <ol className="relative flex flex-col gap-3 before:absolute before:left-0 before:top-2 before:h-[calc(100%-1rem)] before:w-px before:bg-border">
          {artifacts.map((a) => (
            <ArtifactCard key={a.id} artifact={a} sourceMeta={sourceMeta} />
          ))}
        </ol>
      </section>

      {/* Alternative hypotheses */}
      <section className="rounded-2xl border border-border bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Scale className="size-4 text-accent" aria-hidden="true" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Alternative Explanations
          </h2>
        </div>
        <ul className="flex flex-col gap-3">
          {hypotheses.map((h) => (
            <li
              key={h.id}
              className={`rounded-xl border p-3 ${
                h.primary ? 'border-primary/40 bg-primary/5' : 'border-border bg-background/40'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {h.label}
                </span>
                <span
                  className={`text-sm font-semibold ${h.primary ? 'text-primary' : 'text-muted-foreground'}`}
                >
                  {h.confidence}%
                </span>
              </div>
              <p className="mt-1.5 text-sm text-foreground/90">{h.text}</p>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className={`h-full rounded-full ${h.primary ? 'bg-primary' : 'bg-muted-foreground/50'}`}
                  style={{ width: `${h.confidence}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  )
}
