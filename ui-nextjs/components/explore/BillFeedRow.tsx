'use client';

import { PolicyBill } from '@/lib/types';
import { formatRelativeDate, statusToPhase } from '@/lib/explore-config';
import PhaseGlyph from './PhaseGlyph';

interface Props {
  bill: PolicyBill;
  pulse?: boolean;
  staggerIndex?: number;
}

export default function BillFeedRow({ bill, pulse = false, staggerIndex }: Props) {
  const phase = statusToPhase(bill.status);
  const relativeDate = formatRelativeDate(bill.last_action_date);
  const shouldStagger = staggerIndex != null;

  return (
    <article
      className={`py-4 border-b border-[#2a2a2a] last:border-b-0 flex items-start gap-4${
        shouldStagger ? ' bill-fade-in' : ''
      }`}
      style={shouldStagger ? { animationDelay: `${staggerIndex! * 40}ms` } : undefined}
    >
      <div className="pt-1 shrink-0">
        <PhaseGlyph phase={phase} pulse={pulse} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
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

        <p className="text-sm text-gray-200 leading-snug mb-1 line-clamp-2">{bill.title}</p>

        <p className="text-xs font-mono text-gray-600">last action {relativeDate}</p>
      </div>

      {bill.url && (
        <a
          href={bill.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View ${bill.bill_number}: ${bill.title}`}
          className="shrink-0 self-center text-xs font-mono text-[#00ff32] hover:underline whitespace-nowrap"
        >
          view →
        </a>
      )}
    </article>
  );
}
