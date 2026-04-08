'use client';

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { DARK_TOOLTIP_STYLE } from './flywheel-types';

interface CorpusBreakdownProps {
  contentTypes: Record<string, number>;
}

export default function CorpusBreakdown({ contentTypes }: CorpusBreakdownProps) {
  const data = Object.entries(contentTypes)
    .map(([name, count]) => ({ name: name.replace(/_/g, ' '), count }))
    .sort((a, b) => b.count - a.count);

  if (data.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-12 text-center">
        <p className="text-gray-500 text-sm">No documents ingested yet</p>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <h4 className="text-sm font-semibold text-white mb-4">Corpus Composition</h4>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 36)}>
        <BarChart data={data} layout="vertical" margin={{ left: 20 }}>
          <CartesianGrid stroke="#404040" strokeDasharray="3 3" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: '#9ca3af', fontSize: 10 }}
            stroke="#404040"
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            stroke="#404040"
            width={110}
          />
          <Tooltip {...DARK_TOOLTIP_STYLE} />
          <Bar dataKey="count" fill="#00ff32" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
