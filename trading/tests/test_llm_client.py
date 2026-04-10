from llm.client import LLMResult
from llm.providers import ProviderRegistry, BaseProvider

class DummyProvider(BaseProvider):
    name = "dummy"
    async def chat(self, system: str, messages: list[dict], **kwargs) -> LLMResult | None:
        return LLMResult(text="dummy response", provider="dummy", model="dummy", latency_ms=10)

def test_provider_registry():
    registry = ProviderRegistry()
    registry.register(DummyProvider())
    assert "dummy" in registry.providers
    provider = registry.get("dummy")
    assert provider.name == "dummy"
