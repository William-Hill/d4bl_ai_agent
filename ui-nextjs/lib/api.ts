// API base URL - use environment variable or default to localhost:8000
// In development, Next.js rewrites will proxy /api/* requests
// In production, set NEXT_PUBLIC_API_URL to your deployed backend URL
const getApiBase = () => {
  if (typeof window === 'undefined') {
    // Server-side: use environment variable or default
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  }
  // Client-side: use environment variable, or empty string for relative URLs (proxied by Next.js)
  return process.env.NEXT_PUBLIC_API_URL || '';
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

