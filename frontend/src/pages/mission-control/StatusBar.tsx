import { MissionControlStatus } from '../../lib/api/missionControl';
import { Activity, Bot, Briefcase, Radio, TrendingUp } from 'lucide-react';

interface StatusBarProps {
  data: MissionControlStatus | undefined;
}

function KpiTile({
  icon: Icon,
  label,
  value,
  subtext,
  tone,
}: {
  icon: any;
  label: string;
  value: string;
  subtext?: string;
  tone: 'cyan' | 'emerald' | 'violet' | 'rose' | 'amber';
}) {
  const ring = {
    cyan: 'border-cyan-500/40 shadow-[0_0_20px_rgba(34,211,238,0.15)]',
    emerald: 'border-emerald-500/40 shadow-[0_0_20px_rgba(52,211,153,0.15)]',
    violet: 'border-violet-500/40 shadow-[0_0_20px_rgba(167,139,250,0.15)]',
    rose: 'border-rose-500/40 shadow-[0_0_20px_rgba(244,63,94,0.15)]',
    amber: 'border-amber-500/40 shadow-[0_0_20px_rgba(251,191,36,0.15)]',
  };
  const accent = {
    cyan: 'text-cyan-400',
    emerald: 'text-emerald-400',
    violet: 'text-violet-400',
    rose: 'text-rose-400',
    amber: 'text-amber-400',
  };

  return (
    <div
      className={`flex items-center gap-4 p-4 bg-slate-950/60 backdrop-blur border rounded-xl ${ring[tone]}`}
    >
      <Icon className={`w-6 h-6 ${accent[tone]}`} />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">
          {label}
        </div>
        <div className={`text-2xl font-bold font-mono ${accent[tone]} truncate`}>
          {value}
        </div>
        {subtext && (
          <div className="text-xs text-slate-400 truncate">{subtext}</div>
        )}
      </div>
    </div>
  );
}

export function StatusBar({ data }: StatusBarProps) {
  const kpis = data?.kpis;
  const systemHealthy = kpis?.system_status === 'healthy';

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
      <KpiTile
        icon={Activity}
        label="System"
        value={systemHealthy ? 'OPERATIONAL' : 'DEGRADED'}
        subtext={data ? `${data.infra.services.length} services` : 'loading...'}
        tone={systemHealthy ? 'emerald' : 'rose'}
      />
      <KpiTile
        icon={Bot}
        label="Agents"
        value={
          kpis
            ? `${kpis.agents_active}/${kpis.agents_total}`
            : '—/—'
        }
        subtext="running / total"
        tone="cyan"
      />
      <KpiTile
        icon={Briefcase}
        label="Open Trades"
        value={kpis ? String(kpis.open_trades) : '—'}
        subtext={
          kpis
            ? `$${kpis.unrealized_pnl >= 0 ? '+' : ''}${kpis.unrealized_pnl.toFixed(2)} PnL`
            : undefined
        }
        tone={
          kpis && kpis.unrealized_pnl < 0 ? 'rose' : 'violet'
        }
      />
      <KpiTile
        icon={Radio}
        label="Validator"
        value={kpis?.validator_enabled ? 'ONLINE' : 'DISABLED'}
        subtext={
          data?.validator?.scheduler
            ? `${data.validator.scheduler.windows_collected} windows`
            : undefined
        }
        tone={kpis?.validator_enabled ? 'emerald' : 'amber'}
      />
      <KpiTile
        icon={TrendingUp}
        label="Daily PnL"
        value={
          kpis
            ? `$${kpis.unrealized_pnl >= 0 ? '+' : ''}${kpis.unrealized_pnl.toFixed(2)}`
            : '$—'
        }
        subtext="unrealized"
        tone={kpis && kpis.unrealized_pnl < 0 ? 'rose' : 'emerald'}
      />
    </div>
  );
}
