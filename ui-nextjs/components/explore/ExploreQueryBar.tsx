'use client';

import { useState, useCallback, FormEvent, KeyboardEvent } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

interface ExploreQueryBarProps {
  source: string;
  metric: string | null;
  stateFips: string | null;
  race: string | null;
  year: number | null;
  accent: string;
}

interface QueryResponse {
  answer: string;
  data: unknown[] | null;
  visualization_hint: string | null;
}

export default function ExploreQueryBar({
  source,
  metric,
  stateFips,
  race,
  year,
  accent,
}: ExploreQueryBarProps) {
  const { getHeaders } = useAuthHeaders();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = question.trim();
      if (!trimmed || loading) return;

      setLoading(true);
      setAnswer(null);
      setError(null);

      try {
        const resp = await fetch(`${API_BASE}/api/explore/query`, {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
            question: trimmed,
            context: {
              source,
              metric: metric || undefined,
              state_fips: stateFips || undefined,
              race: race || undefined,
              year: year || undefined,
            },
          }),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(
            detail?.detail || `Request failed (${resp.status})`
          );
        }

        const data: QueryResponse = await resp.json();
        setAnswer(data.answer);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Something went wrong');
      } finally {
        setLoading(false);
      }
    },
    [question, loading, source, metric, stateFips, race, year, getHeaders]
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="mt-6 mb-4">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about this data..."
          disabled={loading}
          className="flex-1 bg-[#1a1a1a] text-white text-sm px-4 py-2.5 rounded-lg border border-[#404040] outline-none transition-colors disabled:opacity-50"
          style={{
            borderColor: question ? accent : undefined,
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = accent;
          }}
          onBlur={(e) => {
            if (!question) {
              e.currentTarget.style.borderColor = '#404040';
            }
          }}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="px-4 py-2.5 rounded-lg text-sm font-medium text-white transition-opacity disabled:opacity-40"
          style={{ backgroundColor: accent }}
        >
          {loading ? 'Asking...' : 'Ask'}
        </button>
      </form>

      {loading && (
        <div className="mt-3 px-4 py-3 bg-[#1a1a1a] border border-[#404040] rounded-lg">
          <span className="text-sm text-gray-400">
            Analyzing<span className="animate-pulse">...</span>
          </span>
        </div>
      )}

      {answer && !loading && (
        <div
          className="mt-3 px-4 py-3 rounded-lg border text-sm text-gray-200 leading-relaxed"
          style={{
            backgroundColor: '#1a1a1a',
            borderColor: `${accent}40`,
          }}
        >
          {answer}
        </div>
      )}

      {error && !loading && (
        <div className="mt-3 px-4 py-3 bg-red-900/20 border border-red-800/50 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}
