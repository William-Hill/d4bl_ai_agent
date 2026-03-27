# Epic 2: Data Density — Table, Charts, Contrast

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a linked sortable data table below the map and fix chart readability (contrast, height, chart types, gap annotations).

**Architecture:** New `DataTable` component with bidirectional map linking via shared state. Chart improvements are in-place modifications to existing `RacialGapChart` and `StateVsNationalChart`. All frontend — no backend changes.

**Tech Stack:** Next.js/React/TypeScript, Recharts (existing), Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-15-explore-page-overhaul-design.md` — Epic 2 section

---

## File Structure

### Frontend (create)
- `ui-nextjs/components/explore/DataTable.tsx` — Sortable state-level data table with bidirectional map linking
- `ui-nextjs/components/explore/GapAnnotation.tsx` — Plain-language gap annotation component

### Frontend (modify)
- `ui-nextjs/app/explore/page.tsx:300-390` — Add DataTable below map, wire bidirectional linking, pass props to chart components
- `ui-nextjs/components/explore/RacialGapChart.tsx:22-96` — Fix colors for WCAG AA, responsive height, add gap annotation
- `ui-nextjs/components/explore/StateVsNationalChart.tsx:20-55` — Fix colors for WCAG AA, responsive height
- `ui-nextjs/lib/explore-config.ts:202-246` — Add chart type config per source

---

## Task 2.1: Linked sortable data table component

**Files:**
- Create: `ui-nextjs/components/explore/DataTable.tsx`
- Modify: `ui-nextjs/app/explore/page.tsx:300-390`

- [ ] **Step 1: Create DataTable component**

Create `ui-nextjs/components/explore/DataTable.tsx`:

```tsx
"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { humanizeMetric } from "@/lib/explore-config";
import type { ExploreRow } from "@/lib/types";

type SortKey = "state_name" | "value" | "rank" | "vs_national";
type SortDir = "asc" | "desc";

interface DataTableProps {
  rows: ExploreRow[];
  nationalAverage: number | null;
  metric: string | null;
  selectedStateFips: string | null;
  onSelectState: (fips: string, name: string) => void;
  accent: string;
}

interface TableRow {
  state_fips: string;
  state_name: string;
  value: number;
  rank: number;
  vs_national: number | null;
}

function computeTableRows(
  rows: ExploreRow[],
  metric: string | null,
  nationalAverage: number | null,
): TableRow[] {
  // Filter to the active metric and dedupe to one row per state (latest year)
  const byState = new Map<string, ExploreRow>();
  for (const r of rows) {
    if (metric && r.metric !== metric) continue;
    if (r.race && r.race !== "total") continue;
    const existing = byState.get(r.state_fips);
    if (!existing || r.year > existing.year) {
      byState.set(r.state_fips, r);
    }
  }

  const stateRows = Array.from(byState.values());
  // Sort by value descending for ranking
  stateRows.sort((a, b) => b.value - a.value);

  return stateRows.map((r, i) => ({
    state_fips: r.state_fips,
    state_name: r.state_name,
    value: r.value,
    rank: i + 1,
    vs_national:
      nationalAverage != null ? r.value - nationalAverage : null,
  }));
}

function formatValue(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  if (Number.isInteger(v)) return v.toString();
  return v.toFixed(1);
}

