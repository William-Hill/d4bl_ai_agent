import { useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';

export function useAuthHeaders() {
  const { session } = useAuth();

  const getHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }), [session?.access_token]);

  return { session, getHeaders };
}
