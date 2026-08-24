import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './AppShell'
import { NotFoundPage } from './NotFoundPage'
import { DemonstrationDashboardPage } from '../features/demonstration/DemonstrationDashboardPage'
import { FleetOverviewPage } from '../features/fleet/FleetOverviewPage'
import { PortfolioPage } from '../features/portfolio/PortfolioPage'
import { RegisterFleetPage } from '../features/registration/RegisterFleetPage'
import { TractorOverviewPage } from '../features/tractor/TractorOverviewPage'

const router = createBrowserRouter([
  { path: '/', element: <AppShell />, children: [
    { index: true, element: <DemonstrationDashboardPage /> },
    { path: 'prioridades', element: <PortfolioPage /> },
    { path: 'frotas/nova', element: <RegisterFleetPage /> },
    { path: 'frotas/:fleetId', element: <FleetOverviewPage /> },
    { path: 'tratores/:tractorId', element: <TractorOverviewPage /> },
    { path: '*', element: <NotFoundPage /> },
  ] },
])

export { router }
