from data.sources.base import DataSource
from importlib import import_module


def __getattr__(name: str):
    if name == "BinanceDataSource":
        return import_module("data.sources.binance").BinanceDataSource
    if name == "ExchangeDataSource":
        return import_module("data.sources.exchange_source").ExchangeDataSource
    raise AttributeError(name)


__all__ = ["BinanceDataSource", "ExchangeDataSource", "DataSource"]
