'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import GuideSection from '@/components/guide/GuideSection';
import FeatureRequestForm from '@/components/guide/FeatureRequestForm';

export default function GuidePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login');
    }
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return null;
  }

  return (
    <main className="min-h-screen bg-[#111111] px-6 py-12">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">
          Staff Contributor Guide
        </h1>
        <p className="text-gray-400 text-sm mb-10">
          Learn how to contribute data sources, documents, example queries, and feature ideas
          to the D4BL platform.
        </p>

        <div className="space-y-3">
          {/* Section 1: Adding a Data Source */}
          <GuideSection
            title="Adding a Data Source"
            defaultOpen={true}
            actionLabel="Upload a data source"
            actionHref="/admin"
          >
            <p>
              <span className="text-white font-semibold">What makes a good data source:</span>{' '}
              Datasets should include geographic identifiers (state, county, or census tract),
              racial/ethnic breakdowns, and reasonably recent data (within the last 5 years).
              Sources that compare outcomes across racial groups are especially valuable.
            </p>
            <p>
              <span className="text-white font-semibold">Supported formats:</span>{' '}
              CSV and Excel (.xlsx) files up to 50 MB. Make sure column headers are in the
              first row and that racial group names follow a consistent format across rows.
            </p>
            <p>
              <span className="text-white font-semibold">How to upload:</span>{' '}
              Go to <span className="text-[#00ff32]">Admin &gt; Data Sources</span> tab. Fill in
              the source name, select your file, and add any relevant notes. Your submission
              enters the review queue immediately.
            </p>
            <p>
              <span className="text-white font-semibold">What happens after:</span>{' '}
              An admin reviews your upload and marks it approved or rejected.
              Automated processing and indexing is planned for a follow-up release.
            </p>
            <p>
              <span className="text-white font-semibold">Example:</span>{' '}
              A county-level CSV from{' '}
              <span className="text-gray-300">County Health Rankings</span> with columns like{' '}
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">county_fips</code>,{' '}
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">race</code>, and{' '}
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">premature_death_rate</code>{' '}
              is a great fit.
            </p>
          </GuideSection>

          {/* Section 2: Sharing a Document */}
          <GuideSection
            title="Sharing a Document"
            actionLabel="Upload a document"
            actionHref="/admin"
          >
            <p>
              <span className="text-white font-semibold">Useful document types:</span>{' '}
              Policy briefs, research reports, news articles, academic papers, community impact
              studies, and legislative analyses. Anything that connects data to systemic causes
              or policy outcomes is particularly valuable.
            </p>
            <p>
              <span className="text-white font-semibold">File vs. URL:</span>{' '}
              Upload PDFs or DOCX files directly (25 MB max) for documents you have on disk.
              For web articles and online reports, paste a URL instead. In either case, the
              platform extracts the text at submit time so the admin can review the actual
              content — not just a link that might change later.
            </p>
            <p>
              <span className="text-white font-semibold">What happens after approval:</span>{' '}
              Once an admin approves your upload, the extracted text is split into chunks,
              embedded into the vector store, and tagged with your name as the contributor.
              Research agents cite approved documents when answering queries, and they appear
              in vector search results on <span className="text-[#00ff32]">/explore</span>.
              If processing fails (rare — usually a timeout on Ollama), the admin sees the
              error in the review queue and can retry without you needing to resubmit.
            </p>
            <p>
              <span className="text-white font-semibold">Example:</span>{' '}
              The Vera Institute report <em>Overlooked: Women and Jails in an Era of Reform</em>{' '}
              as a PDF — or a URL to a ProPublica investigation on racial disparities in
              mortgage lending.
            </p>
          </GuideSection>

          {/* Section 3: Contributing Example Queries */}
          <GuideSection
            title="Contributing Example Queries"
            actionLabel="Submit an example query"
            actionHref="/admin"
          >
            <p>
              <span className="text-white font-semibold">What makes a good example query:</span>{' '}
              Good queries are specific, answerable from available data, equity-focused, and
              grounded in a geographic context. Avoid vague or overly broad questions.
            </p>
            <p>
              <span className="text-white font-semibold">Why examples matter:</span>{' '}
              Example queries serve two purposes: they become training data for the fine-tuned
              model, and they provide ready-made templates that help new users understand what
              the platform can answer.
            </p>
            <p>
              <span className="text-white font-semibold">What to include:</span>{' '}
              The query text itself, a short explanation of why it is a good example, and
              optionally a curated answer or the key data points you would expect a correct
              response to include.
            </p>
            <p>
              <span className="text-white font-semibold">Example:</span>{' '}
              <span className="text-gray-300 italic">
                &quot;What are racial disparities in mortgage lending denial rates in Atlanta?&quot;
              </span>{' '}
              — specific city, specific metric, clearly equity-focused.
            </p>
          </GuideSection>

          {/* Section 4: Requesting a Feature */}
          <GuideSection title="Requesting a Feature">
            <p>
              <span className="text-white font-semibold">Tips for good requests:</span>
            </p>
            <ul className="list-disc list-inside space-y-1 pl-2">
              <li>Be specific about the problem you are trying to solve, not just the solution.</li>
              <li>Explain who benefits and how often they would use this feature.</li>
              <li>Include a concrete scenario: &quot;As a researcher, I want to... so that...&quot;</li>
              <li>If a workaround exists but is painful, describe it — that context helps prioritization.</li>
            </ul>
            <FeatureRequestForm />
          </GuideSection>

          {/* Section 5: Developing a Feature (Advanced) */}
          <GuideSection title="Developing a Feature (Advanced)">
            <span className="inline-block px-2 py-0.5 rounded text-xs font-bold bg-yellow-500/20 text-yellow-400 border border-yellow-500/40 mb-3">
              FOR TECHNICAL CONTRIBUTORS
            </span>
            <p>
              <span className="text-white font-semibold">Architecture overview:</span>{' '}
              The platform is a monorepo. The backend is a{' '}
              <span className="text-gray-300">FastAPI</span> app powered by{' '}
              <span className="text-gray-300">CrewAI</span> agents that run inference via a local{' '}
              <span className="text-gray-300">Ollama</span> LLM. The frontend is{' '}
              <span className="text-gray-300">Next.js</span> (App Router, React 19, Tailwind CSS 4).
              Data is persisted in PostgreSQL with a Supabase pgvector extension for embeddings.
            </p>
            <p>
              <span className="text-white font-semibold">Getting started:</span>{' '}
              Read the{' '}
              <a
                href="https://github.com/dataforblacklives/d4bl-ai-agent"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#00ff32] hover:underline"
              >
                Development Guide on GitHub
              </a>{' '}
              for setup instructions, environment variables, and Docker configuration.
            </p>
            <p>
              <span className="text-white font-semibold">Workflow:</span>{' '}
              Branch from <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">main</code>{' '}
              using a descriptive name, run{' '}
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">npm run build</code>{' '}
              and <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">pytest</code>{' '}
              before opening a PR, and use Conventional Commits (
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">feat:</code>,{' '}
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">fix:</code>,{' '}
              <code className="text-xs bg-[#292929] px-1 py-0.5 rounded">refactor:</code>).
            </p>
            <p>
              <span className="text-white font-semibold">Key directories:</span>
            </p>
            <ul className="space-y-1 pl-2 font-mono text-xs text-gray-400">
              <li>
                <span className="text-gray-300">src/d4bl/app/</span>{' '}
                — FastAPI REST endpoints and WebSocket manager
              </li>
              <li>
                <span className="text-gray-300">src/d4bl/agents/</span>{' '}
                — CrewAI agent definitions and tool wrappers
              </li>
              <li>
                <span className="text-gray-300">src/d4bl/infra/</span>{' '}
                — SQLAlchemy models, vector store, database helpers
              </li>
              <li>
                <span className="text-gray-300">src/d4bl/query/</span>{' '}
                — Natural language query engine (parse → search → fuse)
              </li>
              <li>
                <span className="text-gray-300">scripts/ingestion/</span>{' '}
                — Standalone scripts for each external data source
              </li>
              <li>
                <span className="text-gray-300">ui-nextjs/app/</span>{' '}
                — Next.js App Router pages
              </li>
              <li>
                <span className="text-gray-300">ui-nextjs/components/</span>{' '}
                — Shared React components
              </li>
            </ul>
          </GuideSection>
        </div>
      </div>
    </main>
  );
}
