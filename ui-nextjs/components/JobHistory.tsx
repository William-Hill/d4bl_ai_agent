'use client';

import { useState, useEffect } from 'react';
import { getJobHistory, JobStatus } from '@/lib/api';

interface JobHistoryProps {
  onSelectJob?: (job: JobStatus) => void;
}

export default function JobHistory({ onSelectJob }: JobHistoryProps) {
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const pageSize = 10;

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getJobHistory(page, pageSize, statusFilter || undefined);
      setJobs(response.jobs);
      setTotal(response.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load job history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, [page, statusFilter]);

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch {
      return dateString;
    }
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = 'px-2 py-1 rounded text-xs font-semibold';
    switch (status) {
      case 'completed':
        return `${baseClasses} bg-green-900/30 text-green-400 border border-green-700`;
      case 'running':
        return `${baseClasses} bg-blue-900/30 text-blue-400 border border-blue-700`;
      case 'error':
        return `${baseClasses} bg-red-900/30 text-red-400 border border-red-700`;
      case 'pending':
        return `${baseClasses} bg-yellow-900/30 text-yellow-400 border border-yellow-700`;
      default:
        return `${baseClasses} bg-gray-900/30 text-gray-400 border border-gray-700`;
    }
  };

  const truncateQuery = (query: string, maxLength: number = 80) => {
    if (query.length <= maxLength) return query;
    return query.substring(0, maxLength) + '...';
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={loadHistory}
          disabled={loading}
          className="px-3 py-1.5 bg-[#404040] hover:bg-[#505050] text-white rounded-md text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Status Filter */}
      <div className="mb-4 flex gap-2 flex-wrap">
        <button
          onClick={() => setStatusFilter('')}
          className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
            statusFilter === ''
              ? 'bg-[#00ff32] text-black'
              : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setStatusFilter('completed')}
          className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
            statusFilter === 'completed'
              ? 'bg-[#00ff32] text-black'
              : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
          }`}
        >
          Completed
        </button>
        <button
          onClick={() => setStatusFilter('running')}
          className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
            statusFilter === 'running'
              ? 'bg-[#00ff32] text-black'
              : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
          }`}
        >
          Running
        </button>
        <button
          onClick={() => setStatusFilter('error')}
          className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
            statusFilter === 'error'
              ? 'bg-[#00ff32] text-black'
              : 'bg-[#404040] text-gray-300 hover:bg-[#505050]'
          }`}
        >
          Error
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/20 border border-red-700 rounded text-red-400 text-sm">
          {error}
        </div>
      )}

      {loading && jobs.length === 0 ? (
        <div className="text-center py-8 text-gray-400">Loading history...</div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          No jobs found. Start a new research query to see history here.
        </div>
      ) : (
        <>
          <div className="space-y-2 mb-4">
            {jobs.map((job) => (
              <div
                key={job.job_id}
                className="bg-[#292929] border border-[#404040] rounded-lg p-3 hover:border-[#00ff32]/50 transition-colors cursor-pointer"
                onClick={() => onSelectJob?.(job)}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <span className={getStatusBadge(job.status)}>
                      {job.status.toUpperCase()}
                    </span>
                    {job.summary_format && (
                      <span className="text-xs text-gray-500">
                        {job.summary_format}
                      </span>
                    )}
                  </div>
                  <p className="text-white text-sm font-medium line-clamp-2">
                    {job.query ? truncateQuery(job.query, 60) : 'No query'}
                  </p>
                  <div className="flex flex-col gap-1 text-xs text-gray-400">
                    <span>Created: {formatDate(job.created_at)}</span>
                    {job.completed_at && (
                      <span>Completed: {formatDate(job.completed_at)}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex flex-col gap-2 pt-4 border-t border-[#404040]">
              <div className="text-xs text-gray-400 text-center">
                Page {page} of {totalPages} ({total} total)
              </div>
              <div className="flex gap-2 justify-center">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1 || loading}
                  className="px-3 py-1 bg-[#404040] hover:bg-[#505050] text-white rounded text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages || loading}
                  className="px-3 py-1 bg-[#404040] hover:bg-[#505050] text-white rounded text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

