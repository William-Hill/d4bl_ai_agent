'use client';

export default function FlywheelDiagram() {
  return (
    <div className="flex justify-center py-4">
      <svg viewBox="0 0 700 700" className="w-full max-w-[500px] h-auto" role="img" aria-label="D4BL Data Flywheel mapping technical stages to research methodology">
        <defs>
          <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#818cf8" />
          </marker>
          <marker id="arrow-outer" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#a855f7" />
          </marker>
        </defs>

        {/* Inner ring arrows (technical flywheel) */}
        <path d="M 420 130 Q 520 170 540 280" stroke="#818cf8" strokeWidth="2.5" fill="none" markerEnd="url(#arrow)" opacity="0.6"/>
        <path d="M 540 400 Q 520 510 420 555" stroke="#818cf8" strokeWidth="2.5" fill="none" markerEnd="url(#arrow)" opacity="0.6"/>
        <path d="M 280 555 Q 180 510 160 400" stroke="#818cf8" strokeWidth="2.5" fill="none" markerEnd="url(#arrow)" opacity="0.6"/>
        <path d="M 160 280 Q 180 170 280 130" stroke="#818cf8" strokeWidth="2.5" fill="none" markerEnd="url(#arrow)" opacity="0.6"/>

        {/* Outer ring arrows (D4BL methodology) */}
        <path d="M 470 68 Q 620 120 645 240" stroke="#a855f7" strokeWidth="2" fill="none" markerEnd="url(#arrow-outer)" opacity="0.4" strokeDasharray="6 3"/>
        <path d="M 645 440 Q 620 570 470 625" stroke="#a855f7" strokeWidth="2" fill="none" markerEnd="url(#arrow-outer)" opacity="0.4" strokeDasharray="6 3"/>
        <path d="M 230 625 Q 80 570 55 440" stroke="#a855f7" strokeWidth="2" fill="none" markerEnd="url(#arrow-outer)" opacity="0.4" strokeDasharray="6 3"/>
        <path d="M 55 240 Q 80 120 230 68" stroke="#a855f7" strokeWidth="2" fill="none" markerEnd="url(#arrow-outer)" opacity="0.4" strokeDasharray="6 3"/>

        {/* Center */}
        <circle cx="350" cy="345" r="55" fill="#1a1a1a" stroke="#7c3aed" strokeWidth="1.5"/>
        <text x="350" y="330" textAnchor="middle" fontSize="11" fontWeight="700" fill="#a78bfa">DATA AS</text>
        <text x="350" y="346" textAnchor="middle" fontSize="11" fontWeight="700" fill="#a78bfa">PROTEST</text>
        <text x="350" y="362" textAnchor="middle" fontSize="11" fontWeight="700" fill="#a78bfa">ACCOUNTABILITY</text>
        <text x="350" y="378" textAnchor="middle" fontSize="11" fontWeight="700" fill="#a78bfa">COLLECTIVE ACTION</text>

        {/* Stage 1: TOP — Documents In / Data Collection + Analysis */}
        <rect x="195" y="10" width="310" height="28" rx="14" fill="#2d1b69" stroke="#a855f7" strokeWidth="1.5"/>
        <text x="350" y="29" textAnchor="middle" fontSize="11" fontWeight="600" fill="#c4b5fd">D4BL: Data Collection + Analysis</text>

        <rect x="225" y="48" width="250" height="72" rx="12" fill="#052e16" stroke="#22c55e" strokeWidth="2"/>
        <text x="350" y="72" textAnchor="middle" fontSize="14" fontWeight="700" fill="#4ade80">1. Documents In</text>
        <text x="350" y="90" textAnchor="middle" fontSize="11" fill="#86efac">Policy bills, research reports,</text>
        <text x="350" y="105" textAnchor="middle" fontSize="11" fill="#86efac">news articles, community data</text>

        {/* Stage 2: RIGHT — Training / Problem Identification */}
        <rect x="555" y="295" width="145" height="46" rx="14" fill="#2d1b69" stroke="#a855f7" strokeWidth="1.5"/>
        <text x="627" y="314" textAnchor="middle" fontSize="11" fontWeight="600" fill="#c4b5fd">D4BL: Problem</text>
        <text x="627" y="330" textAnchor="middle" fontSize="11" fontWeight="600" fill="#c4b5fd">Identification</text>

        <rect x="460" y="350" width="195" height="72" rx="12" fill="#0c1a3d" stroke="#3b82f6" strokeWidth="2"/>
        <text x="557" y="374" textAnchor="middle" fontSize="14" fontWeight="700" fill="#60a5fa">2. Training</text>
        <text x="557" y="392" textAnchor="middle" fontSize="11" fill="#93c5fd">Model learns to parse</text>
        <text x="557" y="407" textAnchor="middle" fontSize="11" fill="#93c5fd">community framings</text>

        {/* Stage 3: BOTTOM — Research Quality / Policy Innovation */}
        <rect x="220" y="610" width="260" height="28" rx="14" fill="#2d1b69" stroke="#a855f7" strokeWidth="1.5"/>
        <text x="350" y="629" textAnchor="middle" fontSize="11" fontWeight="600" fill="#c4b5fd">D4BL: Policy Innovation</text>

        <rect x="215" y="540" width="270" height="62" rx="12" fill="#2d1600" stroke="#f59e0b" strokeWidth="2"/>
        <text x="350" y="564" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fbbf24">3. Research Quality</text>
        <text x="350" y="584" textAnchor="middle" fontSize="11" fill="#fcd34d">Outputs connect data → policy levers</text>

        {/* Stage 4: LEFT — Feedback / Community Power Building */}
        <rect x="0" y="295" width="145" height="46" rx="14" fill="#2d1b69" stroke="#a855f7" strokeWidth="1.5"/>
        <text x="72" y="314" textAnchor="middle" fontSize="11" fontWeight="600" fill="#c4b5fd">D4BL: Community</text>
        <text x="72" y="330" textAnchor="middle" fontSize="11" fontWeight="600" fill="#c4b5fd">Power Building</text>

        <rect x="45" y="350" width="195" height="72" rx="12" fill="#2d0a1e" stroke="#ec4899" strokeWidth="2"/>
        <text x="142" y="374" textAnchor="middle" fontSize="14" fontWeight="700" fill="#f472b6">4. Feedback</text>
        <text x="142" y="392" textAnchor="middle" fontSize="11" fill="#f9a8d4">Community use generates</text>
        <text x="142" y="407" textAnchor="middle" fontSize="11" fill="#f9a8d4">new documents + corrections</text>

        {/* Legend */}
        <rect x="0" y="660" width="700" height="40" rx="8" fill="#1a1a1a" stroke="#404040" strokeWidth="1"/>
        <line x1="30" y1="680" x2="70" y2="680" stroke="#818cf8" strokeWidth="2.5"/>
        <text x="80" y="684" fontSize="11" fill="#9ca3af">Technical flywheel</text>
        <line x1="260" y1="680" x2="300" y2="680" stroke="#a855f7" strokeWidth="2" strokeDasharray="6 3"/>
        <text x="310" y="684" fontSize="11" fill="#9ca3af">D4BL methodology cycle</text>
      </svg>
    </div>
  );
}
