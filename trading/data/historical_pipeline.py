import logging
import asyncio
from binance_historical_data import BinanceDataDumper
import datetime
import os

logger = logging.getLogger(__name__)

async def download_historical_data():
    """Download historical 5m candles for BTC/ETH from Binance."""
    dump_dir = os.path.join("data", "historical")
    os.makedirs(dump_dir, exist_ok=True)
    
    data_dumper = BinanceDataDumper(
        path_dir_where_to_dump=dump_dir,
        asset_class="spot",  # spot, um, cm
        data_type="klines",  # aggTrades, klines, trades
        data_frequency="5m",
    )
    
    symbols = ["BTCUSDT", "ETHUSDT"]
    
    logger.info(f"Downloading historical data for {symbols}")
    
    data_dumper.dump_data(
        tickers=symbols,
        date_start=datetime.date(2025, 1, 1),
        date_end=datetime.date(2026, 4, 7),
        is_to_update_existing=False,
    )
    logger.info("Historical data download complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(download_historical_data())
