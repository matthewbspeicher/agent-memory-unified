from __future__ import annotations

from typing import Any

_decorated_strategies: list[tuple[str, type, dict[str, Any]]] = []


def strategy(
    name: str,
    description: str = "",
    timeout: float = 120.0,
    default_params: dict[str, Any] | None = None,
):
    def decorator(cls: type) -> type:
        cls._strategy_name = name
        cls._strategy_description = description
        cls._strategy_timeout = timeout
        cls._strategy_default_params = default_params or {}

        _decorated_strategies.append(
            (
                name,
                cls,
                {
                    "description": description,
                    "timeout": timeout,
                    "default_params": default_params,
                },
            )
        )

        return cls

    return decorator


def register_decorated_strategies() -> None:
    from agents.config import register_strategy

    for name, cls, _metadata in _decorated_strategies:
        register_strategy(name, cls)
