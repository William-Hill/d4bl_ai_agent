# `/learn` Educational Page — Design Spec

**Date:** 2026-03-26
**Sprint:** 5 — Educational Page
**Status:** Draft
**Branch:** `feat/learn-page`

---

## Overview

A single-page, fully static educational experience at `/learn` teaching fine-tuning concepts through a racial equity lens. Every concept ties back to why D4BL built a custom model and what it means for data justice. No API calls, no auth required — this is a public showcase page.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Content source | Fully static | No backend dependency, works offline, ships faster |
| Scroll behavior | Intersection Observer | Zero dependencies, CSS transitions for fade/slide-in |
| Visual theme | Dark with D4BL neon green (#00ff32) | Matches existing app aesthetic, leaned into harder for showcase feel |
| Page structure | Monolithic scrollable | Storytelling narrative flows better than fragmented sub-pages |
| Auth | None | Public-facing showcase, accessible to all visitors |
| Animation library | None | Intersection Observer + CSS transitions are sufficient |
| RunPod deployment | Separate ticket | Independent work, different scope |

## Page Structure

Sections in scroll order:

### 1. Hero

Full-width banner with heading "Building AI That Centers Community" and a tagline about D4BL's fine-tuned model. Neon green gradient accent line below the heading. Large typography, generous whitespace. No image.

### 2. What is a Language Model?

`ConceptSection` wrapper with prose explaining LLMs in plain, accessible terms, grounded in D4BL's mission. No interactive component — just well-written educational content.

### 3. Why Fine-Tune?

`ConceptSection` with prose on why generic models fail for racial equity analysis. Includes a static side-by-side text comparison: generic model output vs D4BL model output for the same question, illustrating the difference domain specialization makes.

### 4. How LoRA Works

`LoRAVisualizer` interactive component (see Component Specs below).

### 5. How Quantization Works

`QuantizationSlider` interactive component (see Component Specs below).

### 6. Training Data & Distillation

`DistillationPipeline` step-through animation (see Component Specs below).

### 7. D4BL Methodology in AI

`MethodologyWheel` clickable wheel (see Component Specs below).

### 8. From Data to Justice

`RegisterComparison` tab toggle (see Component Specs below).

### 9. Try It Yourself

Grid of `TutorialStep` cards linking to the 5 Colab notebooks (see Component Specs below).

### 10. What's Next

`PlaygroundPlaceholder` teasing the interactive playground with a brief roadmap of upcoming features.

## Component Specs

### ConceptSection

Reusable wrapper for prose content sections. Provides consistent spacing, typography, and scroll-triggered fade-in animation.

**Props:**
- `title: string` — section heading
- `subtitle?: string` — optional subheading
- `children: ReactNode` — prose content and/or interactive component

**Behavior:**
- Starts with `opacity: 0; transform: translateY(20px)`
- Intersection Observer triggers transition to `opacity: 1; transform: translateY(0)` when element enters viewport (threshold: 0.1)
- Once visible, stays visible (observe once)

### LoRAVisualizer

Interactive visualization of how LoRA adapters work.

**UI:**
- Horizontal slider: rank 4 → 64
- Visual: a large "Base Model" block alongside a proportionally-sized "Adapter" block
- Live-updating text: adapter parameter count, percentage of base model, VRAM estimate

**Logic (all hardcoded, no API):**
- `adapter_params = 2 * rank * hidden_dim` where `hidden_dim = 3072` (Qwen2.5-3B)
- `percentage = adapter_params / total_base_params * 100` where `total_base_params = 3_000_000_000`
- VRAM estimates mapped to rank ranges
- Default slider position: rank 16 (what D4BL actually uses)
- Callout at rank 16: "This is what we use"

### QuantizationSlider

Interactive visualization of quantization trade-offs.

**UI:**
- Horizontal slider: 16-bit → 2-bit (discrete stops: FP16, Q8, Q6_K, Q5_K_M, Q4_K_M, Q3_K, Q2)
- Bar chart showing model file size at the selected bit depth
- Quality indicator: green → yellow → red gradient bar
- Callout highlighting Q4_K_M as "what we use" with brief explanation

**Hardcoded values:**

| Format | File Size | Quality |
|--------|-----------|---------|
| FP16 | 6.2 GB | 100% |
| Q8 | 3.3 GB | 99% |
| Q6_K | 2.5 GB | 97% |
| Q5_K_M | 2.1 GB | 95% |
| Q4_K_M | 1.8 GB | 93% |
| Q3_K | 1.4 GB | 85% |
| Q2 | 1.1 GB | 72% |

### MethodologyWheel

Interactive SVG wheel mapping D4BL's 5 methodology stages to AI model connections.

**UI:**
- SVG circle divided into 5 colored segments
- Center text (default): "Click a stage to explore"
- Click a segment → expands a detail panel below with: stage name, D4BL context, AI model connection
- Selected segment gets neon green border highlight

**Stages and mapping (draft copy, to be replaced by D4BL leadership):**

| Stage | D4BL Context | AI Connection |
|-------|-------------|---------------|
| Community Engagement | Centering the voices and needs of Black communities in data work | Training data includes community-voiced queries; register system makes outputs accessible; community feedback becomes training data |
| Problem Identification | Using data to name and frame injustice as communities experience it | Query parser recognizes community problem framings ("Why can't our kids breathe clean air?") and maps to data sources |
| Data Collection & Analysis | Gathering and interpreting data through an equity lens | Explainer adds structural context and data limitations to every narrative; acknowledges collection biases |
| Policy Innovation | Translating analysis into concrete policy recommendations | Policy connections field maps metrics to policy levers and relevant legislation |
| Power Building | Equipping communities with tools and knowledge to drive change | Open-source model, educational resources, and accessible outputs return power to communities |

### DistillationPipeline

Step-through animation showing how training data is created.

**UI:**
- Horizontal pipeline with 4 connected stages: Real Data → Distillation Prompt → Claude API → Training Pair
- Play/pause button for auto-advance (3 second intervals)
- Manual next/prev buttons
- Active stage is highlighted with neon green
- Description text below updates per stage
- Example snippet per stage

**Stages:**

| # | Stage | Description | Example Snippet |
|---|-------|-------------|-----------------|
| 1 | Real Data | Actual metrics from D4BL's 17 data sources | `{"metric": "maternal_mortality_rate", "black": 55.3, "white": 26.6, "state": "AL"}` |
| 2 | Distillation Prompt | Structured prompt that teaches the model D4BL's methodology | `"Explain this health disparity using D4BL's framework. Include structural context and policy connections."` |
| 3 | Claude API | Large model generates high-quality training response | `"The maternal mortality rate for Black women in Alabama (55.3 per 100k) is 2.1x the rate for white women..."` |
| 4 | Training Pair | Final instruction/response pair for fine-tuning | `{"instruction": "Explain maternal mortality disparities in AL", "response": "...", "register": "community"}` |

### RegisterComparison

Tab toggle showing the same data in three audience registers.

**UI:**
- Three tabs: Community, Policy, Research
- Content panel below shows the same metric written in the selected register
- Subtle banner: "Same data, different audiences"
- Active tab has neon green underline

**Example metric:** Black maternal mortality is 2.6x the white rate.

**Register content (draft):**

- **Community:** "In our communities, Black mothers are dying at more than twice the rate of white mothers. This isn't about individual choices — it's about a healthcare system that doesn't listen to Black women. When we say 'believe Black women,' the data backs us up."

- **Policy:** "The Black maternal mortality rate (55.3 per 100,000 live births) is 2.6 times the white rate (21.3 per 100,000). This disparity persists after controlling for income, education, and insurance status, indicating systemic factors. The Momnibus Act (H.R. 959) addresses several contributing factors including implicit bias training and postpartum Medicaid extension."

- **Research:** "Racial disparities in maternal mortality (RR = 2.6, 95% CI: 2.3–2.9) remain statistically significant after adjustment for socioeconomic confounders (aOR = 2.1, p < 0.001). Weathering theory (Geronimus, 1992) and allostatic load frameworks suggest cumulative physiological stress from structural racism as a primary mechanism. Sample limitations include underreporting in rural counties and inconsistent race/ethnicity classification across vital records systems."

### TutorialStep

Card component for Colab notebook links.

**Props:**
- `step: number` — step number (1-5)
- `title: string` — tutorial title
- `description: string` — one-sentence description
- `colabUrl: string` — external link to Colab notebook

**UI:**
- Card with step number badge, title, description, and "Open in Colab" button
- 5 cards in a responsive grid (3 columns desktop, 2 tablet, 1 mobile)

**Tutorial steps:**

| # | Title | Description |
|---|-------|-------------|
| 1 | Understanding Your Data | Query Supabase and see the shape of equity data |
| 2 | Creating Training Data | Write distillation prompts and generate training pairs |
| 3 | Training with Unsloth | Load the model, configure LoRA, and run training |
| 4 | Testing Your Model | Load in Ollama and compare outputs to the base model |
| 5 | Making It Your Own | Customize the model for your community's data |

**Note:** Colab URLs will be placeholder links until notebooks are created. The cards should work with or without valid URLs.

### PlaygroundPlaceholder

Teaser for the future interactive model playground.

**UI:**
- Mock terminal/chat interface styled to match the app
- Shows a fake prompt: "What does maternal mortality data tell us about Birmingham, AL?"
- Blurred/frosted response text beneath
- "Coming Soon" overlay badge
- Brief text below listing upcoming features: interactive model comparison, custom queries, export results

## File Structure

```
ui-nextjs/
├── app/learn/
│   └── page.tsx                    # Page layout, section ordering, hero
├── components/learn/
│   ├── ConceptSection.tsx          # Reusable prose wrapper with scroll animation
│   ├── LoRAVisualizer.tsx          # Rank slider + adapter visualization
│   ├── QuantizationSlider.tsx      # Bit slider + size/quality chart
│   ├── MethodologyWheel.tsx        # Clickable SVG wheel
│   ├── DistillationPipeline.tsx    # Step-through animation
│   ├── RegisterComparison.tsx      # Tab toggle (community/policy/research)
│   ├── TutorialStep.tsx            # Colab notebook link card
│   └── PlaygroundPlaceholder.tsx   # Coming soon teaser
```

## Navigation Changes

Add "Learn" link to `NavBar.tsx` between "Explore Data" and the admin-only links. Visible to all users including unauthenticated visitors.

## Styling Approach

- Tailwind CSS classes throughout, consistent with the rest of the app
- Dark background (`#1a1a1a` for sections, `#292929` for page background)
- Neon green (`#00ff32`) for accents, active states, and interactive highlights
- Use existing CSS custom properties from `globals.css`
- Generous whitespace between sections (py-24 or similar)
- Large typography for hero and section headings
- Responsive: single column on mobile, components stack naturally
- Interactive sliders use native range inputs styled with Tailwind + custom CSS
- SVG for MethodologyWheel (inline, not external file)

## Out of Scope

- RunPod deployment (separate ticket)
- Live model API calls
- Embedded Colab notebooks
- Gamma slide deck generation
- Mobile 1.5B model
- Database models (ModelEvalRun, TrainingDataLineage)
- CI/CD or deployment changes
