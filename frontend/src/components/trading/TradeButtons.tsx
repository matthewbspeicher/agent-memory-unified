import { cn } from '../../lib/utils';

interface TradeButtonsProps {
  onBuy: () => void;
  onSell: () => void;
  disabled?: boolean;
  buyLabel?: string;
  sellLabel?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function TradeButtons({
  onBuy,
  onSell,
  disabled = false,
  buyLabel = 'Buy',
  sellLabel = 'Sell',
  size = 'md',
}: TradeButtonsProps) {
  const sizeClasses = {
    sm: 'px-4 py-2 text-sm',
    md: 'px-6 py-3 text-base',
    lg: 'px-8 py-4 text-lg',
  };

  return (
    <div className="flex gap-4">
      <button
        onClick={onBuy}
        disabled={disabled}
        className={cn(
          'trading-buy-btn font-semibold rounded-lg transition-all',
          sizeClasses[size],
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        {buyLabel}
      </button>
      <button
        onClick={onSell}
        disabled={disabled}
        className={cn(
          'trading-sell-btn font-semibold rounded-lg transition-all',
          sizeClasses[size],
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        {sellLabel}
      </button>
    </div>
  );
}
