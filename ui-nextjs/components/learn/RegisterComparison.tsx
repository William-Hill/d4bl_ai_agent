'use client';

import { useState } from 'react';

type Register = 'community' | 'policy' | 'research';

const REGISTERS: { key: Register; label: string; content: string }[] = [
  {
    key: 'community',
    label: 'Community',
    content:
      'In our communities, Black mothers are dying at more than twice the rate of white mothers. This isn\'t about individual choices — it\'s about a healthcare system that doesn\'t listen to Black women. When we say "believe Black women," the data backs us up.',
  },
  {
    key: 'policy',
    label: 'Policy',
    content:
      'The Black maternal mortality rate (55.3 per 100,000 live births) is 2.6 times the white rate (21.3 per 100,000). This disparity persists after controlling for income, education, and insurance status, indicating systemic factors. The Momnibus Act (H.R. 959) addresses several contributing factors including implicit bias training and postpartum Medicaid extension.',
  },
  {
    key: 'research',
    label: 'Research',
    content:
      'Racial disparities in maternal mortality (RR = 2.6, 95% CI: 2.3\u20132.9) remain statistically significant after adjustment for socioeconomic confounders (aOR = 2.1, p < 0.001). Weathering theory (Geronimus, 1992) and allostatic load frameworks suggest cumulative physiological stress from structural racism as a primary mechanism. Sample limitations include underreporting in rural counties and inconsistent race/ethnicity classification across vital records systems.',
  },
];

const REGISTER_KEYS = REGISTERS.map((r) => r.key);

export default function RegisterComparison() {
  const [active, setActive] = useState<Register>('community');
  const current = REGISTERS.find((r) => r.key === active)!;

  return (
    <div>
      <p className="text-center text-sm text-gray-500 mb-6 italic">
        Same data, different audiences
      </p>

      <div className="flex gap-1 mb-6 bg-[#292929] rounded-lg p-1" role="tablist">
        {REGISTERS.map((reg) => (
          <button
            key={reg.key}
            id={`tab-${reg.key}`}
            role="tab"
            aria-selected={active === reg.key}
            aria-controls={`tabpanel-${reg.key}`}
            tabIndex={active === reg.key ? 0 : -1}
            onClick={() => setActive(reg.key)}
            onKeyDown={(e) => {
              const idx = REGISTER_KEYS.indexOf(reg.key);
              if (e.key === 'ArrowRight') {
                e.preventDefault();
                const next = REGISTER_KEYS[(idx + 1) % REGISTER_KEYS.length];
                setActive(next);
                document.getElementById(`tab-${next}`)?.focus();
              } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                const prev = REGISTER_KEYS[(idx - 1 + REGISTER_KEYS.length) % REGISTER_KEYS.length];
                setActive(prev);
                document.getElementById(`tab-${prev}`)?.focus();
              }
            }}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 ${
              active === reg.key
                ? 'bg-[#00ff32]/20 text-[#00ff32] border border-[#00ff32]/30'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {reg.label}
          </button>
        ))}
      </div>

      <div
        id={`tabpanel-${active}`}
        role="tabpanel"
        aria-labelledby={`tab-${active}`}
        className="bg-[#292929] border border-[#404040] rounded-lg p-6"
      >
        <p className="text-gray-300 leading-relaxed">{current.content}</p>
      </div>

      <p className="text-center text-xs text-gray-600 mt-4">
        Metric: Black maternal mortality rate (2.6x disparity)
      </p>
    </div>
  );
}
