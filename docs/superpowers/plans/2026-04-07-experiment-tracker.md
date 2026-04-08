# Experiment Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an "Experiments" tab to the /learn page showing the fine-tuning experiment timeline, metrics comparison, and cumulative training costs. All data is static (parsed at build time from `docs/training-experiment-log.md`).

**Architecture:** A new `experiments` tab added to the existing `LearnTabs` component on `/learn`. Three new client components (`ExperimentTimeline`, `ExperimentMetrics`, `TrainingCostTracker`) consume static TypeScript data from `ui-nextjs/lib/experiments.ts`. No API endpoints or backend changes needed.

**Tech Stack:** Next.js (App Router), React 19, TypeScript, Tailwind CSS 4, Recharts (already installed)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `ui-nextjs/lib/experiments.ts` | Static experiment data as typed constants |
| Create | `ui-nextjs/components/learn/ExperimentTimeline.tsx` | Timeline of experiment cards with status badges |
| Create | `ui-nextjs/components/learn/ExperimentMetrics.tsx` | Per-experiment metrics comparison table |
| Create | `ui-nextjs/components/learn/TrainingCostTracker.tsx` | Cumulative cost bar chart via Recharts |
| Modify | `ui-nextjs/app/learn/page.tsx` | Add "Experiments" tab to LearnTabs |

---

### Task 1: Static Experiment Data

**Files:**
- Create: `ui-nextjs/lib/experiments.ts`

- [ ] **Step 1: Create the experiments data module**

```typescript
// ui-nextjs/lib/experiments.ts

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

export const EXPERIMENTS: Experiment[] = [
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
    cumulativeCost: 19,
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
    cumulativeCost: 38,
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
    cumulativeCost: 42.02,
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
    cumulativeCost: 46.61,
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
    cumulativeCost: 51.2,
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
    cumulativeCost: 55.2,
    lessons: [
      'Always verify the editable install target after switching branches/worktrees',
      'Explicit API options > Modelfile parameters for custom GGUFs',
      'Qwen 3.5 thinking mode cannot be disabled for custom GGUF files',
      'Register ALL models the eval harness needs before running evals',
    ],
  },
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run:
```bash
cd ui-nextjs && npx tsc --noEmit lib/experiments.ts
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/lib/experiments.ts
git commit -m "feat(learn): add static experiment data for training tracker (#176)"
```

---

### Task 2: ExperimentTimeline Component

**Files:**
- Create: `ui-nextjs/components/learn/ExperimentTimeline.tsx`

- [ ] **Step 1: Create the timeline component**

This component renders each experiment as a card in a vertical timeline. Cards show date, name, base model, key result, and a pass/fail/partial badge. The design matches the existing dark theme used in `ConceptSection`, `TutorialStep`, and `EvalMetricsPanel`.

```tsx
// ui-nextjs/components/learn/ExperimentTimeline.tsx
'use client';

import { EXPERIMENTS, type Experiment, type ExperimentStatus } from '@/lib/experiments';

const STATUS_CONFIG: Record<ExperimentStatus, { bg: string; text: string; label: string; border: string }> = {
  pass: { bg: 'bg-[#1f3524]', text: 'text-[#4ade80]', label: 'Pass', border: 'border-[#00ff32]/30' },
  fail: { bg: 'bg-[#402424]', text: 'text-[#f87171]', label: 'Failed', border: 'border-red-400/30' },
  partial: { bg: 'bg-[#3d3520]', text: 'text-[#fbbf24]', label: 'Partial', border: 'border-yellow-400/30' },
};

