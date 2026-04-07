import sys
import json
import math
import random
from typing import List

def run_monte_carlo(current_price: float, volatility: float, horizon_days: int, simulations: int = 10000):
    """
    Simple Monte Carlo simulation for price paths.
    Assumes GBM (Geometric Brownian Motion) with drift=0 for simplicity.
    """
    dt = 1 / 252  # daily steps
    results = []
    
    for _ in range(simulations):
        price = current_price
        for _ in range(horizon_days):
            # Price change: P * exp((drift - 0.5 * sigma^2) * dt + sigma * sqrt(dt) * Z)
            # Drift = 0 for risk-neutral/conservative audit
            change = math.exp(-0.5 * (volatility**2) * dt + volatility * math.sqrt(dt) * random.gauss(0, 1))
            price *= change
        results.append(price)
    
    results.sort()
    
    # Calculate VaR
    var_95 = current_price - results[int(simulations * 0.05)]
    var_99 = current_price - results[int(simulations * 0.01)]
    
    return {
        "current_price": current_price,
        "mean_end_price": sum(results) / simulations,
        "min_end_price": results[0],
        "max_end_price": results[-1],
        "var_95": var_95,
        "var_99": var_99,
        "var_95_pct": (var_95 / current_price) * 100,
        "var_99_pct": (var_99 / current_price) * 100
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 risk_analysis.py <current_price> <annual_volatility> [horizon_days]")
        sys.exit(1)
        
    price = float(sys.argv[1])
    vol = float(sys.argv[2])
    horizon = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    analysis = run_monte_carlo(price, vol, horizon)
    print(json.dumps(analysis, indent=2))
