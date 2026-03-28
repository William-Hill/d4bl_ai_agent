-- Add suggestions column for post-eval analysis (rules-based + LLM)
ALTER TABLE model_eval_runs ADD COLUMN IF NOT EXISTS suggestions JSONB;
