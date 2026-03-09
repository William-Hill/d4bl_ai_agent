'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';
import { API_BASE } from '@/lib/api';
import { IngestionRun, STATUS_STYLES } from '@/lib/data-types';
import RunTimeline from '@/components/data/RunTimeline';

function formatDuration(startedAt: string, completedAt: string): string {
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  const diffMs = end - start;

  if (diffMs < 0) return '-';

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s`;

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const { session, getHeaders } = useAuthHeaders();
  const [run, setRun] = useState<IngestionRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRun = useCallback(async () => {
    if (!session?.access_token || !params.id) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/data/runs?limit=100`, {
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const runs: IngestionRun[] = await res.json();
      const found = runs.find((r) => r.id === params.id);
      if (found) {
        setRun(found);
      } else {
        setError('Run not found');
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load run');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, params.id, getHeaders]);

  useEffect(() => {
    fetchRun();
  }, [fetchRun]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#292929]">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-8 animate-pulse">
            <div className="h-6 bg-[#404040] rounded w-1/3 mb-4" />
            <div className="h-4 bg-[#404040] rounded w-1/2 mb-4" />
            <div className="h-4 bg-[#404040] rounded w-2/5" />
          </div>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="min-h-screen bg-[#292929]">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            {error || 'Run not found'}
          </div>
          <Link href="/data" className="text-[#00ff32] text-sm hover:underline">
            &larr; Back to Data Ingestion
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Back link */}
        <Link href="/data" className="text-[#00ff32] text-sm hover:underline mb-6 inline-block">
          &larr; Back to Data Ingestion
        </Link>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Header */}
        <header className="mb-6">
          <div className="flex items-center gap-4 mb-1">
            <h1 className="text-3xl font-bold text-white">Run Detail</h1>
            <span
              className={`inline-block text-sm px-3 py-1 rounded border font-medium ${
                STATUS_STYLES[run.status] ?? STATUS_STYLES.pending
              }`}
            >
              {run.status}
            </span>
          </div>
          <div className="w-16 h-1 bg-[#00ff32] mb-3" />
          <p className="text-gray-500 text-xs font-mono">{run.id}</p>
        </header>

        {/* Info grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
            <dt className="text-xs text-gray-500 mb-1">Source</dt>
            <dd>
              <Link
                href={`/data/sources/${run.data_source_id}`}
                className="text-sm text-[#00ff32] hover:underline font-mono break-all"
              >
                {run.data_source_id}
              </Link>
            </dd>
          </div>
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
            <dt className="text-xs text-gray-500 mb-1">Trigger Type</dt>
            <dd className="text-sm text-gray-300">{run.trigger_type}</dd>
          </div>
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
            <dt className="text-xs text-gray-500 mb-1">Records Ingested</dt>
            <dd className="text-sm text-gray-300">
              {run.records_ingested != null ? run.records_ingested.toLocaleString() : '-'}
            </dd>
          </div>
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
            <dt className="text-xs text-gray-500 mb-1">Dagster Run ID</dt>
            <dd className="text-sm text-gray-300 font-mono break-all">
              {run.dagster_run_id ?? '-'}
            </dd>
          </div>
        </div>

        {/* Timestamps */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Timestamps</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-3">
            <div>
              <dt className="text-xs text-gray-500">Started</dt>
              <dd className="text-sm text-gray-300">
                {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Completed</dt>
              <dd className="text-sm text-gray-300">
                {run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Duration</dt>
              <dd className="text-sm text-gray-300">
                {run.started_at && run.completed_at
                  ? formatDuration(run.started_at, run.completed_at)
                  : '-'}
              </dd>
            </div>
          </dl>
        </div>

        {/* Error details */}
        {run.error_detail && (
          <div className="bg-[#1a1a1a] border border-red-800 rounded-lg p-4 mb-6">
            <h2 className="text-base font-semibold text-red-400 mb-2">Error Details</h2>
            <pre className="text-sm text-red-300 font-mono whitespace-pre-wrap break-words">
              {run.error_detail}
            </pre>
          </div>
        )}

        {/* Run Timeline */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
          <h2 className="text-base font-semibold text-white mb-4">Pipeline Steps</h2>
          <RunTimeline status={run.status} />
        </div>
      </div>
    </div>
  );
}
