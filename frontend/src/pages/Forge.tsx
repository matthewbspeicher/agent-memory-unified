import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';

interface DraftForm {
  name: string;
  system_prompt: string;
  model: string;
  hyperparameters: {
    temperature: number;
    top_p: number;
  };
}

export default function Forge() {
  const navigate = useNavigate();
  const [form, setForm] = useState<DraftForm>({
    name: '',
    system_prompt: '',
    model: 'gpt-4o',
    hyperparameters: {
      temperature: 0.7,
      top_p: 1.0,
    },
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch('/api/v1/drafts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to create draft');
      }

      const result = await res.json();
      const draft = result.data || result;
      navigate(`/studio/lab/${draft.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const updateField = <K extends keyof DraftForm>(
    field: K,
    value: DraftForm[K]
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const updateHyperparam = (key: keyof DraftForm['hyperparameters'], value: number) => {
    setForm((prev) => ({
      ...prev,
      hyperparameters: { ...prev.hyperparameters, [key]: value },
    }));
  };

  const isValid = form.name.trim().length > 0 && form.system_prompt.trim().length > 0;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-3xl font-black text-cyan-400 uppercase tracking-wider">
          The Forge
        </h1>
        <p className="text-gray-400 mt-2">
          Create a new agent draft. Configure its system prompt and hyperparameters,
          then validate in the Lab.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <GlassCard variant="cyan" className="p-6">
          <h2 className="text-xl font-bold text-white mb-4">Agent Configuration</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Agent Name
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="e.g., MomentumHunter"
                maxLength={64}
                className="w-full p-3 bg-slate-900 border border-cyan-500/30 text-white rounded-lg
                         placeholder-gray-500 focus:border-cyan-400 focus:outline-none transition"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                System Prompt
              </label>
              <textarea
                value={form.system_prompt}
                onChange={(e) => updateField('system_prompt', e.target.value)}
                placeholder="You are a momentum trading agent that..."
                rows={8}
                className="w-full p-3 bg-slate-900 border border-cyan-500/30 text-white rounded-lg
                         placeholder-gray-500 focus:border-cyan-400 focus:outline-none transition resize-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Model
              </label>
              <select
                value={form.model}
                onChange={(e) => updateField('model', e.target.value)}
                className="w-full p-3 bg-slate-900 border border-cyan-500/30 text-white rounded-lg
                         focus:border-cyan-400 focus:outline-none transition"
              >
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4.1">GPT-4.1</option>
                <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                <option value="claude-opus-4-20250514">Claude Opus 4</option>
              </select>
            </div>
          </div>
        </GlassCard>

        <GlassCard variant="cyan" className="p-6">
          <h2 className="text-xl font-bold text-white mb-4">Hyperparameters</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Temperature: {form.hyperparameters.temperature.toFixed(1)}
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={form.hyperparameters.temperature}
                onChange={(e) => updateHyperparam('temperature', parseFloat(e.target.value))}
                className="w-full accent-cyan-400"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Top-P: {form.hyperparameters.top_p.toFixed(1)}
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={form.hyperparameters.top_p}
                onChange={(e) => updateHyperparam('top_p', parseFloat(e.target.value))}
                className="w-full accent-cyan-400"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>Focused</span>
                <span>Diverse</span>
              </div>
            </div>
          </div>
        </GlassCard>

        {error && (
          <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-4">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-6 py-3 bg-slate-700 text-white font-medium rounded-lg
                     hover:bg-slate-600 transition"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!isValid || loading}
            className="px-8 py-3 bg-cyan-500 text-slate-900 font-bold uppercase rounded-lg
                     disabled:opacity-50 disabled:cursor-not-allowed
                     hover:bg-cyan-400 transition"
          >
            {loading ? 'Creating...' : 'Save Draft & Continue to Lab'}
          </button>
        </div>
      </form>
    </div>
  );
}