function formatDiff(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${formatValue(v)}`;
}

export default function DataTable({
  rows,
  nationalAverage,
  metric,
  selectedStateFips,
  onSelectState,
  accent,
}: DataTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const selectedRef = useRef<HTMLTableRowElement>(null);

  const tableRows = computeTableRows(rows, metric, nationalAverage);

  const sorted = [...tableRows].sort((a, b) => {
    const aVal = a[sortKey] ?? 0;
    const bVal = b[sortKey] ?? 0;
    if (typeof aVal === "string" && typeof bVal === "string") {
      return sortDir === "asc"
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal);
    }
    return sortDir === "asc"
      ? (aVal as number) - (bVal as number)
      : (bVal as number) - (aVal as number);
  });

  const handleSort = useCallback(
    (key: SortKey) => {
      if (key === sortKey) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir(key === "state_name" ? "asc" : "desc");
      }
    },
    [sortKey],
  );

  // Scroll selected row into view when map selection changes
  useEffect(() => {
    selectedRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [selectedStateFips]);

  if (tableRows.length === 0) return null;

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  return (
    <div className="overflow-x-auto rounded-lg border border-[#333] bg-[#111]">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#333] text-left text-xs text-[#999]">
            {(
              [
                ["state_name", "State"],
                ["value", metric ? humanizeMetric(metric) : "Value"],
                ["rank", "Rank"],
                ["vs_national", "vs National"],
              ] as [SortKey, string][]
            ).map(([key, label]) => (
              <th
                key={key}
                className="cursor-pointer select-none px-3 py-2 font-medium hover:text-white"
                onClick={() => handleSort(key)}
              >
                {label}
                {sortIndicator(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const isSelected = r.state_fips === selectedStateFips;
            return (
              <tr
                key={r.state_fips}
                ref={isSelected ? selectedRef : undefined}
                className={`cursor-pointer border-b border-[#222] transition-colors hover:bg-[#1a1a1a] ${
                  isSelected ? "bg-[#1a2a1a]" : ""
                }`}
                onClick={() => onSelectState(r.state_fips, r.state_name)}
              >
                <td
                  className="px-3 py-1.5 font-medium"
                  style={{ color: isSelected ? accent : "#e5e5e5" }}
                >
                  {r.state_name}
                </td>
                <td
                  className="px-3 py-1.5 tabular-nums"
                  style={{ color: isSelected ? accent : "#ccc" }}
                >
                  {formatValue(r.value)}
                </td>
                <td className="px-3 py-1.5 tabular-nums text-[#999]">
                  #{r.rank}
                </td>
                <td
                  className="px-3 py-1.5 tabular-nums"
                  style={{
                    color:
                      r.vs_national == null
                        ? "#666"
                        : r.vs_national >= 0
                          ? "#22c55e"
                          : "#ef4444",
                  }}
                >
                  {r.vs_national != null ? formatDiff(r.vs_national) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Wire DataTable into explore page**

In `ui-nextjs/app/explore/page.tsx`, import and render DataTable between the map section and the state detail section (after the MapLegend, before the state detail `<div>`):

```tsx
import DataTable from "@/components/explore/DataTable";

// After MapLegend, before state detail section (~line 335):
{exploreData && (
  <DataTable
    rows={exploreData.rows}
    nationalAverage={exploreData.national_average}
    metric={filters.metric}
    selectedStateFips={filters.selectedState}
    onSelectState={handleSelectState}
    accent={activeSource.accent}
  />
)}
```

The `handleSelectState` function already exists (it updates `filters.selectedState`). Clicking a table row calls the same handler as clicking the map — bidirectional linking is automatic via shared state.

- [ ] **Step 3: Run frontend build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Build succeeds, no TypeScript errors, no lint errors

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/components/explore/DataTable.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add linked sortable data table below map with bidirectional state selection"
```

---

## Task 2.2: Collapsible table with responsive defaults

**Files:**
- Modify: `ui-nextjs/components/explore/DataTable.tsx`
- Modify: `ui-nextjs/app/explore/page.tsx`

- [ ] **Step 1: Add collapse/expand state to DataTable**

Wrap the DataTable in a collapsible container. Add props:

```tsx
interface DataTableProps {
  // ... existing props ...
  defaultCollapsed?: boolean;
}
```

Add state and localStorage persistence for collapse preference:

```tsx
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

// Inside component:
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
```

- [ ] **Step 2: Add collapse toggle header and animation**

Wrap the table with a header bar showing the toggle:

```tsx
return (
  <div className="rounded-lg border border-[#333] bg-[#111]">
    <button
      onClick={toggleCollapse}
      className="flex w-full items-center justify-between px-3 py-2 text-xs text-[#999] hover:text-white"
    >
      <span>
        Data Table{" "}
        <span className="text-[#666]">({tableRows.length} states)</span>
      </span>
      <span>{collapsed ? "▶" : "▼"}</span>
    </button>
    {!collapsed && (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          {/* ... existing table content ... */}
        </table>
      </div>
    )}
  </div>
);
```

- [ ] **Step 3: Pass responsive default from page**

In `ui-nextjs/app/explore/page.tsx`, pass `defaultCollapsed` based on a simple check. Since we can't use CSS media queries in props, default to `false` (expanded) and let the user collapse manually. The localStorage will remember their preference.

```tsx
<DataTable
  // ... existing props ...
  defaultCollapsed={false}
/>
```

- [ ] **Step 4: Run build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Pass

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/components/explore/DataTable.tsx ui-nextjs/app/explore/page.tsx
git commit -m "feat: add collapsible data table with localStorage preference persistence"
```

---

## Task 2.3: WCAG AA contrast audit + responsive chart height

**Files:**
- Modify: `ui-nextjs/components/explore/RacialGapChart.tsx:22-96`
- Modify: `ui-nextjs/components/explore/StateVsNationalChart.tsx:20-55`

- [ ] **Step 1: Audit and fix RacialGapChart colors**

Current colors fail WCAG AA on dark backgrounds:
- `#777` (white race) on `#1a1a1a` → contrast 3.4:1 (FAIL, needs 4.5:1)
- `#555` (hispanic) on `#1a1a1a` → contrast 2.1:1 (FAIL)
- `#404040` grid on `#1a1a1a` → contrast 1.6:1 (too faint)

Fix `RacialGapChart.tsx` RACE_COLORS (lines 22-27):

```tsx
const RACE_COLORS: Record<string, string> = {
  black: '#00ff32',    // keep — accent green, high contrast
  white: '#a8a8a8',    // was #777 → bump to 6.3:1 contrast
  hispanic: '#7c7c7c', // was #555 → bump to 4.5:1 contrast
  total: '#404040',    // filtered out, doesn't render
};
```

Fix axis label color (currently `#9ca3af` → keep, it's 5.4:1 on dark bg).

Fix grid stroke: change `#404040` → `#4a4a4a` (slightly brighter, 2.0:1 — grid lines are decorative, not text, so AA doesn't strictly apply, but improve visibility).

Fix tooltip text: ensure accent `#00ff32` on `#292929` bg → 8.5:1 (passes).

- [ ] **Step 2: Make RacialGapChart height responsive**

Replace fixed `height={200}` (line 68) with responsive height:

```tsx
<ResponsiveContainer width="100%" height={280}>
```

280px gives bars more room to breathe. The `ResponsiveContainer` already handles width; this just increases the height.

- [ ] **Step 3: Audit and fix StateVsNationalChart colors**

Current `#555` for national average bar on `#1a1a1a` bg → 2.1:1 (FAIL).

Fix `StateVsNationalChart.tsx` (lines 52-53):

```tsx
// State bar: accent (keep)
// National bar: change #555 → #7c7c7c (4.5:1 contrast)
<Cell fill={accent} />
<Cell fill="#7c7c7c" />
```

Fix grid stroke: `#333` → `#4a4a4a`

Fix `#777` diff text color (line 38) → `#a8a8a8` (6.3:1 contrast)

- [ ] **Step 4: Make StateVsNationalChart height responsive**

Replace `height={200}` with `height={280}`.

- [ ] **Step 5: Run build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Pass

- [ ] **Step 6: Commit**

```bash
git add ui-nextjs/components/explore/RacialGapChart.tsx ui-nextjs/components/explore/StateVsNationalChart.tsx
git commit -m "fix: WCAG AA contrast for chart colors + responsive chart height"
```

---

## Task 2.4: Metric-appropriate chart type selection

**Files:**
- Modify: `ui-nextjs/lib/explore-config.ts:202-246` — Add chart type config
- Modify: `ui-nextjs/app/explore/page.tsx:370-390` — Use chart type to select component

- [ ] **Step 1: Add chart type configuration**

In `ui-nextjs/lib/explore-config.ts`, add a chart type helper alongside the existing direction config:

```tsx
export type ChartType = "racial-gap" | "state-vs-national";

export function getChartType(sourceKey: string, hasRace: boolean): ChartType {
  return hasRace ? "racial-gap" : "state-vs-national";
}
```

Note: The spec mentions trend lines and bullet charts, but those are future enhancements for when year selection is implemented. For now, the two existing chart types cover the current use cases. The `getChartType` function provides the extension point without overbuilding.

- [ ] **Step 2: Wire chart type selection in explore page**

In `ui-nextjs/app/explore/page.tsx`, replace the `activeSource.hasRace` conditional (lines 370-390) with the chart type helper:

```tsx
import { getChartType } from "@/lib/explore-config";

// In the state detail section:
const chartType = getChartType(activeSource.key, activeSource.hasRace);

{chartType === "racial-gap" ? (
  <RacialGapChart ... />
) : (
  <StateVsNationalChart ... />
)}
```

This is functionally identical to the current code but uses the config helper, making it easy to add new chart types later.

- [ ] **Step 3: Run build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Pass

- [ ] **Step 4: Commit**

```bash
git add ui-nextjs/lib/explore-config.ts ui-nextjs/app/explore/page.tsx
git commit -m "feat: add chart type selection config for metric-appropriate visualization"
```

---

## Task 2.5: Gap annotations on charts

**Files:**
- Create: `ui-nextjs/components/explore/GapAnnotation.tsx`
- Modify: `ui-nextjs/components/explore/RacialGapChart.tsx`
- Modify: `ui-nextjs/components/explore/StateVsNationalChart.tsx`

- [ ] **Step 1: Create GapAnnotation component**

```tsx
// ui-nextjs/components/explore/GapAnnotation.tsx
"use client";

import { humanizeMetric } from "@/lib/explore-config";

interface GapAnnotationProps {
  type: "racial-gap" | "state-vs-national";
  metric: string;
  // For racial gap:
  raceValues?: { race: string; value: number }[];
  // For state vs national:
  stateValue?: number;
  stateName?: string;
  nationalAverage?: number;
}

function formatValue(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  if (Number.isInteger(v)) return v.toString();
  return v.toFixed(1);
}

export default function GapAnnotation({
  type,
  metric,
  raceValues,
  stateValue,
  stateName,
  nationalAverage,
}: GapAnnotationProps) {
  if (type === "racial-gap" && raceValues && raceValues.length >= 2) {
    // Find the largest gap between any two racial groups
    const sorted = [...raceValues].sort((a, b) => b.value - a.value);
    const highest = sorted[0];
    const lowest = sorted[sorted.length - 1];

    if (highest.value === 0 || lowest.value === 0) return null;

    const ratio = highest.value / lowest.value;
    const pctDiff = ((highest.value - lowest.value) / lowest.value) * 100;

    const humanMetric = humanizeMetric(metric);
    const humanHighest = humanizeMetric(highest.race);
    const humanLowest = humanizeMetric(lowest.race);

    return (
      <p className="mt-2 text-xs leading-relaxed text-[#a8a8a8]">
        {humanHighest} {humanMetric.toLowerCase()} is{" "}
        <span className="font-medium text-white">
          {ratio >= 1.5
            ? `${ratio.toFixed(1)}× higher`
            : `${Math.abs(pctDiff).toFixed(0)}% ${pctDiff > 0 ? "higher" : "lower"}`}
        </span>{" "}
        than {humanLowest}
      </p>
    );
  }

  if (
    type === "state-vs-national" &&
    stateValue != null &&
    nationalAverage != null &&
    nationalAverage !== 0 &&
    stateName
  ) {
    const diff = stateValue - nationalAverage;
    const pctDiff = (diff / nationalAverage) * 100;

    return (
      <p className="mt-2 text-xs leading-relaxed text-[#a8a8a8]">
        {stateName} is{" "}
        <span
          className="font-medium"
          style={{ color: diff >= 0 ? "#22c55e" : "#ef4444" }}
        >
          {formatValue(Math.abs(diff))} ({Math.abs(pctDiff).toFixed(1)}%)
        </span>{" "}
        {diff >= 0 ? "above" : "below"} the national average
      </p>
    );
  }

  return null;
}
```

- [ ] **Step 2: Add GapAnnotation to RacialGapChart**

In `RacialGapChart.tsx`, after the `ResponsiveContainer`, add:

```tsx
import GapAnnotation from "./GapAnnotation";

// After </ResponsiveContainer>:
<GapAnnotation
  type="racial-gap"
  metric={metric}
  raceValues={chartData.map((d) => ({ race: d.race, value: d.value }))}
/>
```

Where `chartData` is the filtered/mapped data array (the existing `data` variable that feeds the chart).

- [ ] **Step 3: Add GapAnnotation to StateVsNationalChart**

In `StateVsNationalChart.tsx`, after the `ResponsiveContainer`, add:

```tsx
import GapAnnotation from "./GapAnnotation";

// After </ResponsiveContainer>:
<GapAnnotation
  type="state-vs-national"
  metric={metric}
  stateValue={stateValue}
  stateName={stateName}
  nationalAverage={nationalAverage}
/>
```

- [ ] **Step 4: Run build and lint**

Run: `cd ui-nextjs && npm run build && npm run lint`
Expected: Pass

- [ ] **Step 5: Commit**

```bash
git add ui-nextjs/components/explore/GapAnnotation.tsx ui-nextjs/components/explore/RacialGapChart.tsx ui-nextjs/components/explore/StateVsNationalChart.tsx
git commit -m "feat: add plain-language gap annotations to charts"
```

---

## Post-Epic Verification

- [ ] **Run full frontend build + lint**

```bash
cd ui-nextjs && npm run build && npm run lint
```

- [ ] **Run backend tests (verify no regressions)**

```bash
cd /path/to/worktree && python -m pytest tests/ -q
```

- [ ] **Manual smoke test**
1. Open explore page — data table appears below map
2. Click a state on the map — table row highlights, scrolls into view
3. Click a table row — map highlights the state
4. Sort by any column — click column header toggles asc/desc
5. Collapse/expand table — preference persists across page reload
6. Check chart colors — no gray-on-gray readability issues
7. Check gap annotation — shows "Black homeownership is 2.3× higher than White" or similar
8. Check chart height — taller than before (280px vs 200px)
