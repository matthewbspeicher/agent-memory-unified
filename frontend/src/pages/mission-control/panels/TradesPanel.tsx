import { MissionControlStatus } from '../../../lib/api/missionControl';
import { GlassCard } from '../../../components/GlassCard';
import { Briefcase } from 'lucide-react';

interface Props {
  data: MissionControlStatus | undefined;
  onExpand: () => void;
}

export function TradesPanel({ data, onExpand }: Props) {
  const trades = data?.trades;
  const positions = trades?.positions ?? [];
  const pnlClass =
    trades && trades.unrealized_pnl < 0 ? 'text-rose-400' : 'text-emerald-400';

  return (
    <GlassCard
      variant="green"
      className="p-4 cursor-pointer hover:ring-2 hover:ring-emerald-500/50 transition"
    >
      <button onClick={onExpand} className="w-full text-left">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Briefcase className="w-4 h-4 text-emerald-400" />
            <h3 className="font-mono uppercase tracking-widest text-sm text-emerald-400">
              Open Trades
            </h3>
          </div>
          <span className={`text-xs font-mono ${pnlClass}`}>
            $
            {trades
              ? `${trades.unrealized_pnl >= 0 ? '+' : ''}${trades.unrealized_pnl.toFixed(2)}`
              : '—'}
          </span>
        </div>

        {positions.length === 0 ? (
          <div className="text-sm text-slate-500 py-4 text-center">
            No open positions
          </div>
        ) : (
          <ul className="space-y-2 max-h-48 overflow-hidden">
            {positions.slice(0, 5).map((p, i) => {
              const pnl = p.unrealized_pnl ?? 0;
              const cls = pnl < 0 ? 'text-rose-400' : 'text-emerald-400';
              return (
                <li
                  key={`${p.symbol}-${i}`}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-white font-mono">{p.symbol}</span>
                    <span className="text-[10px] uppercase text-slate-500">
                      {p.side}
                    </span>
                  </div>
                  <span className={`font-mono text-xs ${cls}`}>
                    ${pnl >= 0 ? '+' : ''}
                    {pnl.toFixed(2)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        {positions.length > 5 && (
          <div className="mt-3 text-xs text-slate-500">
            +{positions.length - 5} more — click to expand
          </div>
        )}
      </button>
    </GlassCard>
  );
}
