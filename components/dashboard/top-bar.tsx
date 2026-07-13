'use client'

import { Bell, Command, PanelLeftClose, Radar } from 'lucide-react'
import type { Investigation } from '@/lib/domain'

export function TopBar({
  investigation,
  onToggleSidebar,
}: {
  investigation: Investigation
  onToggleSidebar: () => void
}) {
  const initials = investigation.createdBy.displayName
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-background/70 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="flex size-8 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-foreground lg:hidden"
          aria-label="Toggle investigation panel"
        >
          <PanelLeftClose className="size-4" aria-hidden="true" />
        </button>
        <div className="flex items-center gap-2">
          <Radar className="size-4 text-primary" aria-hidden="true" />
          <span className="hidden font-mono text-xs uppercase tracking-widest text-muted-foreground sm:inline">
            Active Investigation
          </span>
        </div>
        <span className="rounded-md border border-border bg-card px-2 py-0.5 font-mono text-xs text-foreground/80">
          {investigation.displayId}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground md:flex">
          <Command className="size-3.5" aria-hidden="true" />
          <span className="font-mono">K to run a new excavation</span>
        </div>
        <button
          className="relative flex size-9 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-foreground"
          aria-label="Notifications"
        >
          <Bell className="size-4" aria-hidden="true" />
          <span className="absolute right-2 top-2 size-1.5 rounded-full bg-primary" />
        </button>
        <div
          className="flex size-9 items-center justify-center rounded-lg bg-primary/20 font-mono text-xs font-semibold text-primary ring-1 ring-primary/30"
          aria-label={`Signed in as ${initials}`}
        >
          {initials}
        </div>
      </div>
    </header>
  )
}
