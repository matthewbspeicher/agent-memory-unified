from rules.models import RuleSet, Rule

def create_snapback_ruleset(config: dict) -> RuleSet:
    s = config.get("scalping", {}).get("snapback", {})
    return RuleSet(
        name="Snap-Back Scalper",
        entry_rules=[
            Rule(name="RSI(3) extreme", condition="rsi_below", threshold=s.get("rsi_oversold", 30)),
            Rule(name="Price near VWAP", condition="distance_within_pct", threshold=s.get("distance_threshold_pct", 1.5)),
            Rule(name="Trend alignment (EMA8)", condition="ema_above", threshold=s.get("ema_period", 8)),
            Rule(name="Min Volatility", condition="volatility_above", threshold=s.get("min_volatility_bb_width", 0.02)),
        ]
    )
