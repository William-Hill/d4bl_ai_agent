'use client';

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { ExploreRow } from '@/lib/types';
import { humanizeMetric, getMetricDirection } from '@/lib/explore-config';

const COLLAPSE_KEY = "d4bl-table-collapsed";

function loadCollapsePreference(defaultValue: boolean): boolean {
  if (typeof window === "undefined") return defaultValue;
  try {
    const stored = localStorage.getItem(COLLAPSE_KEY);
    return stored !== null ? stored === "true" : defaultValue;
  } catch {
    return defaultValue;
  }
}

export interface DataTableProps {
  rows: ExploreRow[];
  nationalAverage: number | null;
  metric: string | null;
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
  accent: string;
  defaultCollapsed?: boolean;
  sourceKey: string;
}

type SortKey = 'name' | 'value' | 'rank' | 'vs_national';
type SortDir = 'asc' | 'desc';

interface TableRow {
  fips: string;
  name: string;
  value: number;
  rank: number;
  vsNational: number | null;
}

/** Format a number for display: ≥1M → "1.2M", ≥1K → "1.2K", int → integer, float → 1dp */
function formatValue(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(1);
}

/** Format vs-national difference with sign prefix. */
function formatDiff(diff: number): string {
  const formatted = formatValue(Math.abs(diff));
  return diff >= 0 ? `+${formatted}` : `-${formatted}`;
}

function SortIcon({ active, dir, accent }: { active: boolean; dir: SortDir; accent: string }) {
  if (!active) return <span className="ml-1 text-[#555]">↕</span>;
  return (
    <span className="ml-1" style={{ color: accent }}>
      {dir === 'asc' ? '↑' : '↓'}
    </span>
  );
}

interface HeaderCellProps {
  col: SortKey;
  label: string;
  align?: 'left' | 'right';
  sortKey: SortKey;
  sortDir: SortDir;
  accent: string;
  onSort: (col: SortKey) => void;
}

