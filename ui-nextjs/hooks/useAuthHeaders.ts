import { useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';

export function useAuthHeaders() {
  const { session } = useAuth();

  const getHeaders = useCallback(() => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (session?.access_token) {
      headers['Authorization'] = `Bearer ${session.access_token}`;
    }
    return headers;
  }, [session]);

  return { session, getHeaders };
}
