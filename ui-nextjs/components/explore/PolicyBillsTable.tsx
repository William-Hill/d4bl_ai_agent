'use client';

import { useMemo, useState } from 'react';
import { PolicyBill } from '@/lib/types';
import { formatRelativeDate, statusToPhase } from '@/lib/explore-config';
import PhaseGlyph from './PhaseGlyph';

interface Props {
  bills: PolicyBill[];
}

type SortKey = 'state' | 'bill_number' | 'title' | 'phase' | 'last_action';
type SortDir = 'asc' | 'desc';

interface Column {
  key: SortKey | null;
  label: string;
  className?: string;
  align?: 'left' | 'right';
}

const COLUMNS: Column[] = [
  { key: 'state', label: 'state', className: 'w-14' },
  { key: 'bill_number', label: 'bill no.', className: 'w-28' },
  { key: 'title', label: 'title' },
  { key: 'phase', label: 'phase', className: 'w-32' },
  { key: null, label: 'topics', className: 'w-40' },
  { key: 'last_action', label: 'last action', className: 'w-28', align: 'right' },
  { key: null, label: '', className: 'w-6' },
];

function compareBills(a: PolicyBill, b: PolicyBill, key: SortKey): number {
  switch (key) {
    case 'state':
      return a.state.localeCompare(b.state);
    case 'bill_number':
      return a.bill_number.localeCompare(b.bill_number, undefined, { numeric: true });
    case 'title':
      return a.title.localeCompare(b.title);
    case 'phase':
      return (
        statusToPhase(a.status).segments - statusToPhase(b.status).segments ||
        a.status.localeCompare(b.status)
      );
    case 'last_action': {
      const av = a.last_action_date ?? '';
      const bv = b.last_action_date ?? '';
      return av.localeCompare(bv);
    }
  }
}

export default function PolicyBillsTable({ bills }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('last_action');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const sorted = useMemo(() => {
    const copy = [...bills];
    copy.sort((a, b) => {
      const cmp = compareBills(a, b, sortKey);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [bills, sortKey, sortDir]);

  const onSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'last_action' ? 'desc' : 'asc');
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr>
            {COLUMNS.map((col, idx) => {
              const sortable = col.key !== null;
              const isActive = sortable && col.key === sortKey;
              return (
                <th
                  key={`${col.label}-${idx}`}
                  scope="col"
                  aria-sort={
                    isActive
                      ? sortDir === 'asc'
                        ? 'ascending'
                        : 'descending'
                      : sortable
                        ? 'none'
                        : undefined
                  }
                  className={`sticky top-0 z-10 bg-[#0f0f0f] border-b border-[#00ff32]/20
                             px-3 py-2.5 text-[10px] font-mono uppercase tracking-[0.18em]
                             ${sortable ? 'select-none' : ''}
                             ${isActive ? 'text-[#00ff32]' : 'text-gray-500'}
                             ${col.align === 'right' ? 'text-right' : 'text-left'}
                             ${col.className ?? ''}`}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => onSort(col.key!)}
                      className="inline-flex items-center gap-1 hover:text-[#00ff32] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#00ff32]/60 rounded"
                    >
                      {col.label}
                      <span
                        aria-hidden="true"
                        className={`text-[9px] leading-none ${
                          isActive ? 'opacity-100' : 'opacity-30'
                        }`}
                      >
                        {isActive ? (sortDir === 'asc' ? '▲' : '▼') : '▾'}
                      </span>
                    </button>
                  ) : (
                    <span className="inline-flex items-center gap-1">{col.label}</span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((bill) => {
            const phase = statusToPhase(bill.status);
            const extraTopics = (bill.topic_tags?.length ?? 0) - 2;
            return (
              <tr
                key={bill.url ?? `${bill.state}-${bill.bill_number}`}
                className="group border-b border-[#1f1f1f] last:border-b-0
                           odd:bg-[#ffffff03] hover:bg-[#00ff3208]
                           transition-colors"
              >
                <td className="pl-3 pr-3 py-2.5 font-mono font-bold text-sm tracking-[0.12em] text-gray-200 group-hover:text-[#00ff32] border-l-2 border-transparent group-hover:border-[#00ff32] transition-colors">
                  {bill.state}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-gray-500">
                  {bill.bill_number}
                </td>
                <td className="px-3 py-2.5 text-sm text-gray-100 leading-snug">
                  <span className="line-clamp-2">{bill.title}</span>
                </td>
                <td className="px-3 py-2.5">
                  <span className="inline-flex items-center gap-2">
                    <PhaseGlyph phase={phase} />
                    <span className="text-[11px] font-mono text-gray-500 whitespace-nowrap">
                      {phase.label}
                    </span>
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {bill.topic_tags && bill.topic_tags.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {bill.topic_tags.slice(0, 2).map((tag) => (
                        <span
                          key={tag}
                          className="px-1.5 py-0.5 rounded bg-[#2a2a2a] text-[10px] text-gray-400 capitalize whitespace-nowrap"
                        >
                          {tag}
                        </span>
                      ))}
                      {extraTopics > 0 && (
                        <span
                          title={bill.topic_tags.slice(2).join(', ')}
                          className="px-1.5 py-0.5 rounded border border-[#2a2a2a] text-[10px] text-gray-500"
                        >
                          +{extraTopics}
                          <span className="sr-only">
                            {` more topics: ${bill.topic_tags.slice(2).join(', ')}`}
                          </span>
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-[10px] font-mono text-gray-700">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[11px] text-gray-500 whitespace-nowrap">
                  {formatRelativeDate(bill.last_action_date)}
                </td>
                <td className="px-3 py-2.5 text-right">
                  {bill.url ? (
                    <a
                      href={bill.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`View ${bill.bill_number}: ${bill.title}`}
                      className="text-[#00ff32]/60 hover:text-[#00ff32] font-mono text-sm transition-colors"
                    >
                      →
                    </a>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
