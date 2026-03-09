'use client';

import { useState } from 'react';
import Link from 'next/link';
import { DataSource, STATUS_STYLES, TYPE_LABELS } from '@/lib/data-types';

interface SourceTableProps {
  sources: DataSource[];
  onToggleEnabled: (id: string, enabled: boolean) => Promise<void>;
}

export default function SourceTable({ sources, onToggleEnabled }: SourceTableProps) {
  const [togglingIds, setTogglingIds] = useState<Set<string>>(new Set());

  const handleToggle = async (id: string, currentEnabled: boolean) => {
    setTogglingIds((prev) => new Set(prev).add(id));
    try {
      await onToggleEnabled(id, !currentEnabled);
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  if (sources.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg px-4 py-12 text-center">
        <p className="text-gray-500 text-sm mb-3">No data sources configured yet.</p>
        <Link
          href="/data/sources/new"
          className="inline-block px-4 py-2 bg-[#00ff32] text-black text-sm font-medium rounded hover:bg-[#00dd2b] transition-colors"
        >
          Add your first source
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#404040]">
              <th className="px-4 py-3 text-left text-sm text-gray-400">Name</th>
              <th className="px-4 py-3 text-left text-sm text-gray-400">Type</th>
              <th className="px-4 py-3 text-left text-sm text-gray-400">Schedule</th>
              <th className="px-4 py-3 text-left text-sm text-gray-400">Last Run</th>
              <th className="px-4 py-3 text-left text-sm text-gray-400">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.id} className="border-b border-[#404040] last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/data/sources/${source.id}`}
                    className="text-white text-sm hover:text-[#00ff32] transition-colors"
                  >
                    {source.name}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span className="inline-block text-xs px-2 py-0.5 rounded border border-[#404040] bg-[#292929] text-gray-300">
                    {TYPE_LABELS[source.source_type] ?? source.source_type}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400 text-sm font-mono">
                  {source.default_schedule ?? '-'}
                </td>
                <td className="px-4 py-3">
                  {source.last_run_status ? (
                    <span
                      className={`inline-block text-xs px-2 py-0.5 rounded border ${
                        STATUS_STYLES[source.last_run_status] ?? STATUS_STYLES.pending
                      }`}
                    >
                      {source.last_run_status}
                    </span>
                  ) : (
                    <span className="text-gray-500 text-sm">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    disabled={togglingIds.has(source.id)}
                    onClick={() => handleToggle(source.id, source.enabled)}
                    className={`relative w-10 h-5 rounded-full transition-colors focus:outline-none ${
                      source.enabled ? 'bg-[#00ff32]/60' : 'bg-[#404040]'
                    } ${togglingIds.has(source.id) ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                        source.enabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
