import { Boxes, CircleCheckBig, MessagesSquare, Ticket, Timer } from 'lucide-react'
import type { InvestigationMetric } from '@/lib/domain'

const icons = {
  commits_indexed: Boxes,
  conversations_analyzed: MessagesSquare,
  tickets_linked: Ticket,
  graph_confidence: CircleCheckBig,
  time_to_insight: Timer,
} as const

export function FooterAnalytics({ metrics }: { metrics: InvestigationMetric[] }) {
  return (
    <footer className="border-t border-border bg-background/70 backdrop-blur">
      <div className="grid grid-cols-2 divide-border sm:grid-cols-3 lg:grid-cols-5 lg:divide-x">
        {metrics.map((m) => {
          const Icon = icons[m.id as keyof typeof icons] ?? Boxes
          return (
            <div key={m.label} className="flex items-center gap-3 px-4 py-3">
              <div className="flex size-9 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                <Icon className="size-4" aria-hidden="true" />
              </div>
              <div className="leading-tight">
                <p className="text-lg font-semibold tabular-nums tracking-tight">{m.value}</p>
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {m.label}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </footer>
  )
}
