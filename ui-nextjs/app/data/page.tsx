'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import SourceHealthCards from '@/components/data/SourceHealthCards';

interface OverviewData {
  total_sources: number;
  enabled_sources: number;
  recent_failures: number;
}

interface IngestionRun {
  id: string;
  data_source_id: string;
  dagster_run_id: string | null;
  status: string;
  triggered_by: string | null;
  trigger_type: string;
  records_ingested: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_detail: string | null;
}

const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-green-900/40 text-green-400 border-green-800',
  running: 'bg-yellow-900/40 text-yellow-400 border-yellow-800',
  failed: 'bg-red-900/40 text-red-400 border-red-800',
  pending: 'bg-gray-800/40 text-gray-400 border-gray-700',
};

export default function DataPage() {
  const { session } = useAuth();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }), [session?.access_token]);

  const fetchData = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);

    try {
      const [overviewRes, runsRes] = await Promise.all([
        fetch(`${API_BASE}/api/data/overview`, { headers: getHeaders() }),
        fetch(`${API_BASE}/api/data/runs?limit=10`, { headers: getHeaders() }),
      ]);

      if (!overviewRes.ok) throw new Error(`Overview: HTTP ${overviewRes.status}`);
      if (!runsRes.ok) throw new Error(`Runs: HTTP ${runsRes.status}`);

      setOverview(await overviewRes.json());
      setRuns(await runsRes.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, getHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">Data Ingestion</h1>
          <div className="w-16 h-1 bg-[#00ff32] mb-3" />
          <p className="text-gray-400 text-sm">
            Monitor data sources, ingestion runs, and pipeline health.
          </p>
        </header>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            Error loading data: {error}
          </div>
        )}

        {/* Alert banner for failing sources */}
        {overview && overview.recent_failures > 0 && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm flex items-center gap-2">
            <span className="font-semibold">Alert:</span>
            {overview.recent_failures} source{overview.recent_failures > 1 ? 's' : ''} with recent failures.
          </div>
        )}

        {/* Health summary cards */}
        {loading && !overview ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 animate-pulse h-20"
              />
            ))}
          </div>
        ) : overview ? (
          <div className="mb-8">
            <SourceHealthCards
              totalSources={overview.total_sources}
              enabledSources={overview.enabled_sources}
              recentFailures={overview.recent_failures}
            />
          </div>
        ) : null}

        {/* Recent runs table */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-[#404040]">
            <h2 className="text-base font-semibold text-white">Recent Runs</h2>
          </div>
          {loading && !runs.length ? (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">Loading runs...</div>
          ) : runs.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">No ingestion runs yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[#404040]">
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Source</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Status</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Trigger</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Records</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Started</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Completed</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id} className="border-b border-[#404040] last:border-0">
                      <td className="px-4 py-3 text-white text-sm font-mono">
                        {run.data_source_id}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block text-xs px-2 py-0.5 rounded border ${
                            STATUS_STYLES[run.status] ?? STATUS_STYLES.pending
                          }`}
                        >
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-sm">{run.trigger_type}</td>
                      <td className="px-4 py-3 text-gray-300 text-sm">
                        {run.records_ingested != null ? run.records_ingested.toLocaleString() : '-'}
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-sm">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-sm">
                        {run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
