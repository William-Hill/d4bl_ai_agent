'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';
import { API_BASE } from '@/lib/api';
import { DataSource, IngestionRun, STATUS_STYLES, TYPE_LABELS } from '@/lib/data-types';
import CronBuilder from '@/components/data/CronBuilder';
import QualityTrendChart from '@/components/data/QualityTrendChart';

export default function SourceDetailPage() {
  const params = useParams<{ id: string }>();
  const { session, getHeaders } = useAuthHeaders();
  const [source, setSource] = useState<DataSource | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [togglingEnabled, setTogglingEnabled] = useState(false);

  // Edit form state
  const [editName, setEditName] = useState('');
  const [editConfig, setEditConfig] = useState('');
  const [editSchedule, setEditSchedule] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!session?.access_token || !params.id) return;
    setLoading(true);
    setError(null);

    try {
      const [sourceRes, runsRes] = await Promise.all([
        fetch(`${API_BASE}/api/data/sources/${params.id}`, { headers: getHeaders() }),
        fetch(`${API_BASE}/api/data/runs?source_id=${params.id}&limit=20`, { headers: getHeaders() }),
      ]);

      if (!sourceRes.ok) throw new Error(`Source: HTTP ${sourceRes.status}`);

      const sourceData: DataSource = await sourceRes.json();
      setSource(sourceData);

      // Initialize edit form
      setEditName(sourceData.name);
      setEditConfig(JSON.stringify(sourceData.config, null, 2));
      setEditSchedule(sourceData.default_schedule);

      // Runs fetch is independent - don't block source display on failure
      if (runsRes.ok) {
        setRuns(await runsRes.json());
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load source');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, params.id, getHeaders]);

  const fetchRuns = useCallback(async () => {
    if (!session?.access_token || !params.id) return;
    try {
      const res = await fetch(`${API_BASE}/api/data/runs?source_id=${params.id}&limit=20`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`Runs: HTTP ${res.status}`);
      setRuns(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load runs');
    }
  }, [session?.access_token, params.id, getHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleTrigger = async () => {
    if (!source) return;
    setTriggering(true);
    setTriggerResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/data/sources/${source.id}/trigger`, {
        method: 'POST',
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTriggerResult(`Run triggered: ${data.run_id}`);
      // Refresh runs list
      fetchRuns();
    } catch (e: unknown) {
      setTriggerResult(e instanceof Error ? e.message : 'Failed to trigger run');
    } finally {
      setTriggering(false);
    }
  };

  const handleToggleEnabled = async () => {
    if (!source) return;
    setTogglingEnabled(true);

    try {
      const res = await fetch(`${API_BASE}/api/data/sources/${source.id}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSource({ ...source, enabled: !source.enabled });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to toggle source');
    } finally {
      setTogglingEnabled(false);
    }
  };

  const handleSave = async () => {
    if (!source) return;
    setSaving(true);
    setError(null);

    try {
      let parsedConfig: unknown;
      try {
        parsedConfig = JSON.parse(editConfig);
      } catch {
        setError('Invalid JSON in config field');
        setSaving(false);
        return;
      }
      if (parsedConfig === null || Array.isArray(parsedConfig) || typeof parsedConfig !== 'object') {
        setError('Config must be a JSON object');
        setSaving(false);
        return;
      }

      const res = await fetch(`${API_BASE}/api/data/sources/${source.id}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({
          name: editName,
          config: parsedConfig,
          default_schedule: editSchedule,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated: DataSource = await res.json();
      setSource(updated);
      setEditing(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

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

  if (!source) {
    return (
      <div className="min-h-screen bg-[#292929]">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            {error || 'Source not found'}
          </div>
          <Link href="/data/sources" className="text-[#00ff32] text-sm hover:underline">
            Back to Sources
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Back link */}
        <Link href="/data/sources" className="text-[#00ff32] text-sm hover:underline mb-6 inline-block">
          &larr; Back to Sources
        </Link>

        {error && (
          <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Header */}
        <header className="mb-6 flex items-start justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold text-white">{source.name}</h1>
            <span className="inline-block text-xs px-2 py-0.5 rounded border border-[#404040] bg-[#292929] text-gray-300">
              {TYPE_LABELS[source.source_type] ?? source.source_type}
            </span>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={source.enabled}
            aria-label={`Toggle ${source.name}`}
            disabled={togglingEnabled}
            onClick={handleToggleEnabled}
            className={`relative w-10 h-5 rounded-full transition-colors focus:ring-2 focus:ring-[#00ff32] focus:ring-offset-1 focus:ring-offset-[#292929] focus:outline-none ${
              source.enabled ? 'bg-[#00ff32]/60' : 'bg-[#404040]'
            } ${togglingEnabled ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                source.enabled ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </header>

        {/* Actions bar */}
        <div className="flex items-center gap-3 mb-6">
          <button
            type="button"
            onClick={handleTrigger}
            disabled={triggering}
            className="px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors disabled:opacity-50 disabled:cursor-wait"
          >
            {triggering ? 'Triggering...' : 'Trigger Now'}
          </button>
          <button
            type="button"
            onClick={() => {
              if (!editing && source) {
                setEditName(source.name);
                setEditConfig(JSON.stringify(source.config, null, 2));
                setEditSchedule(source.default_schedule);
              }
              setEditing(!editing);
            }}
            className="px-4 py-2 bg-[#404040] text-gray-300 text-sm rounded hover:bg-[#505050] transition-colors"
          >
            {editing ? 'Cancel Edit' : 'Edit'}
          </button>
          {triggerResult && (
            <span className="text-sm text-gray-400">{triggerResult}</span>
          )}
        </div>

        {/* Config section */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg mb-6">
          <div className="px-4 py-3 border-b border-[#404040]">
            <h2 className="text-base font-semibold text-white">Configuration</h2>
          </div>
          {editing ? (
            <div className="p-4 space-y-4">
              <div>
                <label htmlFor="edit-name" className="block text-sm text-gray-400 mb-1">Name</label>
                <input
                  id="edit-name"
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white text-sm focus:border-[#00ff32] focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="edit-config" className="block text-sm text-gray-400 mb-1">Config (JSON)</label>
                <textarea
                  id="edit-config"
                  value={editConfig}
                  onChange={(e) => setEditConfig(e.target.value)}
                  rows={8}
                  className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white text-sm font-mono focus:border-[#00ff32] focus:outline-none"
                />
              </div>
              <div>
                <label id="edit-schedule-label" className="block text-sm text-gray-400 mb-2">Schedule</label>
                <CronBuilder value={editSchedule} onChange={setEditSchedule} />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors disabled:opacity-50 disabled:cursor-wait"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (source) {
                      setEditName(source.name);
                      setEditConfig(JSON.stringify(source.config, null, 2));
                      setEditSchedule(source.default_schedule);
                    }
                    setEditing(false);
                  }}
                  className="px-4 py-2 bg-[#404040] text-gray-300 text-sm rounded hover:bg-[#505050] transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="p-4">
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
                <div>
                  <dt className="text-xs text-gray-500">Schedule</dt>
                  <dd className="text-sm text-gray-300 font-mono">{source.default_schedule ?? 'None'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Created</dt>
                  <dd className="text-sm text-gray-300">
                    {source.created_at ? new Date(source.created_at).toLocaleString() : '-'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Last Run</dt>
                  <dd className="text-sm text-gray-300">
                    {source.last_run_at ? new Date(source.last_run_at).toLocaleString() : '-'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Last Run Status</dt>
                  <dd>
                    {source.last_run_status ? (
                      <span
                        className={`inline-block text-xs px-2 py-0.5 rounded border ${
                          STATUS_STYLES[source.last_run_status] ?? STATUS_STYLES.pending
                        }`}
                      >
                        {source.last_run_status}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-500">-</span>
                    )}
                  </dd>
                </div>
                {Object.entries(source.config).map(([key, value]) => (
                  <div key={key}>
                    <dt className="text-xs text-gray-500">{key}</dt>
                    <dd className="text-sm text-gray-300 font-mono break-all">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>

        {/* Quality trend chart */}
        <div className="mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Ingestion Trend</h2>
          <QualityTrendChart runs={runs} />
        </div>

        {/* Run history */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-[#404040]">
            <h2 className="text-base font-semibold text-white">Run History</h2>
          </div>
          {runs.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-500 text-sm">No runs yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[#404040]">
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Status</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Trigger</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Records</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Started</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Completed</th>
                    <th className="px-4 py-3 text-left text-sm text-gray-400">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id} className="border-b border-[#404040] last:border-0">
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
                      <td className="px-4 py-3 text-red-400 text-sm max-w-xs truncate">
                        {run.error_detail ?? '-'}
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
