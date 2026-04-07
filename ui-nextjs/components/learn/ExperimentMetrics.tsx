'use client';

import {
  EXPERIMENTS,
  METRIC_KEYS,
  METRIC_LABELS,
  PERCENT_METRICS,
  LOWER_IS_BETTER,
  SHIP_THRESHOLDS,
  type ExperimentMetrics,
} from '@/lib/experiments';

type MetricKey = keyof ExperimentMetrics;

function formatValue(key: MetricKey, value: string | number | undefined): string {
  if (value === undefined) return '-';
  if (typeof value === 'string') return value;
  if (PERCENT_METRICS.has(key)) return `${value.toFixed(1)}%`;
  return value.toFixed(2);
}

function meetsThreshold(key: MetricKey, value: string | number | undefined): boolean | null {
  if (value === undefined || typeof value === 'string') return null;
  const threshold = SHIP_THRESHOLDS[key];
  if (!threshold) return null;
  return threshold.direction === 'gte' ? value >= threshold.value : value <= threshold.value;
}

function cellColor(key: MetricKey, value: string | number | undefined): string {
  const meets = meetsThreshold(key, value);
  if (meets === true) return 'text-[#4ade80]';
  if (meets === false && value !== undefined) return 'text-gray-300';
  return 'text-gray-500';
}

export default function ExperimentMetrics() {
  return (
    <div>
      <h3 className="text-lg font-semibold text-white mb-2">Metrics Comparison</h3>
      <p className="text-sm text-gray-400 mb-6">
        Key metrics across all training experiments. Green values meet ship thresholds.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#404040]">
              <th className="text-left text-gray-400 text-xs font-medium uppercase tracking-wider py-3 pr-4 sticky left-0 bg-[#1a1a1a]">
                Metric
              </th>
              {EXPERIMENTS.map((exp) => (
                <th
                  key={exp.id}
                  className="text-center text-gray-400 text-xs font-medium uppercase tracking-wider py-3 px-3 min-w-[80px]"
                >
                  <div>Exp {exp.id}</div>
                  <div className="text-[10px] text-gray-600 font-normal normal-case">
                    {exp.date.slice(5)}
                  </div>
                </th>
              ))}
              <th className="text-center text-[#00ff32] text-xs font-medium uppercase tracking-wider py-3 px-3">
                Target
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#333]">
            {METRIC_KEYS.map((key) => {
              const threshold = SHIP_THRESHOLDS[key];
              const isLower = LOWER_IS_BETTER.has(key);
              return (
                <tr key={key}>
                  <td className="text-gray-300 text-xs py-2.5 pr-4 sticky left-0 bg-[#1a1a1a]">
                    {METRIC_LABELS[key] ?? key}
                    {isLower && (
                      <span className="text-gray-600 ml-1 text-[10px]">(lower is better)</span>
                    )}
                  </td>
                  {EXPERIMENTS.map((exp) => {
                    const value = exp.metrics[key as keyof typeof exp.metrics];
                    return (
                      <td
                        key={exp.id}
                        className={`text-center font-mono text-xs py-2.5 px-3 ${cellColor(key, value)}`}
                      >
                        {formatValue(key, value)}
                      </td>
                    );
                  })}
                  <td className="text-center text-xs py-2.5 px-3 text-[#00ff32]/70 font-mono">
                    {threshold
                      ? `${threshold.direction === 'gte' ? '>=' : '<='} ${
                          PERCENT_METRICS.has(key)
                            ? `${threshold.value}%`
                            : threshold.value.toFixed(2)
                        }`
                      : '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
