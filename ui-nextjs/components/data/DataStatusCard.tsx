'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';
import { API_BASE } from '@/lib/api';

interface OverviewData {
  sources: { enabled: number; healthy: number; failing: number };
}

export default function DataStatusCard() {
  const { session, getHeaders } = useAuthHeaders();
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (!session?.access_token) return;

    let cancelled = false;

    async function fetchOverview() {
      try {
        const response = await fetch(`${API_BASE}/api/data/overview`, {
          headers: getHeaders(),
        });
        if (!response.ok) throw new Error('fetch failed');
        const json = await response.json();
        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setHidden(true);
          setLoading(false);
        }
      }
    }

    fetchOverview();
    return () => {
      cancelled = true;
    };
  }, [session?.access_token, getHeaders]);

  if (hidden) return null;

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white mb-1">Data Ingestion</h2>
          {loading ? (
            <p className="text-sm text-gray-400">Loading data status...</p>
          ) : data ? (
            <p className="text-sm text-gray-300">
              <span className="text-[#00ff32] font-medium">{data.sources.healthy}</span> sources healthy
              {data.sources.failing > 0 && (
                <>
                  , <span className="text-red-400 font-medium">{data.sources.failing}</span> failing
                </>
              )}
            </p>
          ) : null}
        </div>
        <Link
          href="/data"
          className="text-sm text-[#00ff32] hover:text-[#00cc28] transition-colors"
        >
          View Dashboard &rarr;
        </Link>
      </div>
    </div>
  );
}
