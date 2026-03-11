'use client';

import { useState } from 'react';
import PolicyTable from './PolicyTable';
import { PolicyBill } from '@/lib/types';

interface Props {
  bills: PolicyBill[];
  stateName: string;
  accent?: string;
}

export default function PolicyBadge({ bills, stateName, accent = '#00ff32' }: Props) {
  const [open, setOpen] = useState(false);

  if (!bills.length) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
          border transition-colors"
        style={{
          backgroundColor: `${accent}1a`,
          color: accent,
          borderColor: `${accent}4d`,
        }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: accent }}
        />
        {bills.length} bill{bills.length !== 1 ? 's' : ''}
      </button>

      {open && (
        <div className="fixed inset-y-0 right-0 w-full max-w-lg z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/50"
            role="button"
            tabIndex={0}
            aria-label="Close policy panel"
            onClick={() => setOpen(false)}
            onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}
          />
          {/* Panel */}
          <div role="dialog" aria-modal="true" className="relative ml-auto h-full w-full max-w-lg bg-[#1a1a1a] border-l border-[#404040] overflow-y-auto p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">
                Policy Tracker — <span style={{ color: accent }}>{stateName}</span>
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close panel"
                className="text-gray-500 hover:text-white text-xl"
              >
                &times;
              </button>
            </div>
            <PolicyTable bills={bills} />
          </div>
        </div>
      )}
    </>
  );
}
