import { useEffect, useState, useRef, useCallback } from 'react';

interface PriceUpdate {
  symbol: string;
  price: number;
  change24h: number;
}

interface UsePriceWebSocketOptions {
  symbols: string[];
  onUpdate?: (update: PriceUpdate) => void;
  interval?: number;
}

export function usePriceWebSocket({
  symbols,
  onUpdate,
  interval = 5000,
}: UsePriceWebSocketOptions) {
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [isConnected, setIsConnected] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const simulatePriceUpdate = useCallback(() => {
    symbols.forEach((symbol) => {
      const basePrice: Record<string, number> = {
        BTC: 73000,
        ETH: 2250,
        SOL: 85,
        ADA: 0.45,
        DOGE: 0.15,
      };

      const base = basePrice[symbol] || 100;
      const volatility = symbol === 'BTC' ? 0.001 : symbol === 'ETH' ? 0.002 : 0.005;
      const change = (Math.random() - 0.5) * 2 * volatility;
      const newPrice = base * (1 + change);

      const update: PriceUpdate = {
        symbol,
        price: newPrice,
        change24h: (Math.random() - 0.5) * 10,
      };

      setPrices((prev) => ({
        ...prev,
        [symbol]: newPrice,
      }));

      onUpdate?.(update);
    });
  }, [symbols, onUpdate]);

  useEffect(() => {
    setIsConnected(true);

    simulatePriceUpdate();

    intervalRef.current = setInterval(simulatePriceUpdate, interval);

    return () => {
      setIsConnected(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [simulatePriceUpdate, interval]);

  return { prices, isConnected };
}
