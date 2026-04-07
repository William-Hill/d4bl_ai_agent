export type ExperimentStatus = 'pass' | 'fail' | 'partial';

export interface ExperimentMetrics {
  /** Parser entity extraction F1 score (0-100) */
  entity_f1?: number;
  /** Parser JSON valid rate (0-100) */
  json_valid_rate?: number;
  /** Integration tests passing (e.g. "11/11") */
  integration_tests?: string;
  /** Evaluator hallucination detection accuracy (0-100) */
  hallucination_accuracy?: number;
  /** Evaluator relevance MAE (lower is better) */
  relevance_mae?: number;
  /** Data source accuracy (0-100) */
  data_source_accuracy?: number;
}

export interface Experiment {
  id: number;
  date: string;
  name: string;
  baseModel: string;
  hypothesis: string;
  keyResult: string;
  status: ExperimentStatus;
  metrics: ExperimentMetrics;
  cost: {
    claudeApi: number;
    colabCompute: number;
    total: number;
  };
  cumulativeCost: number;
  lessons: string[];
}

const RAW_EXPERIMENTS: Omit<Experiment, 'cumulativeCost'>[] = [
  {
    id: 1,
    date: '2026-03-23',
    name: 'Sprint 2 baseline',
    baseModel: 'Qwen2.5-3B',
    hypothesis:
      'Initial fine-tuning on ~115 examples per task would produce usable JSON outputs.',
    keyResult: '3/11 integration tests passing',
    status: 'fail',
    metrics: {
      integration_tests: '3/11',
      json_valid_rate: 30,
    },
    cost: { claudeApi: 15, colabCompute: 4, total: 19 },
    lessons: [
      'Insufficient training data (~115 examples) causes narrative output instead of JSON',
      'Incorrect chat template tokenization loses structure',
    ],
  },
  {
    id: 2,
    date: '2026-03-25',
    name: 'Sprint 2.5 JSON fix',
    baseModel: 'Qwen2.5-3B',
    hypothesis:
      'Increasing data to 1,000 pairs, 7 epochs, proper chat templates, and Modelfile fixes would resolve JSON output failures.',
    keyResult: '11/11 integration tests passing',
    status: 'pass',
    metrics: {
      integration_tests: '11/11',
      json_valid_rate: 95,
    },
    cost: { claudeApi: 15, colabCompute: 4, total: 19 },
    lessons: [
      'Training data volume and chat template formatting were the primary drivers',
      'Ollama double-wraps ChatML templates — needs explicit TEMPLATE directive',
      'Use tokenizer.apply_chat_template() instead of manual formatting',
    ],
  },
  {
    id: 3,
    date: '2026-03-29',
    name: 'v2 Qwen 3.5 upgrade',
    baseModel: 'Qwen3.5-4B',
    hypothesis:
      'Upgrading to Qwen3.5-4B (Gated Delta Networks) would improve multi-task evaluation capacity without significant cost increase.',
    keyResult: 'Base model upgrade, evaluator 0% (prompt mismatch)',
    status: 'partial',
    metrics: {
      entity_f1: 56.83,
      data_source_accuracy: 71.6,
      hallucination_accuracy: 0,
    },
    cost: { claudeApi: 0.02, colabCompute: 4, total: 4.02 },
    lessons: [
      'Evaluator 0% was a system prompt mismatch, not model failure',
      'Inference prompt must match the training prompt exactly for multi-task models',
    ],
  },
  {
    id: 4,
    date: '2026-03-31',
    name: 'v3 document layer + subtask dispatch',
    baseModel: 'Qwen3.5-4B',
    hypothesis:
      'Adding document passages to training data and matching inference prompts to subtask-specific training prompts would improve parser F1 and evaluator accuracy.',
    keyResult: 'Parser entity F1 +16pp, evaluator 0% -> 84%',
    status: 'pass',
    metrics: {
      entity_f1: 72.66,
      data_source_accuracy: 98.77,
      json_valid_rate: 98.77,
      hallucination_accuracy: 84,
      relevance_mae: 1.53,
    },
    cost: { claudeApi: 0.59, colabCompute: 4, total: 4.59 },
    lessons: [
      'Document layer passages taught the model document-style text patterns',
      'Community framing pairs drove parser entity_f1 from 56.83% to 72.66%',
      'Subtask dispatch was the dominant factor for evaluator improvement',
      'Inference prompt must match training prompt exactly for small multi-task models',
    ],
  },
  {
    id: 5,
    date: '2026-04-01',
    name: 'v3.1 expanded state coverage',
    baseModel: 'Qwen3.5-4B',
    hypothesis:
      'Training evaluator on documents from 8 states instead of 4 would push hallucination accuracy past the 85% ship threshold.',
    keyResult: 'FAILED: Domain re-adaptation broke evaluator output format',
    status: 'fail',
    metrics: {
      hallucination_accuracy: 0.5,
      relevance_mae: 4.0,
    },
    cost: { claudeApi: 0.59, colabCompute: 4, total: 4.59 },
    lessons: [
      'Never re-run domain adaptation without retraining ALL task adapters',
      'Preserve domain_merged checkpoint before any re-training run',
      'Evaluator is the most fragile adapter (r=16, attention-only, multiple schemas)',
      'For incremental data additions, retrain only the task adapter without re-running domain adaptation',
    ],
  },
  {
    id: 6,
    date: '2026-04-03',
    name: 'v3.0 full retrain (clean slate)',
    baseModel: 'Qwen3.5-4B',
    hypothesis:
      'Retraining ALL phases from a clean state on the expanded corpus would produce co-adapted adapters, unlike v3.1 which only retrained the evaluator.',
    keyResult: 'Hallucination 87% (ship!), parser entity F1 75%',
    status: 'partial',
    metrics: {
      entity_f1: 74.88,
      json_valid_rate: 96.3,
      hallucination_accuracy: 87.11,
      relevance_mae: 2.7,
    },
    cost: { claudeApi: 0, colabCompute: 4, total: 4 },
    lessons: [
      'Always verify the editable install target after switching branches/worktrees',
      'Explicit API options > Modelfile parameters for custom GGUFs',
      'Qwen 3.5 thinking mode cannot be disabled for custom GGUF files',
      'Register ALL models the eval harness needs before running evals',
    ],
  },
];

