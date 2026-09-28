import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from './AppShell'
import { NotFoundPage } from './NotFoundPage'
import { LoginPage } from './LoginPage'
import { RequireRole, RequireSession } from './AuthSession'
import { EpisodePage } from '../features/episode/EpisodePage'
import { MachinePage } from '../features/machine/MachinePage'
import { AdminPage } from '../features/admin/AdminPage'
import { CatalogPage } from '../features/catalog/CatalogPage'
import { ImportsPage } from '../features/catalog/ImportsPage'
import { TelemetryPage } from '../features/catalog/TelemetryPage'
import { InspectionListPage } from '../features/inspection/InspectionListPage'
import { InspectionCasePage } from '../features/inspection/InspectionCasePage'

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { element: <RequireSession />, children: [
    { path: '/', element: <AppShell />, children: [
      { index: true, element: <CatalogPage /> },
      { path: 'auditoria', element: <Navigate to="/" replace /> },
      { path: 'admin', element: <RequireRole role="ADMIN"><AdminPage /></RequireRole> },
      { path: 'tratores/:tractorId', element: <MachinePage /> },
      { path: 'tratores/:tractorId/telemetria', element: <TelemetryPage /> },
      { path: 'tratores/:tractorId/importacoes', element: <RequireRole role={['INSURER', 'ADMIN']}><ImportsPage /></RequireRole> },
      { path: 'tratores/:tractorId/episodios/:episodeId', element: <EpisodePage /> },
      { path: 'vistorias', element: <RequireRole role={['INSURER', 'INSPECTOR', 'ADMIN']}><InspectionListPage /></RequireRole> },
      { path: 'vistorias/:caseId', element: <RequireRole role={['INSURER', 'INSPECTOR', 'ADMIN']}><InspectionCasePage /></RequireRole> },
      { path: '*', element: <NotFoundPage /> },
    ] },
  ] },
])

export { router }
