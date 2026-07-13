'use client'

import { useState } from 'react'
import { Network } from 'lucide-react'
import type { EvidenceGraph as EvidenceGraphData } from '@/lib/domain'
import {
  formatGraphTimestamp,
  type SourcePresentation,
} from '@/lib/investigation-adapter'

const toneClasses: Record<
  string,
  { ring: string; text: string; bg: string; dot: string }
> = {
  amber: {
    ring: 'ring-primary/50',
    text: 'text-primary',
    bg: 'bg-primary/15',
    dot: 'bg-primary',
  },
  cyan: {
    ring: 'ring-accent/50',
    text: 'text-accent',
    bg: 'bg-accent/15',
    dot: 'bg-accent',
  },
  green: {
    ring: 'ring-emerald-400/50',
    text: 'text-emerald-400',
    bg: 'bg-emerald-400/15',
    dot: 'bg-emerald-400',
  },
  violet: {
    ring: 'ring-violet-400/50',
    text: 'text-violet-300',
    bg: 'bg-violet-400/15',
    dot: 'bg-violet-400',
  },
  neutral: {
    ring: 'ring-border',
    text: 'text-foreground/70',
    bg: 'bg-secondary',
    dot: 'bg-muted-foreground',
  },
}

function curve(a: { x: number; y: number }, b: { x: number; y: number }) {
  const midY = (a.y + b.y) / 2
  return `M ${a.x} ${a.y} C ${a.x} ${midY}, ${b.x} ${midY}, ${b.x} ${b.y}`
}

export function EvidenceGraph({
  evidenceGraph,
  sourceMeta,
}: {
  evidenceGraph: EvidenceGraphData
  sourceMeta: Record<string, SourcePresentation>
}) {
  const [active, setActive] = useState<string | null>(null)
  const nodesByArtifactId = new Map(
    evidenceGraph.nodes.map((node) => [node.artifactId, node]),
  )

  return (
    <section className="rounded-2xl border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Network className="size-4 text-primary" aria-hidden="true" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            Evidence Graph
          </h2>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          Causal reconstruction · {evidenceGraph.nodes.length} nodes
        </span>
      </div>

      <div className="relative mt-4 h-[560px] w-full overflow-hidden rounded-xl border border-border bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,0.04),transparent_60%)]">
        {/* subtle grid */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              'linear-gradient(to right, rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.04) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
          aria-hidden="true"
        />

        {/* connectors */}
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 400 560"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {evidenceGraph.edges.map((edge) => {
            const from = nodesByArtifactId.get(edge.fromArtifactId)
            const to = nodesByArtifactId.get(edge.toArtifactId)

            if (
              !from ||
              !to ||
              from.x === undefined ||
              from.y === undefined ||
              to.x === undefined ||
              to.y === undefined
            ) {
              return null
            }

            const isLit = active === from.id || active === to.id || active === null
            const path = curve({ x: from.x, y: from.y }, { x: to.x, y: to.y })

            return (
              <g key={edge.id}>
                <path
                  d={path}
                  fill="none"
                  stroke="var(--cyan)"
                  strokeWidth={isLit ? 1.6 : 0.8}
                  strokeOpacity={isLit ? 0.5 : 0.18}
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={path}
                  fill="none"
                  stroke="var(--cyan)"
                  strokeWidth={1.4}
                  className="animate-dash"
                  strokeOpacity={isLit ? 0.9 : 0.25}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          })}
        </svg>

        {/* nodes */}
        {evidenceGraph.nodes.map((node) => {
          const meta = sourceMeta[node.sourceType]
          const tone = toneClasses[meta.tone]
          const Icon = meta.icon
          const dim = active !== null && active !== node.id
          return (
            <div
              key={node.id}
              className="absolute w-[46%] max-w-[190px] -translate-x-1/2 -translate-y-1/2 transition-opacity"
              style={{
                left: `${((node.x ?? 0) / 400) * 100}%`,
                top: node.y ?? 0,
                opacity: dim ? 0.55 : 1,
              }}
              onMouseEnter={() => setActive(node.id)}
              onMouseLeave={() => setActive(null)}
            >
              <button
                className={`group w-full rounded-xl border border-border bg-card/90 p-3 text-left ring-1 backdrop-blur transition-all ${tone.ring} ${
                  active === node.id ? 'scale-[1.03] shadow-lg shadow-black/40' : ''
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`relative flex size-8 items-center justify-center rounded-lg ${tone.bg} ${tone.text}`}
                  >
                    <Icon className="size-4" aria-hidden="true" />
                    <span
                      className={`absolute -right-0.5 -top-0.5 size-2 rounded-full ${tone.dot} animate-pulse-node`}
                    />
                  </span>
                  <div className="min-w-0 leading-tight">
                    <p className="truncate text-sm font-semibold">{node.title}</p>
                    <p className="truncate font-mono text-[10px] text-muted-foreground">
                      {meta.label}
                    </p>
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-muted-foreground">
                  <span className="truncate">{node.author?.displayName}</span>
                  <span className={tone.text}>{node.confidence}%</span>
                </div>
                <p className="mt-1 font-mono text-[9px] text-muted-foreground/70">
                  {formatGraphTimestamp(node.occurredAt)}
                </p>
              </button>
            </div>
          )
        })}
      </div>
    </section>
  )
}