function HeaderCell({ col, label, align = 'left', sortKey, sortDir, accent, onSort }: HeaderCellProps) {
  return (
    <th
      className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[#999] cursor-pointer select-none whitespace-nowrap hover:text-[#ccc] transition-colors ${align === 'right' ? 'text-right' : 'text-left'}`}
      onClick={() => onSort(col)}
    >
      {label}
      <SortIcon active={sortKey === col} dir={sortDir} accent={accent} />
    </th>
  );
}

export default function DataTable({
  rows,
  nationalAverage,
  metric,
  selectedStateFips,
  onSelectState,
  accent,
  defaultCollapsed,
  sourceKey,
}: DataTableProps) {
  // Determine if "above national average" is good or bad for this metric
  const metricDir = metric ? getMetricDirection(sourceKey, metric) : null;

  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const selectedRowRef = useRef<HTMLTableRowElement | null>(null);
  const [collapsed, setCollapsed] = useState(() =>
    loadCollapsePreference(defaultCollapsed ?? false)
  );

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem(COLLAPSE_KEY, String(next)); } catch {}
      return next;
    });
  }, []);

  // Compute deduplicated table rows: filter metric + race=total/null, one row per state, ranked
  const tableRows = useMemo<TableRow[]>(() => {
    if (!metric) return [];

    // Filter to the active metric
    const filtered = rows.filter(r => r.metric === metric);

    // Prefer race="total"; fall back to race=null rows
    const totalRows = filtered.filter(r => r.race === 'total');
    const working = totalRows.length > 0 ? totalRows : filtered.filter(r => r.race == null);

    // Dedupe to one row per state (latest year)
    const byState = new Map<string, ExploreRow>();
    for (const r of working) {
      const prev = byState.get(r.state_fips);
      if (!prev || r.year > prev.year) byState.set(r.state_fips, r);
    }

    // Sort by value descending to assign ranks
    const sorted = [...byState.values()].sort((a, b) => b.value - a.value);

    return sorted.map((r, i) => ({
      fips: r.state_fips,
      name: r.state_name,
      value: r.value,
      rank: i + 1,
      vsNational: nationalAverage != null ? r.value - nationalAverage : null,
    }));
  }, [rows, metric, nationalAverage]);

  // Apply user-chosen sort
  const sortedRows = useMemo<TableRow[]>(() => {
    return [...tableRows].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'name':
          cmp = a.name.localeCompare(b.name);
          break;
        case 'value':
          cmp = a.value - b.value;
          break;
        case 'rank':
          cmp = a.rank - b.rank;
          break;
        case 'vs_national':
          cmp = (a.vsNational ?? 0) - (b.vsNational ?? 0);
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [tableRows, sortKey, sortDir]);

  // Toggle sort: same key flips direction; new key resets to default direction
  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Default directions: name asc, rank asc, others desc
      setSortDir(key === 'name' || key === 'rank' ? 'asc' : 'desc');
    }
  }

  // Auto-scroll selected row into view when map selection changes
  useEffect(() => {
    if (selectedStateFips && selectedRowRef.current) {
      selectedRowRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedStateFips]);

  if (!metric || tableRows.length === 0) return null;

  const metricLabel = humanizeMetric(metric);

  return (
    <div className="mb-6 bg-[#111] border border-[#333] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-[#333] flex items-center gap-2">
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: accent }} />
        <h2 className="text-sm font-semibold text-[#e5e5e5]">
          {metricLabel} — All States
        </h2>
        <span className="text-xs text-[#666] ml-auto">{tableRows.length} states</span>
      </div>

      <button
        type="button"
        onClick={toggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-xs text-[#999] hover:text-white"
      >
        <span>Data Table <span className="text-[#666]">({tableRows.length} states)</span></span>
        <span>{collapsed ? "▶" : "▼"}</span>
      </button>

      {!collapsed && (
        <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 bg-[#111] z-10">
              <tr className="border-b border-[#333]">
                <HeaderCell col="name" label="State" sortKey={sortKey} sortDir={sortDir} accent={accent} onSort={handleSort} />
                <HeaderCell col="value" label={metricLabel} align="right" sortKey={sortKey} sortDir={sortDir} accent={accent} onSort={handleSort} />
                <HeaderCell col="rank" label="Rank" align="right" sortKey={sortKey} sortDir={sortDir} accent={accent} onSort={handleSort} />
                {nationalAverage != null && (
                  <HeaderCell col="vs_national" label="vs National" align="right" sortKey={sortKey} sortDir={sortDir} accent={accent} onSort={handleSort} />
                )}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map(row => {
                const isSelected = row.fips === selectedStateFips;
                return (
                  <tr
                    key={row.fips}
                    ref={isSelected ? selectedRowRef : null}
                    onClick={() => onSelectState(row.fips, row.name)}
                    className="border-b border-[#222] cursor-pointer transition-colors hover:bg-[#1a1a1a]"
                    style={
                      isSelected
                        ? { backgroundColor: `${accent}18` }
                        : undefined
                    }
                  >
                    <td className="px-3 py-2 text-[#e5e5e5] font-medium">
                      {isSelected && (
                        <span
                          className="mr-1.5 inline-block w-1.5 h-1.5 rounded-full align-middle"
                          style={{ backgroundColor: accent }}
                        />
                      )}
                      {row.name}
                    </td>
                    <td className="px-3 py-2 text-right text-[#ccc] tabular-nums">
                      {formatValue(row.value)}
                    </td>
                    <td className="px-3 py-2 text-right text-[#999] tabular-nums">
                      #{row.rank}
                    </td>
                    {nationalAverage != null && (
                      <td
                        className="px-3 py-2 text-right tabular-nums font-medium"
                        style={{
                          color:
                            row.vsNational == null
                              ? '#666'
                              : (metricDir === false
                                  ? row.vsNational < 0  // high is bad → below avg is good
                                  : row.vsNational >= 0) // high is good/neutral → above avg is good
                              ? '#22c55e'
                              : '#ef4444',
                        }}
                      >
                        {row.vsNational != null ? formatDiff(row.vsNational) : '—'}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
