'use client';

import { useRef, useState } from 'react';
import { compareModels, CompareResponse, PipelinePath } from '@/lib/api';

const STEP_LABELS: Record<string, string> = {
  parse: 'Parse Query',
  search: 'Search Data',
  synthesize: 'Synthesize Answer',
};

const PLACEHOLDER_PROMPT =
  'What is the median household income for Black families in Mississippi?';

function PipelinePanel({
  path,
  isFineTuned,
}: {
  path: PipelinePath;
  isFineTuned: boolean;
}) {
  const borderClass = isFineTuned ? 'border-[#00ff32]/30' : 'border-[#404040]';
  const labelColor = isFineTuned ? 'text-[#00ff32]' : 'text-gray-400';

  return (
    <div className={`flex-1 min-w-0 bg-[#292929] border ${borderClass} rounded-lg p-4`}>
      <div className="flex justify-between items-center mb-3">
        <span className={`text-xs uppercase tracking-widest font-semibold ${labelColor}`}>
          {path.label}
        </span>
        <span className="bg-[#333] text-gray-400 px-2 py-0.5 rounded text-[10px]">
          {path.total_latency_seconds.toFixed(1)}s total
        </span>
      </div>

      {/* Pipeline steps */}
      <div className="space-y-3 mb-4">
        {path.steps.map((step, i) => (
          <div key={i}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">
                  {i + 1}. {STEP_LABELS[step.step] ?? step.step}
                </span>
                <span className={`px-1.5 py-0.5 rounded text-[9px] ${
                  isFineTuned && step.step !== 'search'
                    ? 'bg-[#1f3524] text-[#4ade80]'
                    : 'bg-[#333] text-gray-500'
                }`}>
                  {step.model_name}
                </span>
              </div>
              <span className="text-[10px] text-gray-600">{step.latency_seconds.toFixed(2)}s</span>
            </div>
            <div className="bg-[#1a1a1a] rounded-md p-2 max-h-[100px] overflow-auto">
              <pre className="text-[11px] text-gray-400 whitespace-pre-wrap break-words font-mono leading-relaxed">
                {step.output.slice(0, 300)}{step.output.length > 300 ? '...' : ''}
              </pre>
            </div>
          </div>
        ))}
      </div>

      {/* Final answer */}
      <div>
        <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium mb-1">
          Final Answer
        </div>
        <div className={`bg-[#1a1a1a] rounded-md p-3 min-h-[80px] max-h-[250px] overflow-auto border ${
          isFineTuned ? 'border-[#00ff32]/20' : 'border-transparent'
        }`}>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">
            {path.final_answer}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function ModelComparisonPlayground() {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const handleCompare = async () => {
    const queryText = prompt.trim() || PLACEHOLDER_PROMPT;
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await compareModels(queryText);
      if (requestIdRef.current !== currentRequestId) return;
      setResult(data);
    } catch (err: unknown) {
      if (requestIdRef.current !== currentRequestId) return;
      setError(err instanceof Error ? err.message : 'Comparison failed');
    } finally {
      if (requestIdRef.current === currentRequestId) {
        setLoading(false);
      }
    }
  };

  return (
    <div className="space-y-4">
      {/* Pipeline diagram */}
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-4">
        <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-3 font-medium">
          How it works
        </div>
        <div className="flex items-center justify-center gap-2 text-xs text-gray-400 flex-wrap">
          <span className="bg-[#1a1a1a] px-3 py-1.5 rounded-md">Your Question</span>
          <span className="text-gray-600">&rarr;</span>
          <span className="bg-[#1a1a1a] px-3 py-1.5 rounded-md">
            <span className="text-gray-500">1.</span> Parse Query
          </span>
          <span className="text-gray-600">&rarr;</span>
          <span className="bg-[#1a1a1a] px-3 py-1.5 rounded-md">
            <span className="text-gray-500">2.</span> Search Data
          </span>
          <span className="text-gray-600">&rarr;</span>
          <span className="bg-[#1a1a1a] px-3 py-1.5 rounded-md">
            <span className="text-gray-500">3.</span> Synthesize Answer
          </span>
        </div>
        <p className="text-[11px] text-gray-600 text-center mt-2">
          Both paths search the same data. The difference is which model parses and synthesizes.
        </p>
      </div>

      {/* Query input */}
      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <label htmlFor="compare-prompt" className="sr-only">
            Prompt
          </label>
          <textarea
            id="compare-prompt"
            rows={2}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={loading}
            placeholder={PLACEHOLDER_PROMPT}
            className="w-full bg-[#292929] border border-[#404040] rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-[#00ff32]/50 resize-y disabled:opacity-50 disabled:cursor-not-allowed"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !loading) {
                e.preventDefault();
                handleCompare();
              }
            }}
          />
        </div>
        <button
          onClick={handleCompare}
          disabled={loading}
          className="bg-[#00ff32] hover:bg-[#00cc28] disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors whitespace-nowrap"
        >
          {loading ? 'Running...' : 'Compare Pipelines'}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-[#2a1a1a] border border-[#803a3a] text-red-200 rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="space-y-4">
          <div className="flex gap-3">
            <div className="flex-1 bg-[#292929] rounded-lg h-64 animate-pulse" />
            <div className="flex-1 bg-[#292929] rounded-lg h-64 animate-pulse" />
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Summary bar */}
          <div className="flex bg-[#292929] rounded-lg overflow-hidden divide-x divide-[#404040]">
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Base Model
              </div>
              <div className="text-sm font-bold text-gray-400">
                {result.baseline.total_latency_seconds.toFixed(1)}s
              </div>
            </div>
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Fine-Tuned
              </div>
              <div className="text-sm font-bold text-[#4ade80]">
                {result.finetuned.total_latency_seconds.toFixed(1)}s
              </div>
            </div>
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Difference
              </div>
              {(() => {
                const delta = result.finetuned.total_latency_seconds - result.baseline.total_latency_seconds;
                const pct = result.baseline.total_latency_seconds > 0
                  ? (delta / result.baseline.total_latency_seconds) * 100
                  : 0;
                return (
                  <div className={`text-sm font-bold ${
                    pct === 0 ? 'text-gray-400' : pct < 0 ? 'text-[#4ade80]' : 'text-[#f87171]'
                  }`}>
                    {pct > 0 ? '+' : ''}{pct.toFixed(0)}%
                  </div>
                );
              })()}
            </div>
          </div>

          {/* Side-by-side pipeline panels */}
          <div className="flex flex-col lg:flex-row gap-3">
            <PipelinePanel path={result.baseline} isFineTuned={false} />
            <PipelinePanel path={result.finetuned} isFineTuned={true} />
          </div>
        </>
      )}
    </div>
  );
}
