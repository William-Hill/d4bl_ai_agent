'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { IndicatorRow } from '@/lib/types';

interface Props {
  indicators: IndicatorRow[];
  metric: string;
  stateName: string;
}

const RACE_COLORS: Record<string, string> = {
  black: '#00ff32',
  white: '#777',
  hispanic: '#555',
  total: '#404040',
};

const RACE_LABELS: Record<string, string> = {
  black: 'Black',
  white: 'White',
  hispanic: 'Hispanic/Latino',
  total: 'All',
};

const METRIC_LABELS: Record<string, string> = {
  homeownership_rate: 'Homeownership Rate (%)',
  median_household_income: 'Median Household Income ($)',
  poverty_rate: 'Poverty Rate (%)',
};

export default function RacialGapChart({ indicators, metric, stateName }: Props) {
  const data = indicators
    .filter((r) => r.race !== 'total')
    .map((r) => ({
      race: RACE_LABELS[r.race] ?? r.race,
      value: r.value,
      fill: RACE_COLORS[r.race] ?? '#666',
    }));

  if (data.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 text-center text-gray-500 text-sm">
        No data available for this selection.
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">
        {METRIC_LABELS[metric] ?? metric} — {stateName}
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
          <XAxis
            dataKey="race"
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: '#292929',
              border: '1px solid #404040',
              borderRadius: 4,
            }}
            labelStyle={{ color: '#e5e7eb' }}
            itemStyle={{ color: '#00ff32' }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={40}>
            {data.map((entry, index) => (
              <Cell key={index} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

