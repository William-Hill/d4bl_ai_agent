'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RelatedDocument, RelatedDocumentsResponse } from '@/lib/types';
import { API_BASE } from '@/lib/api';
import { humanizeMetric } from '@/lib/explore-config';

const COLLAPSE_KEY = 'd4bl-explore-related-docs-collapsed';

function loadCollapsePreference(defaultValue: boolean): boolean {
  if (typeof window === 'undefined') return defaultValue;
  try {
    const stored = window.localStorage.getItem(COLLAPSE_KEY);
    return stored !== null ? stored === 'true' : defaultValue;
  } catch {
    return defaultValue;
  }
}

type CategoryFilter = 'all' | 'policy' | 'research' | 'web';

type SortKey = 'created_at' | 'title' | 'content_type';
type SortDir = 'asc' | 'desc';

function categoryToTypesParam(cat: CategoryFilter): string | null {
  if (cat === 'all') return null;
  if (cat === 'policy') return 'policy_bill';
  if (cat === 'research') return 'research_report';
  return 'scraped,scraped_web';
}

function docCategoryLabel(ct: string): string {
  if (ct === 'policy_bill') return 'Policy';
  if (ct === 'research_report') return 'Research';
  if (ct === 'scraped' || ct === 'scraped_web') return 'Web';
  return ct;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function SortIcon({ active, dir, accent }: { active: boolean; dir: SortDir; accent: string }) {
  if (!active) return <span className="ml-1 text-[#555]">↕</span>;
  return (
    <span className="ml-1" style={{ color: accent }}>
      {dir === 'asc' ? '↑' : '↓'}
    </span>
  );
}

type ColKey = 'kind' | 'title' | 'date';

interface HeaderCellProps {
  col: ColKey;
  label: string;
  align?: 'left' | 'right';
  sortKey: SortKey;
  sortDir: SortDir;
  accent: string;
  onSort: (col: ColKey) => void;
}

function HeaderCell({ col, label, align = 'left', sortKey, sortDir, accent, onSort }: HeaderCellProps) {
  const map: Record<ColKey, SortKey> = {
    kind: 'content_type',
    title: 'title',
    date: 'created_at',
  };
  const sk = map[col];
  const ariaSort =
    sortKey === sk ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none';
  const sortLabel =
    sortKey === sk
      ? `${label}, sorted ${sortDir === 'asc' ? 'ascending' : 'descending'}`
      : `${label}, activate to sort`;

  return (
    <th
      aria-sort={ariaSort}
      className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[#999] whitespace-nowrap ${align === 'right' ? 'text-right' : 'text-left'}`}
    >
      <button
        type="button"
        onClick={() => onSort(col)}
        className={`inline-flex items-center cursor-pointer select-none hover:text-[#ccc] transition-colors ${
          align === 'right' ? 'justify-end w-full text-right' : 'text-left'
        }`}
        aria-label={sortLabel}
      >
        {label}
        <SortIcon active={sortKey === sk} dir={sortDir} accent={accent} />
      </button>
    </th>
  );
}

export interface RelatedDocumentsProps {
  stateFips: string | null;
  metric: string | null;
  accent: string;
  getHeaders: () => Record<string, string>;
  sessionReady: boolean;
}

export default function RelatedDocuments({
  stateFips,
  metric,
  accent,
  getHeaders,
  sessionReady,
}: RelatedDocumentsProps) {
  const [collapsed, setCollapsed] = useState(() => loadCollapsePreference(true));
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [rows, setRows] = useState<RelatedDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const typesParam = useMemo(() => categoryToTypesParam(category), [category]);

  // Stable ref for getHeaders to prevent unnecessary refetches
  const getHeadersRef = useRef(getHeaders);
  useEffect(() => {
    getHeadersRef.current = getHeaders;
  }, [getHeaders]);

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (!sessionReady || !stateFips) {
      setLoading(false);
      setError(null);
      setRows([]);
      setTotal(0);
      return;
    }

    if (collapsed) {
      setRows([]);
      setTotal(0);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set('state_fips', stateFips);
        if (metric && metric.trim()) params.set('metric', metric.trim());
        params.set('sort', sortKey);
        params.set('order', sortDir);
        params.set('limit', '100');
        const tp = typesParam;
        if (tp) params.set('types', tp);

        const res = await fetch(`${API_BASE}/api/documents?${params}`, {
          signal: controller.signal,
          headers: getHeadersRef.current(),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as RelatedDocumentsResponse;
        setRows(data.documents);
        setTotal(data.total);
      } catch (e: unknown) {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : 'Failed to load documents');
        setRows([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [sessionReady, stateFips, metric, sortKey, sortDir, typesParam, collapsed]);

  function handleHeaderSort(col: ColKey) {
    const map: Record<ColKey, SortKey> = {
      kind: 'content_type',
      title: 'title',
      date: 'created_at',
    };
    const nextKey = map[col];
    if (sortKey === nextKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(nextKey);
      setSortDir(nextKey === 'title' || nextKey === 'content_type' ? 'asc' : 'desc');
    }
  }

  if (!stateFips) return null;

  const metricLabel = metric ? humanizeMetric(metric) : 'All metrics';

  const chips: { id: CategoryFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'policy', label: 'Policy' },
    { id: 'research', label: 'Research' },
    { id: 'web', label: 'News & web' },
  ];

  return (
    <div className="mb-6 bg-[#111] border border-[#333] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-[#333] flex items-center gap-2 flex-wrap">
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: accent }} />
        <h2 className="text-sm font-semibold text-[#e5e5e5]">Related documents</h2>
        <span className="text-xs text-[#666]">
          {metricLabel}
          {total > 0
            ? rows.length < total
              ? ` · Showing ${rows.length} of ${total} match${total === 1 ? '' : 'es'}`
              : ` · ${total} match${total === 1 ? '' : 'es'}`
            : ''}
        </span>
      </div>

      <button
        type="button"
        onClick={toggleCollapse}
        aria-expanded={!collapsed}
        aria-controls="related-documents-panel"
        className="flex w-full items-center justify-between px-3 py-2 text-xs text-[#999] hover:text-white"
      >
        <span>
          Bills, research, and scraped sources linked to this state
          {loading && <span className="text-[#666] ml-2">Loading…</span>}
        </span>
        <span>{collapsed ? '▶' : '▼'}</span>
      </button>

      {!collapsed && (
        <div id="related-documents-panel" className="px-3 pb-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            {chips.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCategory(c.id)}
                className={`px-2.5 py-1 rounded text-xs border transition-colors ${
                  category === c.id
                    ? 'text-white border-[#555] bg-[#1f1f1f]'
                    : 'text-[#888] border-[#333] hover:border-[#555] hover:text-[#ccc]'
                }`}
                style={category === c.id ? { borderColor: accent, boxShadow: `inset 0 0 0 1px ${accent}44` } : undefined}
              >
                {c.label}
              </button>
            ))}
          </div>

          {error && (
            <div className="text-xs text-red-400 px-1">{error}</div>
          )}

          {!loading && !error && rows.length === 0 && (
            <p className="text-xs text-[#777] px-1">
              No related documents for this state and filter. Populate the document layer via
              ingestion, research job crawls, or the one-time document migration when available.
            </p>
          )}

          {rows.length > 0 && (
            <div className="overflow-x-auto overflow-y-auto max-h-[360px] rounded border border-[#2a2a2a]">
              <table className="w-full text-sm border-collapse">
                <thead className="sticky top-0 bg-[#111] z-10">
                  <tr className="border-b border-[#333]">
                    <HeaderCell
                      col="kind"
                      label="Type"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      accent={accent}
                      onSort={handleHeaderSort}
                    />
                    <HeaderCell
                      col="title"
                      label="Title"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      accent={accent}
                      onSort={handleHeaderSort}
                    />
                    <HeaderCell
                      col="date"
                      label="Date"
                      align="right"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      accent={accent}
                      onSort={handleHeaderSort}
                    />
                    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-[#999] text-right whitespace-nowrap">
                      Link
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((doc) => {
                    const href =
                      doc.source_url && /^https?:\/\//i.test(doc.source_url) ? doc.source_url : null;
                    const noUrlTitle =
                      doc.source_key && !href
                        ? 'No public URL yet for this storage-backed document.'
                        : doc.job_id && !href
                          ? 'No direct link; open Research and find this job in history.'
                          : undefined;
                    return (
                      <tr
                        key={doc.id}
                        className="border-b border-[#222] hover:bg-[#1a1a1a] transition-colors"
                      >
                        <td className="px-3 py-2 text-[#aaa] whitespace-nowrap text-xs">
                          {docCategoryLabel(doc.content_type)}
                        </td>
                        <td className="px-3 py-2 text-[#e5e5e5] max-w-[min(420px,50vw)]">
                          <div className="font-medium line-clamp-2">
                            {doc.title?.trim() || 'Untitled'}
                          </div>
                          {doc.snippet && (
                            <div className="text-[#777] text-xs mt-0.5 line-clamp-2">{doc.snippet}</div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right text-[#999] tabular-nums text-xs whitespace-nowrap">
                          {formatDate(doc.created_at)}
                        </td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {href ? (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs hover:underline"
                              style={{ color: accent }}
                            >
                              Open ↗
                            </a>
                          ) : (
                            <span className="text-xs text-[#555]" title={noUrlTitle}>
                              {doc.content_type === 'research_report' ? 'Report' : '—'}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}