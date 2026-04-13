import { ExploreRow, IndicatorRow, PolicyBill } from './types';

/** 2-digit FIPS code → 2-letter state abbreviation for API filtering */
export const FIPS_TO_ABBREV: Record<string, string> = {
  '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT',
  '10': 'DE', '11': 'DC', '12': 'FL', '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL',
  '18': 'IN', '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD',
  '25': 'MA', '26': 'MI', '27': 'MN', '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE',
  '32': 'NV', '33': 'NH', '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND',
  '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD',
  '47': 'TN', '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV',
  '55': 'WI', '56': 'WY',
};

/** 2-letter state abbreviation → 2-digit FIPS code. Inverse of FIPS_TO_ABBREV. */
export const ABBREV_TO_FIPS: Record<string, string> = Object.fromEntries(
  Object.entries(FIPS_TO_ABBREV).map(([fips, abbrev]) => [abbrev, fips]),
);

/** Convert an ExploreRow to the IndicatorRow shape expected by map / chart components. */
export function toIndicatorRow(r: ExploreRow): IndicatorRow {
  return {
    fips_code: r.state_fips,
    geography_name: r.state_name,
    state_fips: r.state_fips,
    geography_type: 'state',
    year: r.year,
    race: r.race ?? 'total',
    metric: r.metric,
    value: r.value,
    margin_of_error: null,
  };
}

/** When year is null, collapse multi-year rows to the latest year per state+metric+race. */
export function collapseToLatestYear(rows: ExploreRow[]): ExploreRow[] {
  const byKey = new Map<string, ExploreRow>();
  for (const row of rows) {
    const key = `${row.state_fips}|${row.metric}|${row.race ?? ''}`;
    const prev = byKey.get(key);
    if (!prev || row.year > prev.year) byKey.set(key, row);
  }
  return [...byKey.values()];
}

/** Aggregate bills by state, computing count and the most recent last_action_date per state. */
export interface StateBillAggregate {
  state: string;
  state_name: string;
  fips_code: string;
  bill_count: number;
  last_action_date: string | null;
}

export function aggregateBillsByState(bills: PolicyBill[]): StateBillAggregate[] {
  const byAbbrev = new Map<string, StateBillAggregate>();
  for (const bill of bills) {
    const fips = ABBREV_TO_FIPS[bill.state];
    if (!fips) continue; // skip territories / unknown abbrevs
    const existing = byAbbrev.get(bill.state);
    if (existing) {
      existing.bill_count += 1;
      if (
        bill.last_action_date &&
        (!existing.last_action_date || bill.last_action_date > existing.last_action_date)
      ) {
        existing.last_action_date = bill.last_action_date;
      }
    } else {
      byAbbrev.set(bill.state, {
        state: bill.state,
        state_name: bill.state_name,
        fips_code: fips,
        bill_count: 1,
        last_action_date: bill.last_action_date,
      });
    }
  }
  return [...byAbbrev.values()];
}

/** Number of whole days between an ISO date string and now. Returns null for missing input. */
export function daysSinceLastAction(isoDate: string | null, now: Date = new Date()): number | null {
  if (!isoDate) return null;
  const then = new Date(isoDate);
  if (Number.isNaN(then.getTime())) return null;
  const msPerDay = 1000 * 60 * 60 * 24;
  return Math.max(0, Math.floor((now.getTime() - then.getTime()) / msPerDay));
}

/** Convert a StateBillAggregate into the IndicatorRow shape StateMap consumes.
 *  The `value` is recency expressed as a "heat score": recent activity = high,
 *  dormant = low. We invert daysSinceLastAction so that hotter states map to the
 *  higher end of StateMap's accent gradient. States with no last_action_date get 0.
 */
export function billAggregateToIndicatorRow(agg: StateBillAggregate): IndicatorRow {
  const days = daysSinceLastAction(agg.last_action_date);
  // Cap at 365 days: anything older than a year looks equally cold.
  const cappedDays = days == null ? 365 : Math.min(days, 365);
  const heat = 365 - cappedDays; // 365 = today, 0 = a year+ old or missing
  return {
    fips_code: agg.fips_code,
    geography_name: agg.state_name,
    state_fips: agg.fips_code,
    geography_type: 'state',
    year: new Date().getFullYear(),
    race: 'total',
    metric: 'bill_activity_heat',
    value: heat,
    margin_of_error: null,
  };
}

