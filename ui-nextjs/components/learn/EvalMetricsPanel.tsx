'use client';

import { useEffect, useState } from 'react';
import { EvalRunItem, getEvalRuns } from '@/lib/api';

const TASK_LABELS: Record<string, string> = {
  query_parser: 'Query Parser',
  explainer: 'Explainer',
  evaluator: 'Evaluator',
};

const SHIP_BADGES: Record<string, { bg: string; text: string; label: string }> = {
  ship: { bg: 'bg-[#1f3524]', text: 'text-[#4ade80]', label: 'Ship' },
  no_ship: { bg: 'bg-[#402424]', text: 'text-[#f87171]', label: 'No Ship' },
  ship_with_gaps: { bg: 'bg-[#3d3520]', text: 'text-[#fbbf24]', label: 'Ship with Gaps' },
};

/** Metrics where lower is better (latency, MAE). */
const LOWER_IS_BETTER = new Set(['p50_latency_ms', 'p95_latency_ms', 'relevance_mae', 'bias_mae']);

function MetricRow({ name, value }: { name: string; value: number | null }) {
  if (value === null) {
    return (
      <div className="flex justify-between py-1">
        <span className="text-xs text-gray-500">{name}</span>
        <span className="text-xs text-gray-600 italic">deferred</span>
      </div>
    );
  }

  const isPercent = !LOWER_IS_BETTER.has(name) && value <= 1.0;
  const displayValue = isPercent ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);

  return (
    <div className="flex justify-between py-1">
      <span className="text-xs text-gray-400">{name}</span>
      <span className="text-xs text-gray-200 font-mono">{displayValue}</span>
    </div>
  );
}

function TaskCard({ runs }: { runs: EvalRunItem[] }) {
  const task = runs[0]?.task ?? 'unknown';
  const label = TASK_LABELS[task] ?? task;

  return (
    <div className="bg-[#292929] border border-[#404040] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">{label}</h4>
        <div className="flex gap-1.5">
          {runs.map((r) => {
            const badge = SHIP_BADGES[r.ship_decision] ?? SHIP_BADGES.no_ship;
            return (
              <span
                key={r.model_name}
                className={`${badge.bg} ${badge.text} px-2 py-0.5 rounded text-[10px] font-semibold`}
              >
                {r.model_name}: {badge.label}
              </span>
            );
          })}
        </div>
      </div>

      {runs.map((r) => (
        <div key={r.model_name} className="mb-3 last:mb-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">
              {r.model_name}
            </span>
            <span className="text-[10px] text-gray-600">{r.model_version}</span>
          </div>
          <div className="bg-[#1a1a1a] rounded-md p-3 divide-y divide-[#333]">
            {Object.entries(r.metrics).map(([name, value]) => (
              <MetricRow key={name} name={name} value={value} />
            ))}
          </div>
          {r.blocking_failures && r.blocking_failures.length > 0 && (
            <div className="mt-2">
              {r.blocking_failures.map((f, i) => (
                <div
                  key={i}
                  className="text-[10px] text-[#f87171] bg-[#402424] rounded px-2 py-1 mb-1"
                >
                  {(f as Record<string, unknown>).metric as string}:{' '}
                  {String((f as Record<string, unknown>).actual ?? 'missing')} (need{' '}
                  {(f as Record<string, unknown>).direction === 'min' ? '>=' : '<='}{' '}
                  {String((f as Record<string, unknown>).threshold)})
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {runs[0]?.created_at && (
        <div className="text-[10px] text-gray-600 mt-2">
          Last run: {new Date(runs[0].created_at).toLocaleDateString()}
        </div>
      )}
    </div>
  );
}

export default function EvalMetricsPanel() {
  const [runs, setRuns] = useState<EvalRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getEvalRuns();
        if (!cancelled) setRuns(data.runs);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-[#292929] rounded-lg h-48 animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[#2a1a1a] border border-[#803a3a] text-red-200 rounded-lg px-4 py-3 text-sm">
        {error}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-6 text-center">
        <p className="text-gray-400 text-sm mb-2">No evaluation data yet.</p>
        <p className="text-gray-600 text-xs font-mono">
          python -m scripts.training.run_eval_harness --persist
        </p>
      </div>
    );
  }

  // Group by task
  const byTask: Record<string, EvalRunItem[]> = {};
  for (const run of runs) {
    if (!byTask[run.task]) byTask[run.task] = [];
    byTask[run.task].push(run);
  }

  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Object.entries(byTask).map(([task, taskRuns]) => (
        <TaskCard key={task} runs={taskRuns} />
      ))}
    </div>
  );
}
