'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { API_BASE, getCostSummary, CostSummary } from '@/lib/api';
import DataStatusCard from '@/components/data/DataStatusCard';

interface UserProfile {
  id: string;
  email: string;
  role: string;
  display_name: string | null;
  created_at: string | null;
}

export default function AdminPage() {
  const { isAdmin, isLoading, session } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- Cost tracking state ---
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);

  // --- Data ingestion state ---
  const INGEST_SOURCES = [
    { key: 'cdc', label: 'CDC Health Outcomes' },
    { key: 'census', label: 'Census ACS' },
    { key: 'epa', label: 'EPA Environmental Justice' },
    { key: 'fbi', label: 'FBI Crime Stats' },
    { key: 'bls', label: 'BLS Labor Statistics' },
    { key: 'hud', label: 'HUD Fair Housing' },
    { key: 'usda', label: 'USDA Food Access' },
    { key: 'doe', label: 'DOE Civil Rights' },
    { key: 'police', label: 'Police Violence' },
    { key: 'openstates', label: 'OpenStates Legislation' },
  ] as const;
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [ingestJobId, setIngestJobId] = useState<string | null>(null);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);
  const [ingestLoading, setIngestLoading] = useState(false);

  const getHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token}`,
  }), [session?.access_token]);

  const fetchUsers = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const response = await fetch(`${API_BASE}/api/admin/users`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        setUsers(await response.json());
      } else {
        const data = await response.json().catch(() => ({}));
        setError(data.detail || 'Failed to load users');
      }
    } catch {
      setError('Failed to load users');
    }
  }, [session?.access_token, getHeaders]);

  useEffect(() => {
    if (!isLoading && !isAdmin) {
      router.push('/');
    }
  }, [isAdmin, isLoading, router]);

  useEffect(() => {
    if (isAdmin) {
      fetchUsers();
      getCostSummary().then(setCostSummary).catch(() => { /* ignore if endpoint unavailable */ });
    }
  }, [isAdmin, fetchUsers]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteLoading(true);
    setMessage(null);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/admin/invite`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ email: inviteEmail }),
      });

      if (response.ok) {
        setMessage(`Invitation sent to ${inviteEmail}`);
        setInviteEmail('');
        fetchUsers();
      } else {
        const data = await response.json();
        setError(data.detail || 'Failed to send invitation');
      }
    } catch {
      setError('Failed to send invitation');
    } finally {
      setInviteLoading(false);
    }
  };

  // --- Data ingestion helpers ---
  const toggleSource = (key: string) => {
    setSelectedSources((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const triggerIngestion = async (sources?: string[]) => {
    setError(null);
    setIngestLoading(true);
    setIngestStatus(null);
    setIngestJobId(null);
    try {
      const body: Record<string, unknown> = {};
      if (sources && sources.length > 0) body.sources = sources;
      const resp = await fetch(`${API_BASE}/api/admin/ingest`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        const data = await resp.json();
        setIngestJobId(data.job_id);
        setIngestStatus('running');
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Failed to start ingestion');
      }
    } catch {
      setError('Failed to start ingestion');
    } finally {
      setIngestLoading(false);
    }
  };

  // Poll ingestion status while running
  useEffect(() => {
    if (!ingestJobId || ingestStatus !== 'running') return;
    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/admin/ingest/status/${ingestJobId}`, {
          headers: getHeaders(),
        });
        if (resp.ok) {
          const data = await resp.json();
          setIngestStatus(data.status);
          if (data.status !== 'running') clearInterval(interval);
        }
      } catch {
        /* ignore transient fetch errors */
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [ingestJobId, ingestStatus, getHeaders]);

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ role: newRole }),
      });

      if (response.ok) {
        fetchUsers();
      } else {
        setError('Failed to update role');
      }
    } catch {
      setError('Failed to update role');
    }
  };

  if (isLoading) {
    return <div className="min-h-screen bg-[#292929] flex items-center justify-center">
      <p className="text-gray-400">Loading...</p>
    </div>;
  }

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-white mb-8">User Management</h1>

        {/* External tools */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Tools</h2>
          <button
            type="button"
            onClick={async () => {
              const dagsterUrl = process.env.NEXT_PUBLIC_DAGSTER_URL || 'https://d4bl-dagster-web.fly.dev';
              const resp = await fetch(`${dagsterUrl}/auth/set-token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: session?.access_token }),
                credentials: 'include',
              });
              if (resp.ok) {
                window.open(`${dagsterUrl}/`, '_blank', 'noopener,noreferrer');
              }
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#292929] border border-[#404040]
                       rounded text-white hover:border-[#00ff32] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"
                 aria-hidden="true" focusable="false">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Open Dagster Pipelines
          </button>
        </div>

        {/* LLM Cost Tracking */}
        {costSummary && (
          <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
            <h2 className="text-lg font-semibold text-white mb-4">LLM Cost Tracking</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-400">Total Cost</p>
                <p className="text-2xl font-mono text-[#00ff32]">
                  ${costSummary.total_estimated_cost_usd < 0.01
                    ? costSummary.total_estimated_cost_usd.toFixed(4)
                    : costSummary.total_estimated_cost_usd.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-400">Total Tokens</p>
                <p className="text-2xl font-mono text-white">
                  {costSummary.total_tokens.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-400">Jobs with Usage</p>
                <p className="text-2xl font-mono text-white">
                  {costSummary.jobs_with_usage} / {costSummary.total_jobs}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-400">Prompt / Completion</p>
                <p className="text-sm font-mono text-gray-300 mt-1">
                  {costSummary.total_prompt_tokens.toLocaleString()} / {costSummary.total_completion_tokens.toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Data Ingestion */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Data Ingestion</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
            {INGEST_SOURCES.map((s) => (
              <label key={s.key} className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                <input
                  type="checkbox"
                  aria-label={`Select ${s.label} for ingestion`}
                  checked={selectedSources.has(s.key)}
                  onChange={() => toggleSource(s.key)}
                  className="accent-[#00ff32]"
                />
                {s.label}
              </label>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={ingestLoading || selectedSources.size === 0}
              onClick={() => triggerIngestion(Array.from(selectedSources))}
              className="px-4 py-2 bg-[#00ff32] text-black font-semibold rounded
                         hover:bg-[#00cc28] disabled:opacity-50 transition-colors"
            >
              Run Selected
            </button>
            <button
              type="button"
              disabled={ingestLoading}
              onClick={() => triggerIngestion()}
              className="px-4 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         hover:border-[#00ff32] disabled:opacity-50 transition-colors"
            >
              Run All
            </button>
            {ingestStatus && (
              <span className={`text-sm font-medium ${
                ingestStatus === 'running' ? 'text-yellow-400' :
                ingestStatus === 'done' ? 'text-green-400' :
                'text-red-400'
              }`}>
                {ingestStatus === 'running' && 'Running...'}
                {ingestStatus === 'done' && 'Done'}
                {ingestStatus === 'error' && 'Error'}
              </span>
            )}
          </div>
        </div>

        {/* Invite form */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Invite User</h2>
          <form onSubmit={handleInvite} className="flex gap-3">
            <label htmlFor="invite-email" className="sr-only">Email address</label>
            <input
              id="invite-email"
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="user@example.com"
              required
              className="flex-1 px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors"
            />
            <button
              type="submit"
              disabled={inviteLoading}
              className="px-4 py-2 bg-[#00ff32] text-black font-semibold rounded
                         hover:bg-[#00cc28] disabled:opacity-50 transition-colors"
            >
              {inviteLoading ? 'Sending...' : 'Send Invite'}
            </button>
          </form>
          {message && <p className="mt-3 text-green-400 text-sm">{message}</p>}
          {error && <p className="mt-3 text-red-400 text-sm">{error}</p>}
        </div>

        {/* Data status */}
        <DataStatusCard />

        {/* Users table */}
        <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#404040]">
                <th className="px-4 py-3 text-left text-sm text-gray-400">Email</th>
                <th className="px-4 py-3 text-left text-sm text-gray-400">Role</th>
                <th className="px-4 py-3 text-left text-sm text-gray-400">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-[#404040] last:border-0">
                  <td className="px-4 py-3 text-white text-sm">{u.email}</td>
                  <td className="px-4 py-3">
                    <label htmlFor={`role-${u.id}`} className="sr-only">Role for {u.email}</label>
                    <select
                      id={`role-${u.id}`}
                      value={u.role}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      className="bg-[#292929] border border-[#404040] rounded px-2 py-1
                                 text-sm text-white focus:outline-none focus:border-[#00ff32]"
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-sm">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
