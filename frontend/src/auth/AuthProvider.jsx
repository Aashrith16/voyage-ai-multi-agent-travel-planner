import { useEffect, useMemo, useState } from 'react'
import { authConfigurationReady, supabase } from '../lib/supabase'
import { AuthContext } from './AuthContext'

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(Boolean(supabase))
  const [recoveryMode, setRecoveryMode] = useState(false)

  useEffect(() => {
    if (!supabase) return undefined
    let mounted = true
    supabase.auth.getSession().then(({ data }) => {
      if (mounted) {
        setSession(data.session)
        setLoading(false)
      }
    })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (event === 'PASSWORD_RECOVERY') setRecoveryMode(true)
      setSession(nextSession)
      setLoading(false)
    })
    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [])

  const value = useMemo(() => ({
    session,
    user: session?.user || null,
    loading,
    recoveryMode,
    clearRecoveryMode() { setRecoveryMode(false) },
    configured: authConfigurationReady,
    async signIn(email, password) {
      if (!supabase) throw new Error('Supabase Auth is not configured for this frontend.')
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      setSession(data.session)
      return data
    },
    async signUp(email, password) {
      if (!supabase) throw new Error('Supabase Auth is not configured for this frontend.')
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/login` },
      })
      if (error) throw error
      if (data.session) setSession(data.session)
      return data
    },
    async resetPassword(email) {
      if (!supabase) throw new Error('Supabase Auth is not configured for this frontend.')
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/forgot-password`,
      })
      if (error) throw error
    },
    async updatePassword(password) {
      if (!supabase) throw new Error('Supabase Auth is not configured for this frontend.')
      const { data, error } = await supabase.auth.updateUser({ password })
      if (error) throw error
      return data
    },
    async signOut() {
      if (!supabase) return
      const { error } = await supabase.auth.signOut()
      if (error) throw error
      setSession(null)
    },
  }), [session, loading, recoveryMode])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}