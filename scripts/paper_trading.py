#!/usr/bin/env python3
"""Paper Trading - Simulated trading without real money"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float
    status: OrderStatus
    timestamp: datetime
    filled_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    commission: float = 0.0


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    entry_time: datetime
    last_update: datetime


@dataclass
class Portfolio:
    cash: float
    initial_capital: float
    positions: Dict[str, Position]
    orders: List[Order]
    total_pnl: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int


class PaperTrader:
    COMMISSION_RATE = 0.001

    def __init__(self, initial_capital: float = 100000.0):
        self.portfolio = Portfolio(
            cash=initial_capital,
            initial_capital=initial_capital,
            positions={},
            orders=[],
            total_pnl=0.0,
            win_rate=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
        )
        self.order_counter = 0
        self.trade_history = []

    def generate_order_id(self) -> str:
        self.order_counter += 1
        return f"ORD-{self.order_counter:06d}"

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float,
    ) -> Order:
        order = Order(
            id=self.generate_order_id(),
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            timestamp=datetime.now(),
        )

        if order_type == OrderType.MARKET:
            order = self._fill_order(order, price)

        self.portfolio.orders.append(order)
        return order

    def _fill_order(self, order: Order, market_price: float) -> Order:
        fill_price = market_price
        commission = fill_price * order.quantity * self.COMMISSION_RATE

        order.filled_price = fill_price
        order.filled_quantity = order.quantity
        order.commission = commission
        order.status = OrderStatus.FILLED

        total_cost = fill_price * order.quantity + commission

        if order.side == OrderSide.BUY:
            if self.portfolio.cash < total_cost:
                order.status = OrderStatus.CANCELLED
                return order

            self.portfolio.cash -= total_cost

            if order.symbol in self.portfolio.positions:
                pos = self.portfolio.positions[order.symbol]
                total_qty = pos.quantity + order.quantity
                pos.avg_entry_price = (
                    pos.avg_entry_price * pos.quantity + fill_price * order.quantity
                ) / total_qty
                pos.quantity = total_qty
                pos.last_update = datetime.now()
            else:
                self.portfolio.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    entry_time=datetime.now(),
                    last_update=datetime.now(),
                )

        elif order.side == OrderSide.SELL:
            if order.symbol not in self.portfolio.positions:
                order.status = OrderStatus.CANCELLED
                return order

            pos = self.portfolio.positions[order.symbol]
            if pos.quantity < order.quantity:
                order.status = OrderStatus.CANCELLED
                return order

            proceeds = fill_price * order.quantity - commission
            self.portfolio.cash += proceeds

            cost_basis = pos.avg_entry_price * order.quantity
            pnl = proceeds - cost_basis

            pos.realized_pnl += pnl
            pos.quantity -= order.quantity
            pos.last_update = datetime.now()

            if pos.quantity == 0:
                del self.portfolio.positions[order.symbol]

            self.portfolio.total_trades += 1
            if pnl > 0:
                self.portfolio.winning_trades += 1
            else:
                self.portfolio.losing_trades += 1

            self.trade_history.append(
                {
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "quantity": order.quantity,
                    "entry_price": pos.avg_entry_price,
                    "exit_price": fill_price,
                    "pnl": pnl,
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return order

    def update_prices(self, prices: Dict[str, float]):
        for symbol, price in prices.items():
            if symbol in self.portfolio.positions:
                pos = self.portfolio.positions[symbol]
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.avg_entry_price) * pos.quantity
                pos.last_update = datetime.now()

        self.portfolio.total_pnl = sum(
            pos.unrealized_pnl + pos.realized_pnl
            for pos in self.portfolio.positions.values()
        )

        if self.portfolio.total_trades > 0:
            self.portfolio.win_rate = (
                self.portfolio.winning_trades / self.portfolio.total_trades * 100
            )

    def get_portfolio_summary(self) -> Dict:
        positions_value = sum(
            pos.current_price * pos.quantity
            for pos in self.portfolio.positions.values()
        )

        total_value = self.portfolio.cash + positions_value
        total_return = (
            (total_value - self.portfolio.initial_capital)
            / self.portfolio.initial_capital
            * 100
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "initial_capital": self.portfolio.initial_capital,
            "cash": self.portfolio.cash,
            "positions_value": positions_value,
            "total_value": total_value,
            "total_pnl": self.portfolio.total_pnl,
            "total_return_pct": total_return,
            "total_trades": self.portfolio.total_trades,
            "winning_trades": self.portfolio.winning_trades,
            "losing_trades": self.portfolio.losing_trades,
            "win_rate": self.portfolio.win_rate,
            "open_positions": len(self.portfolio.positions),
            "positions": {
                symbol: {
                    "quantity": pos.quantity,
                    "avg_entry": pos.avg_entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_pct": (
                        (pos.current_price - pos.avg_entry_price)
                        / pos.avg_entry_price
                        * 100
                    ),
                }
                for symbol, pos in self.portfolio.positions.items()
            },
        }

    def execute_signal(self, signal: Dict) -> Optional[Order]:
        symbol = signal.get("symbol")
        signal_type = signal.get("signal")
        price = signal.get("entry_price")
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")

        if not all([symbol, signal_type, price]):
            return None

        if signal_type in ["STRONG_BUY", "BUY"]:
            position_size = self.portfolio.cash * 0.1
            quantity = position_size / price

            order = self.place_order(
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                price=price,
            )

            if stop_loss:
                self.place_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.STOP_LOSS,
                    quantity=quantity,
                    price=stop_loss,
                )

            if take_profit:
                self.place_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.TAKE_PROFIT,
                    quantity=quantity,
                    price=take_profit,
                )

            return order

        elif signal_type in ["STRONG_SELL", "SELL"]:
            if symbol in self.portfolio.positions:
                pos = self.portfolio.positions[symbol]
                order = self.place_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=pos.quantity,
                    price=price,
                )
                return order

        return None


def format_portfolio_report(summary: Dict) -> str:
    report = f"""
{"=" * 70}
📊 PAPER TRADING PORTFOLIO SUMMARY
{"=" * 70}

