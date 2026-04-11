import { useEffect, useState, useCallback } from 'react';
import { PriceCard, TradeButtons, AlertCard } from '../components/trading';
import { WatchlistTable } from '../components/trading/WatchlistTable';
import { usePriceWebSocket } from '../hooks/usePriceWebSocket';

interface Asset {
  id: string;
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  volume24h: number;
  marketCap: number;
}

interface TradeAlert {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: string;
}

const INITIAL_ASSETS: Asset[] = [
  { id: 'bitcoin', symbol: 'BTC', name: 'Bitcoin', price: 73123.45, change24h: 2.34, volume24h: 28000000000, marketCap: 1430000000000 },
  { id: 'ethereum', symbol: 'ETH', name: 'Ethereum', price: 2248.67, change24h: -1.23, volume24h: 15000000000, marketCap: 270000000000 },
  { id: 'solana', symbol: 'SOL', name: 'Solana', price: 84.87, change24h: 5.67, volume24h: 3000000000, marketCap: 38000000000 },
  { id: 'cardano', symbol: 'ADA', name: 'Cardano', price: 0.45, change24h: -0.89, volume24h: 500000000, marketCap: 16000000000 },
  { id: 'dogecoin', symbol: 'DOGE', name: 'Dogecoin', price: 0.15, change24h: 3.21, volume24h: 800000000, marketCap: 21000000000 },
];

export default function TradingDashboard() {
  const [assets, setAssets] = useState<Asset[]>(INITIAL_ASSETS);
  const [alerts, setAlerts] = useState<TradeAlert[]>([]);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);

  const { prices, isConnected } = usePriceWebSocket({
    symbols: ['BTC', 'ETH', 'SOL', 'ADA', 'DOGE'],
    onUpdate: (update) => {
      setAssets(prev => prev.map(asset => {
        if (asset.symbol === update.symbol) {
          const priceChange = update.price - asset.price;
          return {
            ...asset,
            price: update.price,
            change24h: asset.change24h + (priceChange / asset.price) * 100,
          };
        }
        return asset;
      }));
    },
  });

  const handleTrade = useCallback((type: 'buy' | 'sell', asset: Asset) => {
    const newAlert: TradeAlert = {
      id: Date.now().toString(),
      type: type === 'buy' ? 'success' : 'warning',
      title: type === 'buy' ? 'Buy Order Placed' : 'Sell Order Placed',
      message: `${type === 'buy' ? 'Bought' : 'Sold'} ${asset.symbol} @ $${asset.price.toLocaleString()}`,
      timestamp: new Date().toLocaleTimeString(),
    };
    setAlerts(prev => [newAlert, ...prev].slice(0, 5));
  }, []);

  const dismissAlert = useCallback((id: string) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
  }, []);

  return (
    <div className="min-h-screen bg-trading-bg p-6">
      <div className="max-w-7xl mx-auto space-y-8">
        <header className="flex items-center justify-between border-b border-trading-border pb-6">
          <div>
            <h1 className="text-3xl font-display font-bold text-text-primary">
              Trading Dashboard
            </h1>
            <p className="text-text-secondary text-sm mt-1">
              Real-time market data • {assets.length} assets tracked
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-gain animate-pulse' : 'bg-loss'}`} />
            <span className={`text-sm font-mono ${isConnected ? 'text-gain' : 'text-loss'}`}>
              {isConnected ? 'Live' : 'Disconnected'}
            </span>
          </div>
        </header>

        {alerts.length > 0 && (
          <div className="space-y-3">
            {alerts.map(alert => (
              <AlertCard
                key={alert.id}
                type={alert.type}
                title={alert.title}
                message={alert.message}
                timestamp={alert.timestamp}
                onDismiss={() => dismissAlert(alert.id)}
              />
            ))}
          </div>
        )}

        <section>
          <h2 className="text-lg font-semibold text-text-primary mb-4">Market Overview</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
            {assets.map(asset => (
              <PriceCard
                key={asset.id}
                symbol={asset.symbol}
                name={asset.name}
                price={prices[asset.symbol] || asset.price}
                change24h={asset.change24h}
                volume24h={asset.volume24h}
                marketCap={asset.marketCap}
                onClick={() => setSelectedAsset(asset)}
              />
            ))}
          </div>
        </section>

        {selectedAsset && (
          <section className="trading-card">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-semibold text-text-primary">
                  Trade {selectedAsset.symbol}
                </h2>
                <p className="text-text-secondary">
                  Current Price: ${prices[selectedAsset.symbol] || selectedAsset.price.toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => setSelectedAsset(null)}
                className="text-text-muted hover:text-text-primary"
              >
                ✕
              </button>
            </div>
            <TradeButtons
              onBuy={() => handleTrade('buy', selectedAsset)}
              onSell={() => handleTrade('sell', selectedAsset)}
              size="lg"
              buyLabel={`Buy ${selectedAsset.symbol}`}
              sellLabel={`Sell ${selectedAsset.symbol}`}
            />
          </section>
        )}

        <section>
          <h2 className="text-lg font-semibold text-text-primary mb-4">Watchlist</h2>
          <WatchlistTable
            assets={assets.map(a => ({
              ...a,
              price: prices[a.symbol] || a.price,
            }))}
            onTrade={(asset) => setSelectedAsset(asset)}
          />
        </section>
      </div>
    </div>
  );
}
