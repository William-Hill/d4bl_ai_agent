# `/learn` Educational Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static, public `/learn` page with interactive components teaching fine-tuning concepts through a racial equity lens.

**Architecture:** Single Next.js route at `/learn` with 8 client components in `components/learn/`. All content is hardcoded (no API calls). Intersection Observer handles scroll-triggered fade-in animations. Dark theme with D4BL neon green (#00ff32) accents.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind CSS 4, inline SVG, native `<input type="range">`.

**Spec:** `docs/superpowers/specs/2026-03-26-learn-educational-page-design.md`

---

## File Structure

```
ui-nextjs/
├── app/learn/
│   └── page.tsx                    # Page layout, hero, section ordering
├── components/learn/
│   ├── ConceptSection.tsx          # Reusable prose wrapper with scroll fade-in
│   ├── LoRAVisualizer.tsx          # Rank slider + adapter size visualization
│   ├── QuantizationSlider.tsx      # Bit slider + size/quality chart
│   ├── MethodologyWheel.tsx        # Clickable SVG wheel (5 D4BL stages)
│   ├── DistillationPipeline.tsx    # Step-through animation (4 stages)
│   ├── RegisterComparison.tsx      # Tab toggle (community/policy/research)
│   ├── TutorialStep.tsx            # Colab notebook link card
│   └── PlaygroundPlaceholder.tsx   # Coming soon teaser
```

---

## Task 1: ConceptSection wrapper

The foundation component — every section on the page uses this. Build it first so all subsequent tasks can wrap their content in it.

**Files:**
- Create: `ui-nextjs/components/learn/ConceptSection.tsx`

- [ ] **Step 1: Create ConceptSection component**

```tsx
'use client';

import { useEffect, useRef, useState } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

export default function ConceptSection({ title, subtitle, children }: Props) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={ref}
      className={`max-w-4xl mx-auto px-6 py-24 transition-all duration-700 ease-out ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-5'
      }`}
    >
      <h2 className="text-3xl font-bold text-white mb-2">{title}</h2>
      {subtitle && (
        <p className="text-lg text-gray-400 mb-8">{subtitle}</p>
      )}
      <div className="text-gray-300 leading-relaxed space-y-4">{children}</div>
    </section>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds (component isn't imported yet, but should have no syntax errors).
Note: If the full build takes too long or fails for unrelated reasons, just run `npx tsc --noEmit` to type-check.

- [ ] **Step 3: Commit**

```bash
git add ui-nextjs/components/learn/ConceptSection.tsx
git commit -m "feat(learn): add ConceptSection wrapper with scroll fade-in"
```

---

## Task 2: Page scaffold + Hero + NavBar link

Create the route, add the hero section, and wire navigation.

**Files:**
- Create: `ui-nextjs/app/learn/page.tsx`
- Modify: `ui-nextjs/components/NavBar.tsx`

- [ ] **Step 1: Create the /learn page with hero**

```tsx
import ConceptSection from '@/components/learn/ConceptSection';

export const metadata = {
  title: 'Learn — Building AI That Centers Community | D4BL',
  description:
    'An interactive guide to how Data for Black Lives built a fine-tuned language model for racial equity analysis.',
};

