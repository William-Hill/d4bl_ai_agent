# Phoenix Evaluators Guide

This guide explains all available evaluators in Phoenix and their requirements.

## Overview

Phoenix provides two main types of evaluators:

1. **LLM-based Evaluators**: Use an LLM to perform judgments (e.g., hallucination detection, relevance)
2. **Code-based Evaluators**: Use deterministic processes or heuristics (e.g., exact match, BLEU, precision)

## Built-in Evaluators

### Evaluators That Require Reference Data

These evaluators need a `reference` column (ground truth) in your DataFrame:

#### 1. HallucinationEvaluator
**Purpose**: Detects hallucinations in LLM outputs by comparing against reference data.

**Required Columns**: `input`, `output`, `reference`

**Use Case**: Verify that the output doesn't contain information not present in the reference.

```python
from phoenix.evals import HallucinationEvaluator

evaluator = HallucinationEvaluator(model=your_model)
```

#### 2. RelevanceEvaluator
**Purpose**: Evaluates how relevant the output is to the input query.

**Required Columns**: `input`, `output`, `reference`

**Use Case**: Check if the output addresses the input query appropriately.

```python
from phoenix.evals import RelevanceEvaluator

evaluator = RelevanceEvaluator(model=your_model)
```

#### 3. QAEvaluator
**Purpose**: Evaluates question-answering tasks for correctness.

**Required Columns**: `input`, `output`, `reference`

**Use Case**: Verify that answers are correct for Q&A tasks.

```python
from phoenix.evals import QAEvaluator

evaluator = QAEvaluator(model=your_model)
```

#### 4. SummarizationEvaluator
**Purpose**: Evaluates summarization quality.

**Required Columns**: `input`, `output`, `reference`

**Use Case**: Assess how well a summary captures the key points of the reference text.

```python
from phoenix.evals import SummarizationEvaluator

evaluator = SummarizationEvaluator(model=your_model)
```

### Evaluators That Work Without Reference Data

These evaluators only need `input` and `output` columns:

#### 5. ToxicityEvaluator
**Purpose**: Detects toxic or harmful content in outputs.

**Required Columns**: `input`, `output` (reference optional)

**Use Case**: Monitor outputs for toxic, hateful, or inappropriate content.

```python
from phoenix.evals import ToxicityEvaluator

evaluator = ToxicityEvaluator(model=your_model)
```

**Output**: Returns labels like "toxic" or "non-toxic" with scores and explanations.

## Evaluation Types

Phoenix supports three evaluation output types:

### 1. Categorical (Binary)
Produces binary outcomes: true/false, yes/no, or 1/0.

**Example**: ToxicityEvaluator returns "toxic" or "non-toxic"

### 2. Categorical (Multi-class)
Yields one of several predefined categories.

**Example**: QualityEvaluator might return "excellent", "good", "fair", "poor"

### 3. Score
Generates a numeric value within a set range (e.g., 0-1, 1-10).

**Note**: Phoenix recommends using categorical evaluations in production as LLMs can be inconsistent with continuous scales.

## Using Evaluators in Your Script

### With Reference Data

If you have ground truth/reference data:

```python
import pandas as pd
from phoenix.evals import HallucinationEvaluator, RelevanceEvaluator, run_evals

# Your data with reference
df = pd.DataFrame({
    "input": ["What is the capital of France?"],
    "output": ["Paris is the capital of France."],
    "reference": ["Paris is the capital and largest city of France."]
})

# Run evaluations
results = run_evals(
    dataframe=df,
    evaluators=[
        HallucinationEvaluator(),
        RelevanceEvaluator(),
    ],
    provide_explanation=True,
)
```

### Without Reference Data

For evaluators that don't require reference:

```python
import pandas as pd
from phoenix.evals import ToxicityEvaluator, run_evals

# Your data without reference
df = pd.DataFrame({
    "input": ["Tell me about AI"],
    "output": ["AI is a fascinating field of computer science..."]
})

# Run evaluations
results = run_evals(
    dataframe=df,
    evaluators=[ToxicityEvaluator()],
    provide_explanation=True,
)
```

## Custom Evaluators

You can create custom evaluators for your specific use cases:

```python
from phoenix.evals import LLMEvaluator
from phoenix.evals.models import LiteLLMModel

class CustomEvaluator(LLMEvaluator):
    def __init__(self, model):
        super().__init__(
            model=model,
            name="custom_evaluator",
        )
    
    def _create_prompt(self, input: str, output: str, reference: str = None) -> str:
        return f"""
        Evaluate the following output based on your custom criteria:
        
        Input: {input}
        Output: {output}
        Reference: {reference if reference else "N/A"}
        
        Provide a score from 0-1 and an explanation.
        """
```

## Code-based Evaluators

Phoenix also supports code-based evaluators for deterministic metrics:

### Exact Match
Compares output to reference exactly.

### BLEU Score
Measures similarity between output and reference using n-gram precision.

### Precision/Recall/F1
Standard classification metrics.

## Using Ollama for Evaluations

All LLM-based evaluators can use Ollama:

```python
from phoenix.evals.models import LiteLLMModel
from phoenix.evals import ToxicityEvaluator

# Configure Ollama
import os
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434"

# Create Ollama model
ollama_model = LiteLLMModel(model="ollama/mistral")

# Use with evaluator
evaluator = ToxicityEvaluator(model=ollama_model)
```

## Recommendations

1. **For Production**: Use categorical (binary or multi-class) evaluations rather than scores for consistency.

2. **Without Reference Data**: Use `ToxicityEvaluator` to monitor outputs for harmful content.

3. **With Reference Data**: Use `HallucinationEvaluator` and `RelevanceEvaluator` for comprehensive quality assessment.

4. **For Q&A Tasks**: Use `QAEvaluator` with reference answers.

5. **For Summarization**: Use `SummarizationEvaluator` with reference summaries.

## Current Script Configuration

The `run_phoenix_evals.py` script currently uses:
- **ToxicityEvaluator**: Works without reference data, detects toxic content

To add more evaluators, modify the script to:
1. Add reference data to your traces (if available)
2. Include additional evaluators in the evaluators list
3. Ensure your DataFrame has the required columns

## Additional Resources

- [Phoenix Evaluation Documentation](https://docs.arize.com/phoenix/evaluation)
- [Phoenix Evaluators Reference](https://docs.arize.com/phoenix/evaluation/evaluators)
- [Evaluation Types](https://arize.com/docs/phoenix/evaluation/concepts-evals/evaluation-types)

