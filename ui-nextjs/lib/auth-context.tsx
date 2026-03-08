'use client';

import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { createClient } from './supabase';

interface AuthContextType {
  user: User | null;
  session: Session | null;
  role: string | null;
  isAdmin: boolean;
  isLoading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  session: null,
  role: null,
  isAdmin: false,
  isLoading: true,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [mounted, setMounted] = useState(false);

  // Only create the Supabase client on the client side to avoid build-time errors
  // when NEXT_PUBLIC_SUPABASE_URL is not set during static generation
  const supabaseRef = useRef<ReturnType<typeof createClient> | null>(null);
  if (typeof window !== 'undefined' && !supabaseRef.current) {
    try {
      supabaseRef.current = createClient();
    } catch {
      // Supabase env vars not configured; auth will be unavailable
    }
  }
  const supabase = supabaseRef.current;

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !supabase) {
      if (mounted) setIsLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.user) {
        fetchRole(session.access_token);
      } else {
        setIsLoading(false);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
        setUser(session?.user ?? null);
        if (session?.user) {
          fetchRole(session.access_token);
        } else {
          setRole(null);
          setIsLoading(false);
        }
      }
    );

    return () => subscription.unsubscribe();
  }, [mounted]); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchRole(accessToken: string) {
    try {
      const { API_BASE } = await import('./api');
      const response = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setRole(data.role);
      }
    } catch {
      setRole('user');
    } finally {
      setIsLoading(false);
    }
  }

  const signOut = async () => {
    if (supabase) {
      await supabase.auth.signOut();
    }
    setUser(null);
    setSession(null);
    setRole(null);
  };

  return (
    <AuthContext.Provider value={{
      user,
      session,
      role,
      isAdmin: role === 'admin',
      isLoading,
      signOut,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
