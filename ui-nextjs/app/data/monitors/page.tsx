'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';
import { API_BASE } from '@/lib/api';
import { DataSource } from '@/lib/data-types';
import CronBuilder, { describeCron } from '@/components/data/CronBuilder';
import KeywordTagInput from '@/components/data/KeywordTagInput';

interface Monitor {
  id: string;
  name: string;
  keywords: string[];
  source_ids: string[];
  schedule: string | null;
  enabled: boolean;
  created_by: string | null;
  created_at: string | null;
}

interface MonitorFormData {
  name: string;
  keywords: string[];
  source_ids: string[];
  schedule: string | null;
  enabled: boolean;
}

const emptyForm: MonitorFormData = {
  name: '',
  keywords: [],
  source_ids: [],
  schedule: null,
  enabled: true,
};

export default function MonitorsPage() {
  const { session, getHeaders } = useAuthHeaders();
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<MonitorFormData>(emptyForm);
  const [saving, setSaving] = useState(false);

  // Delete confirmation
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchMonitors = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch(`${API_BASE}/api/data/monitors`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`Monitors: HTTP ${res.status}`);
      setMonitors(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load monitors');
    }
  }, [session?.access_token, getHeaders]);

  const fetchSources = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch(`${API_BASE}/api/data/sources`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`Sources: HTTP ${res.status}`);
      setSources(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load sources');
    }
  }, [session?.access_token, getHeaders]);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      setError(null);
      await Promise.all([fetchMonitors(), fetchSources()]);
      setLoading(false);
    };
    loadAll();
  }, [fetchMonitors, fetchSources]);

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (monitor: Monitor) => {
    setEditingId(monitor.id);
    setForm({
      name: monitor.name,
      keywords: [...monitor.keywords],
      source_ids: [...monitor.source_ids],
      schedule: monitor.schedule,
      enabled: monitor.enabled,
    });
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    const body = {
      name: form.name,
      keywords: form.keywords,
      source_ids: form.source_ids,
      schedule: form.schedule,
      enabled: form.enabled,
    };

    try {
      const url = editingId
        ? `${API_BASE}/api/data/monitors/${editingId}`
        : `${API_BASE}/api/data/monitors`;
      const method = editingId ? 'PATCH' : 'POST';

      const res = await fetch(url, {
        method,
        headers: getHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      closeModal();
      fetchMonitors();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save monitor');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (monitor: Monitor) => {
    setTogglingIds((prev) => new Set(prev).add(monitor.id));

    try {
      const res = await fetch(`${API_BASE}/api/data/monitors/${monitor.id}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ enabled: !monitor.enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setMonitors((prev) =>
        prev.map((m) => (m.id === monitor.id ? { ...m, enabled: !m.enabled } : m))
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to toggle monitor');
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(monitor.id);
        return next;
      });
    }
  };

  const handleDelete = async () => {
    if (!deletingId) return;
    setDeleting(true);

    try {
      const res = await fetch(`${API_BASE}/api/data/monitors/${deletingId}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDeletingId(null);
      fetchMonitors();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to delete monitor');
    } finally {
      setDeleting(false);
    }
  };

  const toggleSourceId = (sourceId: string) => {
    setForm((prev) => ({
      ...prev,
      source_ids: prev.source_ids.includes(sourceId)
        ? prev.source_ids.filter((id) => id !== sourceId)
        : [...prev.source_ids, sourceId],
    }));
  };

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <header className="mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white mb-1">Keyword Monitors</h1>
            <div className="w-16 h-1 bg-[#00ff32] mb-3" />
            <p className="text-gray-400 text-sm">
              Track keywords across data sources with automated monitoring.
            </p>
          </div>
          <button
            type="button"
            onClick={openCreate}
            className="px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors"
          >
            Create Monitor
          </button>
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
        ) : monitors.length === 0 ? (
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-12 text-center">
            <p className="text-gray-500 text-sm mb-3">No keyword monitors configured yet.</p>
            <button
              type="button"
              onClick={openCreate}
              className="inline-block px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors"
            >
              Create your first monitor
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {monitors.map((monitor) => (
              <div
                key={monitor.id}
                className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-white font-medium">{monitor.name}</h3>
                    <p className="text-gray-500 text-xs mt-0.5">
                      {monitor.source_ids.length} source{monitor.source_ids.length !== 1 ? 's' : ''}
                      {' | '}
                      {describeCron(monitor.schedule)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => openEdit(monitor)}
                      className="text-gray-400 text-sm hover:text-white transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeletingId(monitor.id)}
                      className="text-gray-400 text-sm hover:text-red-400 transition-colors"
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      disabled={togglingIds.has(monitor.id)}
                      onClick={() => handleToggleEnabled(monitor)}
                      className={`relative w-10 h-5 rounded-full transition-colors focus:outline-none ${
                        monitor.enabled ? 'bg-[#00ff32]/60' : 'bg-[#404040]'
                      } ${togglingIds.has(monitor.id) ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
                    >
                      <span
                        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                          monitor.enabled ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {monitor.keywords.map((keyword) => (
                    <span
                      key={keyword}
                      className="bg-[#404040] text-gray-300 rounded-full px-2 py-0.5 text-xs"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create/Edit modal */}
        {modalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div
              className="absolute inset-0 bg-black/60"
              onClick={closeModal}
            />
            <div className="relative bg-[#1a1a1a] border border-[#404040] rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto mx-4 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">
                {editingId ? 'Edit Monitor' : 'Create Monitor'}
              </h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Name</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="Monitor name"
                    className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white text-sm placeholder-gray-600 focus:border-[#00ff32] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Keywords</label>
                  <KeywordTagInput
                    value={form.keywords}
                    onChange={(keywords) => setForm({ ...form, keywords })}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Sources</label>
                  {sources.length === 0 ? (
                    <p className="text-gray-500 text-sm">No sources available.</p>
                  ) : (
                    <div className="space-y-2 max-h-40 overflow-y-auto">
                      {sources.map((source) => (
                        <label
                          key={source.id}
                          className="flex items-center gap-2 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={form.source_ids.includes(source.id)}
                            onChange={() => toggleSourceId(source.id)}
                            className="w-4 h-4 rounded border-[#404040] bg-[#292929] text-[#00ff32] focus:ring-[#00ff32] focus:ring-offset-0"
                          />
                          <span className="text-sm text-gray-300">{source.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-2">Schedule</label>
                  <CronBuilder
                    value={form.schedule}
                    onChange={(schedule) => setForm({ ...form, schedule })}
                  />
                </div>
                <div className="flex gap-3 pt-2">
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving || !form.name.trim()}
                    className="px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {saving ? 'Saving...' : editingId ? 'Update' : 'Create'}
                  </button>
                  <button
                    type="button"
                    onClick={closeModal}
                    className="px-4 py-2 bg-[#404040] text-gray-300 text-sm rounded hover:bg-[#505050] transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Delete confirmation modal */}
        {deletingId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div
              className="absolute inset-0 bg-black/60"
              onClick={() => setDeletingId(null)}
            />
            <div className="relative bg-[#1a1a1a] border border-[#404040] rounded-lg w-full max-w-sm mx-4 p-6">
              <h2 className="text-lg font-semibold text-white mb-2">Delete Monitor</h2>
              <p className="text-gray-400 text-sm mb-4">
                Are you sure you want to delete this monitor? This action cannot be undone.
              </p>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-wait"
                >
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
                <button
                  type="button"
                  onClick={() => setDeletingId(null)}
                  className="px-4 py-2 bg-[#404040] text-gray-300 text-sm rounded hover:bg-[#505050] transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
