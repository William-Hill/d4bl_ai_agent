import ConceptSection from '@/components/learn/ConceptSection';

export const metadata = {
  title: 'Learn — Building AI That Centers Community | D4BL',
  description:
    'An interactive guide to how Data for Black Lives built a fine-tuned language model for racial equity analysis.',
};

export default function LearnPage() {
  return (
    <main className="min-h-screen bg-[#1a1a1a]">
      {/* Hero */}
      <section className="relative px-6 pt-24 pb-16 text-center">
        <h1 className="text-5xl md:text-6xl font-bold text-white mb-4 tracking-tight">
          Building AI That Centers Community
        </h1>
        <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-8">
          How Data for Black Lives built a fine-tuned language model that treats
          racial equity as the starting point, not an afterthought.
        </p>
        <div className="mx-auto w-24 h-1 bg-gradient-to-r from-[#00ff32] to-[#00cc28] rounded-full" />
      </section>

      {/* Section: What is a Language Model? */}
      <ConceptSection
        title="What is a Language Model?"
        subtitle="The basics, grounded in our mission"
      >
        <p>
          A language model is software that has learned patterns from vast amounts
          of text. Given a question or prompt, it predicts what words should come
          next — generating responses that can inform, explain, and summarize.
        </p>
        <p>
          Think of it like a research assistant that has read millions of
          documents. It can synthesize information, but its perspective depends
          entirely on what it was trained on. Most models are trained on general
          internet text — which means they reflect the biases, blind spots, and
          priorities of that data.
        </p>
        <p>
          For racial equity work, this is a problem. Generic models often treat
          disparities as statistical outliers rather than systemic patterns. They
          lack the context to connect a mortality rate to redlining, or a poverty
          statistic to policy failure.{' '}
          <span className="text-[#00ff32] font-semibold">
            That&apos;s why we built our own.
          </span>
        </p>
      </ConceptSection>

      {/* Section: Why Fine-Tune? */}
      <ConceptSection
        title="Why Fine-Tune?"
        subtitle="Why generic AI fails racial equity analysis"
      >
        <p>
          Fine-tuning means taking a pre-trained model and teaching it your
          specific domain — your data, your methodology, your values. Instead of
          starting from scratch, you build on what the model already knows and
          sharpen it for your work.
        </p>
        <div className="grid md:grid-cols-2 gap-6 mt-6">
          <div className="bg-[#292929] border border-[#404040] rounded-lg p-6">
            <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wide mb-3">
              Generic Model
            </h3>
            <p className="text-gray-400 text-sm">
              &quot;The maternal mortality rate shows racial disparities, with
              Black women experiencing higher rates. Various socioeconomic factors
              may contribute to this difference.&quot;
            </p>
          </div>
          <div className="bg-[#292929] border border-[#00ff32]/30 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-[#00ff32] uppercase tracking-wide mb-3">
              D4BL Model
            </h3>
            <p className="text-gray-400 text-sm">
              &quot;Black maternal mortality in Alabama (55.3 per 100k) is 2.1x
              the white rate — a disparity rooted in decades of hospital closures
              in Black communities, Medicaid coverage gaps, and documented patterns
              of provider bias. The Momnibus Act directly targets these structural
              drivers.&quot;
            </p>
          </div>
        </div>
      </ConceptSection>
    </main>
  );
}
