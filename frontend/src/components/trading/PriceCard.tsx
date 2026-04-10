import { cn } from '../../lib/utils';

interface PriceCardProps {
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  volume24h?: number;
  marketCap?: number;
  onClick?: () => void;
}

export function PriceCard({
  symbol,
  name,
  price,
  change24h,
  volume24h,
  marketCap,
  onClick,
}: PriceCardProps) {
  const isPositive = change24h >= 0;

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
    <div
      onClick={onClick}
      className={cn(
        'trading-card cursor-pointer group',
        'hover:border-accent/30'
      )}
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-display text-lg font-semibold text-text-primary">
            {symbol}
          </h3>
          <p className="text-text-secondary text-sm">{name}</p>
        </div>
        <div className="text-right">
          <p className="trading-price text-xl font-semibold">
            ${formatPrice(price)}
          </p>
          <p
            className={cn(
              'trading-price text-sm font-medium',
              isPositive ? 'trading-gain' : 'trading-loss'
            )}
          >
            {isPositive ? '+' : ''}
            {change24h.toFixed(2)}%
          </p>
        </div>
      </div>

      {(volume24h || marketCap) && (
        <div className="flex gap-4 text-xs text-text-muted mt-3 pt-3 border-t border-trading-border">
          {volume24h && (
            <div>
              <span className="text-text-secondary">Vol </span>
              {formatLargeNumber(volume24h)}
            </div>
          )}
          {marketCap && (
            <div>
              <span className="text-text-secondary">MCap </span>
              {formatLargeNumber(marketCap)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
