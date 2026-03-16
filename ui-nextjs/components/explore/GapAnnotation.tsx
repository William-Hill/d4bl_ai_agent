"use client";

import { humanizeMetric } from "@/lib/explore-config";

interface GapAnnotationProps {
  type: "racial-gap" | "state-vs-national";
  metric: string;
  raceValues?: { race: string; value: number }[];
  stateValue?: number;
  stateName?: string;
  nationalAverage?: number;
  /** true = high is good, false = high is bad, null = neutral */
  metricDirection?: boolean | null;
}

function formatValue(value: number): string {
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

export default function GapAnnotation({
  type,
  metric,
  raceValues,
  stateValue,
  stateName,
  nationalAverage,
  metricDirection,
}: GapAnnotationProps) {
  if (type === "racial-gap") {
    if (!raceValues || raceValues.length < 2) return null;

    const sorted = [...raceValues].sort((a, b) => b.value - a.value);
    const highest = sorted[0];
    const lowest = sorted[sorted.length - 1];

    if (highest.value === 0 || lowest.value === 0) return null;

    const ratio = highest.value / lowest.value;
    const metricLabel = humanizeMetric(metric);

    let annotation: React.ReactNode;

    if (ratio >= 1.5) {
      const ratioFormatted = ratio.toFixed(1);
      annotation = (
        <>
          <span className="text-white font-medium">{highest.race}</span>{" "}
          {metricLabel} is{" "}
          <span className="text-white font-medium">{ratioFormatted}×</span>{" "}
          higher than{" "}
          <span className="text-white font-medium">{lowest.race}</span>.
        </>
      );
    } else {
      const pctDiff = (((highest.value - lowest.value) / lowest.value) * 100).toFixed(1);
      annotation = (
        <>
          <span className="text-white font-medium">{highest.race}</span>{" "}
          {metricLabel} is{" "}
          <span className="text-white font-medium">{pctDiff}%</span>{" "}
          higher than{" "}
          <span className="text-white font-medium">{lowest.race}</span>.
        </>
      );
    }

    return (
      <p className="mt-2 text-xs leading-relaxed text-[#a8a8a8]">{annotation}</p>
    );
  }

  if (type === "state-vs-national") {
    if (
      stateValue === undefined ||
      nationalAverage === undefined ||
      !stateName
    ) {
      return null;
    }

    const diff = stateValue - nationalAverage;
    const absDiff = Math.abs(diff);
    const pctDiff =
      nationalAverage !== 0
        ? Math.abs((diff / nationalAverage) * 100).toFixed(1)
        : "0";

    const isAbove = diff >= 0;
    const direction = isAbove ? "above" : "below";
    // For metrics where high is bad, invert the color logic
    const isFavorable = metricDirection === false ? !isAbove : isAbove;
    const color = isFavorable ? "#22c55e" : "#ef4444";

    return (
      <p className="mt-2 text-xs leading-relaxed text-[#a8a8a8]">
        <span className="text-white font-medium">{stateName}</span> is{" "}
        <span style={{ color }} className="font-medium">
          {formatValue(absDiff)} ({pctDiff}%)
        </span>{" "}
        {direction} the national average.
      </p>
    );
  }

  return null;
}
