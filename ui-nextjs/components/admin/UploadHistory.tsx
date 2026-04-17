'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

interface UploadRecord {
  id: string;
  upload_type: string;
  filename?: string;
  title?: string;
  query_text?: string;
  status: 'pending_review' | 'approved' | 'rejected' | 'processing' | 'live';
  reviewer_notes?: string;
  created_at: string;
}

interface UploadHistoryProps {
  uploadType: string;
  refreshKey: number;
}

const STATUS_STYLES: Record<string, string> = {
  pending_review: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  approved: 'bg-green-900 text-green-300 border border-green-700',
  rejected: 'bg-red-900 text-red-300 border border-red-700',
  processing: 'bg-blue-900 text-blue-300 border border-blue-700',
  live: 'bg-emerald-900 text-emerald-300 border border-emerald-600',
};

const STATUS_LABELS: Record<string, string> = {
  pending_review: 'Pending Review',
  approved: 'Approved',
  rejected: 'Rejected',
  processing: 'Processing',
  live: 'Live',
};

function getPreviewText(record: UploadRecord): string {
  if (record.query_text) {
    return record.query_text.length > 80
      ? record.query_text.slice(0, 80) + '...'
      : record.query_text;
  }
  if (record.title) return record.title;
  if (record.filename) return record.filename;
  return `Upload ${record.id.slice(0, 8)}`;
}

export default function UploadHistory({ uploadType, refreshKey }: UploadHistoryProps) {
  const { session } = useAuth();
  const [records, setRecords] = useState<UploadRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `${API_BASE}/api/admin/uploads?upload_type=${encodeURIComponent(uploadType)}`,
        {
          headers: {
            Authorization: `Bearer ${session.access_token}`,
          },
        }
      );
      if (resp.ok) {
        setRecords(await resp.json());
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Failed to load upload history');
      }
    } catch {
      setError('Failed to load upload history');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, uploadType]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshKey]);

  if (loading) {
    return (
      <div className="mt-6 pt-6 border-t border-[#404040]">
        <h3 className="text-sm font-semibold text-gray-400 mb-3">Your Uploads</h3>
        <p className="text-sm text-gray-500">Loading history...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-6 pt-6 border-t border-[#404040]">
        <h3 className="text-sm font-semibold text-gray-400 mb-3">Your Uploads</h3>
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="mt-6 pt-6 border-t border-[#404040]">
      <h3 className="text-sm font-semibold text-gray-400 mb-3">Your Uploads</h3>
      {records.length === 0 ? (
        <p className="text-sm text-gray-500">No uploads yet.</p>
      ) : (
        <ul className="space-y-2">
          {records.map((record) => (
            <li
              key={record.id}
              className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 bg-[#292929] rounded border border-[#404040]"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white truncate">{getPreviewText(record)}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {new Date(record.created_at).toLocaleDateString()}
                </p>
                {record.reviewer_notes && (
                  <p className="text-xs text-gray-400 mt-1 italic">
                    Note: {record.reviewer_notes}
                  </p>
                )}
              </div>
              <span
                className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${
                  STATUS_STYLES[record.status] ?? 'bg-gray-800 text-gray-300'
                }`}
              >
                {STATUS_LABELS[record.status] ?? record.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
