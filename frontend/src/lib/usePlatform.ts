import { useQuery } from '@tanstack/react-query'

import { api, type PlatformInfo } from './api'

/** Capacidades reales de la máquina donde corre el monitor. */
const POR_DEFECTO: PlatformInfo = {
  os: 'unknown',
  frozen: false,
  hardware_temps: true,
  runner_launch: true,
  runner_python: null,
  auto_advance: true,
}

/**
 * Lee de /api/health qué se puede hacer aquí.
 *
 * Mientras no haya respuesta se asume que todo está disponible: esconder
 * controles por un parpadeo de carga sería peor que mostrarlos un instante.
 */
export function usePlatform(): PlatformInfo {
  return useHealth().data?.platform ?? POR_DEFECTO
}

/** Consulta compartida de /api/health; TanStack Query la deduplica. */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

/** Versión del monitor, para la cabecera. */
export function useVersion(): string | null {
  return useHealth().data?.version ?? null
}
