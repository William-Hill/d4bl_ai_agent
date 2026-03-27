'use client';

import { useState } from 'react';
import { compareModels, CompareResponse } from '@/lib/api';

type Task = 'query_parser' | 'explainer' | 'evaluator';

const TASK_LABELS: Record<Task, string> = {
  query_parser: 'Query Parser',
  explainer: 'Explainer',
  evaluator: 'Evaluator',
};

const PLACEHOLDER_PROMPTS: Record<Task, string> = {
  query_parser: 'What is the median household income for Black families in Mississippi?',
  explainer:
    'Data source: census\nMetric: median_household_income\nState: Mississippi (FIPS 28)\nValue: 45081\nNational average: 69021\nYear: 2022\nRacial breakdown: white: 55602, black: 32815, hispanic: 42189',
  evaluator:
    'Evaluate for equity framing: "The median household income in Mississippi is $45,081, below the national average."',
};

function OutputPanel({
  label,
  modelName,
  output,
  latency,
  validJson,
  errors,
  isFineTuned,
}: {
  label: string;
  modelName: string;
  output: string;
  latency: number;
  validJson: boolean;
  errors: string[] | null;
  isFineTuned: boolean;
}) {
  const borderClass = isFineTuned ? 'border-[#00ff32]/30' : 'border-[#404040]';
  const labelColor = isFineTuned ? 'text-[#00ff32]' : 'text-gray-400';
  const badgeBg = isFineTuned ? 'bg-[#1f3524]' : 'bg-[#333]';
  const badgeText = isFineTuned ? 'text-[#4ade80]' : 'text-gray-400';

  return (
    <div className={`flex-1 min-w-0 bg-[#292929] border ${borderClass} rounded-lg p-4`}>
      <div className="flex justify-between items-center mb-3">
        <span className={`text-xs uppercase tracking-widest ${labelColor}`}>{label}</span>
        <span className={`${badgeBg} ${badgeText} px-2 py-0.5 rounded text-[10px]`}>
          {modelName}
        </span>
      </div>
      <div className="bg-[#1a1a1a] rounded-md p-3 min-h-[120px] max-h-[300px] overflow-auto">
        <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words font-mono leading-relaxed">
          {output}
        </pre>
      </div>
      <div className="flex gap-1.5 mt-2 flex-wrap">
        <span
          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
            validJson ? 'bg-[#1f3524] text-[#4ade80]' : 'bg-[#402424] text-[#f87171]'
          }`}
        >
          {validJson ? 'Valid JSON' : 'Invalid JSON'}
        </span>
        <span className="bg-[#333] text-gray-400 px-2 py-0.5 rounded text-[10px]">
          {latency.toFixed(2)}s
        </span>
        {errors?.map((e, i) => (
          <span key={i} className="bg-[#402424] text-[#f87171] px-2 py-0.5 rounded text-[10px]">
            {e}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ModelComparisonPlayground() {
  const [task, setTask] = useState<Task>('query_parser');
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCompare = async () => {
    const queryText = prompt.trim() || PLACEHOLDER_PROMPTS[task];
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await compareModels(queryText, task);
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
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
            placeholder={PLACEHOLDER_PROMPTS[task]}
            className="w-full bg-[#292929] border border-[#404040] rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-[#00ff32]/50 resize-y"
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
          {loading ? 'Running...' : 'Compare Models'}
        </button>
      </div>

      {/* Task selector */}
      <div className="flex gap-1.5">
        {(Object.keys(TASK_LABELS) as Task[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTask(t);
              setResult(null);
            }}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              task === t
                ? 'bg-[#00ff32] text-black'
                : 'bg-[#333] text-gray-400 hover:text-white'
            }`}
          >
            {TASK_LABELS[t]}
          </button>
        ))}
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
          <div className="bg-[#292929] rounded-lg h-12 animate-pulse" />
          <div className="flex gap-3">
            <div className="flex-1 bg-[#292929] rounded-lg h-48 animate-pulse" />
            <div className="flex-1 bg-[#292929] rounded-lg h-48 animate-pulse" />
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Summary delta bar */}
          <div className="flex bg-[#292929] rounded-lg overflow-hidden divide-x divide-[#404040]">
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Valid JSON
              </div>
              <div className="text-sm font-bold">
                <span className={result.baseline.valid_json ? 'text-[#4ade80]' : 'text-[#f87171]'}>
                  {result.baseline.valid_json ? 'Yes' : 'No'}
                </span>
                <span className="text-gray-600 mx-1">&rarr;</span>
                <span className={result.finetuned.valid_json ? 'text-[#4ade80]' : 'text-[#f87171]'}>
                  {result.finetuned.valid_json ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
            <div className="flex-1 text-center py-2.5 px-2">
              <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                Latency
              </div>
              <div
                className={`text-sm font-bold ${
                  result.metrics.latency_delta_pct < 0 ? 'text-[#4ade80]' : 'text-[#f87171]'
                }`}
              >
                {result.metrics.latency_delta_pct > 0 ? '+' : ''}
                {result.metrics.latency_delta_pct.toFixed(0)}%
              </div>
              <div className="text-[10px] text-gray-600">
                {result.baseline.latency_seconds.toFixed(1)}s &rarr;{' '}
                {result.finetuned.latency_seconds.toFixed(1)}s
              </div>
            </div>
            {result.metrics.task_specific_flag && (
              <div className="flex-1 text-center py-2.5 px-2">
                <div className="text-[9px] text-gray-500 uppercase tracking-widest mb-0.5">
                  Quality
                </div>
                <div className="text-sm font-bold text-[#4ade80]">
                  {result.metrics.task_specific_flag}
                </div>
              </div>
            )}
          </div>

          {/* Side-by-side panels */}
          <div className="flex flex-col sm:flex-row gap-3">
            <OutputPanel
              label="Base Model"
              modelName={result.baseline.model_name}
              output={result.baseline.output}
              latency={result.baseline.latency_seconds}
              validJson={result.baseline.valid_json}
              errors={result.baseline.errors}
              isFineTuned={false}
            />
            <OutputPanel
              label="Fine-Tuned"
              modelName={result.finetuned.model_name}
              output={result.finetuned.output}
              latency={result.finetuned.latency_seconds}
              validJson={result.finetuned.valid_json}
              errors={result.finetuned.errors}
              isFineTuned={true}
            />
          </div>
        </>
      )}
    </div>
  );
}
