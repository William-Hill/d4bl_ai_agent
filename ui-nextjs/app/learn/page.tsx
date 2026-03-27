import ConceptSection from '@/components/learn/ConceptSection';
import DistillationPipeline from '@/components/learn/DistillationPipeline';
import EvalMetricsPanel from '@/components/learn/EvalMetricsPanel';
import LoRAVisualizer from '@/components/learn/LoRAVisualizer';
import MethodologyWheel from '@/components/learn/MethodologyWheel';
import ModelComparisonPlayground from '@/components/learn/ModelComparisonPlayground';
import QuantizationSlider from '@/components/learn/QuantizationSlider';
import RegisterComparison from '@/components/learn/RegisterComparison';
import TutorialStep from '@/components/learn/TutorialStep';

const COLAB_BASE = 'https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials';

const TUTORIALS = [
  { title: 'Understanding Your Data', description: 'Query Supabase and see the shape of equity data.', colabUrl: `${COLAB_BASE}/01_understanding_your_data.ipynb` },
  { title: 'Creating Training Data', description: 'Write distillation prompts and generate training pairs.', colabUrl: `${COLAB_BASE}/02_creating_training_data.ipynb` },
  { title: 'Training with Unsloth', description: 'Load the model, configure LoRA, and run training.', colabUrl: `${COLAB_BASE}/03_training_with_unsloth.ipynb` },
  { title: 'Testing Your Model', description: 'Load in Ollama and compare outputs to the base model.', colabUrl: `${COLAB_BASE}/04_testing_your_model.ipynb` },
  { title: 'Making It Your Own', description: "Customize the model for your community's data.", colabUrl: `${COLAB_BASE}/05_making_it_your_own.ipynb` },
];

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
        <a
          href="https://gamma.app/docs/Building-AI-That-Centers-Racial-Equity-m8qd4n13bdtboa1"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 mt-6 px-6 py-3 bg-[#00ff32]/10 border border-[#00ff32]/30 rounded-lg text-sm text-[#00ff32] hover:bg-[#00ff32]/20 transition-colors"
        >
          View the Slide Deck
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
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

      {/* Section: How LoRA Works */}
      <ConceptSection
        title="How LoRA Works"
        subtitle="Small adapters, big impact"
      >
        <p className="mb-6">
          LoRA (Low-Rank Adaptation) is a technique that lets you fine-tune a
          large model by training only a small set of adapter weights — leaving
          the original model frozen. Drag the slider to see how adapter size
          changes with rank.
        </p>
        <LoRAVisualizer />
      </ConceptSection>

      {/* Section: How Quantization Works */}
      <ConceptSection
        title="How Quantization Works"
        subtitle="Shrinking models without losing their minds"
      >
        <p className="mb-6">
          Quantization reduces the precision of a model&apos;s numbers — from 16-bit
          floating point down to 4-bit or even 2-bit integers. Less precision means
          a smaller file and faster inference, but too aggressive and quality
          drops. Drag to explore the trade-off.
        </p>
        <QuantizationSlider />
      </ConceptSection>

      {/* Section: Training Data & Distillation */}
      <ConceptSection
        title="Training Data & Distillation"
        subtitle="How we create high-quality training data from real equity metrics"
      >
        <p className="mb-6">
          We can&apos;t just fine-tune on raw data — we need instruction/response pairs
          that teach the model how to think about equity. We use a process called
          distillation: a larger model (Claude) generates expert-level responses
          from our real data, creating training examples for the smaller model.
        </p>
        <DistillationPipeline />
      </ConceptSection>

      {/* Section: D4BL Methodology in AI */}
      <ConceptSection
        title="D4BL Methodology in AI"
        subtitle="How each stage of our work maps to the model"
      >
        <p className="mb-6">
          D4BL&apos;s methodology isn&apos;t just a framework we reference — it&apos;s embedded
          in how the model was trained, what it generates, and who it serves. Click
          each stage to see the connection.
        </p>
        <MethodologyWheel />
      </ConceptSection>

      {/* Section: From Data to Justice */}
      <ConceptSection
        title="From Data to Justice"
        subtitle="The same data, told three ways"
      >
        <p className="mb-6">
          Our model doesn&apos;t just analyze data — it communicates findings in the
          register that serves each audience best. Community members, policymakers,
          and researchers all need different framings of the same truth.
        </p>
        <RegisterComparison />
      </ConceptSection>

      {/* Section: Try It Yourself */}
      <ConceptSection
        title="Try It Yourself"
        subtitle="Guided tutorials to build your own equity-focused model"
      >
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4 mt-2">
          {TUTORIALS.map((t, i) => (
            <TutorialStep
              key={t.title}
              step={i + 1}
              title={t.title}
              description={t.description}
              colabUrl={t.colabUrl}
            />
          ))}
        </div>
      </ConceptSection>

      {/* Section: How It Performs */}
      <ConceptSection
        title="How It Performs"
        subtitle="Eval harness results comparing base and fine-tuned models"
      >
        <p className="mb-6">
          We run each model through a standardized test set and measure JSON
          validity, entity extraction, equity framing, and latency. These are
          the latest results from our evaluation harness.
        </p>
        <EvalMetricsPanel />
      </ConceptSection>

      {/* Section: Compare Models Live */}
      <ConceptSection
        title="Compare Models Live"
        subtitle="Run any prompt through both models and see the difference"
      >
        <p className="mb-6">
          Type a query below to see how the fine-tuned D4BL model compares to
          the base model. Select a task type to test different adapters.
        </p>
        <ModelComparisonPlayground />
      </ConceptSection>
    </main>
  );
}
