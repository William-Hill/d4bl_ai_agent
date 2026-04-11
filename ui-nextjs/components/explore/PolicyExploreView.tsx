'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
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

  const fetchBills = useCallback(
    async (signal: AbortSignal) => {
      if (!session?.access_token) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/explore/policies?limit=5000`, {
          signal,
          headers: getHeaders(),
        });
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
      return true;
    });
    result.sort((a, b) => {
      const av = a.last_action_date ?? '';
      const bv = b.last_action_date ?? '';
      return bv.localeCompare(av);
    });
    return result;
  }, [allBills, filters]);

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
        <div className="mb-4 px-4 py-3 bg-red-900/30 border border-red-800 rounded text-red-300 text-sm">
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
          {allBills && (
            <div className="text-xs font-mono text-gray-600">
              showing {filteredBills.length} of {matchingBills.length}
            </div>
          )}
        </header>

        <div className="px-5">
          {!allBills ? null : filteredBills.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-gray-500 font-mono text-xs">
                {filters.stateFips || filters.statuses.size || filters.topics.size
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
              />
            ))
          )}
        </div>
      </section>
    </div>
  );
}
