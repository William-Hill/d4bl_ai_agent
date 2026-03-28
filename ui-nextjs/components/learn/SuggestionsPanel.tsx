"use client";

import { useState } from "react";
import type { Suggestions } from "@/lib/api";

interface SuggestionsPanelProps {
  suggestions: Suggestions | null;
  runId: string;
  onAnalyze?: (runId: string) => Promise<void>;
}

export default function SuggestionsPanel({ suggestions, runId, onAnalyze }: SuggestionsPanelProps) {
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  if (!suggestions && !onAnalyze) {
    return null;
  }

  const blocking = suggestions?.rules.filter((r) => r.severity === "blocking") ?? [];
  const nonblocking = suggestions?.rules.filter((r) => r.severity === "non-blocking") ?? [];

  const handleAnalyze = async () => {
    if (!onAnalyze) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      await onAnalyze(runId);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="mt-4 bg-[#1a1a1a] border border-[#404040] rounded-lg p-4">
      <h4 className="text-sm font-semibold text-white mb-3">Suggested Improvements</h4>

      {blocking.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-red-400 uppercase tracking-wide mb-2">Blocking</p>
          <ul className="space-y-2">
            {blocking.map((s) => (
              <li key={s.metric} className="text-sm bg-red-900/20 border border-red-800/30 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-red-300">{s.metric}</span>
                  <span className="text-xs text-gray-400">
                    {s.current.toFixed(2)} &rarr; {s.target.toFixed(2)}
                  </span>
                </div>
                <p className="text-gray-300">{s.suggestion}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {nonblocking.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-yellow-400 uppercase tracking-wide mb-2">Non-blocking</p>
          <ul className="space-y-2">
            {nonblocking.map((s) => (
              <li key={s.metric} className="text-sm bg-yellow-900/20 border border-yellow-800/30 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-yellow-300">{s.metric}</span>
                  <span className="text-xs text-gray-400">
                    {s.current.toFixed(2)} &rarr; {s.target.toFixed(2)}
                  </span>
                </div>
                <p className="text-gray-300">{s.suggestion}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {suggestions?.llm_analysis ? (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-[#00ff32] hover:text-[#00cc28] font-medium"
          >
            {expanded ? "Hide" : "Show"} LLM Analysis
          </button>
          {expanded && (
            <div className="mt-2 bg-[#292929] rounded p-3 text-sm text-gray-300 whitespace-pre-wrap">
              {suggestions.llm_analysis}
            </div>
          )}
        </div>
      ) : onAnalyze ? (
        <>
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="mt-2 text-sm bg-[#00ff32]/10 border border-[#00ff32]/30 hover:bg-[#00ff32]/20 disabled:opacity-50 text-[#00ff32] px-4 py-2 rounded transition-colors"
          >
            {analyzing ? "Analyzing..." : "Analyze Failures (Coming Soon)"}
          </button>
          {analyzeError && (
            <p className="mt-1 text-xs text-red-400">{analyzeError}</p>
          )}
        </>
      ) : null}
    </div>
  );
}
