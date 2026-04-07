-- Add usage JSONB column to research_jobs for LLM token usage and cost tracking
ALTER TABLE research_jobs
ADD COLUMN IF NOT EXISTS usage JSONB;

COMMENT ON COLUMN research_jobs.usage IS 'LLM token usage and estimated cost: {total_tokens, prompt_tokens, completion_tokens, successful_requests, estimated_cost_usd}';
