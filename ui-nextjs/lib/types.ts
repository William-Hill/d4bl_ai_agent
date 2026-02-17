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
