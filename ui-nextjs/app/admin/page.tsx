'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
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
    if (isAdmin) fetchUsers();
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
          <a
            href={`${process.env.NEXT_PUBLIC_DAGSTER_URL || 'https://d4bl-dagster-web.fly.dev'}/auth/set-token?token=${session?.access_token}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#292929] border border-[#404040]
                       rounded text-white hover:border-[#00ff32] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Open Dagster Pipelines
          </a>
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
