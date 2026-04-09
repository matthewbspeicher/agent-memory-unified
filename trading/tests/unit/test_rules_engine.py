from rules.models import Rule
from rules.engine import RulesEngine

def test_volatility_above_rule():
    engine = RulesEngine()
    rule = Rule(name="Vol High", condition="volatility_above", threshold=0.05)
    data = {"bb_width_pct": 0.06}
    result = engine._evaluate_rule(rule, data)
    assert result.passed is True

def test_distance_within_pct_rule():
    engine = RulesEngine()
    rule = Rule(name="Near VWAP", condition="distance_within_pct", threshold=1.5)
    data = {"price": 101, "vwap": 100} # 1% distance
    result = engine._evaluate_rule(rule, data)
    assert result.passed is True
