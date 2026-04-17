'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import ReviewDetail from './ReviewDetail';

interface Upload {
  id: string;
  upload_type: string;
  status: string;
  original_filename: string;
  file_size_bytes: number | null;
  metadata: Record<string, unknown> | null;
  uploader_email: string;
  uploader_name: string | null;
  created_at: string;
}

type UploadTypeFilter = 'all' | 'datasource' | 'document' | 'query' | 'feature_request';

const TYPE_LABELS: Record<string, string> = {
  datasource: 'Data Source',
  document: 'Document',
  query: 'Example Query',
  feature_request: 'Feature Request',
};

const FILTER_OPTIONS: { value: UploadTypeFilter; label: string }[] = [
  { value: 'all', label: 'All Types' },
  { value: 'datasource', label: 'Data Sources' },
  { value: 'document', label: 'Documents' },
  { value: 'query', label: 'Example Queries' },
  { value: 'feature_request', label: 'Feature Requests' },
];

export default function ReviewQueue() {
  const { session } = useAuth();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [filter, setFilter] = useState<UploadTypeFilter>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchUploads = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ status: 'pending_review' });
      if (filter !== 'all') params.append('upload_type', filter);

      const resp = await fetch(`${API_BASE}/api/admin/uploads?${params.toString()}`, {
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });

      if (resp.ok) {
        const data = await resp.json();
        setUploads(Array.isArray(data) ? data : data.uploads ?? []);
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Failed to load review queue.');
      }
    } catch {
      setError('Failed to load review queue. Please check your connection.');
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, filter]);

  useEffect(() => {
    fetchUploads();
  }, [fetchUploads]);

  const handleReviewed = (id: string) => {
    setExpandedId(null);
    fetchUploads();
    // Optimistically remove the reviewed item
    setUploads((prev) => prev.filter((u) => u.id !== id));
  };

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white">Review Queue</h2>
          {!loading && (
            <span className="text-xs bg-[#404040] text-gray-300 px-2 py-1 rounded">
              {uploads.length} pending
            </span>
          )}
        </div>

        {/* Filter dropdown */}
        <div>
          <label htmlFor="review-type-filter" className="sr-only">Filter by type</label>
          <select
            id="review-type-filter"
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value as UploadTypeFilter);
              setExpandedId(null);
            }}
            className="bg-[#292929] border border-[#404040] rounded px-3 py-1.5 text-sm text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors"
          >
            {FILTER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <p className="text-sm text-gray-400 py-4">Loading...</p>
      )}

      {/* Error state */}
      {error && !loading && (
        <p className="text-sm text-red-400 py-2">{error}</p>
      )}

      {/* Empty state */}
      {!loading && !error && uploads.length === 0 && (
        <p className="text-sm text-gray-500 py-4">No uploads pending review.</p>
      )}

      {/* Upload rows */}
      {!loading && uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((upload) => {
            const isExpanded = expandedId === upload.id;
            const typeLabel = TYPE_LABELS[upload.upload_type] ?? upload.upload_type;

            return (
              <div key={upload.id} className="border border-[#404040] rounded-lg overflow-hidden">
                {/* Row header */}
                <button
                  type="button"
                  onClick={() => toggleExpand(upload.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 bg-[#1a1a1a] hover:bg-[#222]
                             transition-colors text-left"
                  aria-expanded={isExpanded}
                >
                  {/* Type badge */}
                  <span className="text-xs bg-[#404040] text-gray-300 px-2 py-1 rounded flex-shrink-0">
                    {typeLabel}
                  </span>

                  {/* Title / filename */}
                  <span className="flex-1 min-w-0">
                    <span className="text-white text-sm font-medium truncate block">
                      {upload.original_filename}
                    </span>
                    <span className="text-gray-400 text-xs">
                      {upload.uploader_name
                        ? `${upload.uploader_name} · ${upload.uploader_email}`
                        : upload.uploader_email}
                    </span>
                  </span>

                  {/* Date */}
                  <span className="text-gray-500 text-xs flex-shrink-0 hidden sm:block">
                    {new Date(upload.created_at).toLocaleDateString()}
                  </span>

                  {/* Expand/collapse arrow */}
                  <svg
                    className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Expandable detail panel */}
                {isExpanded && (
                  <div className="px-4 pb-4">
                    <ReviewDetail
                      upload={upload}
                      onReviewed={() => handleReviewed(upload.id)}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
