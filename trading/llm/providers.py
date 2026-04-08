from abc import ABC, abstractmethod
from typing import Any
from .client import LLMResult, ProviderName

class BaseProvider(ABC):
    name: ProviderName

    @abstractmethod
    async def chat(self, system: str, messages: list[dict[str, str]], **kwargs) -> LLMResult | None:
        pass

    async def complete(self, prompt: str, **kwargs) -> LLMResult | None:
        raise NotImplementedError

    async def embed(self, text: str, **kwargs) -> list[float]:
        raise NotImplementedError

class ProviderRegistry:
    def __init__(self):
        self.providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        self.providers[provider.name] = provider

    def get(self, name: str) -> BaseProvider | None:
        return self.providers.get(name)
