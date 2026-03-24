#!/usr/bin/env bash
# Sprint 2.5: Generate new training pairs (1000/task) and prepare datasets
# Backs up existing data first, then runs distill + prepare stages.
#
# Usage: bash scripts/run_sprint25_generation.sh

set -euo pipefail
cd /Users/william-meroxa/Development/d4bl_ai_agent

# Activate venv
source .venv/bin/activate

# Load .env
set -a
source .env
set +a

echo "============================================================"
echo "Sprint 2.5: Training Data Generation"
echo "============================================================"
echo ""
echo "Config:"
python -c "from scripts.training.config import PAIRS_PER_TASK, EVALUATOR_PAIRS_PER_SUBTASK; print(f'  PAIRS_PER_TASK={PAIRS_PER_TASK}'); print(f'  EVALUATOR_PAIRS_PER_SUBTASK={EVALUATOR_PAIRS_PER_SUBTASK}')"
echo "  DB: remote Supabase (via DAGSTER_POSTGRES_URL)"
echo "  Model: claude-sonnet-4-20250514"
echo ""

# --- Step 0: Back up existing training data ---
BACKUP_DIR="scripts/training_data/backup_$(date +%Y%m%d_%H%M%S)"
echo "Backing up existing training data to ${BACKUP_DIR}/ ..."
mkdir -p "$BACKUP_DIR"

if [ -d "scripts/training_data/pairs" ]; then
    cp -r scripts/training_data/pairs "$BACKUP_DIR/"
    echo "  Backed up pairs/ ($(wc -l scripts/training_data/pairs/*.jsonl 2>/dev/null | tail -1 | awk '{print $1}') total lines)"
fi
if [ -d "scripts/training_data/final" ]; then
    cp -r scripts/training_data/final "$BACKUP_DIR/"
    echo "  Backed up final/"
fi
echo "  Backup complete: $BACKUP_DIR"
echo ""

# --- Step 1: Generate pairs (distill stage) ---
# Run each task separately so you can see progress per task

echo "============================================================"
echo "STAGE 2a: Generating query_parser pairs (1000 target)"
echo "Started: $(date '+%H:%M:%S')"
echo "============================================================"
python -m scripts.training.generate_training_pairs --task query_parser
echo ""

echo "============================================================"
echo "STAGE 2b: Generating explainer pairs (1000 target)"
echo "Started: $(date '+%H:%M:%S')"
echo "============================================================"
python -m scripts.training.generate_training_pairs --task explainer
echo ""

echo "============================================================"
echo "STAGE 2c: Generating evaluator pairs (250×4=1000 target)"
echo "Started: $(date '+%H:%M:%S')"
echo "============================================================"
python -m scripts.training.generate_training_pairs --task evaluator
echo ""

# --- Step 2: Prepare datasets (filter, dedup, split) ---
echo "============================================================"
echo "STAGE 3: Preparing datasets (filter → dedup → split)"
echo "============================================================"
python -m scripts.training.prepare_dataset --task all
echo ""

# --- Step 3: Create flat files for Colab upload ---
echo "Creating flat files for Colab upload..."
cp scripts/training_data/final/query_parser/train.jsonl scripts/training_data/final/query_parser_train.jsonl
cp scripts/training_data/final/query_parser/val.jsonl scripts/training_data/final/query_parser_val.jsonl
cp scripts/training_data/final/explainer/train.jsonl scripts/training_data/final/explainer_train.jsonl
cp scripts/training_data/final/explainer/val.jsonl scripts/training_data/final/explainer_val.jsonl
cp scripts/training_data/final/evaluator/train.jsonl scripts/training_data/final/evaluator_train.jsonl
cp scripts/training_data/final/evaluator/val.jsonl scripts/training_data/final/evaluator_val.jsonl
echo "Done."
echo ""

# --- Summary ---
echo "============================================================"
echo "FINAL SUMMARY"
echo "============================================================"
echo ""
echo "Raw pairs:"
wc -l scripts/training_data/pairs/*.jsonl
echo ""
echo "Final splits:"
wc -l scripts/training_data/final/*/*.jsonl
echo ""
echo "Flat files for Colab:"
ls -la scripts/training_data/final/*_train.jsonl scripts/training_data/final/*_val.jsonl 2>/dev/null
echo ""
echo "Backup location: $BACKUP_DIR"
echo "Finished: $(date '+%H:%M:%S')"
