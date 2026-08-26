import { useQueryClient } from '@tanstack/react-query'
import { Suspense, lazy, useCallback } from 'react'
import { Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { Login } from './components/Login'
import { useAuth } from './lib/auth'
import { useEvents } from './lib/useEvents'
import { Live } from './pages/Live'

// Live va en el bundle inicial porque es la vista por defecto. El resto se
// carga bajo demanda: react-markdown, el scatter y sobre todo 3Dmol no tienen
// por qué descargarse para mirar el estado de los jobs.
const Agent = lazy(() => import('./pages/Agent').then((m) => ({ default: m.Agent })))
const Jobs = lazy(() => import('./pages/Jobs').then((m) => ({ default: m.Jobs })))
const Candidates = lazy(() =>
  import('./pages/Candidates').then((m) => ({ default: m.Candidates })),
)
const Ml = lazy(() => import('./pages/Ml').then((m) => ({ default: m.Ml })))
const Screening = lazy(() =>
  import('./pages/Screening').then((m) => ({ default: m.Screening })),
)
const Structures = lazy(() =>
  import('./pages/Structures').then((m) => ({ default: m.Structures })),
)
const Results = lazy(() => import('./pages/Results').then((m) => ({ default: m.Results })))

function Cargando() {
  return <p className="p-4 text-sm text-ink-400">Cargando vista…</p>
}

export default function App() {
  const { state, loading } = useAuth()
  const qc = useQueryClient()

  // Un hueco de eventos o una reconexión invalidan el estado local: se refresca
  // por REST en vez de seguir mostrando datos que ya no son ciertos.
  const onResync = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['jobs'] })
    void qc.invalidateQueries({ queryKey: ['summary'] })
    void qc.invalidateQueries({ queryKey: ['health'] })
  }, [qc])

  const authed = Boolean(state?.authenticated)
  const { state: conn, events } = useEvents({ onResync, enabled: authed })

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-400">
        Cargando…
      </div>
    )
  }

  if (!authed) return <Login />

  return (
    <Routes>
      <Route element={<Layout conn={conn} />}>
        <Route index element={<Live events={events} />} />
        <Route
          path="agent"
          element={
            <Suspense fallback={<Cargando />}>
              <Agent />
            </Suspense>
          }
        />
        <Route
          path="jobs"
          element={
            <Suspense fallback={<Cargando />}>
              <Jobs />
            </Suspense>
          }
        />
        <Route
          path="screening"
          element={
            <Suspense fallback={<Cargando />}>
              <Screening />
            </Suspense>
          }
        />
        <Route
          path="candidates"
          element={
            <Suspense fallback={<Cargando />}>
              <Candidates />
            </Suspense>
          }
        />
        <Route
          path="ml"
          element={
            <Suspense fallback={<Cargando />}>
              <Ml />
            </Suspense>
          }
        />
        <Route
          path="structures"
          element={
            <Suspense fallback={<Cargando />}>
              <Structures />
            </Suspense>
          }
        />
        <Route
          path="results"
          element={
            <Suspense fallback={<Cargando />}>
              <Results />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  )
}
