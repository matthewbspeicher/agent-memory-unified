import { cn } from '../../lib/utils';

interface Asset {
  id: string;
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  volume24h: number;
  marketCap: number;
}

interface WatchlistTableProps {
  assets: Asset[];
  onTrade: (asset: Asset) => void;
}

export function WatchlistTable({ assets, onTrade }: WatchlistTableProps) {
  const formatPrice = (value: number) => {
    if (value >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
    if (value >= 1) return value.toFixed(4);
    return value.toFixed(6);
  };

  const formatLargeNumber = (value: number) => {
    if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    return `$${value.toLocaleString()}`;
  };

  return (
    <div className="trading-card overflow-x-auto">
      <table className="trading-table">
        <thead>
          <tr>
            <th>Asset</th>
            <th className="text-right">Price</th>
            <th className="text-right">24h Change</th>
            <th className="text-right">Volume</th>
            <th className="text-right">Market Cap</th>
            <th className="text-center">Action</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id}>
              <td>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-trading-elevated flex items-center justify-center">
                    <span className="text-xs font-bold text-text-primary">
                      {asset.symbol.slice(0, 2)}
                    </span>
                  </div>
                  <div>
                    <p className="font-semibold text-text-primary">{asset.symbol}</p>
                    <p className="text-text-muted text-xs">{asset.name}</p>
                  </div>
                </div>
              </td>
              <td className="text-right">
                <span className="trading-price font-semibold">
                  ${formatPrice(asset.price)}
                </span>
              </td>
              <td className="text-right">
                <span
                  className={cn(
                    'trading-price font-medium',
                    asset.change24h >= 0 ? 'trading-gain' : 'trading-loss'
                  )}
                >
                  {asset.change24h >= 0 ? '+' : ''}
                  {asset.change24h.toFixed(2)}%
                </span>
              </td>
              <td className="text-right text-text-secondary text-sm">
                {formatLargeNumber(asset.volume24h)}
              </td>
              <td className="text-right text-text-secondary text-sm">
                {formatLargeNumber(asset.marketCap)}
              </td>
              <td className="text-center">
                <button
                  onClick={() => onTrade(asset)}
                  className="px-4 py-1.5 rounded-lg text-sm font-medium bg-accent/20 text-accent hover:bg-accent/30 transition-colors"
                >
                  Trade
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
