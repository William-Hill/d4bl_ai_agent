# Tutorial Notebooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create 5 standalone Colab tutorial notebooks teaching users to build equity-focused fine-tuned models, plus update the /learn page with notebook links and the Gamma deck URL.

**Architecture:** Each notebook is a self-contained `.ipynb` file with embedded sample data, markdown explanations, and runnable code cells. No external dependencies beyond what `pip install` provides on Colab. The /learn page gets updated URLs.

**Tech Stack:** Jupyter notebooks (.ipynb), Python, pandas, matplotlib, Unsloth, transformers, Next.js (for page update)

**Spec:** `docs/superpowers/specs/2026-03-26-tutorial-notebooks-design.md`

---

## File Structure

```
notebooks/
└── tutorials/
    ├── 01_understanding_your_data.ipynb
    ├── 02_creating_training_data.ipynb
    ├── 03_training_with_unsloth.ipynb
    ├── 04_testing_your_model.ipynb
    └── 05_making_it_your_own.ipynb

ui-nextjs/
└── app/learn/page.tsx              # Updated colabUrls + Gamma deck link
```

## Notes for Implementers

- **Creating .ipynb files:** Use the Write tool to create valid ipynb JSON. An ipynb file is a JSON object with keys: `nbformat`, `nbformat_minor`, `metadata`, and `cells`. Each cell has `cell_type` ("markdown" or "code"), `source` (list of strings — each line including its `\n`), `metadata` (empty dict `{}`), and for code cells: `execution_count` (null), `outputs` (empty list `[]`).
- **Minimal ipynb structure:**
```json
{
  "nbformat": 4,
  "nbformat_minor": 5,
  "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.10.0"}
  },
  "cells": [...]
}
```
- **Cell format:** `{"cell_type": "markdown", "metadata": {}, "source": ["# Title\n", "\n", "Description"]}` — note each line is a separate string in the array, with `\n` at the end of each line except the last.
- **D4BL context:** Every notebook should frame concepts through the equity lens. Not just "here's LoRA" but "here's why LoRA matters for communities building their own AI tools."
- **Sample data:** Embed directly as Python dicts/lists in code cells. Keep it small but real — actual metric names and values from D4BL's data sources.

---

## Task 1: Notebook 1 — Understanding Your Data

**Files:**
- Create: `notebooks/tutorials/01_understanding_your_data.ipynb`

- [ ] **Step 1: Create the notebook**

Create the ipynb file with these cells in order:

**Cell 1 (markdown):** Title and badge
```
# 📊 Understanding Your Data
### D4BL Tutorial 1 of 5

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/01_understanding_your_data.ipynb)

**What you'll learn:** How equity data is structured, what disparities look like in numbers, and how D4BL organizes data from 17 federal and state sources.

**Time:** ~15 minutes | **Prerequisites:** A Google account (for Colab) | **Dependencies:** pandas, matplotlib (pre-installed)
```

**Cell 2 (markdown):** What is equity data?
```
## What is Equity Data?

Data for Black Lives works with data from 17 sources including the CDC, U.S. Census Bureau, EPA, FBI, and more. This data tracks health outcomes, economic indicators, environmental hazards, and criminal justice metrics — broken down by race, geography, and time.

**Why it matters:** Generic datasets often bury racial disparities in averages. When you break data out by race and place, patterns emerge that reflect decades of structural decisions — redlining, disinvestment, over-policing. Understanding the shape of this data is the first step toward building AI that sees these patterns instead of ignoring them.

D4BL's data sources include:

| Source | What It Covers | Example Metrics |
|--------|---------------|-----------------|
| CDC PLACES | Community health | Diabetes prevalence, mental health, preventive care |
| Census ACS | Economic indicators | Median income, poverty rate, homeownership |
| EPA EJScreen | Environmental justice | PM2.5, lead paint, proximity to hazardous waste |
| FBI UCR | Criminal justice | Arrest rates, offense types |
| BLS | Employment | Unemployment rate by race |
```

**Cell 3 (code):** Setup
```python
import pandas as pd
import matplotlib.pyplot as plt

# D4BL brand colors
D4BL_GREEN = "#00ff32"
D4BL_BG = "#292929"
D4BL_TEXT = "#e5e5e5"
```

**Cell 4 (markdown):** Exploring sample data
```
## Exploring Sample Data

Below is a small sample from three of D4BL's data sources. In the real system, this data lives in a PostgreSQL database with over 25 tables. Here we'll work with embedded samples to understand the structure.
```

**Cell 5 (code):** CDC PLACES sample data
```python
# Sample CDC PLACES data — community health metrics by state and race
cdc_data = [
    {"state": "AL", "metric": "diabetes_prevalence", "race": "black", "value": 16.8, "year": 2022},
    {"state": "AL", "metric": "diabetes_prevalence", "race": "white", "value": 11.2, "year": 2022},
    {"state": "GA", "metric": "diabetes_prevalence", "race": "black", "value": 15.9, "year": 2022},
    {"state": "GA", "metric": "diabetes_prevalence", "race": "white", "value": 10.4, "year": 2022},
    {"state": "MS", "metric": "diabetes_prevalence", "race": "black", "value": 18.1, "year": 2022},
    {"state": "MS", "metric": "diabetes_prevalence", "race": "white", "value": 12.7, "year": 2022},
    {"state": "AL", "metric": "mental_health_not_good", "race": "black", "value": 19.2, "year": 2022},
    {"state": "AL", "metric": "mental_health_not_good", "race": "white", "value": 16.8, "year": 2022},
]

cdc_df = pd.DataFrame(cdc_data)
print("CDC PLACES sample:")
cdc_df
```

**Cell 6 (code):** Census ACS sample data
```python
# Sample Census ACS data — economic indicators
census_data = [
    {"state": "AL", "metric": "median_household_income", "race": "black", "value": 35210, "year": 2022},
    {"state": "AL", "metric": "median_household_income", "race": "white", "value": 58640, "year": 2022},
    {"state": "AL", "metric": "poverty_rate", "race": "black", "value": 28.3, "year": 2022},
    {"state": "AL", "metric": "poverty_rate", "race": "white", "value": 11.5, "year": 2022},
    {"state": "GA", "metric": "median_household_income", "race": "black", "value": 42180, "year": 2022},
    {"state": "GA", "metric": "median_household_income", "race": "white", "value": 72340, "year": 2022},
    {"state": "GA", "metric": "poverty_rate", "race": "black", "value": 22.1, "year": 2022},
    {"state": "GA", "metric": "poverty_rate", "race": "white", "value": 9.8, "year": 2022},
]

census_df = pd.DataFrame(census_data)
print("Census ACS sample:")
census_df
```