export default function LearnPage() {
  return (
    <main className="min-h-screen bg-[#1a1a1a]">
      {/* Hero */}
      <section className="relative px-6 pt-24 pb-16 text-center">
        <h1 className="text-5xl md:text-6xl font-bold text-white mb-4 tracking-tight">
          Building AI That Centers Community
        </h1>
        <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-8">
          How Data for Black Lives built a fine-tuned language model that treats
          racial equity as the starting point, not an afterthought.
        </p>
        <div className="mx-auto w-24 h-1 bg-gradient-to-r from-[#00ff32] to-[#00cc28] rounded-full" />
      </section>

      {/* Section: What is a Language Model? */}
      <ConceptSection
        title="What is a Language Model?"
        subtitle="The basics, grounded in our mission"
      >
        <p>
          A language model is software that has learned patterns from vast amounts
          of text. Given a question or prompt, it predicts what words should come
          next — generating responses that can inform, explain, and summarize.
        </p>
        <p>
          Think of it like a research assistant that has read millions of
          documents. It can synthesize information, but its perspective depends
          entirely on what it was trained on. Most models are trained on general
          internet text — which means they reflect the biases, blind spots, and
          priorities of that data.
        </p>
        <p>
          For racial equity work, this is a problem. Generic models often treat
          disparities as statistical outliers rather than systemic patterns. They
          lack the context to connect a mortality rate to redlining, or a poverty
          statistic to policy failure.{' '}
          <span className="text-[#00ff32] font-semibold">
            That's why we built our own.
          </span>
        </p>
      </ConceptSection>

      {/* Section: Why Fine-Tune? */}
      <ConceptSection
        title="Why Fine-Tune?"
        subtitle="Why generic AI fails racial equity analysis"
      >
        <p>
          Fine-tuning means taking a pre-trained model and teaching it your
          specific domain — your data, your methodology, your values. Instead of
          starting from scratch, you build on what the model already knows and
          sharpen it for your work.
        </p>
        <div className="grid md:grid-cols-2 gap-6 mt-6">
          <div className="bg-[#292929] border border-[#404040] rounded-lg p-6">
            <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wide mb-3">
              Generic Model
            </h3>
            <p className="text-gray-400 text-sm">
              &quot;The maternal mortality rate shows racial disparities, with
              Black women experiencing higher rates. Various socioeconomic factors
              may contribute to this difference.&quot;
            </p>
          </div>
          <div className="bg-[#292929] border border-[#00ff32]/30 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-[#00ff32] uppercase tracking-wide mb-3">
              D4BL Model
            </h3>
            <p className="text-gray-400 text-sm">
              &quot;Black maternal mortality in Alabama (55.3 per 100k) is 2.1x
              the white rate — a disparity rooted in decades of hospital closures
              in Black communities, Medicaid coverage gaps, and documented patterns
              of provider bias. The Momnibus Act directly targets these structural
              drivers.&quot;
            </p>
          </div>
        </div>
      </ConceptSection>

      {/* Placeholder for interactive components — Tasks 3-8 will add them here */}
    </main>
  );
}
```

- [ ] **Step 2: Add "Learn" link to NavBar**

In `ui-nextjs/components/NavBar.tsx`, add a Learn link after the "Explore Data" link:

```tsx
<Link href="/learn" className="text-sm text-gray-300 hover:text-[#00ff32] transition-colors">
  Learn
