'use client';

interface RunTimelineProps {
  status: string;
  startedAt: string | null;
  completedAt: string | null;
}

const STEPS = ['FETCH', 'VALIDATE', 'SCORE', 'TRANSFORM', 'STORE', 'LINEAGE', 'NOTIFY'];

type StepState = 'completed' | 'failed' | 'running' | 'pending';

function getStepStates(status: string): StepState[] {
  switch (status) {
    case 'completed':
      return STEPS.map(() => 'completed');
    case 'failed':
      // First 3 complete, 4th failed, rest pending
      return STEPS.map((_, i) => {
        if (i < 3) return 'completed';
        if (i === 3) return 'failed';
        return 'pending';
      });
    case 'running':
      // First 2 complete, 3rd running, rest pending
      return STEPS.map((_, i) => {
        if (i < 2) return 'completed';
        if (i === 2) return 'running';
        return 'pending';
      });
    default:
      return STEPS.map(() => 'pending');
  }
}

const CIRCLE_STYLES: Record<StepState, string> = {
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  running: 'bg-yellow-500',
  pending: 'bg-gray-600',
};

const ICON_MAP: Record<StepState, string> = {
  completed: '\u2713',
  failed: '\u2717',
  running: '\u2022',
  pending: '',
};

export default function RunTimeline({ status }: RunTimelineProps) {
  const stepStates = getStepStates(status);

  return (
    <div className="relative pl-4">
      {STEPS.map((step, i) => {
        const state = stepStates[i];
        const isLast = i === STEPS.length - 1;

        return (
          <div key={step} className="relative flex items-start pb-6 last:pb-0">
            {/* Vertical line */}
            {!isLast && (
              <div className="absolute left-[9px] top-5 bottom-0 border-l-2 border-[#404040]" />
            )}
            {/* Circle */}
            <div
              className={`relative z-10 flex items-center justify-center w-5 h-5 rounded-full shrink-0 ${CIRCLE_STYLES[state]} ${
                state === 'running' ? 'animate-pulse' : ''
              }`}
            >
              {ICON_MAP[state] && (
                <span className="text-[10px] font-bold text-white leading-none">
                  {ICON_MAP[state]}
                </span>
              )}
            </div>
            {/* Label */}
            <span
              className={`ml-3 text-sm ${
                state === 'pending' ? 'text-gray-500' : 'text-gray-300'
              }`}
            >
              {step}
            </span>
          </div>
        );
      })}
    </div>
  );
}
