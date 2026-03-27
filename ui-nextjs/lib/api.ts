import { ResearchResult } from './types';
import { createClient } from './supabase';

// API base URL
// Strategy:
// - Client-side (browser): Use NEXT_PUBLIC_API_URL to call API directly (browser can access localhost:8000)
// - Server-side (SSR): Use API_INTERNAL_URL for Docker internal networking
const getApiBase = () => {
  if (typeof window === 'undefined') {
    // Server-side: use internal URL if available (for Docker), otherwise use public URL
    return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  }
  // Client-side: Use NEXT_PUBLIC_API_URL if set (browser can access localhost:8000)
  // Otherwise use relative URL for Next.js rewrite
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    return apiUrl.replace(/\/$/, '');
  }
  // Fallback to relative URL (for development without Docker)
  return '';
};

export const API_BASE = getApiBase();
export const WS_BASE = API_BASE.replace(/^http/, 'ws');

async function getAuthHeaders(): Promise<Record<string, string>> {
  if (typeof window !== 'undefined') {
    try {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        return {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        };
      }
    } catch {
      // Supabase not configured; proceed without auth headers
    }
  }
  return { 'Content-Type': 'application/json' };
}

function handle401(response: Response): void {
  if (response.status === 401 && typeof window !== 'undefined') {
    window.location.href = '/login';
    throw new Error('Authentication required');
  }
}

export interface ResearchRequest {
  query: string;
  summary_format: 'brief' | 'detailed' | 'comprehensive';
  selected_agents?: string[];
}

export interface ResearchResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface JobStatus {
  job_id: string;
  trace_id?: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress?: string;
  result?: ResearchResult;
  error?: string;
  query?: string;
  summary_format?: string;
  logs?: string[];
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
}

export interface JobHistoryResponse {
  jobs: JobStatus[];
  total: number;
  page: number;
  page_size: number;
}

export interface EvaluationResultItem {
  id: string;
  span_id: string;
  trace_id?: string;
  eval_name: string;
  label?: string;
  score?: number;
  explanation?: string;
  input_text?: string;
  output_text?: string;
  context_text?: string;
  created_at?: string;
}

export async function createResearchJob(
  query: string,
  summaryFormat: string,
  selectedAgents?: string[],
  model?: string
): Promise<ResearchResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/research`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query,
      summary_format: summaryFormat,
      selected_agents: selectedAgents,
      model,
    }),
  });

  handle401(response);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create research job');
  }

  return response.json();
}

export async function getEvaluations(params?: {
  trace_id?: string;
  job_id?: string;  // job_id maps to trace_id in Phoenix
  span_id?: string;
  eval_name?: string;
  limit?: number;
}): Promise<EvaluationResultItem[]> {
  const search = new URLSearchParams();
  if (params?.job_id) search.append('job_id', params.job_id);
  if (params?.trace_id) search.append('trace_id', params.trace_id);
  if (params?.span_id) search.append('span_id', params.span_id);
  if (params?.eval_name) search.append('eval_name', params.eval_name);
  if (params?.limit) search.append('limit', params.limit.toString());

  const queryString = search.toString();
  const url = queryString ? `${API_BASE}/api/evaluations?${queryString}` : `${API_BASE}/api/evaluations`;

  const headers = await getAuthHeaders();
  const response = await fetch(url, { headers });

  handle401(response);

  if (!response.ok) {
    throw new Error('Failed to fetch evaluations');
  }

  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}`, { headers });

  handle401(response);

  if (!response.ok) {
    throw new Error('Failed to fetch job status');
  }

  return response.json();
}

export async function getJobHistory(
  page: number = 1,
  pageSize: number = 20,
  status?: string
): Promise<JobHistoryResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });

  if (status) {
    params.append('status', status);
  }

  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/jobs?${params.toString()}`, { headers });

  handle401(response);

  if (!response.ok) {
    throw new Error('Failed to fetch job history');
  }

  return response.json();
}

export async function getAuthToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null;
  try {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  } catch {
    return null;
  }
}

// --- Model Comparison types ---

export interface PipelineStep {
  step: string;
  model_name: string;
  output: string;
  latency_seconds: number;
}

export interface PipelinePath {
  label: string;
  steps: PipelineStep[];
  final_answer: string;
  total_latency_seconds: number;
  eval_score: number | null;
}

export interface CompareResponse {
  baseline: PipelinePath;
  finetuned: PipelinePath;
  prompt: string;
}

export interface EvalRunItem {
  model_name: string;
  model_version: string;
  base_model_name: string;
  task: string;
  metrics: Record<string, number | null>;
  ship_decision: string;
  blocking_failures: Record<string, unknown>[] | null;
  created_at: string | null;
}

export interface EvalRunsResponse {
  runs: EvalRunItem[];
}

export async function compareModels(prompt: string): Promise<CompareResponse> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/compare`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ prompt }),
  });

  handle401(response);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Model comparison failed');
  }

  return response.json();
}

export async function getEvalRuns(task?: string): Promise<EvalRunsResponse> {
  const params = task ? `?task=${encodeURIComponent(task)}` : '';
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE}/api/eval-runs${params}`, { headers });

  handle401(response);

  if (!response.ok) {
    throw new Error('Failed to fetch evaluation runs');
  }

  return response.json();
}
