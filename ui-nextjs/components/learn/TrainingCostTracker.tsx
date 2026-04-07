'use client';

import {
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
  Legend,
} from 'recharts';
import { EXPERIMENTS } from '@/lib/experiments';

const chartData = EXPERIMENTS.map((exp) => ({
  name: `Exp ${exp.id}`,
  label: exp.name,
  cost: exp.cost.total,
  cumulative: exp.cumulativeCost,
  status: exp.status,
}));

const TOTAL_COST = EXPERIMENTS.at(-1)?.cumulativeCost ?? 0;

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: (typeof chartData)[number]; value: number; dataKey: string }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0].payload;
  return (
    <div className="bg-[#292929] border border-[#404040] rounded-lg p-3 text-sm shadow-lg">
      <p className="text-white font-semibold mb-1">{data.label}</p>
      <p className="text-gray-400">
        Cost: <span className="text-gray-200 font-mono">${data.cost.toFixed(2)}</span>
      </p>
      <p className="text-gray-400">
        Cumulative: <span className="text-[#00ff32] font-mono">${data.cumulative.toFixed(2)}</span>
      </p>
    </div>
  );
}

export default function TrainingCostTracker() {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-lg font-semibold text-white">Training Costs</h3>
        <span className="text-sm text-gray-400">
          Total: <span className="text-[#00ff32] font-mono">${TOTAL_COST.toFixed(2)}</span>
        </span>
      </div>
      <p className="text-sm text-gray-400 mb-6">
        Cumulative cost across six experiments. Initial experiments dominated by training data
        generation via Claude API; later experiments reused existing data.
      </p>

      <div className="bg-[#292929] border border-[#404040] rounded-lg p-4">
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis
              dataKey="name"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
              axisLine={{ stroke: '#404040' }}
              tickLine={{ stroke: '#404040' }}
            />
            <YAxis
              yAxisId="cost"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
              axisLine={{ stroke: '#404040' }}
              tickLine={{ stroke: '#404040' }}
              tickFormatter={(v: number) => `$${v}`}
            />
            <YAxis
              yAxisId="cumulative"
              orientation="right"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
              axisLine={{ stroke: '#404040' }}
              tickLine={{ stroke: '#404040' }}
              tickFormatter={(v: number) => `$${v}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ color: '#9ca3af', fontSize: 12, paddingTop: 8 }} />
            <Bar
              yAxisId="cost"
              dataKey="cost"
              name="Per-experiment cost"
              fill="#404040"
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="cumulative"
              dataKey="cumulative"
              name="Cumulative total"
              stroke="#00ff32"
              strokeWidth={2}
              dot={{ fill: '#00ff32', r: 4 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Cost breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
        <div className="bg-[#292929] border border-[#404040] rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-white font-mono">${TOTAL_COST.toFixed(2)}</div>
          <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">Total Cost</div>
        </div>
        <div className="bg-[#292929] border border-[#404040] rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-white font-mono">{EXPERIMENTS.length}</div>
          <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">Experiments</div>
        </div>
        <div className="bg-[#292929] border border-[#404040] rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-white font-mono">
            ${EXPERIMENTS.length > 0 ? (TOTAL_COST / EXPERIMENTS.length).toFixed(2) : '0.00'}
          </div>
          <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">
            Avg / Experiment
          </div>
        </div>
      </div>
    </div>
  );
}
