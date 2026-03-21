# D4BL Fine-Tuned Language Model — Product Requirements Document

**Date:** 2026-03-21
**Status:** Draft
**Author:** D4BL Engineering
**Design Spec:** [2026-03-21-fine-tuned-model-design.md](./2026-03-21-fine-tuned-model-design.md)

---

## Executive Summary

D4BL will train a small, domain-specialized language model that embeds our methodology — centering community voice, naming structural causes of racial disparities, connecting findings to policy action, and honestly acknowledging data limitations. This model replaces generic LLM calls in the D4BL research platform with faster, cheaper, more aligned inference.

The model is not just technically fine-tuned — it is **methodologically aligned** with D4BL's theory of change: Community Engagement → Problem Identification → Data Collection + Analysis → Policy Innovation → Power Building → (repeat).

---

## Goals & Success Metrics

### Primary Goals

1. **Domain Specialization (Priority 1):** A model that deeply understands racial equity terminology, data source schemas, FIPS codes, racial categories, and structural framing — producing outputs that align with D4BL's methodology.

2. **Cost Reduction (Priority 2):** Production inference under $30/month, down from variable API costs or heavy local compute.

3. **Latency Improvement (Priority 3):** P95 response time under 1 second for query parsing, under 3 seconds for narrative generation.

4. **On-Device Capability (Priority 4):** A 1.5B sibling model that runs on modern smartphones for offline-capable query parsing.

### Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| D4BL composite alignment score | >3.5/5.0 | Evaluator adapter on held-out test set |
| Query parser entity F1 | >0.85 | Automated eval against gold-standard test set |
| Community framing detection F1 | >0.70 | Automated eval on community-voiced queries |
| Explainer factual accuracy | >90% | Manual verification against source data |
| Production inference cost | <$30/month | RunPod billing at expected traffic |
| P95 query parser latency | <1000ms | Automated latency measurement |
| P95 explainer latency | <3000ms | Automated latency measurement |
| JSON validity rate | >95% | Automated parsing check |
| Mobile query parser latency | <3s on iPhone 15+ | On-device benchmarking |

---

## User Stories

### Community Organizers

> "As a community organizer, I can ask questions about my community in plain language — 'Why are our kids getting suspended instead of taught?' — and get an answer that names the structural causes, connects to policy, and is written for community members, not academics."

### Policy Researchers

> "As a policy researcher, I can request data explanations in a policy-brief register that includes specific policy levers, relevant legislation, and properly cited methodology notes."

### D4BL Platform Users

> "As a platform user, I get faster, more accurate responses that center my community's experience. The model understands terms like 'environmental justice,' 'disparity ratio,' and 'redlining' without needing extra context in my question."

### D4BL Engineering

> "As a developer, I can swap model names in the Ollama configuration and get domain-specialized inference without changing the API layer. The fallback to the general model is automatic."

### Mobile App Users (Future)

> "As a mobile user, I can parse equity data queries on my phone without an internet connection. Complex narratives load from the cloud when I'm online."

---

## D4BL Methodology Integration

### Community Engagement → Training Data

Training data includes questions written in community voice — the language people use in town halls, advocacy meetings, and lived experience. The model bridges between community problem descriptions and structured data sources.

### Problem Identification → Query Understanding

The query parser detects community framings and maps them to data domains:
- "Why can't we breathe in our neighborhood?" → Environmental justice + PM2.5 + EPA data
- "Our kids are getting suspended, not taught" → DOE discipline data by race
- "They're pushing us out of our homes" → Eviction + HUD fair housing data

### Data Collection + Analysis → Structural Context

Every narrative includes structural_context (historical and systemic causes) and data_limitations (collection biases, methodology gaps). The model never frames disparities as innate or cultural.

### Policy Innovation → Actionable Output

The explainer connects metrics to specific policy levers and relevant legislation from the policy_bills table. Output moves beyond "more research needed" to concrete interventions.

### Power Building → Community Tool

- Open-source models on Hugging Face
- Educational /learn page with interactive explainers
- Guided Colab tutorials for community capacity building
- Register system makes data accessible to all audiences
- Community feedback directly improves the model via retraining

### The Cycle → Feedback Loop

Community members flag outputs → corrections become training data → retrain adapter → deploy → community uses improved tool → repeat.

---

## Technical Architecture

### Model Stack

| Component | Model | Size | Purpose |
|-----------|-------|------|---------|
| Query Parser | Qwen2.5-3B + LoRA (rank 8) | 1.8GB | NL → structured intent JSON |
| Data Explainer | Qwen2.5-3B + LoRA (rank 32) | 1.8GB | Metrics → equity narrative JSON |
| Evaluator | Qwen2.5-3B + LoRA (rank 16) | 1.8GB | Content → quality/alignment scores |
| Mobile Parser | Qwen2.5-1.5B + LoRA (rank 8) | 0.9GB | On-device query parsing |
| General Agent | mistral (existing) | 4.1GB | CrewAI research pipeline (fallback) |
| Embeddings | mxbai-embed-large (existing) | 0.7GB | Vector search (unchanged) |

### Training Infrastructure

- **Platform:** Google Colab (free T4 GPU)
- **Framework:** Unsloth + LoRA/QLoRA
- **Data:** Distillation from Claude using Supabase data
- **Format:** ChatML JSONL → GGUF Q4_K_M

