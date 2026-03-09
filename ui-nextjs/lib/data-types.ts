export interface IngestionRun {
  id: string;
  data_source_id: string;
  dagster_run_id: string | null;
  status: string;
  triggered_by: string | null;
  trigger_type: string;
  records_ingested: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_detail: string | null;
}

export interface DataSource {
  id: string;
  name: string;
  source_type: string;
  config: Record<string, unknown>;
  default_schedule: string | null;
  enabled: boolean;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_run_status: string | null;
  last_run_at: string | null;
}

export const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-green-900/40 text-green-400 border-green-800',
  running: 'bg-yellow-900/40 text-yellow-400 border-yellow-800',
  failed: 'bg-red-900/40 text-red-400 border-red-800',
  pending: 'bg-gray-800/40 text-gray-400 border-gray-700',
};

export const TYPE_LABELS: Record<string, string> = {
  api: 'API',
  file_upload: 'File',
  web_scrape: 'Web',
  rss_feed: 'RSS',
  database: 'DB',
  mcp: 'MCP',
};
