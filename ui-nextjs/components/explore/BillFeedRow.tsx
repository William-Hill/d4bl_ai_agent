'use client';

import { PolicyBill } from '@/lib/types';
import { formatRelativeDate, statusToPhase } from '@/lib/explore-config';
import PhaseGlyph from './PhaseGlyph';

interface Props {
  bill: PolicyBill;
  pulse?: boolean;
  staggerIndex?: number;
  /** Hide the dateline stamp (a grouped section header is already showing the state). */
  hideDateline?: boolean;
}

export default function BillFeedRow({
  bill,
  pulse = false,
  staggerIndex,
  hideDateline = false,
}: Props) {
  const phase = statusToPhase(bill.status);
  const relativeDate = formatRelativeDate(bill.last_action_date);
  const shouldStagger = staggerIndex != null;

  return (
    <article
      className={`group py-4 border-b border-[#2a2a2a] last:border-b-0 flex items-start gap-4${
        shouldStagger ? ' bill-fade-in' : ''
      }`}
      style={shouldStagger ? { animationDelay: `${staggerIndex! * 40}ms` } : undefined}
    >
      {/* DATELINE STAMP — the unmistakable "where this came from" block.
          Rendered as a small press-stamp with the 2-letter state monogram,
          a tiny accent tick, and a hairline border. */}
      {!hideDateline && (
        <div
          title={bill.state_name}
          aria-label={`State: ${bill.state_name}`}
          className="shrink-0 w-12 flex flex-col items-center gap-1 pt-0.5"
        >
          <span
            aria-hidden="true"
            className="block h-px w-6 bg-[#00ff32]/40 group-hover:bg-[#00ff32] transition-colors"
          />
          <span className="font-mono font-bold text-base tracking-[0.15em] text-gray-200 group-hover:text-[#00ff32] transition-colors">
            {bill.state}
          </span>
          <span className="text-[9px] font-mono uppercase tracking-widest text-gray-600">
            dateline
          </span>
        </div>
      )}

      <div className="shrink-0 pt-1">
        <PhaseGlyph phase={phase} pulse={pulse} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <span className="text-xs font-mono text-gray-500">{bill.bill_number}</span>
          <span
            className="text-[10px] font-mono uppercase tracking-wider text-gray-500"
            aria-hidden="true"
          >
            ·
          </span>
          <span className="text-xs font-mono text-gray-500">{phase.label}</span>
          {bill.topic_tags && bill.topic_tags.length > 0 && (
            <>
              <span
                className="text-[10px] font-mono uppercase tracking-wider text-gray-500"
                aria-hidden="true"
              >
                ·
              </span>
              <div className="flex flex-wrap gap-1">
                {bill.topic_tags.slice(0, 3).map((tag) => (
                  <span
                    key={tag}
                    className="px-1.5 py-0.5 rounded bg-[#2a2a2a] text-[10px] text-gray-400 capitalize"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Title — the star of the row. Promoted in size, weight, and color. */}
        <p className="text-[15px] font-medium text-gray-100 leading-snug mb-1.5 line-clamp-2">
          {bill.title}
        </p>

        <p className="text-[11px] font-mono text-gray-600 uppercase tracking-wider">
          filed {relativeDate}
        </p>
      </div>

      {bill.url && (
        <a
          href={bill.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View ${bill.bill_number}: ${bill.title}`}
          className="shrink-0 self-center text-[11px] font-mono uppercase tracking-wider text-[#00ff32]/80 hover:text-[#00ff32] whitespace-nowrap border-b border-[#00ff32]/30 hover:border-[#00ff32] pb-0.5 transition-colors"
        >
          dispatch →
        </a>
      )}
    </article>
  );
}
