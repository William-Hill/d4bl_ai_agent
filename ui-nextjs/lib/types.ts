export interface QuerySource {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
  relevance_score: number;
}

export interface QueryResponse {
  answer: string;
  sources: QuerySource[];
  query: string;
}

/** Census / ACS indicator row returned by the explore API. */
export interface IndicatorRow {
  fips_code: string;
  geography_name: string;
  state_fips: string;
  geography_type: string;
  year: number;
  race: string;
  metric: string;
  value: number;
  margin_of_error: number | null;
}

/** Policy bill returned by the explore API. */
export interface PolicyBill {
  state: string;
  state_name: string;
  bill_number: string;
  title: string;
  summary: string | null;
  status: string;
  topic_tags: string[] | null;
  introduced_date: string | null;
  last_action_date: string | null;
  url: string | null;
}

/** Individual task output from a CrewAI agent. */
export interface ResearchTaskOutput {
  agent?: string;
  output?: string;
}

/** Result payload returned when a research job completes. */
export interface ResearchResult {
  report?: string;
  tasks_output?: ResearchTaskOutput[];
  raw_output?: string;
}
