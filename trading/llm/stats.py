from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .providers import LLMResult, ProviderName


@dataclass
class ProviderStats:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_latency_ms: float = 0.0
    last_call_at: float | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def success_rate(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.successes / self.calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successes == 0:
            return 0.0
        return self.total_latency_ms / self.successes

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate, 3),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "last_call_at": self.last_call_at,
        }


class LLMStatsCollector:
    def __init__(self) -> None:
        self._providers: dict[ProviderName, ProviderStats] = defaultdict(ProviderStats)
        self._session_start = time.time()
        self._total_calls = 0
        self._total_tokens = 0

    def record_call(self, result: LLMResult, success: bool = True) -> None:
        provider_name = result.provider
        stats = self._providers[provider_name]

        stats.calls += 1
        stats.last_call_at = time.time()

        if success:
            stats.successes += 1
            stats.total_latency_ms += result.latency_ms
        else:
            stats.failures += 1

        if result.input_tokens is not None:
            stats.input_tokens += result.input_tokens
        if result.output_tokens is not None:
            stats.output_tokens += result.output_tokens

        self._total_calls += 1
        if result.total_tokens is not None:
            self._total_tokens += result.total_tokens

    def get_provider_stats(self, provider: ProviderName) -> dict[str, Any]:
        stats = self._providers.get(provider)
        if stats is None:
            return ProviderStats().to_dict()
        return stats.to_dict()

    def get_all_stats(self) -> dict[str, Any]:
        return {
            "session_start": self._session_start,
            "uptime_seconds": round(time.time() - self._session_start),
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "providers": {
                name: self._providers[name].to_dict() for name in self._providers
            },
        }

    def reset(self) -> None:
        self._providers.clear()
        self._session_start = time.time()
        self._total_calls = 0
        self._total_tokens = 0


_stats_collector = LLMStatsCollector()


def get_stats_collector() -> LLMStatsCollector:
    return _stats_collector
