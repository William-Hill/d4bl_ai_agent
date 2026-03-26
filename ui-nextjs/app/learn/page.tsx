import ConceptSection from '@/components/learn/ConceptSection';
import DistillationPipeline from '@/components/learn/DistillationPipeline';
import LoRAVisualizer from '@/components/learn/LoRAVisualizer';
import MethodologyWheel from '@/components/learn/MethodologyWheel';
import PlaygroundPlaceholder from '@/components/learn/PlaygroundPlaceholder';
import QuantizationSlider from '@/components/learn/QuantizationSlider';
import RegisterComparison from '@/components/learn/RegisterComparison';
import TutorialStep from '@/components/learn/TutorialStep';

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
          <TutorialStep
            step={1}
            title="Understanding Your Data"
            description="Query Supabase and see the shape of equity data."
            colabUrl="#"
          />
          <TutorialStep
            step={2}
            title="Creating Training Data"
            description="Write distillation prompts and generate training pairs."
            colabUrl="#"
          />
          <TutorialStep
            step={3}
            title="Training with Unsloth"
            description="Load the model, configure LoRA, and run training."
            colabUrl="#"
          />
          <TutorialStep
            step={4}
            title="Testing Your Model"
            description="Load in Ollama and compare outputs to the base model."
            colabUrl="#"
          />
          <TutorialStep
            step={5}
            title="Making It Your Own"
            description="Customize the model for your community's data."
            colabUrl="#"
          />
        </div>
      </ConceptSection>

      {/* Section: What's Next */}
      <ConceptSection
        title="What's Next"
        subtitle="The playground is coming"
      >
        <p className="mb-6">
          We&apos;re building an interactive playground where you can query the D4BL
          model directly, compare outputs across registers, and export results
          for your own analysis.
        </p>
        <PlaygroundPlaceholder />
      </ConceptSection>
    </main>
  );
}