**Cell 7 (code):** EPA EJScreen sample data
```python
# Sample EPA EJScreen data — environmental justice indicators
epa_data = [
    {"state": "AL", "metric": "PM25", "percentile_minority": 78, "percentile_lowinc": 72, "year": 2023},
    {"state": "AL", "metric": "lead_paint", "percentile_minority": 85, "percentile_lowinc": 80, "year": 2023},
    {"state": "GA", "metric": "PM25", "percentile_minority": 71, "percentile_lowinc": 65, "year": 2023},
    {"state": "MS", "metric": "PM25", "percentile_minority": 82, "percentile_lowinc": 79, "year": 2023},
]

epa_df = pd.DataFrame(epa_data)
print("EPA EJScreen sample:")
epa_df
```

**Cell 8 (markdown):** Spotting disparities
```
## Spotting Disparities

The most basic equity analysis: compare outcomes across racial groups. A **disparity ratio** tells you how many times worse the outcome is for one group compared to another. A ratio of 2.0 means twice as bad.

These ratios aren't random — they reflect structural conditions: which neighborhoods got investment, which communities got environmental hazards, who got access to healthcare.
```

**Cell 9 (code):** Compute disparity ratios
```python
# Compute Black/white disparity ratios for each metric and state
def compute_disparity(df, metric_name):
    """Compute the Black/white ratio for a given metric."""
    metric_df = df[df["metric"] == metric_name]
    black = metric_df[metric_df["race"] == "black"].set_index("state")["value"]
    white = metric_df[metric_df["race"] == "white"].set_index("state")["value"]
    ratio = black / white
    return ratio.round(2)

# Diabetes prevalence disparity
diabetes_ratio = compute_disparity(cdc_df, "diabetes_prevalence")
print("Diabetes prevalence — Black/white ratio by state:")
print(diabetes_ratio)
print()

# Poverty rate disparity
poverty_ratio = compute_disparity(census_df, "poverty_rate")
print("Poverty rate — Black/white ratio by state:")
print(poverty_ratio)
```

**Cell 10 (code):** Visualize
```python
# Visualize the income gap
income_df = census_df[census_df["metric"] == "median_household_income"]

fig, ax = plt.subplots(figsize=(8, 4))
fig.patch.set_facecolor(D4BL_BG)
ax.set_facecolor(D4BL_BG)

states = income_df["state"].unique()
x = range(len(states))
width = 0.35

black_vals = [income_df[(income_df["state"] == s) & (income_df["race"] == "black")]["value"].iloc[0] for s in states]
white_vals = [income_df[(income_df["state"] == s) & (income_df["race"] == "white")]["value"].iloc[0] for s in states]

ax.bar([i - width/2 for i in x], black_vals, width, label="Black", color=D4BL_GREEN)
ax.bar([i + width/2 for i in x], white_vals, width, label="White", color="#666666")
ax.set_xticks(x)
ax.set_xticklabels(states, color=D4BL_TEXT)
ax.set_ylabel("Median Household Income ($)", color=D4BL_TEXT)
ax.set_title("Income Gap by State", color=D4BL_TEXT, fontsize=14)
ax.legend()
ax.tick_params(colors=D4BL_TEXT)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
plt.tight_layout()
plt.show()
```

**Cell 11 (markdown):** Data shape for training
```
## Data Shape for Training

When we fine-tune a language model, we don't feed it raw numbers. We convert data rows into natural language that the model can learn from. Here's a preview of how a Census ACS row becomes a training input:

**Raw data row:**
```
{"state": "AL", "metric": "poverty_rate", "race": "black", "value": 28.3}
```

**As a training prompt:**
> "Explain the poverty rate disparity in Alabama, where the Black poverty rate is 28.3% compared to 11.5% for white residents."

The model learns to respond with equity-framed analysis — naming structural causes, connecting to policy, and acknowledging data limitations. That's what Notebook 2 covers.
```

**Cell 12 (markdown):** Exercise
```
## ✏️ Exercise

Pick a different metric from the sample data above (e.g., `mental_health_not_good` from CDC, or `median_household_income` from Census) and:

1. Compute the Black/white disparity ratio
2. Create a bar chart comparing the groups
3. Write one sentence explaining what structural factor might contribute to this gap
```

**Cell 13 (code):** Exercise starter
```python
# TODO: Pick a metric and compute the disparity ratio
# metric_name = "..."
# ratio = compute_disparity(??_df, metric_name)
# print(ratio)
```

**Cell 14 (markdown):** Summary
```
## Summary

You've seen how D4BL organizes equity data from 17 sources, computed disparity ratios, and visualized the income gap. These numbers aren't abstract — they reflect structural conditions that policy can change.

**Next:** [Notebook 2 — Creating Training Data](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/02_creating_training_data.ipynb) → Learn how this data becomes training examples for a fine-tuned model.
```

- [ ] **Step 2: Verify the notebook is valid JSON**

Run: `python -c "import json; json.load(open('notebooks/tutorials/01_understanding_your_data.ipynb'))"`
Expected: No errors (valid JSON)

- [ ] **Step 3: Commit**

```bash
git add notebooks/tutorials/01_understanding_your_data.ipynb
git commit -m "feat(tutorials): add Notebook 1 — Understanding Your Data"
```

---

## Task 2: Notebook 2 — Creating Training Data

**Files:**
- Create: `notebooks/tutorials/02_creating_training_data.ipynb`

- [ ] **Step 1: Create the notebook**

Create the ipynb file with these cells:

**Cell 1 (markdown):** Title and badge
```
# 🔧 Creating Training Data
### D4BL Tutorial 2 of 5

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/02_creating_training_data.ipynb)

**What you'll learn:** How real equity data becomes instruction/response training pairs through distillation — the process of using a large model to teach a small one.

**Time:** ~20 minutes | **Prerequisites:** A Google account | **Dependencies:** None (stdlib only)
```

