'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { API_BASE } from '@/lib/api';

export interface StaffDatasetSummary {
  upload_id: string;
  source_name: string;
  metric_name: string;
  geographic_level: string;
  data_year: number;
  has_race: boolean;
  row_count: number;
  uploader_name: string | null;
  approved_at: string | null;
}

interface Props {
  value: string | null;
  onChange: (uploadId: string | null, summary: StaffDatasetSummary | null) => void;
}

export default function StaffDatasetPicker({ value, onChange }: Props) {
  const { session } = useAuth();
  const [datasets, setDatasets] = useState<StaffDatasetSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) {
        setLoading(true);
        setError(null);
      }
    });
    fetch(`${API_BASE}/api/explore/staff-uploads/available`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then(async (resp) => {
        if (cancelled) return;
        if (!resp.ok) {
          setError('Failed to load staff datasets.');
          return;
        }
        const data = await resp.json();
        setDatasets(Array.isArray(data) ? data : []);
      })
      .catch(() => { if (!cancelled) setError('Failed to load staff datasets.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [session?.access_token]);

  if (loading) return <div className="text-sm text-gray-400">Loading datasets...</div>;
  if (error) return <div className="text-sm text-red-400">{error}</div>;
  if (datasets.length === 0) {
    return (
      <div className="text-sm text-gray-400">
        No staff datasets approved yet. Contributors can upload data sources under Admin &gt; Data Sources.
      </div>
    );
  }

  return (
    <div>
      <label htmlFor="staff-dataset-picker" className="block text-sm font-medium text-gray-300 mb-1">
        Dataset
      </label>
      <select
        id="staff-dataset-picker"
        value={value ?? ''}
        onChange={(e) => {
          const id = e.target.value || null;
          const summary = datasets.find((d) => d.upload_id === id) ?? null;
          onChange(id, summary);
        }}
        className="w-full px-3 py-2 bg-[#292929] border border-[#404040] rounded text-white text-sm"
      >
        <option value="">-- Pick a dataset --</option>
        {datasets.map((d) => (
          <option key={d.upload_id} value={d.upload_id}>
            {d.source_name} · {d.metric_name} · {d.data_year} ({d.row_count} rows)
          </option>
        ))}
      </select>
    </div>
  );
}
