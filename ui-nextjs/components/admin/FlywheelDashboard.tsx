'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '@/lib/api';
import type { FlywheelData } from './flywheel-types';
import FlywheelDiagram from './FlywheelDiagram';
import FlywheelTimeSeries from './FlywheelTimeSeries';
import CorpusBreakdown from './CorpusBreakdown';
import ModelVersionTable from './ModelVersionTable';

interface FlywheelDashboardProps {
  accessToken: string | undefined;
}

export default function FlywheelDashboard({ accessToken }: FlywheelDashboardProps) {
  const [data, setData] = useState<FlywheelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/admin/flywheel-metrics`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });
      if (response.ok) {
        setData(await response.json());
      } else {
        const body = await response.json().catch(() => ({}));
        setError(body.detail || 'Failed to load flywheel metrics');
      }
    } catch {
      setError('Failed to load flywheel metrics');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 mb-8">
      <h2 className="text-lg font-semibold text-white mb-6">D4BL Data Flywheel</h2>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded px-4 py-3 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-gray-400 text-sm">Loading flywheel metrics...</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <FlywheelDiagram />
            <FlywheelTimeSeries
              timeSeries={data?.time_series ?? {
                corpus_diversity: [],
                model_accuracy: [],
                research_quality: [],
              }}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CorpusBreakdown contentTypes={data?.corpus.content_types ?? {}} />
            <ModelVersionTable runs={data?.training_runs ?? []} />
          </div>
        </>
      )}
    </div>
  );
}