/** The canonical set of bill statuses emitted by scripts/ingestion/ingest_openstates.py. */
export const BILL_STATUSES = ['introduced', 'passed', 'signed', 'failed', 'other'] as const;
export type BillStatus = typeof BILL_STATUSES[number];

/** Topics the ingestion script tags bills with. Shared by PolicyTable and PolicyFilterPanel. */
export const POLICY_TOPICS = [
  'housing',
  'wealth',
  'education',
  'criminal justice',
  'voting rights',
  'economic development',
  'health care',
] as const;
export type PolicyTopic = typeof POLICY_TOPICS[number];

/** Visual "phase" a bill occupies in the legislative lifecycle, used by PhaseGlyph. */
export interface BillPhase {
  /** Number of filled segments out of PHASE_GLYPH_SEGMENTS. */
  segments: number;
  /** Visual tone: 'active' for in-progress, 'signed' for law, 'failed' for dead, 'dormant' for unknown. */
  tone: 'active' | 'signed' | 'failed' | 'dormant';
  /** Human-readable label for tooltips / aria. */
  label: string;
}

export const PHASE_GLYPH_SEGMENTS = 4;

/** Map a bill's raw status string to its visual phase.
 *
 *  The ingestion pipeline collapses OpenStates statuses into these five values,
 *  so this mapping is the single source of truth for how the lifecycle is
 *  visualized in the Policy Bills tab. Returns a BillPhase with segment count
 *  and visual tone.
 */
export function statusToPhase(status: string | null | undefined): BillPhase {
  const normalized = (status ?? '').toLowerCase().trim();
  switch (normalized) {
    case 'introduced':
      return { segments: 1, tone: 'active', label: 'introduced' };
    case 'passed':
      return { segments: 3, tone: 'active', label: 'passed chamber' };
    case 'signed':
      return { segments: 4, tone: 'signed', label: 'signed into law' };
    case 'failed':
      return { segments: 1, tone: 'failed', label: 'failed or vetoed' };
    default:
      return { segments: 0, tone: 'dormant', label: 'status unknown' };
  }
}

/** Humanize a days-ago count into a compact relative string: "2d ago", "3w ago", "march 14". */
export function formatRelativeDate(isoDate: string | null, now: Date = new Date()): string {
  const days = daysSinceLastAction(isoDate, now);
  if (days == null) return 'no recent action';
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  // Older than a month: show the actual date in a minimal form.
  const d = new Date(isoDate as string);
  return d
    .toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    .toLowerCase();
}

export interface DataSourceConfig {
  key: string;
  label: string;
  accent: string;
  endpoint: string;
  hasRace: boolean;
  primaryFilterKey: string;
  primaryFilterLabel: string;
  description: string;
  sourceUrl: string;
  hasData: boolean;
  /** When true, the tab receives a visual elevation treatment (e.g., pulsing
   *  accent dot) to signal it as a headline or categorically-different source. */
  highlight?: boolean;
}

