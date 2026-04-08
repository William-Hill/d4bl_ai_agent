'use client';

interface TrainingRun {
  model_version: string;
  task: string;
  metrics: Record<string, unknown>;
  ship_decision: string;
  created_at: string | null;
}

interface ModelVersionTableProps {
  runs: TrainingRun[];
}

export default function ModelVersionTable({ runs }: ModelVersionTableProps) {
  if (runs.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-12 text-center">
        <p className="text-gray-500 text-sm">No model evaluations recorded yet</p>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
      <h4 className="text-sm font-semibold text-white px-4 pt-4 pb-2">Model Versions</h4>
      <table className="w-full">
        <thead>
          <tr className="border-b border-[#404040]">
            <th className="px-4 py-2 text-left text-xs text-gray-400">Version</th>
            <th className="px-4 py-2 text-left text-xs text-gray-400">Task</th>
            <th className="px-4 py-2 text-left text-xs text-gray-400">Entity F1</th>
            <th className="px-4 py-2 text-left text-xs text-gray-400">Halluc. Acc</th>
            <th className="px-4 py-2 text-left text-xs text-gray-400">Decision</th>
            <th className="px-4 py-2 text-left text-xs text-gray-400">Date</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run, i) => {
            const f1 = typeof run.metrics.entity_f1 === 'number'
              ? run.metrics.entity_f1.toFixed(3) : '—';
            const halluc = typeof run.metrics.hallucination_accuracy === 'number'
              ? run.metrics.hallucination_accuracy.toFixed(3) : '—';
            const decisionColor = run.ship_decision === 'ship'
              ? 'text-green-400' : run.ship_decision === 'no-ship'
              ? 'text-red-400' : 'text-yellow-400';

            return (
              <tr key={`${run.model_version}-${run.task}-${i}`} className="border-b border-[#404040] last:border-0">
                <td className="px-4 py-2 text-white text-sm font-mono">{run.model_version}</td>
                <td className="px-4 py-2 text-gray-300 text-sm">{run.task}</td>
                <td className="px-4 py-2 text-gray-300 text-sm font-mono">{f1}</td>
                <td className="px-4 py-2 text-gray-300 text-sm font-mono">{halluc}</td>
                <td className={`px-4 py-2 text-sm font-semibold ${decisionColor}`}>{run.ship_decision}</td>
                <td className="px-4 py-2 text-gray-400 text-sm">
                  {run.created_at ? new Date(run.created_at).toLocaleDateString() : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
