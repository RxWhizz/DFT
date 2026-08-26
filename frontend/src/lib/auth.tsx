/** Contexto de sesión: envuelve /auth/me, /auth/login y /auth/logout. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, type ReactNode } from 'react'

import { api, type AuthState } from './api'

interface AuthContextValue {
  state: AuthState | undefined
  loading: boolean
  login: (token: string) => Promise<AuthState>
  logout: () => Promise<void>
  loginError: string | null
  loggingIn: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['auth'],
    queryFn: api.me,
    retry: false,
    staleTime: 60_000,
  })

  const loginMut = useMutation({
    mutationFn: api.login,
    onSuccess: (next) => {
      qc.setQueryData(['auth'], next)
      qc.invalidateQueries()
    },
  })

  const logoutMut = useMutation({
    mutationFn: api.logout,
    onSuccess: (next) => {
      // Al cerrar sesión no debe quedar nada cacheado del usuario anterior.
      qc.clear()
      qc.setQueryData(['auth'], next)
    },
  })

  return (
    <AuthContext.Provider
      value={{
        state: data,
        loading: isLoading,
        login: (token) => loginMut.mutateAsync(token),
        logout: async () => {
          await logoutMut.mutateAsync()
        },
        loginError: loginMut.error ? (loginMut.error as Error).message : null,
        loggingIn: loginMut.isPending,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