</Link>
```

Place it immediately after the Explore Data `<Link>` and before the `{isAdmin && (` block.

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds. The /learn route should appear in the build output.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/app/learn/page.tsx ui-nextjs/components/NavBar.tsx
git commit -m "feat(learn): add /learn page scaffold with hero and nav link"
```

---

## Task 3: LoRAVisualizer

**Files:**
- Create: `ui-nextjs/components/learn/LoRAVisualizer.tsx`
- Modify: `ui-nextjs/app/learn/page.tsx` (add import + section)

- [ ] **Step 1: Create LoRAVisualizer component**

```tsx
'use client';

import { useState } from 'react';

const HIDDEN_DIM = 3072; // Qwen2.5-3B
const BASE_PARAMS = 3_000_000_000;

const VRAM_TABLE: Record<number, string> = {
  4: '~0.1 GB',
  8: '~0.2 GB',
  16: '~0.4 GB',
  32: '~0.8 GB',
  64: '~1.5 GB',
};

function formatParams(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function nearestVram(rank: number): string {
  const keys = Object.keys(VRAM_TABLE).map(Number).sort((a, b) => a - b);
  let closest = keys[0];
  for (const k of keys) {
    if (Math.abs(k - rank) <= Math.abs(closest - rank)) closest = k;
  }
  return VRAM_TABLE[closest];
}

export default function LoRAVisualizer() {
  const [rank, setRank] = useState(16);

  const adapterParams = 2 * rank * HIDDEN_DIM;
  const percentage = ((adapterParams / BASE_PARAMS) * 100).toFixed(4);
  const vram = nearestVram(rank);

  // Visual: adapter width as percentage of base block (scaled for visibility)
  const adapterWidthPct = Math.max(4, (rank / 64) * 40);

  return (
    <div>
      {/* Slider */}
      <div className="mb-8">
        <label className="block text-sm text-gray-400 mb-2">
          LoRA Rank: <span className="text-white font-mono font-bold">{rank}</span>
        </label>
        <input
          type="range"
          min={4}
          max={64}
          step={4}
          value={rank}
          onChange={(e) => setRank(Number(e.target.value))}
          className="w-full accent-[#00ff32]"
          aria-label="LoRA rank slider"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>4</span>
          <span>16</span>
          <span>32</span>
          <span>48</span>
          <span>64</span>
        </div>
      </div>

      {/* Visual blocks */}
      <div className="flex items-end gap-3 mb-6 h-32">
        <div className="bg-[#404040] rounded-lg flex-1 h-full flex items-center justify-center">
          <div className="text-center">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Base Model</p>
            <p className="text-lg font-mono text-white">3B params</p>
          </div>
        </div>
        <div
          className="bg-[#00ff32]/20 border border-[#00ff32]/40 rounded-lg h-full flex items-center justify-center transition-all duration-300"
          style={{ width: `${adapterWidthPct}%`, minWidth: '60px' }}
        >
          <div className="text-center px-2">
            <p className="text-xs text-[#00ff32] uppercase tracking-wide">Adapter</p>
            <p className="text-sm font-mono text-white">{formatParams(adapterParams)}</p>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="bg-[#292929] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase mb-1">Parameters</p>
          <p className="text-lg font-mono text-white">{formatParams(adapterParams)}</p>
        </div>
        <div className="bg-[#292929] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase mb-1">% of Base</p>
          <p className="text-lg font-mono text-white">{percentage}%</p>
        </div>
        <div className="bg-[#292929] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase mb-1">VRAM Overhead</p>
          <p className="text-lg font-mono text-white">{vram}</p>
        </div>
      </div>

      {/* Callout */}
      {rank === 16 && (
        <div className="mt-4 px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] text-center">
          This is what we use — rank 16 gives strong results with minimal overhead.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add to page**

In `ui-nextjs/app/learn/page.tsx`, add the import at the top:

```tsx
import LoRAVisualizer from '@/components/learn/LoRAVisualizer';
```

Add after the "Why Fine-Tune?" ConceptSection:

```tsx
{/* Section: How LoRA Works */}
<ConceptSection
  title="How LoRA Works"
  subtitle="Small adapters, big impact"
>
  <p className="mb-6">
    LoRA (Low-Rank Adaptation) is a technique that lets you fine-tune a
    large model by training only a small set of adapter weights — leaving
    the original model frozen. Drag the slider to see how adapter size
    changes with rank.
  </p>
  <LoRAVisualizer />
</ConceptSection>
```

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/learn/LoRAVisualizer.tsx ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add LoRA rank visualizer with interactive slider"
```

---

## Task 4: QuantizationSlider

**Files:**
- Create: `ui-nextjs/components/learn/QuantizationSlider.tsx`
- Modify: `ui-nextjs/app/learn/page.tsx` (add import + section)

- [ ] **Step 1: Create QuantizationSlider component**

```tsx
'use client';

import { useState } from 'react';

interface QuantLevel {
  label: string;
  fileSize: number;  // GB
  quality: number;   // percentage
}

const LEVELS: QuantLevel[] = [
  { label: 'FP16',   fileSize: 6.2, quality: 100 },
  { label: 'Q8',     fileSize: 3.3, quality: 99 },
  { label: 'Q6_K',   fileSize: 2.5, quality: 97 },
  { label: 'Q5_K_M', fileSize: 2.1, quality: 95 },
  { label: 'Q4_K_M', fileSize: 1.8, quality: 93 },
  { label: 'Q3_K',   fileSize: 1.4, quality: 85 },
  { label: 'Q2',     fileSize: 1.1, quality: 72 },
];

const OUR_PICK = 'Q4_K_M';

function qualityColor(quality: number): string {
  if (quality >= 93) return '#00ff32';
  if (quality >= 85) return '#fbbf24';
  return '#ef4444';
}

export default function QuantizationSlider() {
  const [index, setIndex] = useState(4); // default to Q4_K_M
  const level = LEVELS[index];
  const isOurPick = level.label === OUR_PICK;

  return (
    <div>
      {/* Slider */}
      <div className="mb-8">
        <label className="block text-sm text-gray-400 mb-2">
          Quantization:{' '}
          <span className="text-white font-mono font-bold">{level.label}</span>
        </label>
        <input
          type="range"
          min={0}
          max={LEVELS.length - 1}
          step={1}
          value={index}
          onChange={(e) => setIndex(Number(e.target.value))}
          className="w-full accent-[#00ff32]"
          aria-label="Quantization level slider"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          {LEVELS.map((l) => (
            <span key={l.label}>{l.label}</span>
          ))}
        </div>
      </div>

      {/* Bar chart + quality */}
      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {/* File size bar */}
        <div className="bg-[#292929] rounded-lg p-6">
          <p className="text-xs text-gray-500 uppercase mb-3">Model File Size</p>
          <div className="relative h-8 bg-[#404040] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#00ff32]/60 rounded-full transition-all duration-300"
              style={{ width: `${(level.fileSize / 6.2) * 100}%` }}
            />
          </div>
          <p className="text-right text-lg font-mono text-white mt-2">
            {level.fileSize} GB
          </p>
        </div>

        {/* Quality indicator */}
        <div className="bg-[#292929] rounded-lg p-6">
          <p className="text-xs text-gray-500 uppercase mb-3">Quality Retained</p>
          <div className="relative h-8 bg-[#404040] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${level.quality}%`,
                backgroundColor: qualityColor(level.quality),
                opacity: 0.6,
              }}
            />
          </div>
          <p
            className="text-right text-lg font-mono mt-2"
            style={{ color: qualityColor(level.quality) }}
          >
            {level.quality}%
          </p>
        </div>
      </div>

      {/* Callout */}
      {isOurPick && (
        <div className="px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] text-center">
          This is what we use — Q4_K_M cuts the file size by 70% while keeping 93% quality.
          The sweet spot for running on a laptop or affordable GPU.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add to page**

In `ui-nextjs/app/learn/page.tsx`, add the import:

```tsx
import QuantizationSlider from '@/components/learn/QuantizationSlider';
```

Add after the LoRA section:

```tsx
{/* Section: How Quantization Works */}
<ConceptSection
  title="How Quantization Works"
  subtitle="Shrinking models without losing their minds"
>
  <p className="mb-6">
    Quantization reduces the precision of a model's numbers — from 16-bit
    floating point down to 4-bit or even 2-bit integers. Less precision means
    a smaller file and faster inference, but too aggressive and quality
    drops. Drag to explore the trade-off.
  </p>
  <QuantizationSlider />
</ConceptSection>
```

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/learn/QuantizationSlider.tsx ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add quantization slider with size/quality visualization"
```

---

## Task 5: DistillationPipeline

**Files:**
- Create: `ui-nextjs/components/learn/DistillationPipeline.tsx`
- Modify: `ui-nextjs/app/learn/page.tsx` (add import + section)

- [ ] **Step 1: Create DistillationPipeline component**

```tsx
'use client';

import { useState, useEffect, useCallback } from 'react';

interface Stage {
  title: string;
  description: string;
  example: string;
}

const STAGES: Stage[] = [
  {
    title: 'Real Data',
    description:
      'Actual metrics from D4BL\'s 17 data sources — CDC, Census, EPA, FBI, and more.',
    example:
      '{"metric": "maternal_mortality_rate", "black": 55.3, "white": 26.6, "state": "AL"}',
  },
  {
    title: 'Distillation Prompt',
    description:
      'A structured prompt that teaches the model D4BL\'s methodology and values.',
    example:
      '"Explain this health disparity using D4BL\'s framework. Include structural context, data limitations, and policy connections."',
  },
  {
    title: 'Claude API',
    description:
      'A large, capable model generates a high-quality training response.',
    example:
      '"The maternal mortality rate for Black women in Alabama (55.3 per 100k) is 2.1x the rate for white women, reflecting decades of hospital closures in Black communities..."',
  },
  {
    title: 'Training Pair',
    description:
      'The final instruction/response pair used to fine-tune the small model.',
    example:
      '{"instruction": "Explain maternal mortality disparities in AL", "response": "...", "register": "community"}',
  },
];

export default function DistillationPipeline() {
  const [activeStep, setActiveStep] = useState(0);
  const [playing, setPlaying] = useState(false);

  const advance = useCallback(() => {
    setActiveStep((prev) => (prev + 1) % STAGES.length);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(advance, 3000);
    return () => clearInterval(timer);
  }, [playing, advance]);

  return (
    <div>
      {/* Pipeline steps */}
      <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2">
        {STAGES.map((stage, i) => (
          <div key={stage.title} className="flex items-center">
            <button
              onClick={() => { setActiveStep(i); setPlaying(false); }}
              className={`flex-shrink-0 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-300 ${
                i === activeStep
                  ? 'bg-[#00ff32]/20 border border-[#00ff32] text-[#00ff32]'
                  : 'bg-[#292929] border border-[#404040] text-gray-400 hover:border-gray-500'
              }`}
              aria-label={`Step ${i + 1}: ${stage.title}`}
            >
              <span className="block text-xs text-gray-500 mb-0.5">Step {i + 1}</span>
              {stage.title}
            </button>
            {i < STAGES.length - 1 && (
              <svg className="w-6 h-6 text-gray-600 flex-shrink-0 mx-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            )}
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="flex gap-3 mb-6">
        <button
          onClick={() => setPlaying(!playing)}
          className="px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors"
          aria-label={playing ? 'Pause auto-advance' : 'Play auto-advance'}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <button
          onClick={() => { setActiveStep((prev) => Math.max(0, prev - 1)); setPlaying(false); }}
          disabled={activeStep === 0}
          className="px-4 py-2 bg-[#292929] border border-[#404040] rounded-lg text-sm text-gray-400 hover:text-white disabled:opacity-30 transition-colors"
          aria-label="Previous step"
        >
          Prev
        </button>
        <button
          onClick={() => { setActiveStep((prev) => Math.min(STAGES.length - 1, prev + 1)); setPlaying(false); }}
          disabled={activeStep === STAGES.length - 1}
          className="px-4 py-2 bg-[#292929] border border-[#404040] rounded-lg text-sm text-gray-400 hover:text-white disabled:opacity-30 transition-colors"
          aria-label="Next step"
        >
          Next
        </button>
      </div>

      {/* Detail panel */}
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-6">
        <p className="text-gray-300 mb-4">{STAGES[activeStep].description}</p>
        <pre className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 text-sm text-gray-400 overflow-x-auto whitespace-pre-wrap font-mono">
          {STAGES[activeStep].example}
        </pre>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add to page**

Import:
```tsx
import DistillationPipeline from '@/components/learn/DistillationPipeline';
```

Add after the Quantization section:

```tsx
{/* Section: Training Data & Distillation */}
<ConceptSection
  title="Training Data & Distillation"
  subtitle="How we create high-quality training data from real equity metrics"
>
  <p className="mb-6">
    We can't just fine-tune on raw data — we need instruction/response pairs
    that teach the model how to think about equity. We use a process called
    distillation: a larger model (Claude) generates expert-level responses
    from our real data, creating training examples for the smaller model.
  </p>
  <DistillationPipeline />
</ConceptSection>
```

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/learn/DistillationPipeline.tsx ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add distillation pipeline step-through animation"
```

---

## Task 6: MethodologyWheel

**Files:**
- Create: `ui-nextjs/components/learn/MethodologyWheel.tsx`
- Modify: `ui-nextjs/app/learn/page.tsx` (add import + section)

- [ ] **Step 1: Create MethodologyWheel component**

This is the most complex component — an SVG circle divided into 5 segments with click interaction and keyboard accessibility.

```tsx
'use client';

import { useState } from 'react';

interface MethodologyStage {
  name: string;
  color: string;
  d4bl: string;
  ai: string;
}

const STAGES: MethodologyStage[] = [
  {
    name: 'Community Engagement',
    color: '#00ff32',
    d4bl: 'Centering the voices and needs of Black communities in data work.',
    ai: 'Training data includes community-voiced queries. The register system makes model outputs accessible to non-technical audiences. Community feedback becomes future training data.',
  },
  {
    name: 'Problem Identification',
    color: '#00cc28',
    d4bl: 'Using data to name and frame injustice as communities experience it.',
    ai: 'The query parser recognizes community problem framings — like "Why can\'t our kids breathe clean air?" — and maps them to the right data sources and metrics.',
  },
  {
    name: 'Data Collection & Analysis',
    color: '#00a320',
    d4bl: 'Gathering and interpreting data through an equity lens.',
    ai: 'The explainer adapter adds structural context and data limitations to every narrative. It acknowledges collection biases rather than presenting data as neutral truth.',
  },
  {
    name: 'Policy Innovation',
    color: '#008a1b',
    d4bl: 'Translating analysis into concrete policy recommendations.',
    ai: 'The policy_connections field maps every metric to relevant policy levers and legislation — turning data into actionable information for advocates.',
  },
  {
    name: 'Power Building',
    color: '#007116',
    d4bl: 'Equipping communities with tools and knowledge to drive change.',
    ai: 'The model is open-source. These educational resources, accessible outputs, and the register system all return analytical power to communities.',
  },
];

// Generate SVG arc path for a segment of a circle
function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle <= 180 ? 0 : 1;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

export default function MethodologyWheel() {
  const [selected, setSelected] = useState<number | null>(null);

  const cx = 150, cy = 150, r = 130;
  const segmentAngle = 360 / STAGES.length;

  return (
    <div>
      <div className="flex justify-center mb-8">
        <svg viewBox="0 0 300 300" className="w-72 h-72 md:w-80 md:h-80" role="group" aria-label="D4BL Methodology Wheel">
          {STAGES.map((stage, i) => {
            const startAngle = i * segmentAngle;
            const endAngle = (i + 1) * segmentAngle;
            const isSelected = selected === i;
            // Label position: midpoint of arc
            const midAngle = startAngle + segmentAngle / 2;
            const labelPos = polarToCartesian(cx, cy, r * 0.65, midAngle);

            return (
              <g key={stage.name}>
                <path
                  d={describeArc(cx, cy, r, startAngle, endAngle)}
                  fill={stage.color}
                  fillOpacity={isSelected ? 0.4 : 0.15}
                  stroke={isSelected ? '#00ff32' : stage.color}
                  strokeWidth={isSelected ? 3 : 1}
                  className="cursor-pointer transition-all duration-200"
                  onClick={() => setSelected(isSelected ? null : i)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(isSelected ? null : i); } }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${stage.name} — click to learn more`}
                  aria-pressed={isSelected}
                />
                <text
                  x={labelPos.x}
                  y={labelPos.y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-gray-300 text-[9px] pointer-events-none select-none"
                  aria-hidden="true"
                >
                  {stage.name.length > 18
                    ? stage.name.split(' ').reduce<string[]>((lines, word) => {
                        const last = lines[lines.length - 1];
                        if (last && last.length + word.length < 16) {
                          lines[lines.length - 1] = `${last} ${word}`;
                        } else {
                          lines.push(word);
                        }
                        return lines;
                      }, []).map((line, li) => (
                        <tspan key={li} x={labelPos.x} dy={li === 0 ? '-0.3em' : '1.1em'}>
                          {line}
                        </tspan>
                      ))
                    : stage.name}
                </text>
              </g>
            );
          })}
          {/* Center text */}
          {selected === null && (
            <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" className="fill-gray-500 text-xs">
              Click a stage
            </text>
          )}
        </svg>
      </div>

      {/* Detail panel */}
      {selected !== null && (
        <div className="bg-[#292929] border border-[#00ff32]/30 rounded-lg p-6 transition-all duration-300">
          <h3 className="text-lg font-semibold text-[#00ff32] mb-3">
            {STAGES[selected].name}
          </h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                In D4BL&apos;s Work
              </p>
              <p className="text-gray-300 text-sm">{STAGES[selected].d4bl}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                In the AI Model
              </p>
              <p className="text-gray-300 text-sm">{STAGES[selected].ai}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add to page**

Import:
```tsx
import MethodologyWheel from '@/components/learn/MethodologyWheel';
```

Add after the Distillation section:

```tsx
{/* Section: D4BL Methodology in AI */}
<ConceptSection
  title="D4BL Methodology in AI"
  subtitle="How each stage of our work maps to the model"
>
  <p className="mb-6">
    D4BL&apos;s methodology isn&apos;t just a framework we reference — it&apos;s embedded
    in how the model was trained, what it generates, and who it serves. Click
    each stage to see the connection.
  </p>
  <MethodologyWheel />
</ConceptSection>
```

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/learn/MethodologyWheel.tsx ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add interactive methodology wheel with SVG segments"
```

---

## Task 7: RegisterComparison

**Files:**
- Create: `ui-nextjs/components/learn/RegisterComparison.tsx`
- Modify: `ui-nextjs/app/learn/page.tsx` (add import + section)

- [ ] **Step 1: Create RegisterComparison component**

```tsx
'use client';

import { useState } from 'react';

type Register = 'community' | 'policy' | 'research';

const REGISTERS: { key: Register; label: string; content: string }[] = [
  {
    key: 'community',
    label: 'Community',
    content:
      'In our communities, Black mothers are dying at more than twice the rate of white mothers. This isn\'t about individual choices — it\'s about a healthcare system that doesn\'t listen to Black women. When we say "believe Black women," the data backs us up.',
  },
  {
    key: 'policy',
    label: 'Policy',
    content:
      'The Black maternal mortality rate (55.3 per 100,000 live births) is 2.6 times the white rate (21.3 per 100,000). This disparity persists after controlling for income, education, and insurance status, indicating systemic factors. The Momnibus Act (H.R. 959) addresses several contributing factors including implicit bias training and postpartum Medicaid extension.',
  },
  {
    key: 'research',
    label: 'Research',
    content:
      'Racial disparities in maternal mortality (RR = 2.6, 95% CI: 2.3\u20132.9) remain statistically significant after adjustment for socioeconomic confounders (aOR = 2.1, p < 0.001). Weathering theory (Geronimus, 1992) and allostatic load frameworks suggest cumulative physiological stress from structural racism as a primary mechanism. Sample limitations include underreporting in rural counties and inconsistent race/ethnicity classification across vital records systems.',
  },
];

export default function RegisterComparison() {
  const [active, setActive] = useState<Register>('community');
  const current = REGISTERS.find((r) => r.key === active)!;

  return (
    <div>
      {/* Banner */}
      <p className="text-center text-sm text-gray-500 mb-6 italic">
        Same data, different audiences
      </p>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-[#292929] rounded-lg p-1" role="tablist">
        {REGISTERS.map((reg) => (
          <button
            key={reg.key}
            role="tab"
            aria-selected={active === reg.key}
            aria-controls={`tabpanel-${reg.key}`}
            onClick={() => setActive(reg.key)}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
              active === reg.key
                ? 'bg-[#00ff32]/20 text-[#00ff32] border border-[#00ff32]/30'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {reg.label}
          </button>
        ))}
      </div>

      {/* Content panel */}
      <div
        id={`tabpanel-${active}`}
        role="tabpanel"
        className="bg-[#292929] border border-[#404040] rounded-lg p-6"
      >
        <p className="text-gray-300 leading-relaxed">{current.content}</p>
      </div>

      {/* Metric label */}
      <p className="text-center text-xs text-gray-600 mt-4">
        Metric: Black maternal mortality rate (2.6x disparity)
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Add to page**

Import:
```tsx
import RegisterComparison from '@/components/learn/RegisterComparison';
```

Add after the Methodology section:

```tsx
{/* Section: From Data to Justice */}
<ConceptSection
  title="From Data to Justice"
  subtitle="The same data, told three ways"
>
  <p className="mb-6">
    Our model doesn&apos;t just analyze data — it communicates findings in the
    register that serves each audience best. Community members, policymakers,
    and researchers all need different framings of the same truth.
  </p>
  <RegisterComparison />
</ConceptSection>
```

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/learn/RegisterComparison.tsx ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add register comparison tabs (community/policy/research)"
```

---

## Task 8: TutorialStep + PlaygroundPlaceholder

**Files:**
- Create: `ui-nextjs/components/learn/TutorialStep.tsx`
- Create: `ui-nextjs/components/learn/PlaygroundPlaceholder.tsx`
- Modify: `ui-nextjs/app/learn/page.tsx` (add imports + sections)

- [ ] **Step 1: Create TutorialStep component**

```tsx
interface Props {
  step: number;
  title: string;
  description: string;
  colabUrl: string;
}

export default function TutorialStep({ step, title, description, colabUrl }: Props) {
  return (
    <div className="bg-[#292929] border border-[#404040] rounded-lg p-6 flex flex-col">
      <div className="flex items-center gap-3 mb-3">
        <span className="flex-shrink-0 w-8 h-8 rounded-full bg-[#00ff32]/20 text-[#00ff32] text-sm font-bold flex items-center justify-center">
          {step}
        </span>
        <h3 className="text-white font-semibold">{title}</h3>
      </div>
      <p className="text-gray-400 text-sm flex-1 mb-4">{description}</p>
      <a
        href={colabUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors self-start"
      >
        Open in Colab
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      </a>
    </div>
  );
}
```

- [ ] **Step 2: Create PlaygroundPlaceholder component**

```tsx
export default function PlaygroundPlaceholder() {
  return (
    <div className="relative">
      {/* Mock chat interface */}
      <div className="bg-[#292929] border border-[#404040] rounded-lg overflow-hidden">
        {/* Header bar */}
        <div className="bg-[#1a1a1a] px-4 py-2 border-b border-[#404040] flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/50" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/50" />
          <div className="w-3 h-3 rounded-full bg-green-500/50" />
          <span className="text-xs text-gray-500 ml-2">D4BL Model Playground</span>
        </div>

        {/* Mock prompt */}
        <div className="p-6">
          <div className="bg-[#1a1a1a] rounded-lg p-4 mb-4">
            <p className="text-sm text-gray-400">
              <span className="text-[#00ff32]">$</span> What does maternal
              mortality data tell us about Birmingham, AL?
            </p>
          </div>

          {/* Blurred response */}
          <div className="bg-[#1a1a1a] rounded-lg p-4 blur-sm select-none" aria-hidden="true">
            <p className="text-sm text-gray-400">
              Birmingham&apos;s maternal mortality data reveals significant disparities
              rooted in decades of healthcare infrastructure disinvestment. The
              Black maternal mortality rate in Jefferson County is 3.1x the white
              rate, with contributing factors including hospital closures in
              predominantly Black neighborhoods, Medicaid coverage gaps, and
              documented patterns of provider bias...
            </p>
          </div>
        </div>
      </div>

      {/* Coming Soon overlay */}
      <div className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg">
        <div className="text-center">
          <span className="inline-block px-4 py-2 bg-[#00ff32]/20 border border-[#00ff32] rounded-full text-[#00ff32] font-semibold text-sm mb-3">
            Coming Soon
          </span>
          <p className="text-gray-400 text-sm max-w-xs">
            Interactive model comparison, custom queries, and export results.
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add both to page**

Imports:
```tsx
import TutorialStep from '@/components/learn/TutorialStep';
import PlaygroundPlaceholder from '@/components/learn/PlaygroundPlaceholder';
```

Add after the RegisterComparison section:

```tsx
{/* Section: Try It Yourself */}
<ConceptSection
  title="Try It Yourself"
  subtitle="Guided tutorials to build your own equity-focused model"
>
  <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4 mt-2">
    <TutorialStep
      step={1}
      title="Understanding Your Data"
      description="Query Supabase and see the shape of equity data."
      colabUrl="#"
    />
    <TutorialStep
      step={2}
      title="Creating Training Data"
      description="Write distillation prompts and generate training pairs."
      colabUrl="#"
    />
    <TutorialStep
      step={3}
      title="Training with Unsloth"
      description="Load the model, configure LoRA, and run training."
      colabUrl="#"
    />
    <TutorialStep
      step={4}
      title="Testing Your Model"
      description="Load in Ollama and compare outputs to the base model."
      colabUrl="#"
    />
    <TutorialStep
      step={5}
      title="Making It Your Own"
      description="Customize the model for your community's data."
      colabUrl="#"
    />
  </div>
</ConceptSection>

{/* Section: What's Next */}
<ConceptSection
  title="What's Next"
  subtitle="The playground is coming"
>
  <p className="mb-6">
    We&apos;re building an interactive playground where you can query the D4BL
    model directly, compare outputs across registers, and export results
    for your own analysis.
  </p>
  <PlaygroundPlaceholder />
</ConceptSection>
```

- [ ] **Step 4: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds. All /learn components render without errors.

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/components/learn/TutorialStep.tsx ui-nextjs/components/learn/PlaygroundPlaceholder.tsx ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): add tutorial steps and playground placeholder"
```

---

## Task 9: Final build + lint check

**Files:** None (verification only)

- [ ] **Step 1: Run full build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds with no errors. The /learn route appears in the output.

- [ ] **Step 2: Run lint**

Run: `cd ui-nextjs && npm run lint`
Expected: No lint errors.

- [ ] **Step 3: Fix any issues found**

If the build or lint fail, fix the issues and commit the fixes.

- [ ] **Step 4: Visual smoke test**

Run: `cd ui-nextjs && npm run dev`
Open `http://localhost:3000/learn` and verify:
- Hero renders with heading and green accent line
- All 8 concept sections appear on scroll
- LoRA slider moves and updates stats
- Quantization slider changes bar chart and quality indicator
- Pipeline play/pause works, steps are clickable
- Methodology wheel segments are clickable, detail panel appears
- Register tabs switch content
- Tutorial cards render in grid
- Playground shows blurred response with Coming Soon overlay
- NavBar has "Learn" link
- Page is responsive on narrow viewport

- [ ] **Step 5: Commit any final fixes**

Stage only the specific files that were fixed, then commit:

```bash
git add <fixed-files>
git commit -m "fix(learn): final build and lint fixes"
```

Only commit this step if there were actually fixes to make.