**Cell 2 (markdown):** What is distillation?
```
## What is Distillation?

Fine-tuning a language model requires thousands of high-quality instruction/response pairs. Writing these by hand would take months. Instead, we use **distillation**: a large, capable model (Claude) generates expert-level responses from our real data, and we use those responses to train a much smaller, cheaper model.

Think of it like an experienced mentor teaching a new hire. The mentor (Claude) demonstrates how to analyze equity data with the right framing, and the trainee (Qwen2.5-3B) learns by studying those examples.

The key insight: **the prompts we write determine what the small model learns.** By embedding D4BL's methodology into our distillation prompts — center community voice, name structural causes, connect to policy — the small model inherits those values.
```

**Cell 3 (markdown):** Anatomy of a training pair
```
## Anatomy of a Training Pair

Every training example follows the ChatML format with three roles:

| Role | Purpose | Example |
|------|---------|---------|
| **system** | Sets the model's identity and values | "You are an AI assistant trained to support data justice..." |
| **user** | The question or task | "Explain poverty rate disparities in Alabama" |
| **assistant** | The ideal response | Structured JSON with equity-framed analysis |

Here's a real example from D4BL's query parser training data:
```

**Cell 4 (code):** Show a real training pair
```python
import json

# A real training pair from D4BL's query parser dataset
example_pair = {
    "messages": [
        {
            "role": "system",
            "content": (
                "You are an AI assistant trained to support data justice and racial equity research "
                "following the Data for Black Lives (D4BL) methodology.\n\n"
                "Core principles:\n"
                "1. Center communities most impacted by structural racism in all analysis and framing.\n"
                "2. Name structural causes of racial disparities — never frame them as innate or cultural.\n"
                "3. Connect data findings to actionable policy levers and advocacy opportunities.\n"
                "4. Acknowledge data limitations, sampling gaps, and margin-of-error uncertainties.\n"
                "5. Make analysis accessible to organizers, advocates, and community members.\n"
                "6. Never suggest that racial disparities are innate, biological, or the result of cultural deficits.\n\n"
                "Respond with ONLY valid JSON."
            )
        },
        {
            "role": "user",
            "content": "Why can't our kids just go to a good school in this neighborhood?"
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "entities": ["neighborhood", "schools"],
                "search_queries": [
                    "school quality racial segregation neighborhood",
                    "education funding disparities by race",
                    "school district boundary gerrymandering"
                ],
                "data_sources": ["census_acs", "doe"],
                "community_framing": {
                    "detected": True,
                    "issue_domain": "education",
                    "structural_frame": "residential_segregation"
                }
            }, indent=2)
        }
    ]
}

print("=== Training Pair ===")
print(f"\nSystem prompt ({len(example_pair['messages'][0]['content'])} chars):")
print(example_pair["messages"][0]["content"][:200] + "...")
print(f"\nUser input:")
print(example_pair["messages"][1]["content"])
print(f"\nAssistant response (what the model learns to generate):")
print(example_pair["messages"][2]["content"])
```

**Cell 5 (markdown):** The three adapters
```
## The Three Adapters

D4BL trains three specialized LoRA adapters, each for a different task:

### 1. Query Parser
Converts natural-language questions into structured search intents. Recognizes community framings like "Why can't our kids breathe clean air?" and maps them to data sources.

### 2. Explainer
Transforms data findings into equity-framed narratives with three **registers** (audience styles):
- **Community:** Accessible, action-oriented language
- **Policy:** Formal, citation-heavy, legislative framing
- **Research:** Statistical, methodology-focused

### 3. Evaluator
Scores model outputs for hallucination, relevance, bias, and equity framing alignment.

Each adapter has its own training data, distillation prompts, and evaluation criteria.
```

**Cell 6 (markdown):** Writing a distillation prompt
```
## Writing a Distillation Prompt

The distillation prompt is the most important piece — it encodes D4BL's methodology into the training data. Here's D4BL's actual system prompt, annotated:
```

**Cell 7 (code):** Annotated system prompt
```python
# D4BL's actual system prompt for distillation
# Each principle maps to the D4BL methodology cycle

D4BL_SYSTEM_PROMPT = """\
You are an AI assistant trained to support data justice and racial equity research \
following the Data for Black Lives (D4BL) methodology.

Core principles:
1. Center communities most impacted by structural racism in all analysis and framing.
   # ← Community Engagement stage
2. Name structural causes of racial disparities — never frame them as innate or cultural.
   # ← Problem Identification stage
3. Connect data findings to actionable policy levers and advocacy opportunities.
   # ← Policy Innovation stage
4. Acknowledge data limitations, sampling gaps, and margin-of-error uncertainties.
   # ← Data Collection & Analysis stage
5. Make analysis accessible to organizers, advocates, and community members, not just researchers.
   # ← Power Building stage
6. Never suggest that racial disparities are innate, biological, or the result of cultural deficits.
   # ← Safety guardrail

Respond with ONLY valid JSON."""

print("System prompt length:", len(D4BL_SYSTEM_PROMPT), "characters")
print("\nNotice: each principle maps to a stage in D4BL's methodology cycle.")
print("This isn't just a generic 'be helpful' prompt — it embeds a specific worldview.")
```