export const EXPERIMENTS: Experiment[] = RAW_EXPERIMENTS.reduce<Experiment[]>((acc, exp) => {
  const prev = acc.length > 0 ? acc[acc.length - 1].cumulativeCost : 0;
  acc.push({
    ...exp,
    cumulativeCost: +(prev + exp.cost.total).toFixed(2),
  });
  return acc;
}, []);

/** All metric keys that appear in at least one experiment. */
export const METRIC_KEYS: (keyof ExperimentMetrics)[] = [
  'integration_tests',
  'json_valid_rate',
  'entity_f1',
  'data_source_accuracy',
  'hallucination_accuracy',
  'relevance_mae',
];


/** Metrics that should be displayed as percentages (value is 0-100). */
export const PERCENT_METRICS = new Set([
  'entity_f1',
  'json_valid_rate',
  'hallucination_accuracy',
  'data_source_accuracy',
]);

/** Metrics where lower is better. */
export const LOWER_IS_BETTER = new Set(['relevance_mae']);

/** Human-readable labels for metric keys. */
export const METRIC_LABELS: Record<string, string> = {
  entity_f1: 'Parser Entity F1',
  json_valid_rate: 'JSON Valid Rate',
  integration_tests: 'Integration Tests',
  hallucination_accuracy: 'Hallucination Detection',
  relevance_mae: 'Relevance MAE',
  data_source_accuracy: 'Data Source Accuracy',
};

/** Ship thresholds for key metrics. */
export const SHIP_THRESHOLDS: Record<string, { value: number; direction: 'gte' | 'lte' }> = {
  entity_f1: { value: 80, direction: 'gte' },
  hallucination_accuracy: { value: 85, direction: 'gte' },
  relevance_mae: { value: 0.8, direction: 'lte' },
  json_valid_rate: { value: 95, direction: 'gte' },
};
