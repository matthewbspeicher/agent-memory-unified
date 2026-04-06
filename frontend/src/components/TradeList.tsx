import type { Trade } from '../lib/api/trading';

interface TradeListProps {
  trades: Trade[];
}

export function TradeList({ trades }: TradeListProps) {
  if (trades.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        No trades yet
      </div>
    );
  }

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-700/50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300">Symbol</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300">Side</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300">Quantity</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300">Entry</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300">P&L</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300">Status</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id} className="border-t border-gray-700 hover:bg-gray-750">
              <td className="px-4 py-3 font-mono text-sm text-gray-100">{trade.ticker}</td>
              <td className="px-4 py-3">
                <span
                  className={`px-2 py-1 rounded text-xs font-medium ${
                    trade.direction === 'long'
                      ? 'bg-green-900/50 text-green-300'
                      : 'bg-red-900/50 text-red-300'
                  }`}
                >
                  {trade.direction}
                </span>
              </td>
              <td className="px-4 py-3 text-right text-sm text-gray-200">{trade.quantity}</td>
              <td className="px-4 py-3 text-right text-sm text-gray-200">${trade.entry_price}</td>
              <td className={`px-4 py-3 text-right text-sm font-medium ${
                trade.pnl && parseFloat(trade.pnl) >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {trade.pnl ? `$${trade.pnl}` : '-'}
              </td>
              <td className="px-4 py-3">
                <span className={`text-xs ${
                  trade.status === 'open' ? 'text-blue-400' : 
                  trade.status === 'closed' ? 'text-gray-400' : 'text-yellow-400'
                }`}>
                  {trade.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
