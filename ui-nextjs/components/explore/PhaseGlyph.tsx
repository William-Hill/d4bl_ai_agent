'use client';

import { BillPhase, PHASE_GLYPH_SEGMENTS, statusToPhase } from '@/lib/explore-config';

interface Props {
  /** Raw bill status; ignored if `phase` is provided directly. */
  status?: string | null;
  /** Optional pre-computed phase; if omitted, derived from `status`. */
  phase?: BillPhase;
  /** If true, the final filled segment pulses subtly (for most-recent row). */
  pulse?: boolean;
}

const TONE_COLORS: Record<BillPhase['tone'], { filled: string; dim: string }> = {
  active: { filled: '#00ff32', dim: '#00ff3222' },
  signed: { filled: '#7cffa1', dim: '#00ff3222' },
  failed: { filled: '#ff5566', dim: '#ff556622' },
  dormant: { filled: '#555', dim: '#333' },
};

/**
 * A 4-segment monospace phase indicator showing where a bill sits in the
 * legislative lifecycle. Reads the phase via `statusToPhase` from explore-config,
 * which is the single source of truth for status → visual mapping.
 */
export default function PhaseGlyph({ status, phase, pulse = false }: Props) {
  const resolved = phase ?? statusToPhase(status);
  const colors = TONE_COLORS[resolved.tone];
  const segments = Array.from({ length: PHASE_GLYPH_SEGMENTS }, (_, i) => i < resolved.segments);

  return (
    <span
      role="img"
      aria-label={`Legislative phase: ${resolved.label}`}
      title={resolved.label}
      className="inline-flex items-center gap-[2px] font-mono leading-none select-none"
    >
      {segments.map((filled, i) => {
        const isLastFilled = filled && i === resolved.segments - 1;
        return (
          <span
            key={i}
            aria-hidden="true"
            className={
              pulse && isLastFilled
                ? 'inline-block w-2 h-2.5 rounded-[1px] animate-pulse'
                : 'inline-block w-2 h-2.5 rounded-[1px]'
            }
            style={{
              backgroundColor: filled ? colors.filled : colors.dim,
              boxShadow: filled && resolved.tone !== 'dormant' ? `0 0 4px ${colors.filled}66` : undefined,
            }}
          />
        );
      })}
    </span>
  );
}
