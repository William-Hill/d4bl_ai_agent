'use client';

import { useEffect, useMemo, useState } from 'react';
import { EvaluationResultItem, getEvaluations } from '@/lib/api';

interface EvaluationsPanelProps {
  defaultLimit?: number;
  jobId?: string | null;  // Filter evaluations by job_id (maps to trace_id)
}

export default function EvaluationsPanel({ defaultLimit = 50, jobId }: EvaluationsPanelProps) {
  const [evaluations, setEvaluations] = useState<EvaluationResultItem[]>([]);
  const [traceFilter, setTraceFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEvaluations = async (trace_id?: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await getEvaluations({
        job_id: jobId || undefined,  // Use jobId prop if provided
        trace_id: trace_id?.trim() || undefined,
        limit: defaultLimit,
      });
      setEvaluations(data);
    } catch (err: any) {
      console.error('Failed to fetch evaluations', err);
      setError(err.message || 'Failed to fetch evaluations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvaluations();
  }, [jobId]);  // Refetch when jobId changes

  const grouped = useMemo(() => {
    const map: Record<string, EvaluationResultItem[]> = {};
    evaluations.forEach((item) => {
      const key = item.eval_name || 'evaluation';
      if (!map[key]) map[key] = [];
      map[key].push(item);
    });
    return map;
  }, [evaluations]);

  return (
    <div className="bg-[#333333] border border-[#404040] rounded-lg p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">LLM Evaluations</h2>
          <p className="text-gray-400 text-sm mt-1">
            {jobId 
              ? `Evaluations for job ${jobId.slice(0, 8)}...`
              : 'Latest hallucination, bias, and reference checks logged in Phoenix & Postgres.'
            }
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            placeholder="Filter by trace ID"
            value={traceFilter}
            onChange={(e) => setTraceFilter(e.target.value)}
            className="bg-[#1a1a1a] border border-[#404040] rounded-md px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-[#00ff32]"
          />
          <button
            onClick={() => fetchEvaluations(traceFilter)}
            className="bg-[#00ff32] hover:bg-[#00cc28] text-black font-semibold px-4 py-2 rounded-md text-sm transition-colors"
            disabled={loading}
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-[#2a1a1a] border border-[#803a3a] text-red-200 rounded-md px-3 py-2 text-sm mb-4">
          {error}
        </div>
      )}

      {evaluations.length === 0 && !loading && (
        <p className="text-gray-400 text-sm">No evaluation results found yet.</p>
      )}

      <div className="space-y-6">
        {Object.entries(grouped).map(([name, rows]) => (
          <div key={name} className="border border-[#404040] rounded-lg overflow-hidden">
            <div className="bg-[#1f1f1f] px-4 py-3 border-b border-[#404040] flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white capitalize">{name}</h3>
                <p className="text-gray-400 text-xs">{rows.length} annotations</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-[#404040] text-sm">
                <thead className="bg-[#1a1a1a]">
                  <tr>
                    <th className="px-4 py-2 text-left text-gray-400 font-medium">Span ID</th>
                    <th className="px-4 py-2 text-left text-gray-400 font-medium">Trace ID</th>
                    <th className="px-4 py-2 text-left text-gray-400 font-medium">Label</th>
                    <th className="px-4 py-2 text-left text-gray-400 font-medium">Score</th>
                    <th className="px-4 py-2 text-left text-gray-400 font-medium">Explanation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#404040]">
                  {rows.map((row) => (
                    <tr key={row.id} className="hover:bg-[#2a2a2a] transition-colors">
                      <td className="px-4 py-3 text-gray-200 font-mono text-xs">{row.span_id}</td>
                      <td className="px-4 py-3 text-gray-300 font-mono text-xs">
                        {row.trace_id || '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-1 rounded text-xs font-semibold ${
                            row.label === 'BIASED' || row.label === 'UNGROUNDED' ? 'bg-[#402424] text-red-200' : 'bg-[#1f3524] text-green-200'
                          }`}
                        >
                          {row.label || 'n/a'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-200">{row.score ?? '—'}</td>
                      <td className="px-4 py-3 max-w-xl text-gray-300">
                        {row.explanation ? row.explanation.slice(0, 240) : '—'}
                        {row.explanation && row.explanation.length > 240 && '…'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


