'use client';

import {
  BILL_STATUSES,
  BillStatus,
  POLICY_TOPICS,
  PolicyTopic,
  statusToPhase,
} from '@/lib/explore-config';
import PhaseGlyph from './PhaseGlyph';

export interface PolicyFilters {
  stateFips: string | null;
  statuses: Set<BillStatus>;
  topics: Set<PolicyTopic>;
}

interface Props {
  filters: PolicyFilters;
  onChange: (next: PolicyFilters) => void;
  /** FIPS → state name, sourced from loaded bills so we only offer real options. */
  stateNameByFips: Record<string, string>;
}

const ACCENT = '#00ff32';

function toggleSet<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export default function PolicyFilterPanel({ filters, onChange, stateNameByFips }: Props) {

  const stateEntries = Object.entries(stateNameByFips).sort(([, a], [, b]) => a.localeCompare(b));

  return (
    <aside className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-5 text-sm">
      {/* State selector */}
      <div>
        <label
          htmlFor="policy-state-select"
          className="block text-xs font-mono uppercase tracking-wider text-gray-500 mb-2"
        >
          State
        </label>
        <select
          id="policy-state-select"
          value={filters.stateFips ?? ''}
          onChange={(e) => onChange({ ...filters, stateFips: e.target.value || null })}
          className="w-full bg-[#292929] border border-[#404040] rounded px-2 py-1.5 text-gray-200
            focus:border-[#00ff32] focus:outline-none"
        >
          <option value="">All states</option>
          {stateEntries.map(([fips, name]) => (
            <option key={fips} value={fips}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {/* Status chips */}
      <div>
        <div className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-2">Status</div>
        <div className="flex flex-wrap gap-1.5">
          {BILL_STATUSES.map((status) => {
            const active = filters.statuses.has(status);
            const phase = statusToPhase(status);
            return (
              <button
                key={status}
                type="button"
                onClick={() =>
                  onChange({ ...filters, statuses: toggleSet(filters.statuses, status) })
                }
                aria-pressed={active}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-mono
                  border transition-colors ${
                    active
                      ? 'text-black'
                      : 'bg-[#2a2a2a] text-gray-400 border-[#404040] hover:border-gray-500'
                  }`}
                style={
                  active
                    ? { backgroundColor: ACCENT, borderColor: ACCENT }
                    : undefined
                }
              >
                <PhaseGlyph phase={phase} />
                <span>{status}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Topic chips */}
      <div>
        <div className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-2">Topic</div>
        <div className="flex flex-wrap gap-1.5">
          {POLICY_TOPICS.map((topic) => {
            const active = filters.topics.has(topic);
            return (
              <button
                key={topic}
                type="button"
                onClick={() => onChange({ ...filters, topics: toggleSet(filters.topics, topic) })}
                aria-pressed={active}
                className={`px-2.5 py-1 rounded-full text-xs capitalize border transition-colors ${
                  active
                    ? 'text-black'
                    : 'bg-[#2a2a2a] text-gray-400 border-[#404040] hover:border-gray-500'
                }`}
                style={
                  active
                    ? { backgroundColor: ACCENT, borderColor: ACCENT }
                    : undefined
                }
              >
                {topic}
              </button>
            );
          })}
        </div>
      </div>

      {/* Clear filters — only when any filter is active */}
      {(filters.stateFips || filters.statuses.size > 0 || filters.topics.size > 0) && (
        <button
          type="button"
          onClick={() =>
            onChange({ stateFips: null, statuses: new Set(), topics: new Set() })
          }
          className="text-xs font-mono text-gray-500 hover:text-[#00ff32] transition-colors"
        >
          {'// clear filters'}
        </button>
      )}
    </aside>
  );
}
