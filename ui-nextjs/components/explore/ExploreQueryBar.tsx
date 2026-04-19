'use client';

import { useState, useCallback, useEffect, FormEvent, KeyboardEvent } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

interface ExampleQueryTemplate {
  id: string;
  query_text: string;
  description: string;
  summary_format: string;
}

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
  const { session, getHeaders } = useAuthHeaders();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<ExampleQueryTemplate[]>([]);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    let cancelled = false;

    async function loadTemplates() {
      try {
        const resp = await fetch(`${API_BASE}/api/explore/example-query-templates`, {
          headers: getHeaders(),
        });
        if (!resp.ok) return;
        const data = (await resp.json()) as ExampleQueryTemplate[];
        if (!cancelled && Array.isArray(data)) setTemplates(data);
      } catch {
        /* ignore — templates are optional */
      }
    }

    void loadTemplates();
    return () => {
      cancelled = true;
    };
  }, [session?.access_token, getHeaders]);

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
      {templates.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-gray-500 mb-2">Try a contributor example</p>
          <div className="flex flex-wrap gap-2">
            {templates.map((t) => {
              const label =
                t.query_text.length > 72 ? `${t.query_text.slice(0, 70)}…` : t.query_text;
              return (
                <button
                  key={t.id}
                  type="button"
                  title={t.description ? `${t.query_text}\n\n${t.description}` : t.query_text}
                  onClick={() => setQuestion(t.query_text)}
                  className="text-left text-xs px-2.5 py-1.5 rounded-md border border-[#404040] bg-[#141414] text-gray-200 hover:border-gray-500 transition-colors max-w-full"
                >
                  <span className="line-clamp-2">{label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
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