export const DATA_SOURCES: DataSourceConfig[] = [
  {
    key: "census",
    label: "Census ACS",
    accent: "#00ff32",
    endpoint: "/api/explore/indicators",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
    description: "American Community Survey estimates for homeownership, income, and poverty rates disaggregated by race. Source: U.S. Census Bureau.",
    sourceUrl: "https://data.census.gov/",
    hasData: true,
  },
  // PolicyExploreView renders on this tab; page.tsx short-circuits metric
  // fetch/layout when key === 'policy', so the metric-shaped fields below
  // are unused placeholders. Widen DataSourceConfig to a discriminated union
  // if a second non-metric source lands.
  {
    key: "policy",
    label: "Policy Bills",
    accent: "#00ff32",
    endpoint: "/api/explore/policies",
    hasRace: false,
    primaryFilterKey: "status",
    primaryFilterLabel: "Status",
    description: "State-level legislative bill tracking from OpenStates, with status and topic tags across housing, criminal justice, voting rights, and more.",
    sourceUrl: "https://openstates.org/",
    hasData: true,
    highlight: true,
  },
  {
    key: "cdc",
    label: "CDC Health",
    accent: "#ff6b6b",
    endpoint: "/api/explore/cdc",
    hasRace: false,
    primaryFilterKey: "measure",
    primaryFilterLabel: "Measure",
    description: "County-level health outcome prevalence from the CDC PLACES dataset, covering chronic disease and health risk behaviors.",
    sourceUrl: "https://www.cdc.gov/places/",
    hasData: true,
  },
  {
    key: "epa",
    label: "EPA Environment",
    accent: "#4ecdc4",
    endpoint: "/api/explore/epa",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
    description: "Tract-level environmental justice screening indicators from the EPA EJScreen tool.",
    sourceUrl: "https://www.epa.gov/ejscreen",
    hasData: false,
  },
  {
    key: "fbi",
    label: "FBI Crime",
    accent: "#ffd93d",
    endpoint: "/api/explore/fbi",
    hasRace: false,
    primaryFilterKey: "offense",
    primaryFilterLabel: "Offense",
    description: "Hate crime incidents reported to the FBI's Uniform Crime Reporting program, disaggregated by bias motivation.",
    sourceUrl: "https://cde.ucr.cjis.gov/",
    hasData: true,
  },
  {
    key: "bls",
    label: "BLS Labor",
    accent: "#6c5ce7",
    endpoint: "/api/explore/bls",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
    description: "Monthly labor force statistics including unemployment rates disaggregated by race. Source: Bureau of Labor Statistics.",
    sourceUrl: "https://www.bls.gov/",
    hasData: false,
  },
  {
    key: "hud",
    label: "HUD Housing",
    accent: "#fd79a8",
    endpoint: "/api/explore/hud",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
    description: "Fair housing indicators measuring residential segregation and housing discrimination patterns. Source: HUD.",
    sourceUrl: "https://www.huduser.gov/",
    hasData: true,
  },
  {
    key: "usda",
    label: "USDA Food",
    accent: "#00b894",
    endpoint: "/api/explore/usda",
    hasRace: false,
    primaryFilterKey: "indicator",
    primaryFilterLabel: "Indicator",
    description: "Food access indicators measuring proximity to grocery stores and food deserts at the census tract level. Source: USDA ERS.",
    sourceUrl: "https://www.ers.usda.gov/data-products/food-access-research-atlas/",
    hasData: true,
  },
  {
    key: "doe",
    label: "DOE Education",
    accent: "#fdcb6e",
    endpoint: "/api/explore/doe",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
    description: "Civil rights data on school discipline, enrollment, and staffing disaggregated by race. Source: DOE Office for Civil Rights.",
    sourceUrl: "https://ocrdata.ed.gov/",
    hasData: false,
  },
  {
    key: "police",
    label: "Police Violence",
    accent: "#e17055",
    endpoint: "/api/explore/police-violence",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
    description: "Documented incidents of police violence including use of force and fatal encounters, tracked by race and geography.",
    sourceUrl: "https://mappingpoliceviolence.us/",
    hasData: true,
  },
  {
    key: "census-demographics",
    label: "Census Demographics",
    accent: "#45b7d1",
    endpoint: "/api/explore/census-demographics",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
    description: "Decennial Census population counts by race and ethnicity at county and tract level, aggregated to state. Source: U.S. Census Bureau.",
    sourceUrl: "https://data.census.gov/",
    hasData: true,
  },
  {
    key: "cdc-mortality",
    label: "CDC Mortality",
    accent: "#c0392b",
    endpoint: "/api/explore/cdc-mortality",
    hasRace: true,
    primaryFilterKey: "cause_of_death",
    primaryFilterLabel: "Cause of Death",
    description: "Age-adjusted mortality rates by cause of death and race from the CDC WONDER database.",
    sourceUrl: "https://wonder.cdc.gov/",
    hasData: true,
  },
  {
    key: "bjs",
    label: "BJS Incarceration",
    accent: "#8e44ad",
    endpoint: "/api/explore/bjs",
    hasRace: true,
    primaryFilterKey: "metric",
    primaryFilterLabel: "Metric",
    description: "State and federal incarceration statistics from the Bureau of Justice Statistics, disaggregated by race and gender.",
    sourceUrl: "https://bjs.ojp.gov/",
    hasData: true,
  },
];

