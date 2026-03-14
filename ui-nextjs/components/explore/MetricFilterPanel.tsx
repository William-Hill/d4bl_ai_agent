'use client';

/** @deprecated Use `string` directly — kept for backward compatibility. */
export type Metric = string;
/** @deprecated Use `string | null` directly — kept for backward compatibility. */
export type Race = string | null;

export interface ExploreFilters {
  metric: string;
  race: string | null;
  year: number | null;
  selectedState: string | null;
}

interface Props {
  filters: ExploreFilters;
  onChange: (filters: ExploreFilters) => void;
  /** List of metric values to render as radio buttons. Falls back to Census ACS defaults. */
  availableMetrics?: string[];
  /** List of years for the dropdown. Falls back to [2022, 2021, 2020, 2019]. */
  availableYears?: number[];
  /** List of race/ethnicity values. If empty or absent, the race section is hidden. */
  availableRaces?: string[];
  /** Heading for the primary (metric) filter section. Default: "Metric". */
  primaryFilterLabel?: string;
  /** Accent color for the active radio indicator. Default: "#00ff32". */
  accent?: string;
}

/* ── Default Census ACS options (backward compat) ── */

const DEFAULT_METRICS: { value: string; label: string }[] = [
  { value: 'homeownership_rate', label: 'Homeownership Rate' },
  { value: 'median_household_income', label: 'Median Household Income' },
  { value: 'poverty_rate', label: 'Poverty Rate' },
];

const DEFAULT_RACES: { value: string; label: string }[] = [
  { value: 'total', label: 'All' },
  { value: 'black', label: 'Black' },
  { value: 'white', label: 'White' },
  { value: 'hispanic', label: 'Hispanic/Latino' },
];

const DEFAULT_YEARS = [2022, 2021, 2020, 2019];

/* ── Helpers ── */

/** Convert a snake_case / kebab-case value into a human-friendly label. */
function humanize(value: string): string {
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Component ── */

export default function MetricFilterPanel({
  filters,
  onChange,
  availableMetrics,
  availableYears,
  availableRaces,
  primaryFilterLabel = 'Metric',
  accent = '#00ff32',
}: Props) {
  // Resolve effective lists — only fall back to Census defaults when the prop
  // is truly absent (undefined).  An empty array means "no options yet" and
  // should NOT be replaced with defaults.
  const metrics =
    availableMetrics === undefined
      ? DEFAULT_METRICS
      : availableMetrics.map((v) => ({ value: v, label: humanize(v) }));

  const years = availableYears === undefined ? DEFAULT_YEARS : availableYears;

  const rawRaces = availableRaces === undefined ? DEFAULT_RACES : availableRaces.map((v) => ({ value: v, label: humanize(v) }));

  // Race section: show if availableRaces is explicitly provided (with items),
  // OR if no availableRaces prop was given (backward compat — show Census defaults).
  const showRace = availableRaces === undefined || availableRaces.length > 0;
  const races = rawRaces;

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 space-y-5">
      {/* Primary metric filter */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          {primaryFilterLabel}
        </p>
        <div className="space-y-1">
          {metrics.map((m) => {
            const isSelected = filters.metric === m.value;
            return (
              <label key={m.value} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="metric"
                  value={m.value}
                  checked={isSelected}
                  onChange={() => onChange({ ...filters, metric: m.value })}
                  className="peer sr-only"
                />
                <span
                  className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-gray-500 peer-focus-visible:ring-2 peer-focus-visible:ring-offset-1"
                >
                  {isSelected && (
                    <span
                      className="block w-2 h-2 rounded-full"
                      style={{ backgroundColor: accent }}
                    />
                  )}
                </span>
                <span className="text-sm text-gray-300">{m.label}</span>
              </label>
            );
          })}
        </div>
      </div>

      {showRace && (
        <>
          <div className="border-t border-[#404040]" />

          {/* Race / Ethnicity */}
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Race / Ethnicity
            </p>
            <div className="space-y-1">
              {races.map((r) => {
                const isSelected = filters.race === r.value;
                return (
                  <label key={r.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="race"
                      value={r.value ?? ''}
                      checked={isSelected}
                      onChange={() => onChange({ ...filters, race: r.value })}
                      className="peer sr-only"
                    />
                    <span
                      className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-gray-500 peer-focus-visible:ring-2 peer-focus-visible:ring-offset-1"
                    >
                      {isSelected && (
                        <span
                          className="block w-2 h-2 rounded-full"
                          style={{ backgroundColor: accent }}
                        />
                      )}
                    </span>
                    <span className="text-sm text-gray-300">{r.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </>
      )}

      <div className="border-t border-[#404040]" />

      {/* Year */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Year
        </p>
        <select
          value={filters.year ?? ''}
          onChange={(e) => onChange({ ...filters, year: e.target.value ? Number(e.target.value) : null })}
          className="w-full bg-[#292929] border border-[#404040] rounded px-2 py-1.5 text-sm text-gray-300 focus:ring-2 focus:ring-offset-1"
        >
          {filters.year === null && <option value="">All years</option>}
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
