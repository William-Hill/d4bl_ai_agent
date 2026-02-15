"use client";

import { useState } from "react";

interface QuerySource {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
  relevance_score: number;
}

interface QueryResponse {
  answer: string;
  sources: QuerySource[];
  query: string;
}

interface QueryBarProps {
  onResult: (result: QueryResponse) => void;
  onLoading: (loading: boolean) => void;
  onError: (error: string | null) => void;
}

export default function QueryBar({ onResult, onLoading, onError }: QueryBarProps) {
  const [question, setQuestion] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    onLoading(true);
    onError(null);

    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (!response.ok) {
        throw new Error(`Query failed: ${response.statusText}`);
      }

      const data: QueryResponse = await response.json();
      onResult(data);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Query failed");
    } finally {
      onLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask a question about your research data..."
        className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-[#00ff32]"
      />
      <button
        type="submit"
        disabled={!question.trim()}
        className="px-6 py-2 bg-[#00ff32] text-black font-medium rounded-lg hover:bg-[#00cc28] disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Query
      </button>
    </form>
  );
}