// Metric direction: true = high is good, false = high is bad, null = neutral
export const METRIC_DIRECTION: Record<string, Record<string, boolean | null>> = {
  census: {
    homeownership_rate: true,
    median_household_income: true,
    poverty_rate: false,
    unemployment_rate: false,
  },
  cdc: { default: false },
  epa: { default: false },
  fbi: { default: false },
  bls: {
    unemployment_rate: false,
    labor_force_participation_rate: true,
    default: false,
  },
  hud: { default: false },
  usda: { default: false },
  doe: {
    suspension_rate: false,
    expulsion_rate: false,
    enrollment_rate: null,
    default: false,
  },
  police: { default: false },
  "census-demographics": { default: null },
  "cdc-mortality": { default: false },
  bjs: { default: false },
};

export function getMetricDirection(sourceKey: string, metric: string): boolean | null {
  const sourceDir = METRIC_DIRECTION[sourceKey];
  if (!sourceDir) return null;
  return sourceDir[metric] ?? sourceDir["default"] ?? null;
}

export function getDirectionalColors(
  sourceKey: string,
  metric: string,
  accent: string,
): { colorStart: string; colorEnd: string } {
  // Always use the source accent color for the map gradient so the map
  // visually matches the active tab. Directionality (good vs bad) is
  // communicated through the legend label, gap annotations, and the
  // DataTable's vs-national column colors — not the map gradient itself.
  return { colorStart: "#444", colorEnd: accent };
}

export type ChartType = "racial-gap" | "state-vs-national";

export function getChartType(sourceKey: string, hasRace: boolean): ChartType {
  return hasRace ? "racial-gap" : "state-vs-national";
}

/** Convert a snake_case / kebab-case metric name into a human-friendly label. */
export function humanizeMetric(metric: string): string {
  return metric.replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Metric descriptions keyed by source key + metric value. Used for tooltips. */
export const METRIC_DESCRIPTIONS: Partial<Record<string, Record<string, string>>> = {
  census: {
    homeownership_rate: "Percentage of occupied housing units that are owner-occupied",
    median_household_income: "Median annual household income in inflation-adjusted dollars",
    poverty_rate: "Percentage of population living below the federal poverty line",
  },
  cdc: {
    DIABETES: "Prevalence of diagnosed diabetes among adults aged 18+",
    BPHIGH: "Prevalence of high blood pressure among adults aged 18+",
    CASTHMA: "Prevalence of current asthma among adults aged 18+",
    OBESITY: "Prevalence of obesity (BMI >= 30) among adults aged 18+",
    MHLTH: "Poor mental health for 14+ days in the past 30 days among adults",
    CSMOKING: "Prevalence of current smoking among adults aged 18+",
    CHD: "Prevalence of coronary heart disease among adults aged 18+",
    STROKE: "Prevalence of stroke among adults aged 18+",
    CANCER: "Prevalence of cancer (excluding skin cancer) among adults aged 18+",
    KIDNEY: "Prevalence of chronic kidney disease among adults aged 18+",
  },
  fbi: {
    "Aggravated Assault": "Attack with a weapon or causing serious bodily injury",
    "Robbery": "Taking property by force or threat of force",
    "Burglary": "Unlawful entry into a structure to commit a crime",
  },
  bls: {
    unemployment_rate: "Percentage of the labor force that is unemployed and actively seeking work",
    labor_force_participation_rate: "Percentage of working-age population in the labor force",
  },
  "census-demographics": {
    population: "Total population count from the Decennial Census",
    pct_of_total: "Percentage of total population for a given race/ethnicity group",
  },
  "cdc-mortality": {},
  bjs: {
    incarceration_rate: "Number of inmates per 100,000 residents",
    total_population: "Total incarcerated population count",
  },
};
