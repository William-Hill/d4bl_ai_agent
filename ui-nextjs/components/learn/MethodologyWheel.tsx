'use client';

import { useState } from 'react';

interface MethodologyStage {
  name: string;
  color: string;
  d4bl: string;
  ai: string;
}

const STAGES: MethodologyStage[] = [
  {
    name: 'Community Engagement',
    color: '#00ff32',
    d4bl: 'Centering the voices and needs of Black communities in data work.',
    ai: 'Training data includes community-voiced queries. The register system makes model outputs accessible to non-technical audiences. Community feedback becomes future training data.',
  },
  {
    name: 'Problem Identification',
    color: '#00cc28',
    d4bl: 'Using data to name and frame injustice as communities experience it.',
    ai: 'The query parser recognizes community problem framings — like "Why can\'t our kids breathe clean air?" — and maps them to the right data sources and metrics.',
  },
  {
    name: 'Data Collection & Analysis',
    color: '#00a320',
    d4bl: 'Gathering and interpreting data through an equity lens.',
    ai: 'The explainer adapter adds structural context and data limitations to every narrative. It acknowledges collection biases rather than presenting data as neutral truth.',
  },
  {
    name: 'Policy Innovation',
    color: '#008a1b',
    d4bl: 'Translating analysis into concrete policy recommendations.',
    ai: 'The policy_connections field maps every metric to relevant policy levers and legislation — turning data into actionable information for advocates.',
  },
  {
    name: 'Power Building',
    color: '#007116',
    d4bl: 'Equipping communities with tools and knowledge to drive change.',
    ai: 'The model is open-source. These educational resources, accessible outputs, and the register system all return analytical power to communities.',
  },
];

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle <= 180 ? 0 : 1;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

export default function MethodologyWheel() {
  const [selected, setSelected] = useState<number | null>(null);

  const cx = 150, cy = 150, r = 130;
  const segmentAngle = 360 / STAGES.length;

  return (
    <div>
      <div className="flex justify-center mb-8">
        <svg viewBox="0 0 300 300" className="w-72 h-72 md:w-80 md:h-80" role="group" aria-label="D4BL Methodology Wheel">
          {STAGES.map((stage, i) => {
            const startAngle = i * segmentAngle;
            const endAngle = (i + 1) * segmentAngle;
            const isSelected = selected === i;
            const midAngle = startAngle + segmentAngle / 2;
            const labelPos = polarToCartesian(cx, cy, r * 0.65, midAngle);

            return (
              <g key={stage.name}>
                <path
                  d={describeArc(cx, cy, r, startAngle, endAngle)}
                  fill={stage.color}
                  fillOpacity={isSelected ? 0.4 : 0.15}
                  stroke={isSelected ? '#00ff32' : stage.color}
                  strokeWidth={isSelected ? 3 : 1}
                  className="cursor-pointer transition-all duration-200"
                  onClick={() => setSelected(isSelected ? null : i)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(isSelected ? null : i); } }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${stage.name} — click to learn more`}
                  aria-pressed={isSelected}
                />
                <text
                  x={labelPos.x}
                  y={labelPos.y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-gray-300 text-[9px] pointer-events-none select-none"
                  aria-hidden="true"
                >
                  {stage.name.length > 18
                    ? stage.name.split(' ').reduce<string[]>((lines, word) => {
                        const last = lines[lines.length - 1];
                        if (last && last.length + word.length < 16) {
                          lines[lines.length - 1] = `${last} ${word}`;
                        } else {
                          lines.push(word);
                        }
                        return lines;
                      }, []).map((line, li) => (
                        <tspan key={li} x={labelPos.x} dy={li === 0 ? '-0.3em' : '1.1em'}>
                          {line}
                        </tspan>
                      ))
                    : stage.name}
                </text>
              </g>
            );
          })}
          {selected === null && (
            <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" className="fill-gray-500 text-xs">
              Click a stage
            </text>
          )}
        </svg>
      </div>

      {selected !== null && (
        <div className="bg-[#292929] border border-[#00ff32]/30 rounded-lg p-6 transition-all duration-300">
          <h3 className="text-lg font-semibold text-[#00ff32] mb-3">
            {STAGES[selected].name}
          </h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                In D4BL&apos;s Work
              </p>
              <p className="text-gray-300 text-sm">{STAGES[selected].d4bl}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                In the AI Model
              </p>
              <p className="text-gray-300 text-sm">{STAGES[selected].ai}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
