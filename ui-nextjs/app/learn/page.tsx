import ConceptSection from '@/components/learn/ConceptSection';
import DistillationPipeline from '@/components/learn/DistillationPipeline';
import EvalMetricsPanel from '@/components/learn/EvalMetricsPanel';
import LoRAVisualizer from '@/components/learn/LoRAVisualizer';
import MethodologyWheel from '@/components/learn/MethodologyWheel';
import ModelComparisonPlayground from '@/components/learn/ModelComparisonPlayground';
import QuantizationSlider from '@/components/learn/QuantizationSlider';
import RegisterComparison from '@/components/learn/RegisterComparison';
import LearnTabs from '@/components/learn/LearnTabs';
import BuildTab from '@/components/learn/BuildTab';
import ExperimentTimeline from '@/components/learn/ExperimentTimeline';
import ExperimentMetrics from '@/components/learn/ExperimentMetrics';
import TrainingCostTracker from '@/components/learn/TrainingCostTracker';

export const metadata = {
  title: 'Learn — Building AI That Centers Community | D4BL',
  description:
    'Compare model pipelines, explore evaluation metrics, and learn how fine-tuning embeds equity methodology into AI systems.',
};

export default function LearnPage() {
  return (
    <main className="min-h-screen bg-[#1a1a1a]">
      {/* Compact hero */}
      <section className="px-6 pt-24 pb-8 text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-white mb-3 tracking-tight">
          Building AI That Centers Community
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto">
          Compare model pipelines, explore evaluation metrics, and learn how
          fine-tuning embeds equity methodology into AI systems.
        </p>
      </section>

      {/* Tabs */}
      <section className="max-w-6xl mx-auto px-6 pb-16">
        <LearnTabs
          tabs={[
            {
              id: 'compare',
              label: 'Compare',
              content: (
                <div className="space-y-12">
                  <ModelComparisonPlayground />
                  <EvalMetricsPanel />
                </div>
              ),
            },
            {
              id: 'learn',
              label: 'Learn',
              content: (
                <div className="space-y-16">
                  {/* What is a Language Model? */}
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

                  {/* Why Fine-Tune? */}
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

                  {/* How LoRA Works */}
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

                  {/* How Quantization Works */}
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

                  {/* Training Data & Distillation */}
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

                  {/* D4BL Methodology in AI */}
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

                  {/* From Data to Justice */}
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
                </div>
              ),
            },
            {
              id: 'build',
              label: 'Build',
              content: <BuildTab />,
            },
            {
              id: 'experiments',
              label: 'Experiments',
              content: (
                <div className="space-y-12">
                  <ExperimentTimeline />
                  <ExperimentMetrics />
                  <TrainingCostTracker />
                </div>
              ),
            },
          ]}
        />
      </section>
    </main>
  );
}
