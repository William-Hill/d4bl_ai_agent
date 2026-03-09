'use client';

import SourceWizard from '@/components/data/SourceWizard';

export default function NewSourcePage() {
  return (
    <div className="min-h-screen bg-[#292929]">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">New Data Source</h1>
          <div className="w-16 h-1 bg-[#00ff32] mb-3" />
          <p className="text-gray-400 text-sm">
            Configure a new data ingestion source.
          </p>
        </header>

        <SourceWizard />
      </div>
    </div>
  );
}
