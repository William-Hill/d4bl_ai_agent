'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import SourceTable from '@/components/data/SourceTable';

interface DataSource {
  id: string;
  name: string;
  source_type: string;
  config: Record<string, unknown>;
  default_schedule: string | null;
  enabled: boolean;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_run_status: string | null;
  last_run_at: string | null;
}

export default function SourcesPage() {
  const { session } = useAuth();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }), [session?.access_token]);

  const fetchSources = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/data/sources`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSources(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load sources');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, getHeaders]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const handleToggleEnabled = async (id: string, enabled: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/data/sources/${id}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSources((prev) =>
        prev.map((s) => (s.id === id ? { ...s, enabled } : s))
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update source');
    }
  };

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <header className="mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white mb-1">Data Sources</h1>
            <div className="w-16 h-1 bg-[#00ff32] mb-3" />
            <p className="text-gray-400 text-sm">
              Manage and monitor your data ingestion sources.
            </p>
          </div>
          <Link
            href="/data/sources/new"
            className="px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors"
          >
            Add Source
          </Link>
        </header>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            Error: {error}
          </div>
        )}

        {loading ? (
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-8 animate-pulse">
            <div className="h-4 bg-[#404040] rounded w-1/3 mb-4" />
            <div className="h-4 bg-[#404040] rounded w-1/2 mb-4" />
            <div className="h-4 bg-[#404040] rounded w-2/5" />
          </div>
        ) : (
          <SourceTable sources={sources} onToggleEnabled={handleToggleEnabled} />
        )}
      </div>
    </div>
  );
}
