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

const API_BASE = getApiBase();

export interface ResearchRequest {
  query: string;
  summary_format: 'brief' | 'detailed' | 'comprehensive';
}

export interface ResearchResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface JobStatus {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  progress?: string;
  result?: any;
  error?: string;
}

export async function createResearchJob(
  query: string,
  summaryFormat: string
): Promise<ResearchResponse> {
  const response = await fetch(`${API_BASE}/api/research`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      summary_format: summaryFormat,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create research job');
  }

  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}`);

  if (!response.ok) {
    throw new Error('Failed to fetch job status');
  }

  return response.json();
}

