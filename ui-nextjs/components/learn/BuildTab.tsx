import TutorialStep from './TutorialStep';

const COLAB_BASE = 'https://colab.research.google.com/github/William-Hill/d4bl_ai_agent/blob/main/notebooks/tutorials';

const TUTORIALS = [
  { title: 'Understanding Your Data', description: 'Query Supabase and see the shape of equity data.', colabUrl: `${COLAB_BASE}/01_understanding_your_data.ipynb` },
  { title: 'Creating Training Data', description: 'Write distillation prompts and generate training pairs.', colabUrl: `${COLAB_BASE}/02_creating_training_data.ipynb` },
  { title: 'Training with Unsloth', description: 'Load the model, configure LoRA, and run training.', colabUrl: `${COLAB_BASE}/03_training_with_unsloth.ipynb` },
  { title: 'Testing Your Model', description: 'Load in Ollama and compare outputs to the base model.', colabUrl: `${COLAB_BASE}/04_testing_your_model.ipynb` },
  { title: 'Making It Your Own', description: "Customize the model for your community's data.", colabUrl: `${COLAB_BASE}/05_making_it_your_own.ipynb` },
];

const SLIDE_DECK_URL = 'https://gamma.app/docs/Building-AI-That-Centers-Racial-Equity-m8qd4n13bdtboa1';

export default function BuildTab() {
  return (
    <div className="space-y-8">
      {/* Slide deck link */}
      <div className="bg-[#292929] border border-[#404040] rounded-lg p-6">
        <h3 className="text-lg font-semibold text-white mb-2">Presentation Slide Deck</h3>
        <p className="text-gray-400 mb-4">
          A comprehensive walkthrough of the fine-tuning methodology, from data preparation to deployment.
        </p>
        <a
          href={SLIDE_DECK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-[#00ff32] hover:text-[#00cc28] font-medium"
        >
          View Slide Deck
          <span aria-hidden="true">&rarr;</span>
        </a>
      </div>

      {/* Tutorial grid */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">Hands-On Tutorials</h3>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
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
      </div>
    </div>
  );
}
