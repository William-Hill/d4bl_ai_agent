'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import StateMap from './StateMap';
import PolicyFilterPanel, { PolicyFilters } from './PolicyFilterPanel';
import BillFeedRow from './BillFeedRow';
import { PolicyBill } from '@/lib/types';
import {
  aggregateBillsByState,
  billAggregateToIndicatorRow,
  FIPS_TO_ABBREV,
  formatRelativeDate,
} from '@/lib/explore-config';
import { API_BASE } from '@/lib/api';
import { useAuthHeaders } from '@/hooks/useAuthHeaders';

const ACCENT = '#00ff32';
const FEED_LIMIT = 50;
const STAGGER_COUNT = 5;
const API_BILL_LIMIT = 5000;

export default function PolicyExploreView() {
  const { session, getHeaders } = useAuthHeaders();
  const [allBills, setAllBills] = useState<PolicyBill[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<PolicyFilters>({
    stateFips: null,
    statuses: new Set(),
    topics: new Set(),
  });
  const [searchQuery, setSearchQuery] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut: "/" focuses search (skip if already typing in an input).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        target?.isContentEditable
      ) {
        return;
      }
      e.preventDefault();
      searchRef.current?.focus();
      searchRef.current?.select();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const fetchBills = useCallback(
    async (signal: AbortSignal) => {
      // Clear loading + cached bills on missing auth so the component can't
      // get stuck at loading=true if a previous fetch was aborted during an
      // auth change (the aborted finally block skips setLoading(false)).
      if (!session?.access_token) {
        setLoading(false);
        setAllBills(null);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `${API_BASE}/api/explore/policies?limit=${API_BILL_LIMIT}`,
          { signal, headers: getHeaders() },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as PolicyBill[];
        setAllBills(data);
      } catch (e: unknown) {
        if (signal.aborted) return;
        setError(e instanceof Error ? e.message : 'Failed to load bills');
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [session?.access_token, getHeaders],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchBills(controller.signal);
    return () => controller.abort();
  }, [fetchBills]);

  const stateAggregates = useMemo(
    () => (allBills ? aggregateBillsByState(allBills) : []),
    [allBills],
  );

  const mapIndicators = useMemo(
    () => stateAggregates.map(billAggregateToIndicatorRow),
    [stateAggregates],
  );

  const matchingBills = useMemo(() => {
    if (!allBills) return [];
    const stateAbbrev = filters.stateFips ? FIPS_TO_ABBREV[filters.stateFips] : null;
    const q = searchQuery.trim().toLowerCase();
    const result = allBills.filter((bill) => {
      if (stateAbbrev && bill.state !== stateAbbrev) return false;
      if (filters.statuses.size > 0 && !(filters.statuses as Set<string>).has(bill.status)) {
        return false;
      }
      if (filters.topics.size > 0) {
        if (
          !bill.topic_tags ||
          !bill.topic_tags.some((t) => (filters.topics as Set<string>).has(t))
        ) {
          return false;
        }
      }
      if (q) {
        const haystack = [
          bill.title,
          bill.bill_number,
          bill.summary ?? '',
          bill.state,
          bill.state_name,
        ]
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
    result.sort((a, b) => {
      const av = a.last_action_date ?? '';
      const bv = b.last_action_date ?? '';
      return bv.localeCompare(av);
    });
    return result;
  }, [allBills, filters, searchQuery]);

  const filteredBills = useMemo(
    () => matchingBills.slice(0, FEED_LIMIT),
    [matchingBills],
  );

  // Memoized so a stable object reference is passed to PolicyFilterPanel —
  // otherwise the filter rail re-renders on every parent render.
  const stateNameByFips = useMemo(() => {
    const out: Record<string, string> = {};
    for (const agg of stateAggregates) out[agg.fips_code] = agg.state_name;
    return out;
  }, [stateAggregates]);

  const selectedAggregate = filters.stateFips
    ? stateAggregates.find((s) => s.fips_code === filters.stateFips)
    : null;

  const feedHeader = selectedAggregate
    ? `${selectedAggregate.state_name} — ${selectedAggregate.bill_count} bills tracked · last action ${formatRelativeDate(selectedAggregate.last_action_date)}`
    : null;

  const handleMapSelectState = (fips: string) => {
    setFilters((prev) => ({
      ...prev,
      stateFips: prev.stateFips === fips ? null : fips,
    }));
  };

  return (
    <div>
      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm"
        >
          Error loading bills: {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 mb-6">
        <div className="relative">
          {loading && !allBills ? (
            <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-6 h-80 flex items-center justify-center">
              <div className="text-gray-500 font-mono text-xs">{'// loading legislative signal...'}</div>
            </div>
          ) : (
            <StateMap
              indicators={mapIndicators}
              selectedStateFips={filters.stateFips}
              onSelectState={handleMapSelectState}
              accent={ACCENT}
              colorStart="#222"
              colorEnd={ACCENT}
            />
          )}
        </div>
        <PolicyFilterPanel
          filters={filters}
          onChange={setFilters}
          stateNameByFips={stateNameByFips}
        />
      </div>

      <section className="bg-[#1a1a1a] border border-[#404040] rounded-lg">
        <header className="px-5 py-3 border-b border-[#2a2a2a] flex items-center justify-between gap-3 flex-wrap">
          <div className="text-xs font-mono uppercase tracking-wider text-gray-400">
            {feedHeader ?? 'activity feed'}
          </div>
          <div className="relative flex-1 min-w-[220px] max-w-md group/search">
            <span
              aria-hidden="true"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[#00ff32]/70 font-mono text-xs select-none pointer-events-none"
            >
              &gt;
            </span>
            <input
              ref={searchRef}
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape' && searchQuery) {
                  e.preventDefault();
                  setSearchQuery('');
                }
              }}
              placeholder={
                allBills
                  ? `filter ${allBills.length.toLocaleString()} dispatches…`
                  : 'filter dispatches…'
              }
              aria-label="Search bills"
              className="w-full pl-7 pr-16 py-1.5 text-xs font-mono bg-[#0f0f0f] border border-[#2a2a2a] rounded
                         text-gray-100 placeholder:text-gray-600 caret-[#00ff32]
                         focus:outline-none focus:border-[#00ff32]/60 focus:bg-black"
            />
            {searchQuery ? (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery('');
                  searchRef.current?.focus();
                }}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded
                           text-[10px] font-mono uppercase tracking-wider
                           text-gray-500 hover:text-[#00ff32] hover:bg-[#00ff32]/10
                           border border-[#2a2a2a] hover:border-[#00ff32]/50 transition-colors"
              >
                esc
              </button>
            ) : (
              <kbd
                aria-hidden="true"
                className="absolute right-2 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded
                           text-[10px] font-mono uppercase tracking-wider
                           text-gray-600 border border-[#2a2a2a]
                           group-focus-within/search:opacity-0 transition-opacity pointer-events-none"
              >
                /
              </kbd>
            )}
          </div>
          {allBills && (
            <div className="text-xs font-mono text-gray-600 flex items-center gap-3">
              {allBills.length >= API_BILL_LIMIT && (
                <span
                  aria-label={`Showing newest ${API_BILL_LIMIT} bills. Response hit the ${API_BILL_LIMIT}-bill cap; per-state counts may be incomplete for dormant bills.`}
                  title={`Response hit the ${API_BILL_LIMIT}-bill cap; per-state counts may be incomplete for dormant bills.`}
                  className="text-amber-400/80"
                >
                  showing newest {API_BILL_LIMIT}
                </span>
              )}
              <span>
                showing {filteredBills.length} of {matchingBills.length}
              </span>
            </div>
          )}
        </header>

        <div className="px-5">
          {!allBills ? null : filteredBills.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-gray-500 font-mono text-xs">
                {filters.stateFips || filters.statuses.size || filters.topics.size || searchQuery.trim()
                  ? '// no bills match current filters'
                  : '// no bills found'}
              </p>
            </div>
          ) : (
            filteredBills.map((bill, i) => (
              <BillFeedRow
                key={bill.url ?? `${bill.state}-${bill.bill_number}-${bill.introduced_date ?? i}`}
                bill={bill}
                pulse={i === 0}
                staggerIndex={i < STAGGER_COUNT ? i : undefined}
                hideDateline={filters.stateFips !== null}
              />
            ))
          )}
        </div>
      </section>
    </div>
  );
}