function ExperimentCard({ experiment }: { experiment: Experiment }) {
  const status = STATUS_CONFIG[experiment.status];

  return (
    <div className="relative pl-8 pb-8 last:pb-0">
      {/* Timeline connector line */}
      <div className="absolute left-[11px] top-6 bottom-0 w-px bg-[#404040] last:hidden" />

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
        {EXPERIMENTS.map((exp) => (
          <ExperimentCard key={exp.id} experiment={exp} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run:
```bash
cd ui-nextjs && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/ExperimentTimeline.tsx
git commit -m "feat(learn): add ExperimentTimeline component (#176)"
```

---

### Task 3: ExperimentMetrics Component

**Files:**
- Create: `ui-nextjs/components/learn/ExperimentMetrics.tsx`

- [ ] **Step 1: Create the metrics comparison component**

This component shows a table comparing key metrics across all experiments, following the `MetricRow` pattern from `EvalMetricsPanel`. Metrics that meet the ship threshold get a green highlight; those that regressed get red.

```tsx
// ui-nextjs/components/learn/ExperimentMetrics.tsx
'use client';

import {
  EXPERIMENTS,
  METRIC_LABELS,
  PERCENT_METRICS,
  LOWER_IS_BETTER,
  SHIP_THRESHOLDS,
} from '@/lib/experiments';

/** All metric keys that appear in at least one experiment. */
const METRIC_KEYS = [
  'integration_tests',
  'json_valid_rate',
  'entity_f1',
  'data_source_accuracy',
  'hallucination_accuracy',
  'relevance_mae',
] as const;

type MetricKey = (typeof METRIC_KEYS)[number];

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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run:
```bash
cd ui-nextjs && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/ExperimentMetrics.tsx
git commit -m "feat(learn): add ExperimentMetrics comparison table (#176)"
```

---

### Task 4: TrainingCostTracker Component

**Files:**
- Create: `ui-nextjs/components/learn/TrainingCostTracker.tsx`

- [ ] **Step 1: Create the cost tracker component**

Uses Recharts (already in `package.json`) to render a bar chart of per-experiment costs with a cumulative line overlay. Follows the dark theme styling.

```tsx
// ui-nextjs/components/learn/TrainingCostTracker.tsx
'use client';

import {
  BarChart,
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

const TOTAL_COST = EXPERIMENTS[EXPERIMENTS.length - 1].cumulativeCost;

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
            <Legend
              wrapperStyle={{ color: '#9ca3af', fontSize: 12, paddingTop: 8 }}
            />
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
          <div className="text-2xl font-bold text-white font-mono">
            ${TOTAL_COST.toFixed(2)}
          </div>
          <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">Total Cost</div>
        </div>
        <div className="bg-[#292929] border border-[#404040] rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-white font-mono">{EXPERIMENTS.length}</div>
          <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">Experiments</div>
        </div>
        <div className="bg-[#292929] border border-[#404040] rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-white font-mono">
            ${(TOTAL_COST / EXPERIMENTS.length).toFixed(2)}
          </div>
          <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">Avg / Experiment</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run:
```bash
cd ui-nextjs && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/TrainingCostTracker.tsx
git commit -m "feat(learn): add TrainingCostTracker chart component (#176)"
```

---

### Task 5: Wire Experiments Tab into Learn Page

**Files:**
- Modify: `ui-nextjs/app/learn/page.tsx`

- [ ] **Step 1: Add imports for the new components**

At the top of `ui-nextjs/app/learn/page.tsx`, add the three new imports after the existing imports (line 10):

```typescript
// Add after line 10 (after `import BuildTab from '@/components/learn/BuildTab';`)
import ExperimentTimeline from '@/components/learn/ExperimentTimeline';
import ExperimentMetrics from '@/components/learn/ExperimentMetrics';
import TrainingCostTracker from '@/components/learn/TrainingCostTracker';
```

- [ ] **Step 2: Add the Experiments tab to LearnTabs**

In the `tabs` array prop of `<LearnTabs>`, add a new tab entry after the `build` tab (after line 190):

```typescript
            {
              id: 'experiments',
              label: 'Experiments',
              content: (
                <div className="space-y-12">
                  <ExperimentTimeline />
                  <ExperimentMetrics />
                  <TrainingCostTracker />
                </div>
              ),
            },
```

The full modified `tabs` prop should be (showing only the new entry in context):

```typescript
        <LearnTabs
          tabs={[
            {
              id: 'compare',
              label: 'Compare',
              content: ( /* ... existing ... */ ),
            },
            {
              id: 'learn',
              label: 'Learn',
              content: ( /* ... existing ... */ ),
            },
            {
              id: 'build',
              label: 'Build',
              content: <BuildTab />,
            },
            {
              id: 'experiments',
              label: 'Experiments',
              content: (
                <div className="space-y-12">
                  <ExperimentTimeline />
                  <ExperimentMetrics />
                  <TrainingCostTracker />
                </div>
              ),
            },
          ]}
        />
```

- [ ] **Step 3: Verify build passes**

Run:
```bash
cd ui-nextjs && npm run build
```
Expected: Build succeeds with no errors.

- [ ] **Step 4: Verify lint passes**

Run:
```bash
cd ui-nextjs && npm run lint
```
Expected: No lint errors.

- [ ] **Step 5: Manual verification**

Run `cd ui-nextjs && npm run dev` and navigate to `http://localhost:3000/learn#experiments`. Verify:
1. The "Experiments" tab appears in the tab bar alongside Compare, Learn, Build
2. Clicking it shows the ExperimentTimeline with 6 experiment cards
3. Each card shows date, name, base model, key result, and a colored status badge
4. The ExperimentMetrics table shows all 6 experiments with metric values
5. Green values indicate metrics meeting ship thresholds
6. The TrainingCostTracker shows a bar chart with cumulative line
7. Total cost displays as $55.20
8. Direct navigation via `#experiments` hash works

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add Experiments tab with timeline, metrics, and costs (#176)"
```

---

### Task 6: Final Verification

- [ ] **Step 1: Full build from clean state**

Run:
```bash
cd ui-nextjs && rm -rf .next && npm run build
```
Expected: Production build succeeds.

- [ ] **Step 2: Verify all new files exist**

```bash
ls -la ui-nextjs/lib/experiments.ts
ls -la ui-nextjs/components/learn/ExperimentTimeline.tsx
ls -la ui-nextjs/components/learn/ExperimentMetrics.tsx
ls -la ui-nextjs/components/learn/TrainingCostTracker.tsx
```

- [ ] **Step 3: Verify tab hash navigation**

Open `http://localhost:3000/learn#experiments` in browser. The Experiments tab should be active on page load.
