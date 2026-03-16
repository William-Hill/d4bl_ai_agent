'use client';

import { useState } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

interface RacialGapGroup {
  race: string;
  value: number;
}

interface RacialGap {
  groups: RacialGapGroup[];
  max_ratio: number;
  max_ratio_label: string;
}

interface ExplainResponse {
  narrative: string;
  methodology_note: string;
  caveats: string[];
  generated_at: string;
}

interface Props {
  source: string;
  metric: string;
  stateFips: string;
  stateName: string;
  value: number;
  nationalAverage: number;
  year: number;
  accent?: string;
  racialGap?: RacialGap | null;
}

export default function ExplainPanel({
  source,
  metric,
  stateFips,
  stateName,
  value,
  nationalAverage,
  year,
  accent = '#00ff32',
  racialGap,
}: Props) {
  const { getHeaders } = useAuthHeaders();
  const [data, setData] = useState<ExplainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState(true);

  const fetchExplanation = async () => {
    setLoading(true);
    setError(false);
    setData(null);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);

    try {
      const res = await fetch(`${API_BASE}/api/explore/explain`, {
        method: 'POST',
        signal: controller.signal,
        headers: getHeaders(),
        body: JSON.stringify({
          source,
          metric,
          state_fips: stateFips,
          state_name: stateName,
          value,
          national_average: nationalAverage,
          racial_gap: racialGap ?? null,
          year,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = (await res.json()) as ExplainResponse;
      setData(result);
      setExpanded(true);
    } catch {
      setError(true);
    } finally {
      clearTimeout(timeout);
      setLoading(false);
    }
  };

  // Loading shimmer
  if (loading) {
    return (
      <div className="mb-4 p-4 bg-[#1a1a1a] border border-[#404040] rounded-lg space-y-3">
        <div className="h-4 w-32 bg-[#333] rounded animate-pulse" />
        <div className="h-3 w-full bg-[#333] rounded animate-pulse" />
        <div className="h-3 w-5/6 bg-[#333] rounded animate-pulse" />
        <div className="h-3 w-4/6 bg-[#333] rounded animate-pulse" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="mb-4 flex items-center gap-3">
        <span className="text-xs text-gray-500">
          AI analysis unavailable &mdash; check that Ollama is running
        </span>
        <button
          onClick={fetchExplanation}
          className="text-xs px-2 py-1 rounded border border-[#555] text-gray-400 hover:text-white hover:border-gray-400 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  // Success: collapsible panel
  if (data) {
    return (
      <div className="mb-4">
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex items-center gap-2 text-xs text-gray-400 hover:text-white transition-colors mb-1"
        >
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold"
            style={{ backgroundColor: `${accent}1a`, color: accent }}
          >
            &#10022; AI Analysis
          </span>
          <span className="text-gray-600">{expanded ? '\u25B2' : '\u25BC'}</span>
        </button>

        {expanded && (
          <div className="p-4 bg-[#1a1a1a] border border-[#404040] rounded-lg space-y-3">
            <p className="text-sm text-gray-300 leading-relaxed">
              {data.narrative}
            </p>

            {data.methodology_note && (
              <p className="text-xs text-gray-500 italic">
                {data.methodology_note}
              </p>
            )}

            {data.caveats.length > 0 && (
              <ul className="list-disc list-inside space-y-1">
                {data.caveats.map((caveat, i) => (
                  <li key={i} className="text-[11px] text-gray-500">
                    {caveat}
                  </li>
                ))}
              </ul>
            )}

            <p className="text-[10px] text-gray-600">
              Generated {new Date(data.generated_at).toLocaleString()}
            </p>
          </div>
        )}
      </div>
    );
  }

  // Default: show Explain button
  return (
    <div className="mb-4">
      <button
        onClick={fetchExplanation}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors border"
        style={{
          borderColor: `${accent}4d`,
          backgroundColor: `${accent}0d`,
          color: accent,
        }}
      >
        &#10022; Explain
      </button>
    </div>
  );
}
