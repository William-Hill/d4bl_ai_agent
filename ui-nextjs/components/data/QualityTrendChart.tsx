'use client';

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

interface Run {
  id: string;
  started_at: string | null;
  records_ingested: number | null;
  status: string;
}

interface QualityTrendChartProps {
  runs: Run[];
}

export default function QualityTrendChart({ runs }: QualityTrendChartProps) {
  const completedRuns = runs
    .filter((r) => r.status === 'completed' && r.started_at && r.records_ingested != null)
    .sort((a, b) => new Date(a.started_at!).getTime() - new Date(b.started_at!).getTime())
    .map((r) => ({
      date: new Date(r.started_at!).toLocaleDateString(),
      records: r.records_ingested!,
    }));

  if (completedRuns.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-12 text-center">
        <p className="text-gray-500 text-sm">No completed runs yet</p>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-4">Records Ingested Over Time</h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={completedRuns}>
          <CartesianGrid stroke="#404040" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            stroke="#404040"
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            stroke="#404040"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #404040',
              borderRadius: '6px',
              color: '#d1d5db',
              fontSize: 12,
            }}
            labelStyle={{ color: '#9ca3af' }}
          />
          <Line
            type="monotone"
            dataKey="records"
            stroke="#00ff32"
            strokeWidth={2}
            dot={{ fill: '#00ff32', r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