**Cell 8 (code):** Mock distillation function
```python
# In production, this calls Claude API. Here we simulate with pre-written responses
# to show the shape of the process without requiring an API key.

MOCK_RESPONSES = {
    "poverty_rate": {
        "community": (
            "In Alabama, nearly 1 in 3 Black residents lives below the poverty line (28.3%), "
            "compared to about 1 in 9 white residents (11.5%). This isn't about individual "
            "choices — it reflects decades of job discrimination, wage theft in low-income "
            "industries, and underinvestment in Black neighborhoods. The gap is structural, "
            "and closing it requires policy action: raising the minimum wage, expanding "
            "Medicaid, and enforcing fair lending laws."
        ),
        "policy": (
            "The Black poverty rate in Alabama (28.3%) is 2.5x the white rate (11.5%), "
            "a disparity that persists after controlling for education and employment status. "
            "Contributing factors include occupational segregation, the state's refusal to "
            "expand Medicaid (leaving ~170,000 in the coverage gap), and historically low "
            "minimum wage. The LIFT Act (S. 1138) and Medicaid expansion would directly "
            "address these structural drivers."
        ),
        "research": (
            "Racial disparities in poverty rates (Black: 28.3%, white: 11.5%; RR = 2.46, "
            "95% CI: 2.31-2.62) in Alabama remain statistically significant after adjustment "
            "for educational attainment and labor force participation (aOR = 1.89, p < 0.001). "
            "Decomposition analysis suggests ~60% of the gap is attributable to structural "
            "factors including occupational segregation and geographic concentration in "
            "low-opportunity census tracts. Limitations include ACS sampling variability "
            "in rural counties."
        ),
    }
}

def mock_distill(data_row, register="community"):
    """Simulate what Claude would generate for a data row.

    In production, this calls the Claude API with D4BL_SYSTEM_PROMPT.
    Here we return pre-written responses to show the expected shape.
    """
    metric = data_row["metric"]
    if metric in MOCK_RESPONSES and register in MOCK_RESPONSES[metric]:
        return MOCK_RESPONSES[metric][register]
    return f"[Mock response for {metric} in {register} register — in production, Claude generates this]"

# Demo: generate an explanation for Alabama's poverty data
data_row = {"state": "AL", "metric": "poverty_rate", "race": "black", "value": 28.3}
response = mock_distill(data_row, register="community")
print("Input data:", data_row)
print(f"\nCommunity register response:\n{response}")
```

**Cell 9 (markdown):** The register system
```
## The Register System

The same data, explained three ways. This is one of D4BL's key innovations — the model doesn't just analyze data, it communicates findings in the register that serves each audience best.
```

**Cell 10 (code):** Show all three registers
```python
data_row = {"state": "AL", "metric": "poverty_rate", "race": "black", "value": 28.3}

for register in ["community", "policy", "research"]:
    response = mock_distill(data_row, register=register)
    print(f"{'=' * 60}")
    print(f"Register: {register.upper()}")
    print(f"{'=' * 60}")
    print(response)
    print()
```

**Cell 11 (code):** Build a complete training pair
```python
def build_training_pair(data_row, register, response):
    """Assemble a complete ChatML training pair."""
    metric = data_row["metric"].replace("_", " ")
    state = data_row["state"]
    value = data_row["value"]

    user_prompt = f"Explain the {metric} in {state} ({value}%) in the {register} register."

    return {
        "messages": [
            {"role": "system", "content": D4BL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": response},
        ]
    }

# Build a complete training pair
pair = build_training_pair(
    data_row={"state": "AL", "metric": "poverty_rate", "race": "black", "value": 28.3},
    register="community",
    response=mock_distill({"state": "AL", "metric": "poverty_rate"}, "community"),
)

print("Complete training pair (ChatML format):")
print(json.dumps(pair, indent=2)[:500] + "...")
```

**Cell 12 (markdown):** Exercise
```
## ✏️ Exercise

1. Write your own distillation prompt by modifying `D4BL_SYSTEM_PROMPT` above. Try adding a principle specific to your community's priorities (e.g., "Center Indigenous data sovereignty" or "Acknowledge environmental racism in industrial corridors").

2. Use `build_training_pair()` to create a training example for a different metric — maybe income or environmental exposure.
```

**Cell 13 (code):** Exercise starter
```python
# TODO: Modify the system prompt and build a training pair
# my_system_prompt = """..."""
# my_data_row = {"state": "...", "metric": "...", "race": "...", "value": ...}
# my_response = "..."  # Write the response you'd want the model to generate
# my_pair = build_training_pair(my_data_row, "community", my_response)
```

**Cell 14 (markdown):** Summary
```
## Summary

You've learned how D4BL creates training data through distillation — using a large model to generate equity-framed responses that teach a smaller model. The key insight: the prompts encode the methodology. By embedding D4BL's principles in the system prompt, every training example carries those values.

**Next:** [Notebook 3 — Training with Unsloth](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/03_training_with_unsloth.ipynb) → Actually fine-tune a model on Colab's free GPU.
```

- [ ] **Step 2: Verify valid JSON**

Run: `python -c "import json; json.load(open('notebooks/tutorials/02_creating_training_data.ipynb'))"`

- [ ] **Step 3: Commit**

```bash
git add notebooks/tutorials/02_creating_training_data.ipynb
git commit -m "feat(tutorials): add Notebook 2 — Creating Training Data"
```

---

## Task 3: Notebook 3 — Training with Unsloth

**Files:**
- Create: `notebooks/tutorials/03_training_with_unsloth.ipynb`

- [ ] **Step 1: Create the notebook**

This is the most complex notebook — it actually trains a model on Colab T4.

**Cell 1 (markdown):** Title
```
# 🚀 Training with Unsloth
### D4BL Tutorial 3 of 5

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/03_training_with_unsloth.ipynb)

**What you'll learn:** How to fine-tune Qwen2.5-3B with LoRA adapters using D4BL's actual training configuration. You'll run real training on Colab's free T4 GPU.

**Time:** ~10 min (quick mode) / ~25 min (full training) | **Prerequisites:** Google account with Colab GPU access | **Dependencies:** unsloth, transformers, trl

⚠️ **Important:** This notebook requires a GPU runtime. Go to Runtime → Change runtime type → T4 GPU.
```

**Cell 2 (code):** Config + setup
```python
# === CONFIGURATION ===
# Set to False for full 7-epoch training run (~25 min on T4)
QUICK_MODE = True  # True = 10 steps only (~2 min), good for learning

# Install Unsloth (optimized for Colab T4)
!pip install -q unsloth transformers datasets trl
```

**Cell 3 (markdown):** What is LoRA?
```
## What is LoRA?

LoRA (Low-Rank Adaptation) lets you fine-tune a large model by training only a small set of adapter weights — typically less than 1% of the total parameters. The original model stays frozen.

**Why this matters for equity work:** LoRA makes fine-tuning possible on free hardware. You don't need a $10,000 GPU or a cloud computing budget. A community organization can train a model on Colab's free T4 GPU in under 30 minutes.

D4BL uses rank 16, which means each adapter is about 98K parameters — 0.003% of the 3B base model. See the [interactive LoRA visualizer](https://d4bl.org/learn) for more.
```

**Cell 4 (code):** Load model
```python
from unsloth import FastLanguageModel
import torch

# Load Qwen2.5-3B — D4BL's base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-3B-Instruct",
    max_seq_length=2048,
    dtype=None,  # auto-detect
    load_in_4bit=True,  # saves VRAM on free Colab
)

print(f"Model loaded: {model.config._name_or_path}")
print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
```

