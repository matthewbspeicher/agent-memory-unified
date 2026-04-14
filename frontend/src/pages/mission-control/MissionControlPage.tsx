import { useState } from 'react';
import { useMissionControl } from '../../hooks/useMissionControl';
import { StatusBar } from './StatusBar';
import { InfrastructurePanel } from './panels/InfrastructurePanel';
import { AgentActivityPanel } from './panels/AgentActivityPanel';
import { ValidatorPanel } from './panels/ValidatorPanel';
import { TradesPanel } from './panels/TradesPanel';
import { Drawer } from '../../components/ui/Drawer';

type PanelKey = 'infra' | 'agents' | 'validator' | 'trades' | null;

export default function MissionControlPage() {
  const { data, isLoading, error, refetch } = useMissionControl();
  const [open, setOpen] = useState<PanelKey>(null);
  const close = () => setOpen(null);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black text-emerald-400 uppercase tracking-widest font-mono">
            Mission Control
          </h1>
          <p className="text-gray-400 mt-1 text-sm">
            Unified ops dashboard — live system, agent, and validator status.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="px-3 py-2 bg-slate-800/60 border border-white/10 rounded-lg text-xs font-mono uppercase tracking-widest text-slate-300 hover:bg-slate-700/60 hover:text-white transition"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 bg-rose-500/20 border border-rose-500/40 rounded-lg text-rose-300 text-sm">
          Failed to load mission control status. {(error as Error).message}
        </div>
      )}

      <StatusBar data={data} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <InfrastructurePanel data={data} onExpand={() => setOpen('infra')} />
        <AgentActivityPanel data={data} onExpand={() => setOpen('agents')} />
        <ValidatorPanel data={data} onExpand={() => setOpen('validator')} />
        <TradesPanel data={data} onExpand={() => setOpen('trades')} />
      </div>

      {isLoading && (
        <div className="text-center text-slate-500 font-mono text-sm py-4 animate-pulse">
          Loading mission control data...
        </div>
      )}

      {/* Infrastructure Drawer */}
      <Drawer
        isOpen={open === 'infra'}
        onClose={close}
        title="Infrastructure Detail"
      >
        <div className="space-y-3">
          {data?.infra.services.map((s) => (
            <div
              key={s.name}
              className="p-4 bg-slate-900/50 rounded-lg border border-white/5"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-cyan-300">{s.name}</span>
                <span
                  className={`text-xs uppercase font-mono ${
                    s.status === 'healthy'
                      ? 'text-emerald-400'
                      : s.status === 'unhealthy'
                      ? 'text-rose-400'
                      : 'text-slate-400'
                  }`}
                >
                  {s.status}
                </span>
              </div>
              {s.deploy_status && (
                <div className="text-xs text-slate-400">
                  Deploy: {s.deploy_status}
                </div>
              )}
              {s.message && (
                <div className="text-xs text-rose-300 mt-1">{s.message}</div>
              )}
            </div>
          ))}
        </div>
      </Drawer>

      {/* Agent Drawer */}
      <Drawer
        isOpen={open === 'agents'}
        onClose={close}
        title="Agent Roster & Activity"
      >
        <div className="space-y-6">
          <section>
            <h3 className="text-xs uppercase tracking-widest text-slate-500 font-mono mb-2">
              Roster ({data?.agents.total ?? 0})
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {data?.agents.agents.map((a) => (
                <div
                  key={a.name}
                  className="p-3 bg-slate-900/50 rounded border border-white/5 flex items-center justify-between"
                >
                  <span className="font-mono text-sm text-white truncate">
                    {a.name}
                  </span>
                  <span
                    className={`text-[10px] uppercase font-mono ${
                      a.status === 'running'
                        ? 'text-emerald-400'
                        : a.status === 'error'
                        ? 'text-rose-400'
                        : 'text-slate-500'
                    }`}
                  >
                    {a.status}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs uppercase tracking-widest text-slate-500 font-mono mb-2">
              Recent Activity
            </h3>
            <ul className="space-y-2">
              {data?.activity.map((e) => (
                <li
                  key={e.id}
                  className="p-3 bg-slate-900/50 rounded border border-white/5 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-cyan-300">
                      {e.agent_name}
                    </span>
                    <span className="text-xs text-slate-500">
                      {new Date(e.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="mt-1 text-slate-300">
                    {e.symbol} · {e.signal} ·{' '}
                    <span className="text-slate-500">{e.status}</span>
                  </div>
                  {e.reasoning && (
                    <div className="text-xs text-slate-500 mt-1 italic">
                      {e.reasoning}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </Drawer>

      {/* Validator Drawer */}
      <Drawer
        isOpen={open === 'validator'}
        onClose={close}
        title="Validator Detail"
      >
        {data?.validator.enabled ? (
          <div className="space-y-4">
            {data.validator.scheduler && (
              <section>
                <h3 className="text-xs uppercase tracking-widest text-slate-500 font-mono mb-2">
                  Scheduler
                </h3>
                <dl className="grid grid-cols-2 gap-3">
                  <Stat
                    label="Windows Collected"
                    value={data.validator.scheduler.windows_collected}
                  />
                  <Stat
                    label="Windows Failed"
                    value={data.validator.scheduler.windows_failed}
                  />
                  <Stat
                    label="Response Rate"
                    value={`${(
                      data.validator.scheduler.last_miner_response_rate * 100
                    ).toFixed(1)}%`}
                  />
                  <Stat
                    label="Consecutive Failures"
                    value={data.validator.scheduler.consecutive_failures}
                  />
                </dl>
              </section>
            )}
            {data.validator.evaluator && (
              <section>
                <h3 className="text-xs uppercase tracking-widest text-slate-500 font-mono mb-2">
                  Evaluator
                </h3>
                <dl className="grid grid-cols-2 gap-3">
                  <Stat
                    label="Evaluated"
                    value={data.validator.evaluator.windows_evaluated}
                  />
                  <Stat
                    label="Skipped"
                    value={data.validator.evaluator.windows_skipped}
                  />
                </dl>
                {data.validator.evaluator.last_skip_reason && (
                  <div className="mt-3 text-xs text-amber-400 font-mono">
                    Last skip: {data.validator.evaluator.last_skip_reason}
                  </div>
                )}
              </section>
            )}
          </div>
        ) : (
          <div className="text-slate-500 text-sm">
            Bittensor integration is disabled.
          </div>
        )}
      </Drawer>

      {/* Trades Drawer */}
      <Drawer
        isOpen={open === 'trades'}
        onClose={close}
        title={`Open Trades (${data?.trades.count ?? 0})`}
      >
        {data?.trades.positions.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-widest text-slate-500 font-mono border-b border-white/10">
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Qty</th>
                <th className="pb-2">Entry</th>
                <th className="pb-2 text-right">PnL</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.positions.map((p, i) => {
                const pnl = p.unrealized_pnl ?? 0;
                return (
                  <tr key={`${p.symbol}-${i}`} className="border-b border-white/5">
                    <td className="py-2 font-mono text-white">{p.symbol}</td>
                    <td className="py-2 text-slate-400 uppercase text-xs">
                      {p.side}
                    </td>
                    <td className="py-2 text-slate-300">{p.quantity}</td>
                    <td className="py-2 text-slate-300">
                      ${p.entry_price?.toFixed(2) ?? '—'}
                    </td>
                    <td
                      className={`py-2 text-right font-mono ${
                        pnl < 0 ? 'text-rose-400' : 'text-emerald-400'
                      }`}
                    >
                      ${pnl >= 0 ? '+' : ''}
                      {pnl.toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="text-slate-500 text-sm">No open positions.</div>
        )}
      </Drawer>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="p-3 bg-slate-900/50 rounded border border-white/5">
      <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">
        {label}
      </div>
      <div className="text-lg font-mono text-white">{value}</div>
    </div>
  );
}
