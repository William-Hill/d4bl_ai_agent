export default function PlaygroundPlaceholder() {
  return (
    <div className="relative">
      {/* Mock chat interface */}
      <div className="bg-[#292929] border border-[#404040] rounded-lg overflow-hidden">
        {/* Header bar */}
        <div className="bg-[#1a1a1a] px-4 py-2 border-b border-[#404040] flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/50" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/50" />
          <div className="w-3 h-3 rounded-full bg-green-500/50" />
          <span className="text-xs text-gray-500 ml-2">D4BL Model Playground</span>
        </div>

        {/* Mock prompt */}
        <div className="p-6">
          <div className="bg-[#1a1a1a] rounded-lg p-4 mb-4">
            <p className="text-sm text-gray-400">
              <span className="text-[#00ff32]">$</span> What does maternal
              mortality data tell us about Birmingham, AL?
            </p>
          </div>

          {/* Blurred response */}
          <div className="bg-[#1a1a1a] rounded-lg p-4 blur-sm select-none" aria-hidden="true">
            <p className="text-sm text-gray-400">
              Birmingham&apos;s maternal mortality data reveals significant disparities
              rooted in decades of healthcare infrastructure disinvestment. The
              Black maternal mortality rate in Jefferson County is 3.1x the white
              rate, with contributing factors including hospital closures in
              predominantly Black neighborhoods, Medicaid coverage gaps, and
              documented patterns of provider bias...
            </p>
          </div>
        </div>
      </div>

      {/* Coming Soon overlay */}
      <div className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg">
        <div className="text-center">
          <span className="inline-block px-4 py-2 bg-[#00ff32]/20 border border-[#00ff32] rounded-full text-[#00ff32] font-semibold text-sm mb-3">
            Coming Soon
          </span>
          <p className="text-gray-400 text-sm max-w-xs">
            Interactive model comparison, custom queries, and export results.
          </p>
        </div>
      </div>
    </div>
  );
}
