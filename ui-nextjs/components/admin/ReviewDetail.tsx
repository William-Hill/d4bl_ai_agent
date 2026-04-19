'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import type { UploadRecord } from './upload-types';

interface ReviewDetailProps {
  upload: UploadRecord;
  onReviewed: () => void;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null) return 'Unknown';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ReviewDetail({ upload, onReviewed }: ReviewDetailProps) {
  const { session } = useAuth();
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleReview = async (action: 'approve' | 'reject') => {
    if (action === 'reject' && !notes.trim()) {
      setError('Reviewer notes are required when rejecting an upload.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const resp = await fetch(`${API_BASE}/api/admin/uploads/${upload.id}/review`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ action, notes: notes.trim() || null }),
      });

      if (resp.ok) {
        onReviewed();
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || `Failed to ${action} upload.`);
      }
    } catch {
      setError(`Failed to ${action} upload. Please check your connection.`);
    } finally {
      setLoading(false);
    }
  };

  const mapping = upload.metadata?.mapping as Record<string, string | null> | undefined;
  const previewRows = upload.metadata?.preview_rows as Array<Record<string, unknown>> | undefined;
  const rowCount = upload.metadata?.row_count as number | undefined;
  const isDatasource = upload.upload_type === 'datasource';

  const HIDE_GENERIC_KEYS = new Set(['mapping', 'preview_rows', 'row_count', 'dropped_counts', 'full_text', 'preview_text']);

  const metadataEntries = upload.metadata
    ? Object.entries(upload.metadata).filter(
        ([k, v]) => v !== null && v !== undefined && v !== '' && !HIDE_GENERIC_KEYS.has(k),
      )
    : [];

  return (
    <div className="bg-[#222] border border-[#404040] rounded-lg p-4 mt-2 space-y-4">
      {/* Upload info grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-0.5">Uploader</p>
          <p className="text-gray-300">
            {upload.uploader_name || <span className="text-gray-500 italic">No name</span>}
          </p>
          <p className="text-gray-400 text-xs">{upload.uploader_email}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-0.5">Type</p>
          <p className="text-gray-300">{upload.upload_type}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-0.5">Filename</p>
          <p className="text-gray-300 break-all">{upload.original_filename}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-0.5">File Size</p>
          <p className="text-gray-300">{formatBytes(upload.file_size_bytes)}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-0.5">Submitted</p>
          <p className="text-gray-300">{new Date(upload.created_at).toLocaleString()}</p>
        </div>
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-0.5">Status</p>
          <p className="text-gray-300">{upload.status}</p>
        </div>
      </div>

      {isDatasource && mapping && (
        <div className="space-y-3">
          <div>
            <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Column mapping</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              <div><span className="text-gray-500">geo:</span> <span className="text-gray-200">{mapping.geo_column}</span></div>
              <div><span className="text-gray-500">value:</span> <span className="text-gray-200">{mapping.metric_value_column}</span></div>
              <div><span className="text-gray-500">metric name:</span> <span className="text-gray-200">{mapping.metric_name}</span></div>
              <div><span className="text-gray-500">race:</span> <span className="text-gray-200">{mapping.race_column ?? <em>(none)</em>}</span></div>
              <div><span className="text-gray-500">year:</span> <span className="text-gray-200">{mapping.year_column ?? <em>(uses data_year)</em>}</span></div>
            </div>
          </div>
          <div className="text-sm text-gray-400">
            {rowCount ?? 0} rows · geographic level: {String(upload.metadata?.geographic_level ?? '')} · data year: {String(upload.metadata?.data_year ?? '')}
          </div>
          {previewRows && previewRows.length > 0 && (
            <div>
              <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Preview (first {previewRows.length})</p>
              <div className="overflow-x-auto">
                <table className="text-xs text-gray-300 border border-[#404040]">
                  <thead className="bg-[#292929]">
                    <tr>
                      <th className="px-2 py-1 text-left">state_fips</th>
                      <th className="px-2 py-1 text-left">race</th>
                      <th className="px-2 py-1 text-left">year</th>
                      <th className="px-2 py-1 text-left">value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, i) => (
                      <tr key={i} className="border-t border-[#404040]">
                        <td className="px-2 py-1">{String(row.state_fips ?? '')}</td>
                        <td className="px-2 py-1">{row.race == null ? '—' : String(row.race)}</td>
                        <td className="px-2 py-1">{String(row.year ?? '')}</td>
                        <td className="px-2 py-1">{String(row.value ?? '')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Metadata key-value pairs */}
      {metadataEntries.length > 0 && (
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide mb-2">Metadata</p>
          <div className="bg-[#292929] border border-[#404040] rounded p-3 space-y-1.5">
            {metadataEntries.map(([key, value]) => (
              <div key={key} className="flex gap-3 text-sm">
                <span className="text-gray-400 min-w-[120px] flex-shrink-0 font-mono text-xs">
                  {key}
                </span>
                <span className="text-gray-300 break-all">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reviewer notes */}
      <div>
        <label htmlFor={`notes-${upload.id}`} className="block text-sm font-medium text-gray-300 mb-1">
          Reviewer Notes{' '}
          <span className="text-gray-500 font-normal">(required for rejection)</span>
        </label>
        <textarea
          id={`notes-${upload.id}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Add notes about your decision..."
          className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                     focus:outline-none focus:border-[#00ff32] transition-colors text-sm resize-none"
        />
      </div>

      {/* Error display */}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          type="button"
          disabled={loading}
          onClick={() => handleReview('approve')}
          className="px-4 py-2 bg-[#00ff32] text-black font-semibold rounded
                     hover:bg-[#00cc28] disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Processing...' : 'Approve'}
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => handleReview('reject')}
          className="px-4 py-2 bg-red-600 text-white font-semibold rounded
                     hover:bg-red-700 disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Processing...' : 'Reject'}
        </button>
      </div>
    </div>
  );
}