### Deployment

- **Local:** Ollama (same API as current setup)
- **Cloud:** RunPod Serverless ($5-25/month) or dedicated A4000 ($24-144/month)
- **Mobile:** llama.cpp via Swift/Kotlin bindings
- **Registry:** Hugging Face Hub (versioned model cards)

---

## Phased Rollout

### Phase 1: MVP (3-5 days)

**Scope:**
- Extract domain corpus from Supabase (50K passages)
- Generate query parser training data via Claude (300 pairs)
- Continued pre-training on domain corpus
- Train query parser LoRA adapter
- Build automated eval pipeline (comparison script)
- Validate against ship criteria

**Deliverables:**
- `d4bl-query-parser-q4_k_m.gguf`
- `scripts/eval_fine_tuned_model.py`
- Training data JSONL files
- Eval comparison report

### Phase 2: Full Adapter Suite (1 week)

**Scope:**
- Generate explainer training data (300 total pairs covering all 3 registers)
- Generate evaluator training data (600 pairs × 4 tasks)
- Train explainer and evaluator adapters
- Integration with existing FastAPI endpoints
- Fallback strategy implementation

**Deliverables:**
- `d4bl-explainer-q4_k_m.gguf`
- `d4bl-evaluator-q4_k_m.gguf`
- Updated API endpoints with model routing
- Regression test suite

### Phase 3: Mobile + Education (2 weeks)

**Scope:**
- Train 1.5B sibling models for mobile
- Build `/learn` educational page with interactive components
- Create Gamma slide deck with D4BL branding
- Publish models to Hugging Face Hub
- Create Colab tutorial notebooks

**Deliverables:**
- `d4bl-query-parser-1.5b-q4_k_m.gguf`
- `/learn` page with 5 interactive components
- Gamma presentation (18 slides)
- 5 Colab tutorial notebooks
- Hugging Face model cards

### Phase 4: Playground + Feedback (Future)

**Scope:**
- Live model playground on /learn page
- A/B eval comparison UI
- Community feedback collection mechanism
- Automated retraining pipeline
- Eval dashboard for version tracking

---

## Risks & Mitigations

### Cost Estimates

| Item | Cost | Frequency |
|------|------|-----------|
| Google Colab T4 (training) | Free | Per training run |
| Google Colab Pro (backup) | $10/month | Monthly if needed |
| Claude API (distillation) | ~$15-30 | Per dataset version |
| RunPod Serverless (production) | $5-25/month | Monthly |
| Hugging Face Hub | Free (public) | Monthly |
| **Total MVP** | **~$20-55 one-time + $5-25/month** | |

### Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| Model reproduces biased framing | High | Medium | Equity alignment evaluator; D4BL-aligned training prompts; community review |
| 3B insufficient for narrative quality | Medium | Medium | Fallback to mistral; path to 7B; hybrid approach |
| Training data too small | Medium | Low | Start with 300 examples, iterate; Claude distillation scales easily |
| Cold start latency in production | Low | Medium | RunPod dedicated pod if serverless too slow |
| Mobile memory pressure | Low | Medium | 1.5B model at 0.9GB; task-limited on-device |
| Community feedback insufficient | Medium | Medium | Seed feedback with D4BL staff; integrate into existing platform workflows |
| Model versioning confusion | Low | Low | Hugging Face Hub model cards; eval result database; ship criteria gates |
| Colab free tier session limits | Medium | Medium | Training pipeline (~135 min) may exceed session; Colab Pro or local GPU backup |
| Claude distillation costs | Low | Low | Budget ~$15-30; track token usage during generation |
| Evaluator circular dependency | Medium | Low | Use Claude as judge during evaluator training; self-evaluation only in production |

---

## Educational Deliverables

### `/learn` Page

Interactive educational page teaching fine-tuning concepts through a racial equity lens. Every concept ties back to why D4BL is building this and what it means for data justice.

**Components:**
- LoRA Visualizer (interactive rank slider)
- Quantization Slider (bit depth → model size → quality)
- D4BL Methodology Wheel (clickable stage → AI connection)
- Distillation Pipeline (step-through animation)
- Register Comparison (tab toggle: community/policy/research)

### Gamma Slide Deck

18-slide presentation for stakeholders, funders, and community partners. Dark theme with D4BL neon green accents. Emphasizes methodology alignment and community benefit.

### Colab Tutorial Notebooks

5-step guided tutorial:
1. Understanding Your Data
2. Creating Training Data
3. Training with Unsloth
4. Testing Your Model
5. Making It Your Own

### Open-Source Models

Published to Hugging Face Hub with full model cards documenting training data, methodology, metrics, and limitations.

---

## Dependencies

- Google Colab (free tier) — training infrastructure
- Hugging Face Hub — model hosting and versioning
- Claude API — training data generation via distillation
- Supabase — source data for corpus and training pairs
- RunPod — production GPU inference
- Ollama — local and cloud inference runtime

---

## Out of Scope (This Phase)

- Full mobile app development (mobile model is a building block)
- Real-time model retraining pipeline (manual retraining for now)
- Multi-language support (English only initially)
- Replacing CrewAI agents with fine-tuned models
- Custom tokenizer training
- RLHF or DPO alignment (LoRA SFT only)
