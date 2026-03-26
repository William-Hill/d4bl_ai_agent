'use client';

import { useState, useEffect, useCallback } from 'react';

interface Stage {
  title: string;
  description: string;
  example: string;
}

const STAGES: Stage[] = [
  {
    title: 'Real Data',
    description:
      'Actual metrics from D4BL\'s 17 data sources — CDC, Census, EPA, FBI, and more.',
    example:
      '{"metric": "maternal_mortality_rate", "black": 55.3, "white": 26.6, "state": "AL"}',
  },
  {
    title: 'Distillation Prompt',
    description:
      'A structured prompt that teaches the model D4BL\'s methodology and values.',
    example:
      '"Explain this health disparity using D4BL\'s framework. Include structural context, data limitations, and policy connections."',
  },
  {
    title: 'Claude API',
    description:
      'A large, capable model generates a high-quality training response.',
    example:
      '"The maternal mortality rate for Black women in Alabama (55.3 per 100k) is 2.1x the rate for white women, reflecting decades of hospital closures in Black communities..."',
  },
  {
    title: 'Training Pair',
    description:
      'The final instruction/response pair used to fine-tune the small model.',
    example:
      '{"instruction": "Explain maternal mortality disparities in AL", "response": "...", "register": "community"}',
  },
];

export default function DistillationPipeline() {
  const [activeStep, setActiveStep] = useState(0);
  const [playing, setPlaying] = useState(false);

  const advance = useCallback(() => {
    setActiveStep((prev) => (prev + 1) % STAGES.length);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(advance, 3000);
    return () => clearInterval(timer);
  }, [playing, advance]);

  return (
    <div>
      {/* Pipeline steps */}
      <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2">
        {STAGES.map((stage, i) => (
          <div key={stage.title} className="flex items-center">
            <button
              onClick={() => { setActiveStep(i); setPlaying(false); }}
              className={`flex-shrink-0 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-300 ${
                i === activeStep
                  ? 'bg-[#00ff32]/20 border border-[#00ff32] text-[#00ff32]'
                  : 'bg-[#292929] border border-[#404040] text-gray-400 hover:border-gray-500'
              }`}
              aria-label={`Step ${i + 1}: ${stage.title}`}
            >
              <span className="block text-xs text-gray-500 mb-0.5">Step {i + 1}</span>
              {stage.title}
            </button>
            {i < STAGES.length - 1 && (
              <svg className="w-6 h-6 text-gray-600 flex-shrink-0 mx-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            )}
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="flex gap-3 mb-6">
        <button
          onClick={() => setPlaying(!playing)}
          className="px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors"
          aria-label={playing ? 'Pause auto-advance' : 'Play auto-advance'}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <button
          onClick={() => { setActiveStep((prev) => Math.max(0, prev - 1)); setPlaying(false); }}
          disabled={activeStep === 0}
          className="px-4 py-2 bg-[#292929] border border-[#404040] rounded-lg text-sm text-gray-400 hover:text-white disabled:opacity-30 transition-colors"
          aria-label="Previous step"
        >
          Prev
        </button>
        <button
          onClick={() => { setActiveStep((prev) => Math.min(STAGES.length - 1, prev + 1)); setPlaying(false); }}
          disabled={activeStep === STAGES.length - 1}
          className="px-4 py-2 bg-[#292929] border border-[#404040] rounded-lg text-sm text-gray-400 hover:text-white disabled:opacity-30 transition-colors"
          aria-label="Next step"
        >
          Next
        </button>
      </div>

      {/* Detail panel */}
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-6">
        <p className="text-gray-300 mb-4">{STAGES[activeStep].description}</p>
        <pre className="bg-[#1a1a1a] border border-[#404040] rounded-lg p-4 text-sm text-gray-400 overflow-x-auto whitespace-pre-wrap font-mono">
          {STAGES[activeStep].example}
        </pre>
      </div>
    </div>
  );
}