Timestamp: {summary["timestamp"]}

💰 Account Summary:
   Initial Capital: ${summary["initial_capital"]:,.2f}
   Cash Balance: ${summary["cash"]:,.2f}
   Positions Value: ${summary["positions_value"]:,.2f}
   Total Value: ${summary["total_value"]:,.2f}

📈 Performance:
   Total P&L: ${summary["total_pnl"]:+,.2f}
   Total Return: {summary["total_return_pct"]:+.2f}%

📊 Trading Statistics:
   Total Trades: {summary["total_trades"]}
   Winning Trades: {summary["winning_trades"]}
   Losing Trades: {summary["losing_trades"]}
   Win Rate: {summary["win_rate"]:.1f}%

{"=" * 70}
📋 OPEN POSITIONS
{"=" * 70}
"""

    if summary["positions"]:
        for symbol, pos in summary["positions"].items():
            pnl_emoji = "🟢" if pos["unrealized_pnl"] >= 0 else "🔴"
            report += f"""
{pnl_emoji} {symbol}
   Quantity: {pos["quantity"]:.6f}
   Avg Entry: ${pos["avg_entry"]:,.2f}
   Current: ${pos["current_price"]:,.2f}
   Unrealized P&L: ${pos["unrealized_pnl"]:+,.2f} ({pos["unrealized_pnl_pct"]:+.2f}%)
"""
    else:
        report += "\n   No open positions\n"

    return report


def main():
    print("=" * 70)
    print("📊 PAPER TRADING SYSTEM - ENHANCED")
    print("=" * 70)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    trader = PaperTrader(initial_capital=100000.0)

    print("\n💰 Initial Capital: $100,000.00")

    print("\n📊 Loading enhanced signals...")
    try:
        with open("/opt/agent-memory-unified/data/enhanced_signals.json", "r") as f:
            data = json.load(f)
            signals = data.get("signals", [])
    except FileNotFoundError:
        print("⚠️ No enhanced signals found. Run enhanced_integrated_signal.py first.")
        signals = []

    if signals:
        print(f"\n📋 Found {len(signals)} signals to process")

        buy_signals = [
            s
            for s in signals
            if s.get("action") == "BUY" and s.get("confidence", 0) > 50
        ]
        sell_signals = [
            s
            for s in signals
            if s.get("action") == "SELL" and s.get("confidence", 0) > 50
        ]

        print(f"   Buy signals: {len(buy_signals)}")
        print(f"   Sell signals: {len(sell_signals)}")

        for signal in signals:
            symbol = signal.get("symbol", "")
            action = signal.get("action", "")
            confidence = signal.get("confidence", 0)
            price = signal.get("price", 0)

            if not all([symbol, action, price]):
                continue

            print(f"\n{'─' * 50}")
            print(
                f"Processing: {symbol} - {signal.get('signal', 'N/A')} (Confidence: {confidence:.1f}%)"
            )

            if action == "BUY" and confidence > 50:
                position_size = trader.portfolio.cash * min(0.15, confidence / 500)
                quantity = position_size / price

                order = trader.place_order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    price=price,
                )

                if order.status.value == "FILLED":
                    print(f"✅ BUY {quantity:.6f} {symbol} @ ${price:,.2f}")
                else:
                    print(f"❌ Order failed: {order.status.value}")

            elif action == "SELL" and symbol in trader.portfolio.positions:
                pos = trader.portfolio.positions[symbol]
                order = trader.place_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=pos.quantity,
                    price=price,
                )

                if order.status.value == "FILLED":
                    print(f"✅ SELL {pos.quantity:.6f} {symbol} @ ${price:,.2f}")
                else:
                    print(f"❌ Order failed: {order.status.value}")

            else:
                print(f"⏭️ Skipped (confidence too low or no action)")

    print("\n" + "=" * 70)
    print("📈 SIMULATING PRICE MOVEMENTS")
    print("=" * 70)

    simulated_prices = {
        "BTC": 73028.0 * 0.99,
        "ETH": 2245.57 * 0.98,
        "SOL": 84.82 * 1.01,
        "BNB": 607.48 * 1.005,
        "XRP": 1.35 * 0.99,
        "DOGE": 0.09 * 1.02,
        "ADA": 0.25 * 0.98,
    }

    trader.update_prices(simulated_prices)

    for symbol, price in simulated_prices.items():
        print(f"   {symbol}: ${price:,.4f}")

    summary = trader.get_portfolio_summary()
    print(format_portfolio_report(summary))

    output_file = "/opt/agent-memory-unified/data/paper_trading.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")

    print("\n" + "=" * 70)
    print("✅ Paper trading session complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
