'use client';

import { useCallback, useEffect, useState } from 'react';
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

interface StateSummaryInsight {
  state_fips: string;
  state_name: string;
  metric: string;
  value: number;
  national_average: number;
  national_rank: number;
  national_rank_total: number;
  percentile: number;
  racial_gap: RacialGap | null;
  year: number;
  source: string;
}

interface Props {
  source: string;
  stateFips: string;
  metric: string;
  accent?: string;
}

export default function StateAnnotation({ source, stateFips, metric, accent = '#00ff32' }: Props) {
  const { session, getHeaders } = useAuthHeaders();
  const [data, setData] = useState<StateSummaryInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const fetchSummary = useCallback(async (signal: AbortSignal) => {
    if (!session?.access_token || !source || !stateFips || !metric) return;

    setLoading(true);
    setError(false);

    const params = new URLSearchParams({
      source,
      state_fips: stateFips,
      metric,
    });

    try {
      const res = await fetch(`${API_BASE}/api/explore/state-summary?${params}`, {
        signal,
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = (await res.json()) as StateSummaryInsight;
      if (!signal.aborted) {
        setData(result);
        setLoading(false);
      }
    } catch (err) {
      if (signal.aborted) return;
      setError(true);
      setLoading(false);
      if (!(err instanceof Error && err.message.includes('404'))) {
        console.error('StateAnnotation fetch error:', err);
      }
    }
  }, [session?.access_token, source, stateFips, metric, getHeaders]);

  useEffect(() => {
    const controller = new AbortController();
    fetchSummary(controller.signal);
    return () => controller.abort();
  }, [fetchSummary]);

  // Skeleton shimmer while loading
  if (loading) {
    return (
      <div className="flex items-center gap-3 mb-2">
        <div className="h-4 w-28 bg-[#333] rounded animate-pulse" />
        <div className="h-4 w-20 bg-[#333] rounded animate-pulse" />
        <div className="h-4 w-32 bg-[#333] rounded animate-pulse" />
      </div>
    );
  }

  // Don't render anything on error or no data
  if (error || !data) return null;

  const ordinalSuffix = (n: number): string => {
    const s = ['th', 'st', 'nd', 'rd'];
    const v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };

  return (
    <div className="flex flex-wrap items-center gap-2 mb-2 text-xs text-gray-400">
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded border"
        style={{
          borderColor: `${accent}4d`,
          backgroundColor: `${accent}0d`,
        }}
      >
        <span className="font-medium" style={{ color: accent }}>
          #{data.national_rank}
        </span>
        <span>of {data.national_rank_total} states</span>
      </span>

      <span className="text-gray-600">|</span>

      <span>{ordinalSuffix(Math.round(data.percentile))} percentile</span>

      {data.racial_gap && (
        <>
          <span className="text-gray-600">|</span>
          <span>
            {data.racial_gap.max_ratio.toFixed(1)}x gap{' '}
            <span className="text-gray-500">({data.racial_gap.max_ratio_label})</span>
          </span>
        </>
      )}
    </div>
  );
}