**Cell 5 (markdown):** Configure LoRA
```
## Configuring LoRA

These are D4BL's actual LoRA settings from Sprint 2.5. Each parameter matters:

| Parameter | Value | Why |
|-----------|-------|-----|
| `r` (rank) | 16 | Sweet spot: enough capacity for structured JSON output without overfitting |
| `lora_alpha` | 32 | 2x rank — standard scaling that keeps learning stable |
| `lora_dropout` | 0.05 | Light regularization to prevent memorizing training examples |
| `target_modules` | q_proj, k_proj, v_proj, o_proj, etc. | All attention + MLP layers — the model needs to learn new output patterns, not just new facts |
```

**Cell 6 (code):** Configure LoRA
```python
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    use_gradient_checkpointing="unsloth",
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"Trainable parameters: {trainable:,} ({trainable/total:.4%} of total)")
```

**Cell 7 (markdown):** Prepare dataset
```
## Preparing the Dataset

This is where Sprint 2.5's critical fix lives. The original Sprint 2 training manually concatenated ChatML strings — and the model failed to produce structured JSON. The fix: use `tokenizer.apply_chat_template()`, which produces the exact token boundaries the model expects.

**Wrong way (Sprint 2):**
```python
text = "<|im_start|>system\n" + system + "<|im_end|>\n..."  # Manual string concat
```

**Right way (Sprint 2.5):**
```python
text = tokenizer.apply_chat_template(messages, tokenize=False)  # Native template
```

This single change took the integration test pass rate from 3/11 to 11/11.
```

**Cell 8 (code):** Prepare training data
```python
from datasets import Dataset

# Embedded sample training data — 50 query parser examples
# (In production, D4BL uses 1000 per adapter from scripts/training_data/final/)
SAMPLE_TRAINING_DATA = [
    {
        "messages": [
            {"role": "system", "content": "You are an AI assistant trained to support data justice and racial equity research following the Data for Black Lives (D4BL) methodology.\n\nCore principles:\n1. Center communities most impacted by structural racism.\n2. Name structural causes of racial disparities.\n3. Connect findings to policy levers.\n4. Acknowledge data limitations.\n5. Make analysis accessible to communities.\n\nRespond with ONLY valid JSON."},
            {"role": "user", "content": "What's the homeownership gap between Black and white families in Georgia?"},
            {"role": "assistant", "content": '{"entities": ["Georgia"], "search_queries": ["homeownership rate racial disparity Georgia", "Black white homeownership gap Georgia"], "data_sources": ["census_acs"], "community_framing": {"detected": false, "issue_domain": "housing", "structural_frame": null}}'}
        ]
    },
    {
        "messages": [
            {"role": "system", "content": "You are an AI assistant trained to support data justice and racial equity research following the Data for Black Lives (D4BL) methodology.\n\nCore principles:\n1. Center communities most impacted by structural racism.\n2. Name structural causes of racial disparities.\n3. Connect findings to policy levers.\n4. Acknowledge data limitations.\n5. Make analysis accessible to communities.\n\nRespond with ONLY valid JSON."},
            {"role": "user", "content": "Why are so many people in my neighborhood getting asthma?"},
            {"role": "assistant", "content": '{"entities": ["neighborhood"], "search_queries": ["asthma prevalence environmental racism", "air quality racial disparity", "industrial pollution proximity minority communities"], "data_sources": ["cdc_places", "epa_ejscreen"], "community_framing": {"detected": true, "issue_domain": "health", "structural_frame": "environmental_racism"}}'}
        ]
    },
    # Implementer: add 18 more pairs (20 total) following this exact pattern.
    # Distribution: ~4 per domain (health, housing, education, environment, criminal justice).
    # Mix: ~12 standard questions, ~8 community-framed (e.g., "Why can't we...", "How come our...").
    # Each assistant response must be valid JSON with the query parser schema.
    # Use realistic but not necessarily real data source keys from: census_acs, cdc_places,
    # epa_ejscreen, fbi_ucr, bls, hud, doe, police_violence.
    # 20 examples is enough for a tutorial demo — production uses 1000.
]

# Format using the tokenizer's native chat template (Sprint 2.5 fix)
def format_example(example):
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}

dataset = Dataset.from_list(SAMPLE_TRAINING_DATA)
dataset = dataset.map(format_example)

print(f"Training examples: {len(dataset)}")
print(f"\nFirst example (formatted):")
print(dataset[0]["text"][:300] + "...")
```

**Cell 9 (code):** Training
```python
from trl import SFTTrainer
from transformers import TrainingArguments

training_args = TrainingArguments(
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    warmup_ratio=0.1,
    num_train_epochs=1 if QUICK_MODE else 7,
    max_steps=10 if QUICK_MODE else -1,
    learning_rate=2e-4,
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    logging_steps=1,
    output_dir="outputs",
    optim="adamw_8bit",
    seed=42,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=2048,
    args=training_args,
)

print(f"Training mode: {'QUICK (10 steps)' if QUICK_MODE else 'FULL (7 epochs)'}")
print("Starting training...")
stats = trainer.train()
print(f"\nDone! Final loss: {stats.training_loss:.4f}")
```

**Cell 10 (code):** Save adapter
```python
# Save the LoRA adapter (not the full model — just the small adapter weights)
model.save_pretrained("d4bl-query-parser-adapter")
tokenizer.save_pretrained("d4bl-query-parser-adapter")

import os
adapter_size = sum(
    os.path.getsize(os.path.join("d4bl-query-parser-adapter", f))
    for f in os.listdir("d4bl-query-parser-adapter")
)
print(f"Adapter saved to: d4bl-query-parser-adapter/")
print(f"Adapter size: {adapter_size / 1e6:.1f} MB")
print(f"Base model size: ~6.2 GB (FP16)")
print(f"Adapter is {adapter_size / 6.2e9:.4%} of the base model")
```

**Cell 11 (markdown):** Exercise
```
## ✏️ Exercise

1. Change `QUICK_MODE = False` and run the full training. Watch the loss curve — it should decrease steadily.
2. Try changing the LoRA rank: set `r=8` or `r=32` in the LoRA config cell. How does it affect adapter size and training speed?
3. Check the training loss at different steps. If it plateaus early, the model may need more data or epochs.
```

