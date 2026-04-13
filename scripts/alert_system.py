#!/usr/bin/env python3
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    PRICE_BREAKOUT = "price_breakout"
    VOLUME_SPIKE = "volume_spike"
    RSI_EXTREME = "rsi_extreme"
    WHALE_MOVEMENT = "whale_movement"
    SENTIMENT_SHIFT = "sentiment_shift"
    CORRELATION_BREAK = "correlation_break"
    SIGNAL_CONVERGENCE = "signal_convergence"


@dataclass
class Alert:
    id: str
    timestamp: str
    alert_type: str
    severity: str
    symbol: str
    message: str
    data: Dict
    acknowledged: bool = False


class AlertSystem:
    def __init__(
        self, config_path: str = "/opt/agent-memory-unified/data/alert_config.json"
    ):
        self.config = self._load_config(config_path)
        self.alerts: List[Alert] = []
        self.alert_history: List[Alert] = []
        self.cooldown_tracker: Dict[str, float] = {}

    def _load_config(self, config_path: str) -> Dict:
        default_config = {
            "thresholds": {
                "rsi_overbought": 70,
                "rsi_oversold": 30,
                "volume_spike_multiplier": 2.0,
                "price_change_24h": 5.0,
                "confidence_minimum": 70,
                "whale_threshold_usd": 1000000,
            },
            "cooldowns": {
                "price_breakout": 300,
                "volume_spike": 600,
                "rsi_extreme": 1800,
                "whale_movement": 300,
                "sentiment_shift": 3600,
            },
            "notification_channels": {"console": True, "file": True, "webhook": False},
        }

        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return default_config

    def check_price_breakout(
        self, symbol: str, current_price: float, resistance: float, support: float
    ) -> Optional[Alert]:
        if current_price > resistance * 1.01:
            return self._create_alert(
                AlertType.PRICE_BREAKOUT,
                AlertSeverity.HIGH,
                symbol,
                f"{symbol} broke above resistance at ${resistance:.2f}",
                {
                    "current_price": current_price,
                    "resistance": resistance,
                    "direction": "up",
                },
            )
        elif current_price < support * 0.99:
            return self._create_alert(
                AlertType.PRICE_BREAKOUT,
                AlertSeverity.HIGH,
                symbol,
                f"{symbol} broke below support at ${support:.2f}",
                {
                    "current_price": current_price,
                    "support": support,
                    "direction": "down",
                },
            )
        return None

    def check_volume_spike(
        self, symbol: str, current_volume: float, avg_volume: float
    ) -> Optional[Alert]:
        multiplier = self.config["thresholds"]["volume_spike_multiplier"]
        if current_volume > avg_volume * multiplier:
            return self._create_alert(
                AlertType.VOLUME_SPIKE,
                AlertSeverity.MEDIUM,
                symbol,
                f"{symbol} volume {current_volume / avg_volume:.1f}x above average",
                {
                    "current_volume": current_volume,
                    "avg_volume": avg_volume,
                    "multiplier": current_volume / avg_volume,
                },
            )
        return None

    def check_rsi_extreme(self, symbol: str, rsi: float) -> Optional[Alert]:
        overbought = self.config["thresholds"]["rsi_overbought"]
        oversold = self.config["thresholds"]["rsi_oversold"]

        if rsi > overbought:
            return self._create_alert(
                AlertType.RSI_EXTREME,
                AlertSeverity.MEDIUM,
                symbol,
                f"{symbol} RSI overbought at {rsi:.1f}",
                {"rsi": rsi, "level": "overbought"},
            )
        elif rsi < oversold:
            return self._create_alert(
                AlertType.RSI_EXTREME,
                AlertSeverity.MEDIUM,
                symbol,
                f"{symbol} RSI oversold at {rsi:.1f}",
                {"rsi": rsi, "level": "oversold"},
            )
        return None

    def check_signal_convergence(self, symbol: str, signals: Dict) -> Optional[Alert]:
        buy_signals = sum(1 for s in signals.values() if s.get("signal") == "BUY")
        sell_signals = sum(1 for s in signals.values() if s.get("signal") == "SELL")
        total_signals = len(signals)

        if buy_signals >= total_signals * 0.7:
            return self._create_alert(
                AlertType.SIGNAL_CONVERGENCE,
                AlertSeverity.HIGH,
                symbol,
                f"{symbol} strong BUY convergence ({buy_signals}/{total_signals} signals)",
                {
                    "buy_signals": buy_signals,
                    "sell_signals": sell_signals,
                    "total_signals": total_signals,
                    "direction": "BUY",
                },
            )
        elif sell_signals >= total_signals * 0.7:
            return self._create_alert(
                AlertType.SIGNAL_CONVERGENCE,
                AlertSeverity.HIGH,
                symbol,
                f"{symbol} strong SELL convergence ({sell_signals}/{total_signals} signals)",
                {
                    "buy_signals": buy_signals,
                    "sell_signals": sell_signals,
                    "total_signals": total_signals,
                    "direction": "SELL",
                },
            )
        return None

    def check_whale_movement(
        self, symbol: str, transaction_value: float, direction: str
    ) -> Optional[Alert]:
        threshold = self.config["thresholds"]["whale_threshold_usd"]
        if transaction_value > threshold:
            return self._create_alert(
                AlertType.WHALE_MOVEMENT,
                AlertSeverity.HIGH,
                symbol,
                f"Whale {direction}: ${transaction_value:,.0f} {symbol}",
                {"value_usd": transaction_value, "direction": direction},
            )
        return None

    def check_sentiment_shift(
        self, symbol: str, current_sentiment: float, previous_sentiment: float
    ) -> Optional[Alert]:
        shift = current_sentiment - previous_sentiment
        if abs(shift) > 20:
            direction = "bullish" if shift > 0 else "bearish"
            return self._create_alert(
                AlertType.SENTIMENT_SHIFT,
                AlertSeverity.MEDIUM,
                symbol,
                f"{symbol} sentiment shifted {direction} by {abs(shift):.1f} points",
                {
                    "current": current_sentiment,
                    "previous": previous_sentiment,
                    "shift": shift,
                    "direction": direction,
                },
            )
        return None

    def _create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        symbol: str,
        message: str,
        data: Dict,
    ) -> Optional[Alert]:
        alert_key = f"{alert_type.value}:{symbol}"
        cooldown = self.config["cooldowns"].get(alert_type.value, 300)

        if alert_key in self.cooldown_tracker:
            time_since = time.time() - self.cooldown_tracker[alert_key]
            if time_since < cooldown:
                return None

        alert = Alert(
            id=f"{alert_type.value}_{symbol}_{int(time.time())}",
            timestamp=datetime.now().isoformat(),
            alert_type=alert_type.value,
            severity=severity.value,
            symbol=symbol,
            message=message,
            data=data,
        )

        self.alerts.append(alert)
        self.alert_history.append(alert)
        self.cooldown_tracker[alert_key] = time.time()

        self._notify(alert)
        return alert

    def _notify(self, alert: Alert):
        if self.config["notification_channels"]["console"]:
            severity_emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🚨", "critical": "🔴"}
            emoji = severity_emoji.get(alert.severity, "ℹ️")
            print(f"\n{emoji} [{alert.severity.upper()}] {alert.message}")

        if self.config["notification_channels"]["file"]:
            self._save_alert(alert)

    def _save_alert(self, alert: Alert):
        alert_file = "/opt/agent-memory-unified/data/alerts.json"
        try:
            with open(alert_file, "r") as f:
                alerts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            alerts = []

        alerts.append(asdict(alert))

        with open(alert_file, "w") as f:
            json.dump(alerts[-100:], f, indent=2)

    def get_active_alerts(self, severity: Optional[str] = None) -> List[Alert]:
        if severity:
            return [
                a for a in self.alerts if a.severity == severity and not a.acknowledged
            ]
        return [a for a in self.alerts if not a.acknowledged]

    def acknowledge_alert(self, alert_id: str):
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                break

    def clear_old_alerts(self, max_age_hours: int = 24):
        cutoff = time.time() - (max_age_hours * 3600)
        self.alerts = [
            a
            for a in self.alerts
            if datetime.fromisoformat(a.timestamp).timestamp() > cutoff
        ]

    def get_alert_summary(self) -> Dict:
        return {
            "total_alerts": len(self.alert_history),
            "active_alerts": len(self.get_active_alerts()),
            "by_severity": {
                "low": len([a for a in self.alerts if a.severity == "low"]),
                "medium": len([a for a in self.alerts if a.severity == "medium"]),
                "high": len([a for a in self.alerts if a.severity == "high"]),
                "critical": len([a for a in self.alerts if a.severity == "critical"]),
            },
            "by_type": {
                alert_type: len([a for a in self.alerts if a.alert_type == alert_type])
                for alert_type in set(a.alert_type for a in self.alerts)
            },
        }


