'use client';

import { useState } from 'react';

interface PolicyBill {
  state: string;
  state_name?: string;
  bill_number: string;
  title: string;
  summary: string | null;
  status: string;
  topic_tags: string[] | null;
  introduced_date: string | null;
  last_action_date: string | null;
  url: string | null;
}

interface Props {
  bills: PolicyBill[];
}

const STATUS_COLORS: Record<string, string> = {
  introduced: 'bg-blue-900 text-blue-300',
  passed: 'bg-green-900 text-green-300',
  signed: 'bg-[#1a3a1a] text-[#00ff32]',
  failed: 'bg-red-900 text-red-300',
  other: 'bg-[#333] text-gray-400',
};

const ALL_TOPICS = [
  'housing',
  'wealth',
  'education',
  'criminal justice',
  'voting rights',
  'economic development',
  'health care',
];

export default function PolicyTable({ bills }: Props) {
  const [activeTopic, setActiveTopic] = useState<string | null>(null);

  const filtered = activeTopic
    ? bills.filter((b) => b.topic_tags?.includes(activeTopic))
    : bills;

  return (
    <div className="space-y-3">
      {/* Topic filter chips */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setActiveTopic(null)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
            activeTopic === null
              ? 'bg-[#00ff32] text-black'
              : 'bg-[#2a2a2a] text-gray-400 border border-[#404040] hover:border-[#00ff32]'
          }`}
        >
          All
        </button>
        {ALL_TOPICS.map((topic) => (
          <button
            key={topic}
            onClick={() => setActiveTopic(activeTopic === topic ? null : topic)}
            className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
              activeTopic === topic
                ? 'bg-[#00ff32] text-black'
                : 'bg-[#2a2a2a] text-gray-400 border border-[#404040] hover:border-[#00ff32]'
            }`}
          >
            {topic}
          </button>
        ))}
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">
          No bills match this filter.
        </p>
      ) : (
        <div className="divide-y divide-[#404040]">
          {filtered.map((bill, i) => (
            <div key={i} className="py-3 flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-gray-500">{bill.bill_number}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      STATUS_COLORS[bill.status] ?? STATUS_COLORS.other
                    }`}
                  >
                    {bill.status}
                  </span>
                  {bill.topic_tags?.slice(0, 2).map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 rounded bg-[#2a2a2a] text-xs text-gray-400 capitalize"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <p className="text-sm text-gray-200 leading-snug">{bill.title}</p>
                {bill.last_action_date && (
                  <p className="text-xs text-gray-500 mt-1">
                    Last action: {bill.last_action_date}
                  </p>
                )}
              </div>
              {bill.url && (
                <a
                  href={bill.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-xs text-[#00ff32] hover:underline"
                >
                  View →
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

