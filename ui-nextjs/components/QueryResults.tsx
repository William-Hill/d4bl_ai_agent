"use client";

interface QuerySource {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
  relevance_score: number;
}

interface QueryResultsProps {
  answer: string;
  sources: QuerySource[];
  query: string;
}

export default function QueryResults({ answer, sources, query }: QueryResultsProps) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 space-y-4">
      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-1">Query</h3>
        <p className="text-white">{query}</p>
      </div>

      <div>
        <h3 className="text-sm font-medium text-gray-400 mb-1">Answer</h3>
        <div className="text-white whitespace-pre-wrap">{answer}</div>
      </div>

      {sources.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-2">
            Sources ({sources.length})
          </h3>
          <ul className="space-y-2">
            {sources.map((source, i) => (
              <li
                key={i}
                className="bg-gray-800 rounded p-3 text-sm"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      source.source_type === "vector"
                        ? "bg-blue-900 text-blue-300"
                        : "bg-purple-900 text-purple-300"
                    }`}
                  >
                    {source.source_type}
                  </span>
                  <span className="text-gray-500 text-xs">
                    {(source.relevance_score * 100).toFixed(0)}% relevant
                  </span>
                </div>
                <p className="text-white font-medium">{source.title}</p>
                <p className="text-gray-400 mt-1">{source.snippet}</p>
                {source.url && !source.url.startsWith("job://") && (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#00ff32] text-xs mt-1 inline-block hover:underline"
                  >
                    {source.url}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
