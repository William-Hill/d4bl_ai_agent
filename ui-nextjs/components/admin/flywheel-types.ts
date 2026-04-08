export interface TimeSeriesPoint {
  date: string;
  value: number;
}

export interface TrainingRun {
  model_version: string;
  task: string;
  metrics: Record<string, unknown>;
  ship_decision: string;
  created_at: string | null;
}

export interface CorpusStats {
  total_chunks: number;
  total_tokens: number;
  content_types: Record<string, number>;
  unstructured_pct: number;
}

export interface FlywheelData {
  corpus: CorpusStats;
  training_runs: TrainingRun[];
  research_quality: Record<string, { avg_score: number; count: number }>;
  time_series: {
    corpus_diversity: TimeSeriesPoint[];
    model_accuracy: TimeSeriesPoint[];
    research_quality: TimeSeriesPoint[];
  };
}

export const DARK_TOOLTIP_STYLE = {
  contentStyle: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #404040',
    borderRadius: '6px',
    color: '#d1d5db',
    fontSize: 12,
  },
  labelStyle: { color: '#9ca3af' },
} as const;
