'use client';

import { useState, FormEvent } from 'react';

interface ResearchFormProps {
  onSubmit: (query: string, summaryFormat: string, selectedAgents?: string[]) => void;
  disabled?: boolean;
}

const AVAILABLE_AGENTS = [
  { id: 'researcher', label: 'Researcher', description: 'Conducts web research' },
  { id: 'data_analyst', label: 'Data Analyst', description: 'Analyzes research data' },
  { id: 'writer', label: 'Writer', description: 'Writes summaries' },
  { id: 'fact_checker', label: 'Fact Checker', description: 'Verifies claims' },
  { id: 'citation_agent', label: 'Citation Agent', description: 'Manages citations' },
  { id: 'bias_detection_agent', label: 'Bias Detection', description: 'Detects biases' },
  { id: 'editor', label: 'Editor', description: 'Edits and refines' },
  { id: 'data_visualization_agent', label: 'Data Visualization', description: 'Creates visualizations' },
];

export default function ResearchForm({ onSubmit, disabled }: ResearchFormProps) {
  const [query, setQuery] = useState('');
  const [summaryFormat, setSummaryFormat] = useState('detailed');
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim() && !disabled) {
      onSubmit(query.trim(), summaryFormat, selectedAgents.length > 0 ? selectedAgents : undefined);
    }
  };

  const toggleAgent = (agentId: string) => {
    setSelectedAgents(prev =>
      prev.includes(agentId)
        ? prev.filter(id => id !== agentId)
        : [...prev, agentId]
    );
  };

  return (
    <div className="bg-[#333333] border border-[#404040] rounded-lg p-8 shadow-sm">
      <h2 className="text-2xl font-bold text-white mb-6">
        Start New Research
      </h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="query"
            className="block text-sm font-medium text-gray-300 mb-2"
          >
            Research Query
          </label>
          <textarea
            id="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={4}
            placeholder="Enter your research question here...&#10;&#10;Example: How does algorithmic bias affect criminal justice outcomes for Black communities?"
            className="w-full px-4 py-3 border border-[#404040] rounded-md focus:outline-none focus:ring-2 focus:ring-[#00ff32] focus:border-[#00ff32] text-white placeholder:text-gray-500 bg-[#292929] disabled:bg-[#1a1a1a] disabled:text-gray-500"
            required
            disabled={disabled}
          />
        </div>

        <div>
          <label
            htmlFor="summaryFormat"
            className="block text-sm font-medium text-gray-300 mb-2"
          >
            Summary Format
          </label>
          <select
            id="summaryFormat"
            value={summaryFormat}
            onChange={(e) => setSummaryFormat(e.target.value)}
            className="w-full px-4 py-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-black focus:border-black text-black bg-white disabled:bg-gray-50 disabled:text-gray-600"
            disabled={disabled}
          >
            <option value="brief">Brief (250-500 words)</option>
            <option value="detailed">Detailed (1000-1500 words)</option>
            <option value="comprehensive">Comprehensive (2000-3000 words)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Select Agents (optional - leave empty to run all)
          </label>
          <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto border border-[#404040] rounded-md p-3 bg-[#292929]">
            {AVAILABLE_AGENTS.map((agent) => (
              <label
                key={agent.id}
                className="flex items-start space-x-2 cursor-pointer hover:bg-[#333333] p-2 rounded"
              >
                <input
                  type="checkbox"
                  checked={selectedAgents.includes(agent.id)}
                  onChange={() => toggleAgent(agent.id)}
                  disabled={disabled}
                  className="mt-1 h-4 w-4 text-[#00ff32] border-[#404040] rounded focus:ring-[#00ff32] focus:ring-2 bg-[#1a1a1a]"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium text-white">{agent.label}</div>
                  <div className="text-xs text-gray-400">{agent.description}</div>
                </div>
              </label>
            ))}
          </div>
          {selectedAgents.length > 0 && (
            <p className="mt-2 text-xs text-gray-400">
              Selected: {selectedAgents.length} agent(s)
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={disabled || !query.trim()}
            className="w-full bg-[#00ff32] text-black py-3 px-6 rounded-md hover:bg-[#00cc28] focus:outline-none focus:ring-2 focus:ring-[#00ff32] focus:ring-offset-2 focus:ring-offset-[#292929] disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {disabled ? 'Research in Progress...' : 'Start Research'}
        </button>
      </form>
    </div>
  );
}

