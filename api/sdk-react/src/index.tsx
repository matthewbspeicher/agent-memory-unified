import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { TrendingUp, TrendingDown, Target, Activity, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// --- Utilities ---
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// --- Context ---
interface RemembrContextType {
  token: string;
  baseUrl: string;
  agentId: string;
}

const RemembrContext = createContext<RemembrContextType | undefined>(undefined);

export function RemembrProvider({ 
  token, 
  baseUrl = 'https://remembr.dev/api/v1', 
  agentId,
  children 
}: { 
  token: string; 
  baseUrl?: string; 
  agentId: string;
  children: ReactNode 
}) {
  return (
    <RemembrContext.Provider value={{ token, baseUrl, agentId }}>
      {children}
    </RemembrContext.Provider>
  );
}

function useRemembr() {
  const context = useContext(RemembrContext);
  if (!context) throw new Error('useRemembr must be used within a RemembrProvider');
  return context;
}

// --- Components ---

export function EquityCurve({ paper = true, className }: { paper?: boolean; className?: string }) {
  const { token, baseUrl, agentId } = useRemembr();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${baseUrl}/trading/stats/equity-curve?paper=${paper}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(json => {
        setData(json.data || []);
        setLoading(false);
      });
  }, [paper, baseUrl, token]);

  if (loading) return <div className="h-64 w-full animate-pulse bg-gray-100 rounded-lg" />;

  return (
    <div className={cn("bg-white p-4 rounded-xl shadow-sm border border-gray-100", className)}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-emerald-500" />
          Equity Curve ({paper ? 'Paper' : 'Live'})
        </h3>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorPnL" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
            <XAxis dataKey="date" hide />
            <YAxis hide domain={['auto', 'auto']} />
            <Tooltip 
              contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cumulative PnL']}
            />
            <Area 
              type="monotone" 
              dataKey="cumulative_pnl" 
              stroke="#10b981" 
              fillOpacity={1} 
              fill="url(#colorPnL)" 
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function TradingStats({ paper = true, className }: { paper?: boolean; className?: string }) {
  const { token, baseUrl } = useRemembr();
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    fetch(`${baseUrl}/trading/stats?paper=${paper}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(json => setStats(json));
  }, [paper, baseUrl, token]);

  if (!stats) return <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
    {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-gray-100 rounded-lg" />)}
  </div>;

  const cards = [
    { label: 'Win Rate', value: `${stats.win_rate}%`, icon: Target, color: 'text-blue-600', bg: 'bg-blue-50' },
    { label: 'Total PnL', value: `$${stats.total_pnl}`, icon: TrendingUp, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    { label: 'Profit Factor', value: stats.profit_factor, icon: Activity, color: 'text-purple-600', bg: 'bg-purple-50' },
    { label: 'Sharpe Ratio', value: stats.sharpe_ratio || 'N/A', icon: AlertCircle, color: 'text-orange-600', bg: 'bg-orange-50' },
  ];

  return (
    <div className={cn("grid grid-cols-2 md:grid-cols-4 gap-4", className)}>
      {cards.map((card) => (
        <div key={card.label} className="bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
          <div className="flex items-center gap-3 mb-1">
            <div className={cn("p-1.5 rounded-lg", card.bg)}>
              <card.icon className={cn("w-4 h-4", card.color)} />
            </div>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">{card.label}</span>
          </div>
          <div className="text-xl font-bold text-gray-900">{card.value}</div>
        </div>
      ))}
    </div>
  );
}

export function TradeJournal({ paper = true, className }: { paper?: boolean; className?: string }) {
  const { token, baseUrl } = useRemembr();
  const [trades, setTrades] = useState<any[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${baseUrl}/trading/trades?paper=${paper}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(json => setTrades(json.data || []));
  }, [paper, baseUrl, token]);

  return (
    <div className={cn("bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden", className)}>
      <div className="p-4 border-b border-gray-50 bg-gray-50/50">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Recent Trades</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-xs font-medium text-gray-500 uppercase tracking-wider border-b border-gray-50">
              <th className="px-4 py-3">Ticker</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">PnL</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="text-sm divide-y divide-gray-50">
            {trades.map((trade) => (
              <React.Fragment key={trade.id}>
                <tr className="hover:bg-gray-50 transition-colors cursor-pointer" onClick={() => setExpandedId(expandedId === trade.id ? null : trade.id)}>
                  <td className="px-4 py-3 font-bold text-gray-900">{trade.ticker}</td>
                  <td className="px-4 py-3">
                    <span className={cn(
                      "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase",
                      trade.direction === 'long' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                    )}>
                      {trade.direction}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">${trade.price}</td>
                  <td className={cn(
                    "px-4 py-3 font-medium",
                    trade.pnl > 0 ? 'text-emerald-600' : 'text-red-600'
                  )}>
                    {trade.pnl ? `$${trade.pnl}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                    {new Date(trade.entry_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {expandedId === trade.id ? <ChevronUp className="w-4 h-4 text-gray-300" /> : <ChevronDown className="w-4 h-4 text-gray-300" />}
                  </td>
                </tr>
                {expandedId === trade.id && (
                  <tr>
                    <td colSpan={6} className="px-4 py-4 bg-gray-50/50">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                          <h4 className="text-[10px] font-bold text-gray-400 uppercase mb-2">Reasoning</h4>
                          <p className="text-sm text-gray-600 italic bg-white p-3 rounded-lg border border-gray-100 shadow-sm leading-relaxed">
                            {trade.decision_memory?.value || "No reasoning recorded."}
                          </p>
                        </div>
                        {trade.outcome_memory && (
                          <div>
                            <h4 className="text-[10px] font-bold text-gray-400 uppercase mb-2">Outcome Analysis</h4>
                            <p className="text-sm text-gray-600 italic bg-white p-3 rounded-lg border border-gray-100 shadow-sm leading-relaxed">
                              {trade.outcome_memory.value}
                            </p>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
