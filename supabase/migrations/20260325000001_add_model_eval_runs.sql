-- Track evaluation runs per model version for regression detection
CREATE TABLE IF NOT EXISTS model_eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    base_model_name VARCHAR(100) NOT NULL,
    task VARCHAR(50) NOT NULL,
    test_set_hash VARCHAR(64) NOT NULL,
    metrics JSONB NOT NULL,
    ship_decision VARCHAR(20) NOT NULL,
    blocking_failures JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_eval_runs_model_name ON model_eval_runs (model_name);
CREATE INDEX IF NOT EXISTS idx_model_eval_runs_task ON model_eval_runs (task);
CREATE INDEX IF NOT EXISTS idx_model_eval_runs_created_at ON model_eval_runs (created_at);
CREATE INDEX IF NOT EXISTS idx_model_eval_runs_model_task_created_at
ON model_eval_runs (model_name, task, created_at DESC);
