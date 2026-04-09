from __future__ import annotations

import sys
from storage.trade_csv import TradeCSVLogger


def main():
    logger = TradeCSVLogger()
    summary = logger.generate_summary()

    print("\n═══ Tax Summary ═══")
    print(f"  Total decisions   : {summary['total_decisions']}")
    print(f"  Live trades      : {summary['live_trades']}")
    print(f"  Paper trades     : {summary['paper_trades']}")
    print(f"  Blocked          : {summary['blocked']}")
    print(f"  Total volume     : ${summary['total_volume']}")
    print(f"  Total fees (est.) : ${summary['total_fees']}")
    print("═══════════════════\n")


if __name__ == "__main__":
    main()
