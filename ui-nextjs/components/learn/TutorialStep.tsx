interface Props {
  step: number;
  title: string;
  description: string;
  colabUrl: string;
}

export default function TutorialStep({ step, title, description, colabUrl }: Props) {
  return (
    <div className="bg-[#292929] border border-[#404040] rounded-lg p-6 flex flex-col">
      <div className="flex items-center gap-3 mb-3">
        <span className="flex-shrink-0 w-8 h-8 rounded-full bg-[#00ff32]/20 text-[#00ff32] text-sm font-bold flex items-center justify-center">
          {step}
        </span>
        <h3 className="text-white font-semibold">{title}</h3>
      </div>
      <p className="text-gray-400 text-sm flex-1 mb-4">{description}</p>
      <a
        href={colabUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 px-4 py-2 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors self-start"
      >
        Open in Colab
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      </a>
    </div>
  );
}
