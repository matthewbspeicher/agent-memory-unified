import sys
import json
from typing import List

def detect_regime(prices: List[float]):
    """
    Simple regime detection based on returns and volatility.
    In a real system, this would use ATR, ADX, and volume.
    """
    if len(prices) < 2:
        return "unknown"
        
    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
    avg_return = sum(returns) / len(returns)
    volatility = (sum((r - avg_return)**2 for r in returns) / len(returns))**0.5
    
    # Simple heuristic thresholds
    is_trending = abs(avg_return) > 0.001
    is_volatile = volatility > 0.01
    
    if is_trending:
        if avg_return > 0:
            return "trending_bull" if not is_volatile else "volatile_uptrend"
        else:
            return "trending_bear" if not is_volatile else "volatile_downtrend"
    else:
        return "quiet_range" if not is_volatile else "volatile_range"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 regime_detector.py <json_price_list>")
        sys.exit(1)
        
    try:
        prices = json.loads(sys.argv[1])
        regime = detect_regime(prices)
        print(json.dumps({"regime": regime}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