**Cell 12 (markdown):** Summary
```
## Summary

You just fine-tuned a 3B parameter language model on free hardware. The key ingredients: LoRA for parameter efficiency, `apply_chat_template()` for correct formatting, and D4BL's methodology embedded in every training example.

**Next:** [Notebook 4 — Testing Your Model](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/04_testing_your_model.ipynb) → Load your trained model and see how it compares to the base.
```

- [ ] **Step 2: Verify valid JSON**

Run: `python -c "import json; json.load(open('notebooks/tutorials/03_training_with_unsloth.ipynb'))"`

- [ ] **Step 3: Commit**

```bash
git add notebooks/tutorials/03_training_with_unsloth.ipynb
git commit -m "feat(tutorials): add Notebook 3 — Training with Unsloth"
```

---

## Task 4: Notebook 4 — Testing Your Model

**Files:**
- Create: `notebooks/tutorials/04_testing_your_model.ipynb`

- [ ] **Step 1: Create the notebook**

**Cell 1 (markdown):** Title
```
# 🧪 Testing Your Model
### D4BL Tutorial 4 of 5

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/04_testing_your_model.ipynb)

**What you'll learn:** How to evaluate your fine-tuned model against the base model, validate structured output, and apply D4BL's ship criteria.

**Time:** ~15 minutes | **Prerequisites:** GPU runtime (for inference) | **Dependencies:** unsloth, transformers
```

**Cell 2 (code):** Setup
```python
!pip install -q unsloth transformers

from unsloth import FastLanguageModel
import json
```

**Cell 3 (markdown):** Load model
```
## Loading Your Model

If you ran Notebook 3, your adapter is saved locally. If not, we'll download a pre-trained one.
```

**Cell 4 (code):** Load with fallback
```python
import os

ADAPTER_PATH = "d4bl-query-parser-adapter"

if os.path.exists(ADAPTER_PATH):
    print(f"Found local adapter at {ADAPTER_PATH}")
else:
    print("No local adapter found.")
    print("Option 1: Run Notebook 3 first to train your own.")
    print("Option 2: Uncomment the line below to download a pre-trained adapter.")
    # !git clone https://huggingface.co/d4bl/query-parser-adapter {ADAPTER_PATH}
    # For now, we'll use the base model for comparison purposes
    ADAPTER_PATH = None

# Load base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-3B-Instruct",
    max_seq_length=2048,
    dtype=None,
    load_in_4bit=True,
)

# Load adapter if available
if ADAPTER_PATH:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    print("Adapter loaded successfully!")
else:
    print("Running with base model only (no fine-tuning).")

FastLanguageModel.for_inference(model)
```

**Cell 5 (code):** Test prompts
```python
# Test prompts — a mix of community-framed and standard questions
TEST_PROMPTS = [
    "Why can't our kids breathe clean air in this neighborhood?",
    "What's the maternal mortality rate for Black women in Alabama?",
    "Show me poverty data for Mississippi",
    "Why do they keep building factories near our homes?",
    "Compare homeownership rates by race in Georgia",
]

SYSTEM_PROMPT = (
    "You are an AI assistant trained to support data justice and racial equity research "
    "following the Data for Black Lives (D4BL) methodology.\n\n"
    "Respond with ONLY valid JSON."
)

def generate_response(prompt):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    input_text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs, max_new_tokens=512, temperature=0.1, do_sample=True
    )
    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return response.strip()

# Run all test prompts
print("Generating responses...\n")
results = []
for prompt in TEST_PROMPTS:
    response = generate_response(prompt)
    results.append({"prompt": prompt, "response": response})
    print(f"Q: {prompt}")
    print(f"A: {response[:200]}...")
    print()
```

**Cell 6 (markdown):** Validate structure
```
## Validating Structured Output

For the query parser, every response should be valid JSON with specific fields. Let's check:
```

**Cell 7 (code):** Validation
```python
REQUIRED_FIELDS = {"entities", "search_queries", "data_sources", "community_framing"}

def validate_response(response_text):
    """Check if response is valid JSON with required fields."""
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        return {"valid_json": False, "has_fields": False, "parsed": None}

    has_fields = REQUIRED_FIELDS.issubset(set(parsed.keys()))
    return {"valid_json": True, "has_fields": has_fields, "parsed": parsed}

print("Validation Results:")
print("=" * 60)
valid_count = 0
for r in results:
    v = validate_response(r["response"])
    status = "✅" if v["valid_json"] and v["has_fields"] else "❌"
    if v["valid_json"] and v["has_fields"]:
        valid_count += 1
    print(f"{status} {r['prompt'][:50]}...")
    print(f"   Valid JSON: {v['valid_json']} | Required fields: {v['has_fields']}")

print(f"\nPass rate: {valid_count}/{len(results)} ({valid_count/len(results):.0%})")
```

**Cell 8 (markdown):** Ship criteria
```
## Ship Criteria

D4BL doesn't just ask "does it work?" — we have formal ship criteria:

| Metric | Threshold | What It Measures |
|--------|-----------|-----------------|
| JSON validity rate | ≥ 90% | Model produces parseable structured output |
| Field completeness | ≥ 85% | All required fields present |
| Community framing detection | ≥ 70% | Recognizes community-voiced questions |
| P95 latency | < 1000ms | Fast enough for interactive use |

If any **blocking** criterion fails, the model doesn't ship. Non-blocking gaps are tracked but don't prevent deployment.
```

**Cell 9 (markdown):** Exercise
```
## ✏️ Exercise

1. Write 3 test prompts about a topic you care about — housing, environment, health, education.
2. Run them through `generate_response()` and validate the output.
3. For community-framed questions, check if `community_framing.detected` is `true`.
```

**Cell 10 (code):** Exercise
```python
# TODO: Add your own test prompts
# my_prompts = [
#     "...",
#     "...",
#     "...",
# ]
# for p in my_prompts:
#     response = generate_response(p)
#     print(f"Q: {p}")
#     print(f"A: {response}")
#     print(f"Valid: {validate_response(response)}")
#     print()
```

