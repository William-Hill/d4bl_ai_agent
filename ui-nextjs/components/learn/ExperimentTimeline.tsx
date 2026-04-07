'use client';

import { EXPERIMENTS, type Experiment, type ExperimentStatus } from '@/lib/experiments';

const STATUS_CONFIG: Record<
  ExperimentStatus,
  { bg: string; text: string; label: string; border: string }
> = {
  pass: {
    bg: 'bg-[#1f3524]',
    text: 'text-[#4ade80]',
    label: 'Pass',
    border: 'border-[#00ff32]/30',
  },
  fail: {
    bg: 'bg-[#402424]',
    text: 'text-[#f87171]',
    label: 'Failed',
    border: 'border-red-400/30',
  },
  partial: {
    bg: 'bg-[#3d3520]',
    text: 'text-[#fbbf24]',
    label: 'Partial',
    border: 'border-yellow-400/30',
  },
};

function ExperimentCard({ experiment, isLast }: { experiment: Experiment; isLast: boolean }) {
  const status = STATUS_CONFIG[experiment.status];

  return (
    <div className={`relative pl-8 ${isLast ? 'pb-0' : 'pb-8'}`}>
      {/* Timeline connector line */}
      {!isLast && <div className="absolute left-[11px] top-6 bottom-0 w-px bg-[#404040]" />}

      {/* Timeline dot */}
      <div
        className={`absolute left-0 top-1.5 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${status.bg} ${status.text} ring-2 ring-[#1a1a1a]`}
      >
        {experiment.id}
      </div>

      {/* Card */}
      <div className={`bg-[#292929] border ${status.border} rounded-lg p-5`}>
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <h4 className="text-white font-semibold text-sm">{experiment.name}</h4>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-xs text-gray-500">{experiment.date}</span>
              <span className="text-xs text-gray-500">{experiment.baseModel}</span>
            </div>
          </div>
          <span
            className={`flex-shrink-0 ${status.bg} ${status.text} px-2.5 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wide`}
          >
            {status.label}
          </span>
        </div>

        {/* Key result */}
        <p className="text-gray-300 text-sm mb-3">{experiment.keyResult}</p>

        {/* Hypothesis (collapsed style) */}
        <p className="text-gray-500 text-xs italic">{experiment.hypothesis}</p>

        {/* Cost badge */}
        <div className="mt-3 flex items-center gap-2">
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">Cost</span>
          <span className="text-xs text-gray-400 font-mono">
            ${experiment.cost.total.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function ExperimentTimeline() {
  return (
    <div>
      <h3 className="text-lg font-semibold text-white mb-2">Training Timeline</h3>
      <p className="text-sm text-gray-400 mb-6">
        Six experiments over two weeks, from baseline failure to shipping hallucination detection.
      </p>
      <div className="max-w-3xl">
        {EXPERIMENTS.map((exp, i) => (
          <ExperimentCard key={exp.id} experiment={exp} isLast={i === EXPERIMENTS.length - 1} />
        ))}
      </div>
    </div>
  );
}
