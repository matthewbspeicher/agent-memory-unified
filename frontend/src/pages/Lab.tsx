import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';

interface Draft {
  id: string;
  name: string;
  system_prompt: string;
  model: string;
  hyperparameters: {
    temperature: number;
    top_p: number;
  };
  status: string;
  backtest_results: {
    sharpe_ratio: number;
    win_rate: number;
    max_drawdown: number;
    total_trades: number;
    equity_curve: { timestamp: string; equity: number }[];
    status: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export default function Lab() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [backtesting, setBacktesting] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDraft = async () => {
      try {
        const res = await fetch(`/api/v1/drafts/${id}`);
        if (!res.ok) throw new Error('Draft not found');
        const data = await res.json();
        setDraft(data.data || data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load draft');
      } finally {
        setLoading(false);
      }
    };
    fetchDraft();
  }, [id]);

  const runBacktest = async () => {
    if (!id) return;
    setBacktesting(true);
    setError(null);

    try {
      const res = await fetch(`/api/v1/drafts/${id}/backtest`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Backtest failed');
      const { data } = await res.json();
      setDraft((prev) => prev ? { ...prev, backtest_results: data, status: 'tested' } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed');
    } finally {
      setBacktesting(false);
    }
  };

  const deployAgent = async () => {
    if (!id) return;
    setDeploying(true);
    setError(null);

    try {
      const res = await fetch(`/api/v1/drafts/${id}/deploy`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Deployment failed');
      }
      setDraft((prev) => prev ? { ...prev, status: 'deployed' } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deployment failed');
    } finally {
      setDeploying(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 max-w-4xl mx-auto flex items-center justify-center min-h-[400px]">
        <div className="text-gray-500 font-mono animate-pulse">Loading draft...</div>
      </div>
    );
  }

  if (error && !draft) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300">
          {error}
        </div>
        <button
          onClick={() => navigate('/studio/forge')}
          className="mt-4 px-4 py-2 bg-slate-700 text-white rounded hover:bg-slate-600"
        >
          Create New Draft
        </button>
      </div>
    );
  }

  if (!draft) return null;

  const results = draft.backtest_results;
  const canDeploy = draft.status === 'tested' && results && results.sharpe_ratio >= 1.0;

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6 animate-in fade-in duration-500">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-black text-violet-400 uppercase tracking-wider">
            The Lab
          </h1>
          <p className="text-gray-400 mt-2">
            Evaluate <span className="text-white font-medium">{draft.name}</span> through backtesting.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${
            draft.status === 'draft' ? 'bg-gray-500/30 text-gray-300' :
            draft.status === 'tested' ? 'bg-blue-500/30 text-blue-300' :
            draft.status === 'deployed' ? 'bg-green-500/30 text-green-300' :
            'bg-gray-500/30 text-gray-300'
          }`}>
            {draft.status.toUpperCase()}
          </span>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <GlassCard variant="violet" className="p-6 space-y-4">
          <h2 className="text-xl font-bold text-white">Configuration</h2>

          <div className="space-y-3 text-sm">
            <div>
              <span className="text-gray-400">Model:</span>
              <span className="ml-2 text-white font-mono">{draft.model}</span>
            </div>
            <div>
              <span className="text-gray-400">Temperature:</span>
              <span className="ml-2 text-white">{draft.hyperparameters?.temperature ?? 0.7}</span>
            </div>
            <div>
              <span className="text-gray-400">Top-P:</span>
              <span className="ml-2 text-white">{draft.hyperparameters?.top_p ?? 1.0}</span>
            </div>
          </div>

          <div className="pt-4 border-t border-violet-500/30">
            <span className="text-gray-400 text-sm">System Prompt:</span>
            <pre className="mt-2 p-3 bg-slate-900/50 rounded text-gray-300 text-xs whitespace-pre-wrap max-h-48 overflow-y-auto">
              {draft.system_prompt}
            </pre>
          </div>

          <button
            onClick={runBacktest}
            disabled={backtesting || draft.status === 'deployed'}
            className="w-full mt-4 px-6 py-3 bg-violet-500 text-white font-bold uppercase rounded-lg
                     disabled:opacity-50 disabled:cursor-not-allowed
                     hover:bg-violet-400 transition"
          >
            {backtesting ? 'Simulating...' : 'Run Sync Backtest'}
          </button>

          <p className="text-xs text-gray-500 text-center">
            Synthetic metrics for UI validation. Real backtest integration pending.
          </p>
        </GlassCard>

        {results && (
          <GlassCard variant="green" className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">Results</h2>
              {results.status === 'scaffold' && (
                <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded">
                  SCAFFOLD
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-slate-900/50 rounded-lg">
                <div className="text-gray-400 text-sm">Sharpe Ratio</div>
                <div className={`text-2xl font-mono font-bold ${
                  results.sharpe_ratio >= 1.0 ? 'text-emerald-400' : 'text-yellow-400'
                }`}>
                  {results.sharpe_ratio.toFixed(2)}
                </div>
              </div>
              <div className="p-4 bg-slate-900/50 rounded-lg">
                <div className="text-gray-400 text-sm">Win Rate</div>
                <div className="text-2xl font-mono font-bold text-emerald-400">
                  {(results.win_rate * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-4 bg-slate-900/50 rounded-lg">
                <div className="text-gray-400 text-sm">Max Drawdown</div>
                <div className="text-2xl font-mono font-bold text-red-400">
                  {(results.max_drawdown * 100).toFixed(1)}%
                </div>
              </div>
              <div className="p-4 bg-slate-900/50 rounded-lg">
                <div className="text-gray-400 text-sm">Total Trades</div>
                <div className="text-2xl font-mono font-bold text-white">
                  {results.total_trades}
                </div>
              </div>
            </div>

            {results.equity_curve && results.equity_curve.length > 0 && (
              <div className="mt-4">
                <div className="text-gray-400 text-sm mb-2">Equity Curve</div>
                <div className="h-32 bg-slate-900/50 rounded-lg p-2 flex items-end gap-px">
                  {results.equity_curve.map((point, i) => {
                    const minEquity = Math.min(...results.equity_curve.map(p => p.equity));
                    const maxEquity = Math.max(...results.equity_curve.map(p => p.equity));
                    const range = maxEquity - minEquity || 1;
                    const height = ((point.equity - minEquity) / range) * 100;
                    return (
                      <div
                        key={i}
                        className="flex-1 bg-emerald-500/60 rounded-t"
                        style={{ height: `${Math.max(5, height)}%` }}
                        title={`$${point.equity.toLocaleString()}`}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            <button
              onClick={deployAgent}
              disabled={!canDeploy || deploying}
              className="w-full mt-4 px-6 py-3 bg-emerald-500 text-slate-900 font-bold uppercase rounded-lg
                       disabled:opacity-50 disabled:cursor-not-allowed
                       hover:bg-emerald-400 transition"
            >
              {deploying ? 'Deploying...' : canDeploy ? 'Deploy Agent' : 'Sharpe must be >= 1.0 to deploy'}
            </button>
          </GlassCard>
        )}
      </div>

      <div className="flex justify-between pt-4">
        <button
          onClick={() => navigate('/studio/forge')}
          className="px-4 py-2 text-gray-400 hover:text-white transition"
        >
          ← Back to Forge
        </button>
        <button
          onClick={() => navigate('/roster')}
          className="px-4 py-2 text-gray-400 hover:text-white transition"
        >
          View Roster →
        </button>
      </div>
    </div>
  );
}