**Cell 11 (markdown):** Summary
```
## Summary

You've tested a fine-tuned model against real prompts, validated structured output, and learned about D4BL's ship criteria. The model isn't just "good enough" — it meets explicit standards for JSON validity, field completeness, and community framing detection.

**Next:** [Notebook 5 — Making It Your Own](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/05_making_it_your_own.ipynb) → Customize the model for your community's data.
```

- [ ] **Step 2: Verify valid JSON**

Run: `python -c "import json; json.load(open('notebooks/tutorials/04_testing_your_model.ipynb'))"`

- [ ] **Step 3: Commit**

```bash
git add notebooks/tutorials/04_testing_your_model.ipynb
git commit -m "feat(tutorials): add Notebook 4 — Testing Your Model"
```

---

## Task 5: Notebook 5 — Making It Your Own

**Files:**
- Create: `notebooks/tutorials/05_making_it_your_own.ipynb`

- [ ] **Step 1: Create the notebook**

**Cell 1 (markdown):** Title
```
# 🌱 Making It Your Own
### D4BL Tutorial 5 of 5

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials/05_making_it_your_own.ipynb)

**What you'll learn:** How to adapt D4BL's approach for your own community — bring your own data, customize prompts, and train a model that reflects your priorities.

**Time:** ~20 min (quick mode) / ~35 min (full) | **Prerequisites:** GPU runtime | **Dependencies:** unsloth, transformers, trl
```

**Cell 2 (code):** Setup
```python
QUICK_MODE = True  # Set to False for full training

!pip install -q unsloth transformers datasets trl
```

**Cell 3 (markdown):** The methodology is portable
```
## The D4BL Methodology is Portable

D4BL's approach isn't just for one organization — it's a framework any community can use:

1. **Center your community** — Who is most impacted? What are their priorities?
2. **Name structural causes** — What historical and policy decisions created these conditions?
3. **Connect to policy** — What specific changes could improve outcomes?
4. **Acknowledge limitations** — What does the data miss? Who isn't counted?
5. **Build power** — How does this analysis serve community organizing and advocacy?

The model you build should reflect *your* community's version of these principles.
```

**Cell 4 (markdown):** Bring your own data
```
## Bring Your Own Data

Replace the sample data below with your community's data. The format is simple: each row needs a metric name, a value, and enough context to generate a meaningful training prompt.
```

**Cell 5 (code):** Data template
```python
# === REPLACE THIS WITH YOUR DATA ===
# Format: list of dicts with at minimum: metric, state/location, value, race (if applicable)

my_data = [
    {"location": "Jefferson County, AL", "metric": "childhood_asthma_rate", "group": "Black children", "value": 14.2, "comparison_group": "white children", "comparison_value": 7.8},
    {"location": "Jefferson County, AL", "metric": "park_access", "group": "Black neighborhoods", "value": 23, "comparison_group": "white neighborhoods", "comparison_value": 67},
    # Add more rows here...
]

print(f"Your dataset: {len(my_data)} rows")
for row in my_data:
    ratio = row["value"] / row["comparison_value"] if row["comparison_value"] else 0
    print(f"  {row['metric']} in {row['location']}: {row['group']} = {row['value']}, "
          f"{row['comparison_group']} = {row['comparison_value']} (ratio: {ratio:.1f}x)")
```

**Cell 6 (markdown):** Customize prompts
```
## Customize Your Distillation Prompts

Start from D4BL's system prompt and modify it for your community. Think about:
- What structural factors are most relevant in your area?
- What policy context should the model know about?
- Who is the primary audience for the model's output?
```

**Cell 7 (code):** Custom system prompt
```python
# === CUSTOMIZE THIS PROMPT ===
# Start from D4BL's template and make it yours

MY_SYSTEM_PROMPT = """\
You are an AI assistant trained to support community data analysis \
for [YOUR COMMUNITY/ORGANIZATION NAME].

Core principles:
1. Center [YOUR COMMUNITY] in all analysis and framing.
2. Name structural causes — including [SPECIFIC STRUCTURAL FACTORS IN YOUR AREA].
3. Connect findings to [SPECIFIC POLICY LEVERS RELEVANT TO YOUR CONTEXT].
4. Acknowledge data limitations and gaps in [SPECIFIC DATA CHALLENGES].
5. Make analysis accessible to [YOUR PRIMARY AUDIENCE].

Respond with ONLY valid JSON."""

print("Your custom system prompt:")
print(MY_SYSTEM_PROMPT)
print(f"\nLength: {len(MY_SYSTEM_PROMPT)} chars")
```

**Cell 8 (code):** Generate custom training pairs
```python
import json

def build_custom_pair(data_row, system_prompt, response_text):
    """Build a ChatML training pair from your data."""
    metric = data_row["metric"].replace("_", " ")
    location = data_row["location"]
    group = data_row["group"]
    value = data_row["value"]

    user_prompt = f"Explain the {metric} for {group} in {location} ({value})."

    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": response_text},
        ]
    }

# Example: generate a pair (in production, Claude writes the response)
example_response = json.dumps({
    "entities": ["Jefferson County", "AL"],
    "search_queries": [
        "childhood asthma rate racial disparity Jefferson County",
        "air quality environmental racism Birmingham Alabama"
    ],
    "data_sources": ["cdc_places", "epa_ejscreen"],
    "community_framing": {
        "detected": True,
        "issue_domain": "health",
        "structural_frame": "environmental_racism"
    }
}, indent=2)

pair = build_custom_pair(my_data[0], MY_SYSTEM_PROMPT, example_response)
print("Your training pair:")
print(json.dumps(pair, indent=2)[:500] + "...")
```

