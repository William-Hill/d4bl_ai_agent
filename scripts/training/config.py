"""Shared constants for the training data pipeline."""

from pathlib import Path

# Output directories
BASE_DIR = Path(__file__).resolve().parent.parent / "training_data"
CORPUS_DIR = BASE_DIR / "corpus"
PAIRS_DIR = BASE_DIR / "pairs"
FINAL_DIR = BASE_DIR / "final"

# Corpus extraction
CORPUS_BATCH_SIZE = 500
MAX_PASSAGES_PER_TABLE = 10_000

# Distillation
DISTILLATION_MODEL = "claude-sonnet-4-20250514"
PAIRS_PER_TASK = 300
EVALUATOR_PAIRS_PER_SUBTASK = 150

# Dataset split ratios
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10

# Deduplication
JACCARD_THRESHOLD = 0.8
