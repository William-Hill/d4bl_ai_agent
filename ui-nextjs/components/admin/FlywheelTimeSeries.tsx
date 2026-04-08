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

interface TimeSeriesPoint {
  date: string;
  value: number;
}

interface MiniChartProps {
  title: string;
  data: TimeSeriesPoint[];
  color: string;
  unit?: string;
  emptyMessage?: string;
}

function MiniChart({ title, data, color, unit = '', emptyMessage }: MiniChartProps) {
  const currentValue = data.length > 0 ? data[data.length - 1].value : null;

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">{title}</h4>
        {currentValue !== null && (
          <span className="text-lg font-bold" style={{ color }}>
            {currentValue}{unit}
          </span>
        )}
      </div>
      {data.length === 0 ? (
        <div className="flex items-center justify-center h-[160px]">
          <p className="text-gray-500 text-sm">{emptyMessage || 'No data yet'}</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data}>
            <CartesianGrid stroke="#404040" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#9ca3af', fontSize: 10 }}
              stroke="#404040"
            />
            <YAxis
              tick={{ fill: '#9ca3af', fontSize: 10 }}
              stroke="#404040"
              width={40}
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
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={{ fill: color, r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

interface FlywheelTimeSeriesProps {
  timeSeries: {
    corpus_diversity: TimeSeriesPoint[];
    model_accuracy: TimeSeriesPoint[];
    research_quality: TimeSeriesPoint[];
  };
}

export default function FlywheelTimeSeries({ timeSeries }: FlywheelTimeSeriesProps) {
  return (
    <div className="grid grid-cols-1 gap-4">
      <MiniChart
        title="Corpus Diversity"
        data={timeSeries.corpus_diversity}
        color="#22c55e"
        unit="%"
        emptyMessage="Metrics appear after training runs are recorded"
      />
      <MiniChart
        title="Model Accuracy"
        data={timeSeries.model_accuracy}
        color="#3b82f6"
        emptyMessage="Metrics appear after training runs are recorded"
      />
      <MiniChart
        title="Research Output Quality"
        data={timeSeries.research_quality}
        color="#f59e0b"
        emptyMessage="Metrics appear after evaluation runs complete"
      />
    </div>
  );
}
