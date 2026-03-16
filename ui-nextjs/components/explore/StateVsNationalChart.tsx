'use client';

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface Props {
  stateValue: number;
  nationalAverage: number;
  stateName: string;
  metric: string;
  accent: string;
}

export default function StateVsNationalChart({
  stateValue,
  nationalAverage,
  stateName,
  metric,
  accent,
}: Props) {
  const data = [
    { name: stateName, value: stateValue },
    { name: 'National Avg', value: nationalAverage },
  ];

  const diff = stateValue - nationalAverage;
  const pctDiff = nationalAverage !== 0
    ? ((diff / nationalAverage) * 100).toFixed(1)
    : '0';

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-4">
        <h3 className="text-base font-semibold text-white">
          {metric} — {stateName}
        </h3>
        <span
          className="text-sm font-mono"
          style={{ color: diff >= 0 ? accent : '#a8a8a8' }}
        >
          {diff >= 0 ? '+' : ''}{pctDiff}% vs national
        </span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} barCategoryGap="30%">
          <CartesianGrid strokeDasharray="3 3" stroke="#4a4a4a" />
          <XAxis dataKey="name" tick={{ fill: '#999', fontSize: 12 }} />
          <YAxis tick={{ fill: '#999', fontSize: 12 }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#292929', border: '1px solid #404040', color: '#fff' }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            <Cell fill={accent} />
            <Cell fill="#7c7c7c" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
