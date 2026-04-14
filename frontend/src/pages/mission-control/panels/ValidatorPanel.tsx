import { MissionControlStatus } from '../../../lib/api/missionControl';
import { GlassCard } from '../../../components/GlassCard';
import { Radio } from 'lucide-react';

interface Props {
  data: MissionControlStatus | undefined;
  onExpand: () => void;
}

export function ValidatorPanel({ data, onExpand }: Props) {
  const v = data?.validator;
  const enabled = !!v?.enabled;
  const scheduler = v?.scheduler;
  const evaluator = v?.evaluator;

  return (
    <GlassCard
      variant="cyan"
      className="p-4 cursor-pointer hover:ring-2 hover:ring-cyan-500/50 transition"
    >
      <button onClick={onExpand} className="w-full text-left">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-cyan-400" />
            <h3 className="font-mono uppercase tracking-widest text-sm text-cyan-400">
              Validator
            </h3>
          </div>
          <span
            className={`text-xs uppercase font-mono ${
              enabled ? 'text-emerald-400' : 'text-slate-500'
            }`}
          >
            {enabled ? 'ONLINE' : 'DISABLED'}
          </span>
        </div>

        {!enabled ? (
          <div className="text-sm text-slate-500 py-4 text-center">
            Bittensor integration disabled
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div className="p-2 bg-slate-900/50 rounded">
              <div className="text-[10px] text-slate-500 uppercase">
                Windows Collected
              </div>
              <div className="font-mono text-lg text-cyan-300">
                {scheduler?.windows_collected ?? '—'}
              </div>
            </div>
            <div className="p-2 bg-slate-900/50 rounded">
              <div className="text-[10px] text-slate-500 uppercase">
                Response Rate
              </div>
              <div className="font-mono text-lg text-cyan-300">
                {scheduler
                  ? `${(scheduler.last_miner_response_rate * 100).toFixed(0)}%`
                  : '—'}
              </div>
            </div>
            <div className="p-2 bg-slate-900/50 rounded">
              <div className="text-[10px] text-slate-500 uppercase">
                Evaluated
              </div>
              <div className="font-mono text-lg text-emerald-400">
                {evaluator?.windows_evaluated ?? '—'}
              </div>
            </div>
            <div className="p-2 bg-slate-900/50 rounded">
              <div className="text-[10px] text-slate-500 uppercase">Skipped</div>
              <div className="font-mono text-lg text-amber-400">
                {evaluator?.windows_skipped ?? '—'}
              </div>
            </div>
          </div>
        )}
      </button>
    </GlassCard>
  );
}
