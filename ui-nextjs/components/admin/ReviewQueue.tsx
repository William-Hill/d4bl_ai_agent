'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import ReviewDetail from './ReviewDetail';
import type { UploadRecord } from './upload-types';

type UploadTypeFilter = 'all' | 'datasource' | 'document' | 'query' | 'feature_request';
type StatusFilter = 'pending_review' | 'processing_failed';

const TYPE_LABELS: Record<string, string> = {
  datasource: 'Data Source',
  document: 'Document',
  query: 'Example Query',
  feature_request: 'Feature Request',
};

const TYPE_OPTIONS: { value: UploadTypeFilter; label: string }[] = [
  { value: 'all', label: 'All Types' },
  { value: 'datasource', label: 'Data Sources' },
  { value: 'document', label: 'Documents' },
  { value: 'query', label: 'Example Queries' },
  { value: 'feature_request', label: 'Feature Requests' },
];

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'pending_review', label: 'Pending Review' },
  { value: 'processing_failed', label: 'Processing Failures' },
];

export default function ReviewQueue() {
  const { session } = useAuth();
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [typeFilter, setTypeFilter] = useState<UploadTypeFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending_review');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<{ id: string; message: string } | null>(null);

  const fetchUploads = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ status: statusFilter });
      if (typeFilter !== 'all') params.append('upload_type', typeFilter);

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
  }, [session?.access_token, typeFilter, statusFilter]);

  useEffect(() => {
    fetchUploads();
  }, [fetchUploads]);

  const handleReviewed = (id: string) => {
    setExpandedId(null);
    setUploads((prev) => prev.filter((u) => u.id !== id));
  };

  const handleRetry = async (id: string) => {
    if (!session?.access_token) return;
    setRetryingId(id);
    setRetryError(null);
    try {
      const resp = await fetch(
        `${API_BASE}/api/admin/uploads/${id}/retry-processing`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${session.access_token}` },
        }
      );
      if (resp.ok) {
        const data = await resp.json();
        if (data.status === 'indexed') {
          setUploads((prev) => prev.filter((u) => u.id !== id));
        } else {
          setRetryError({ id, message: data.error || 'Retry failed.' });
        }
      } else {
        const data = await resp.json().catch(() => ({}));
        setRetryError({ id, message: data.detail || 'Retry failed.' });
      }
    } catch {
      setRetryError({ id, message: 'Network error during retry.' });
    } finally {
      setRetryingId(null);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const isFailureView = statusFilter === 'processing_failed';

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white">Review Queue</h2>
          {!loading && (
            <span className="text-xs bg-[#404040] text-gray-300 px-2 py-1 rounded">
              {uploads.length} {isFailureView ? 'failed' : 'pending'}
            </span>
          )}
        </div>

        <div className="flex gap-2">
          <div>
            <label htmlFor="review-status-filter" className="sr-only">Filter by status</label>
            <select
              id="review-status-filter"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as StatusFilter);
                setExpandedId(null);
              }}
              className="bg-[#292929] border border-[#404040] rounded px-3 py-1.5 text-sm text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="review-type-filter" className="sr-only">Filter by type</label>
            <select
              id="review-type-filter"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value as UploadTypeFilter);
                setExpandedId(null);
              }}
              className="bg-[#292929] border border-[#404040] rounded px-3 py-1.5 text-sm text-white
                         focus:outline-none focus:border-[#00ff32] transition-colors"
            >
              {TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {loading && (
        <p className="text-sm text-gray-400 py-4">Loading...</p>
      )}

      {error && !loading && (
        <p className="text-sm text-red-400 py-2">{error}</p>
      )}

      {!loading && !error && uploads.length === 0 && (
        <p className="text-sm text-gray-500 py-4">
          {isFailureView ? 'No failed uploads.' : 'No uploads pending review.'}
        </p>
      )}

      {!loading && uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((upload) => {
            const isExpanded = expandedId === upload.id;
            const typeLabel = TYPE_LABELS[upload.upload_type] ?? upload.upload_type;

            return (
              <div key={upload.id} className="border border-[#404040] rounded-lg overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggleExpand(upload.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 bg-[#1a1a1a] hover:bg-[#222]
                             transition-colors text-left"
                  aria-expanded={isExpanded}
                >
                  <span className="text-xs bg-[#404040] text-gray-300 px-2 py-1 rounded flex-shrink-0">
                    {typeLabel}
                  </span>

                  <span className="flex-1 min-w-0">
                    <span className="text-white text-sm font-medium truncate block">
                      {upload.original_filename ||
                        (typeof upload.metadata?.title === 'string' ? upload.metadata.title : null) ||
                        (typeof upload.metadata?.source_name === 'string' ? upload.metadata.source_name : null) ||
                        (typeof upload.metadata?.query_text === 'string' ? upload.metadata.query_text.slice(0, 60) : null) ||
                        'Upload'}
                    </span>
                    <span className="text-gray-400 text-xs">
                      {upload.uploader_name
                        ? `${upload.uploader_name} · ${upload.uploader_email ?? ''}`
                        : upload.uploader_email ?? ''}
                    </span>
                  </span>

                  <span className="text-gray-500 text-xs flex-shrink-0 hidden sm:block">
                    {upload.created_at
                      ? new Date(upload.created_at).toLocaleDateString()
                      : '—'}
                  </span>

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

                {isExpanded && (
                  <div className="px-4 pb-4">
                    {isFailureView ? (
                      <div className="bg-[#222] border border-[#404040] rounded-lg p-4 mt-2 space-y-3">
                        {upload.reviewer_notes && (
                          <div>
                            <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">
                              Failure reason
                            </p>
                            <p className="text-red-400 text-sm whitespace-pre-wrap break-words">
                              {upload.reviewer_notes}
                            </p>
                          </div>
                        )}
                        {retryError?.id === upload.id && (
                          <p className="text-sm text-red-400">{retryError.message}</p>
                        )}
                        <button
                          type="button"
                          disabled={retryingId === upload.id}
                          onClick={() => handleRetry(upload.id)}
                          className="px-4 py-2 bg-[#00ff32] text-black font-semibold rounded
                                     hover:bg-[#00cc28] disabled:opacity-50 transition-colors text-sm"
                        >
                          {retryingId === upload.id ? 'Retrying...' : 'Retry processing'}
                        </button>
                      </div>
                    ) : (
                      <ReviewDetail
                        upload={upload}
                        onReviewed={() => handleReviewed(upload.id)}
                      />
                    )}
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