**Cell 9 (code):** Train on custom data
```python
from unsloth import FastLanguageModel
from datasets import Dataset
from trl import SFTTrainer
from transformers import TrainingArguments
import torch

# Load base model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-3B-Instruct",
    max_seq_length=2048, dtype=None, load_in_4bit=True,
)

model = FastLanguageModel.get_peft_model(
    model, r=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=32, lora_dropout=0.05, bias="none",
    use_gradient_checkpointing="unsloth",
)

# Build training pairs from your data
# (In a real workflow, you'd have 50-1000 pairs generated by Claude)
training_pairs = []
for row in my_data:
    # Using the example response format — in production, each would be unique
    response = json.dumps({
        "entities": [row["location"]],
        "search_queries": [f"{row['metric']} racial disparity {row['location']}"],
        "data_sources": ["census_acs"],
        "community_framing": {"detected": True, "issue_domain": "health", "structural_frame": "structural_racism"}
    })
    training_pairs.append(build_custom_pair(row, MY_SYSTEM_PROMPT, response))

def format_example(example):
    return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)}

dataset = Dataset.from_list(training_pairs).map(format_example)
print(f"Custom training set: {len(dataset)} examples")

# Train
trainer = SFTTrainer(
    model=model, tokenizer=tokenizer, train_dataset=dataset,
    dataset_text_field="text", max_seq_length=2048,
    args=TrainingArguments(
        per_device_train_batch_size=2, gradient_accumulation_steps=4,
        warmup_ratio=0.1, num_train_epochs=1 if QUICK_MODE else 7,
        max_steps=10 if QUICK_MODE else -1, learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(), bf16=torch.cuda.is_bf16_supported(),
        logging_steps=1, output_dir="my-custom-model", optim="adamw_8bit", seed=42,
    ),
)

print(f"Training ({'QUICK' if QUICK_MODE else 'FULL'} mode)...")
stats = trainer.train()
print(f"Done! Final loss: {stats.training_loss:.4f}")
```

**Cell 10 (markdown):** What's next
```
## What's Next

You've built an equity-focused AI model customized for your community. Here's where to go from here:

### Run locally with Ollama
Export to GGUF format and run on your own computer — no cloud, no API costs:
```bash
# Export (from Python)
model.save_pretrained_gguf("my-model", tokenizer, quantization_method="q4_k_m")

# Create Ollama model
ollama create my-community-model -f Modelfile
ollama run my-community-model
```

### Publish to Hugging Face
Share your model with other communities:
```bash
model.push_to_hub("your-username/your-model-name")
```

### Contribute back to D4BL
- Share your distillation prompts and methodology adaptations
- Report data gaps or biases you discover
- Join the D4BL community: [d4bl.org](https://d4bl.org)

### Learn more
- [D4BL /learn page](https://d4bl.org/learn) — Interactive visualizations of LoRA, quantization, and the D4BL methodology
- [Slide deck: Building AI That Centers Racial Equity](https://gamma.app/docs/Building-AI-That-Centers-Racial-Equity-m8qd4n13bdtboa1)
```

**Cell 11 (markdown):** Exercise
```
## ✏️ Final Exercise

Go end-to-end:
1. Replace `my_data` with real data from your community (even 3-5 rows is enough)
2. Customize `MY_SYSTEM_PROMPT` with your organization's principles
3. Generate training pairs (write the assistant responses yourself — think about what a good analysis looks like)
4. Train the model (QUICK_MODE is fine)
5. Test it: does the output reflect your community's framing?
```

**Cell 12 (code):** Exercise
```python
# TODO: Your end-to-end pipeline here
# 1. my_data = [...]
# 2. MY_SYSTEM_PROMPT = """..."""
# 3. training_pairs = [build_custom_pair(...) for ...]
# 4. Train (copy the training cell above)
# 5. Test with generate_response() from Notebook 4
```

- [ ] **Step 2: Verify valid JSON**

Run: `python -c "import json; json.load(open('notebooks/tutorials/05_making_it_your_own.ipynb'))"`

- [ ] **Step 3: Commit**

```bash
git add notebooks/tutorials/05_making_it_your_own.ipynb
git commit -m "feat(tutorials): add Notebook 5 — Making It Your Own"
```

---

## Task 6: Update /learn page with notebook URLs and Gamma deck

**Files:**
- Modify: `ui-nextjs/app/learn/page.tsx`

- [ ] **Step 1: Update TUTORIALS array with Colab URLs**

In `ui-nextjs/app/learn/page.tsx`, replace the `TUTORIALS` array (around line 10) with:

```tsx
const COLAB_BASE = 'https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials';

const TUTORIALS = [
  { title: 'Understanding Your Data', description: 'Query Supabase and see the shape of equity data.', colabUrl: `${COLAB_BASE}/01_understanding_your_data.ipynb` },
  { title: 'Creating Training Data', description: 'Write distillation prompts and generate training pairs.', colabUrl: `${COLAB_BASE}/02_creating_training_data.ipynb` },
  { title: 'Training with Unsloth', description: 'Load the model, configure LoRA, and run training.', colabUrl: `${COLAB_BASE}/03_training_with_unsloth.ipynb` },
  { title: 'Testing Your Model', description: 'Load in Ollama and compare outputs to the base model.', colabUrl: `${COLAB_BASE}/04_testing_your_model.ipynb` },
  { title: 'Making It Your Own', description: "Customize the model for your community's data.", colabUrl: `${COLAB_BASE}/05_making_it_your_own.ipynb` },
];
```

Update the `TutorialStep` rendering to use `t.colabUrl` instead of `"#"`:

```tsx
<TutorialStep
  key={t.title}
  step={i + 1}
  title={t.title}
  description={t.description}
  colabUrl={t.colabUrl}
/>
```

- [ ] **Step 2: Add Gamma deck link to hero section**

After the green gradient divider in the hero section, add:

```tsx
<a
  href="https://gamma.app/docs/Building-AI-That-Centers-Racial-Equity-m8qd4n13bdtboa1"
  target="_blank"
  rel="noopener noreferrer"
  className="inline-flex items-center gap-2 mt-6 px-6 py-3 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors"
>
  View the Slide Deck
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
</a>
```

- [ ] **Step 3: Verify build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/app/learn/page.tsx
git commit -m "feat(learn): update tutorial URLs and add Gamma deck link"
```

---

## Task 7: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Verify all notebooks are valid JSON**

```bash
python -c "
import json, glob
for f in sorted(glob.glob('notebooks/tutorials/*.ipynb')):
    data = json.load(open(f))
    cells = len(data.get('cells', []))
    print(f'{f}: {cells} cells — OK')
"
```
Expected: All 5 notebooks listed with cell counts, no errors.

- [ ] **Step 2: Verify frontend build**

Run: `cd ui-nextjs && npx next build`
Expected: Build succeeds, /learn route present.

- [ ] **Step 3: Run lint**

Run: `cd ui-nextjs && npm run lint`
Expected: No errors.

- [ ] **Step 4: Fix any issues and commit**

If any fixes needed:
```bash
git add <fixed-files>
git commit -m "fix(tutorials): final verification fixes"
```
