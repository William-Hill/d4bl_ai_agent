"use client";

import { humanizeMetric } from '@/lib/explore-config';

interface MapLegendProps {
  min: number;
  max: number;
  nationalAverage: number | null;
  metric: string;
  colorStart: string;
  colorEnd: string;
  accent: string;
}

function formatValue(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(1);
}

export default function MapLegend({
  min,
  max,
  nationalAverage,
  metric,
  colorStart,
  colorEnd,
  accent,
}: MapLegendProps) {
  const range = max - min;
  const avgPct =
    nationalAverage != null && range > 0
      ? Math.max(0, Math.min(100, ((nationalAverage - min) / range) * 100))
      : null;

  const showAvg =
    avgPct != null &&
    nationalAverage != null &&
    nationalAverage >= min &&
    nationalAverage <= max;

  return (
    <div className="mt-2 px-1">
      {/* Metric label */}
      <p className="text-xs mb-2" style={{ color: accent }}>
        Colored by:{" "}
        <span className="font-medium">{humanizeMetric(metric)}</span>
      </p>

      {/* Gradient bar */}
      <div
        className="w-full rounded"
        style={{
          height: "12px",
          background: `linear-gradient(to right, ${colorStart}, ${colorEnd})`,
          position: "relative",
        }}
      >
        {/* National average marker */}
        {showAvg && (
          <div
            style={{
              position: "absolute",
              left: `${avgPct}%`,
              top: 0,
              bottom: 0,
              width: "2px",
              backgroundColor: "#fff",
              transform: "translateX(-50%)",
            }}
          />
        )}
      </div>

      {/* Labels row */}
      <div className="relative mt-1" style={{ height: "16px" }}>
        {/* Min label */}
        <span
          className="absolute left-0 text-[10px]"
          style={{ color: "#999" }}
        >
          {formatValue(min)}
        </span>

        {/* Average label */}
        {showAvg && nationalAverage != null && (
          <span
            className="absolute text-[10px] -translate-x-1/2"
            style={{ left: `${avgPct}%`, color: "#777" }}
          >
            Avg: {formatValue(nationalAverage)}
          </span>
        )}

        {/* Max label */}
        <span
          className="absolute right-0 text-[10px]"
          style={{ color: "#999" }}
        >
          {formatValue(max)}
        </span>
      </div>
    </div>
  );
}
