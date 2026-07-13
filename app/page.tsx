'use client'

import { useState } from 'react'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TopBar } from '@/components/dashboard/top-bar'
import { InvestigationPanel } from '@/components/dashboard/investigation-panel'
import { ExcavationTrail } from '@/components/dashboard/excavation-trail'
import { FooterAnalytics } from '@/components/dashboard/footer-analytics'
import { getInvestigationDashboardData } from '@/lib/investigation-adapter'

export default function Page() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const dashboardData = getInvestigationDashboardData()

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <TopBar
        investigation={dashboardData.investigation}
        onToggleSidebar={() => setSidebarOpen((o) => !o)}
      />

      <div className="flex min-h-0 flex-1">
        {/* Left sidebar */}
        <div className="hidden w-72 shrink-0 border-r border-border bg-sidebar lg:block xl:w-80">
          <Sidebar
            activeRepository={dashboardData.activeRepository}
            dataSources={dashboardData.integrations}
            exampleQueries={dashboardData.exampleQueries}
            followUps={dashboardData.followUpQuestions}
          />
        </div>

        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-background/70 backdrop-blur-sm"
              onClick={() => setSidebarOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute left-0 top-0 h-full w-72 border-r border-border bg-sidebar shadow-2xl">
              <Sidebar
                activeRepository={dashboardData.activeRepository}
                dataSources={dashboardData.integrations}
                exampleQueries={dashboardData.exampleQueries}
                followUps={dashboardData.followUpQuestions}
              />
            </div>
          </div>
        )}

        {/* Center investigation panel */}
        <main className="min-w-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto max-w-3xl">
            <InvestigationPanel
              evidenceGraph={dashboardData.evidenceGraph}
              investigation={dashboardData.investigation}
              sourceMeta={dashboardData.sourceMeta}
            />
          </div>
        </main>

        {/* Right excavation trail */}
        <div className="hidden w-80 shrink-0 border-l border-border bg-sidebar xl:block 2xl:w-96">
          <ExcavationTrail
            artifacts={dashboardData.artifacts}
            hypotheses={dashboardData.investigation.hypotheses}
            sourceMeta={dashboardData.sourceMeta}
          />
        </div>
      </div>

      <FooterAnalytics metrics={dashboardData.investigation.metrics} />
    </div>
  )
}
