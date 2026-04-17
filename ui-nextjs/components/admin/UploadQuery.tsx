'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';
import UploadHistory from './UploadHistory';

export default function UploadQuery() {
  const { session } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [queryText, setQueryText] = useState('');
  const [summaryFormat, setSummaryFormat] = useState('detailed');
  const [description, setDescription] = useState('');
  const [curatedAnswer, setCuratedAnswer] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session?.access_token) return;

    setLoading(true);
    setSuccess(null);
    setError(null);

    try {
      const body: Record<string, string> = {
        query_text: queryText,
        summary_format: summaryFormat,
        description,
      };
      if (curatedAnswer) body.curated_answer = curatedAnswer;

      const resp = await fetch(`${API_BASE}/api/admin/uploads/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(body),
      });

      if (resp.ok) {
        setSuccess('Query submitted successfully. It will be reviewed before being added to the example set.');
        setQueryText('');
        setSummaryFormat('detailed');
        setDescription('');
        setCuratedAnswer('');
        setRefreshKey((k) => k + 1);
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Submission failed. Please try again.');
      }
    } catch {
      setError('Submission failed. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Query text */}
        <div>
          <label htmlFor="q-query-text" className="block text-sm font-medium text-gray-300 mb-1">
            Query Text <span className="text-red-400">*</span>
          </label>
          <textarea
            id="q-query-text"
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            required
            maxLength={2000}
            rows={4}
            placeholder="e.g. What are the racial disparities in maternal mortality rates across US states?"
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm resize-none"
          />
          <p className="mt-1 text-xs text-gray-500 text-right">
            {queryText.length} / 2000
          </p>
        </div>

        {/* Summary format */}
        <div>
          <label htmlFor="q-summary-format" className="block text-sm font-medium text-gray-300 mb-1">
            Summary Format <span className="text-red-400">*</span>
          </label>
          <select
            id="q-summary-format"
            value={summaryFormat}
            onChange={(e) => setSummaryFormat(e.target.value)}
            required
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm"
          >
            <option value="detailed">Detailed</option>
            <option value="brief">Brief</option>
          </select>
        </div>

        {/* Description */}
        <div>
          <label htmlFor="q-description" className="block text-sm font-medium text-gray-300 mb-1">
            Description <span className="text-red-400">*</span>
          </label>
          <textarea
            id="q-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
            rows={3}
            placeholder="Why is this a good example query? What context or skills does it test?"
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm resize-none"
          />
        </div>

        {/* Curated answer (optional) */}
        <div>
          <label htmlFor="q-curated-answer" className="block text-sm font-medium text-gray-300 mb-1">
            Curated Answer <span className="text-gray-500">(optional)</span>
          </label>
          <textarea
            id="q-curated-answer"
            value={curatedAnswer}
            onChange={(e) => setCuratedAnswer(e.target.value)}
            rows={5}
            placeholder="Provide an ideal or reference answer for this query, if available."
            className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white
                       focus:outline-none focus:border-[#00ff32] transition-colors text-sm resize-none"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="px-5 py-2 bg-[#00ff32] text-black font-semibold rounded
                     hover:bg-[#00cc28] disabled:opacity-50 transition-colors text-sm"
        >
          {loading ? 'Submitting...' : 'Submit Query'}
        </button>

        {success && <p className="text-sm text-green-400">{success}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </form>

      <UploadHistory uploadType="query" refreshKey={refreshKey} />
    </div>
  );
}
