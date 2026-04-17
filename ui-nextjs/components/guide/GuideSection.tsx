'use client';

import { useState, ReactNode } from 'react';
import Link from 'next/link';

interface GuideSectionProps {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
  actionLabel?: string;
  actionHref?: string;
}

export default function GuideSection({
  title,
  defaultOpen = false,
  children,
  actionLabel,
  actionHref,
}: GuideSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="bg-[#1a1a1a] border border-[#404040] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-[#222222] transition-colors"
        aria-expanded={open}
      >
        <span className="font-semibold text-white text-base">{title}</span>
        <span className="text-[#00ff32] text-xl font-bold leading-none select-none">
          {open ? '−' : '+'}
        </span>
      </button>

      {open && (
        <div className="px-6 pb-6 pt-2 text-gray-400 text-sm space-y-3">
          {children}
          {actionLabel && actionHref && (
            <div className="pt-2">
              <Link
                href={actionHref}
                className="inline-block px-4 py-2 rounded bg-[#00ff32] text-black text-sm font-semibold hover:bg-[#00cc28] transition-colors"
              >
                {actionLabel}
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