def run_alert_demo():
    print("🔔 Alert System Demo")
    print("=" * 60)

    system = AlertSystem()

    test_cases = [
        ("check_rsi_extreme", {"symbol": "BTC", "rsi": 75}),
        ("check_rsi_extreme", {"symbol": "ETH", "rsi": 25}),
        (
            "check_volume_spike",
            {"symbol": "SOL", "current_volume": 5000000, "avg_volume": 1000000},
        ),
        (
            "check_signal_convergence",
            {
                "symbol": "ADA",
                "signals": {
                    "technical": {"signal": "BUY"},
                    "sentiment": {"signal": "BUY"},
                    "whale": {"signal": "BUY"},
                    "momentum": {"signal": "BUY"},
                },
            },
        ),
        (
            "check_whale_movement",
            {"symbol": "BTC", "transaction_value": 5000000, "direction": "deposit"},
        ),
        (
            "check_sentiment_shift",
            {"symbol": "DOGE", "current_sentiment": 75, "previous_sentiment": 40},
        ),
    ]

    for method_name, params in test_cases:
        method = getattr(system, method_name)
        alert = method(**params)
        if alert:
            print(f"  Generated: {alert.alert_type} for {alert.symbol}")

    print("\n📊 Alert Summary:")
    summary = system.get_alert_summary()
    print(f"  Total Alerts: {summary['total_alerts']}")
    print(f"  Active: {summary['active_alerts']}")
    print(f"  By Severity: {summary['by_severity']}")

    return system


if __name__ == "__main__":
    run_alert_demo()
