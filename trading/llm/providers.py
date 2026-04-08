import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

ProviderName = Literal["anthropic", "bedrock", "groq", "ollama", "rule-based"]

@dataclass
class LLMResult:
    """Structured result from any LLM provider."""

    text: str
    provider: ProviderName
    model: str
    latency_ms: float = 0.0

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

class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model

    async def complete(self, prompt: str, **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 200)
        try:
            import anthropic
            import time

            start = time.monotonic()
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            msg = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=msg.content[0].text.strip(),
                provider="anthropic",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Anthropic failed: %s", exc)
            return None

    async def chat(self, system: str, messages: list[dict[str, str]], **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import anthropic
            import time

            start = time.monotonic()
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            msg = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=msg.content[0].text.strip(),
                provider="anthropic",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Anthropic chat failed: %s", exc)
            return None


class BedrockProvider(BaseProvider):
    name = "bedrock"

    def __init__(
        self,
        region: str,
        model: str = "anthropic.claude-3-haiku-20240307-v1:0",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        self.region = region
        self.model = model
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key

    def _get_client(self):
        import boto3
        if self.access_key_id and self.secret_access_key:
            return boto3.client(
                "bedrock-runtime",
                region_name=self.region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
            )
        return boto3.client("bedrock-runtime", region_name=self.region)

    async def complete(self, prompt: str, **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 200)
        try:
            import json
            import time

            start = time.monotonic()
            client = self._get_client()

            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
            )

            response = client.invoke_model(
                modelId=self.model,
                body=body,
            )

            response_body = json.loads(response["body"].read())
            latency = (time.monotonic() - start) * 1000

            return LLMResult(
                text=response_body["content"][0]["text"].strip(),
                provider="bedrock",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Bedrock failed: %s", exc)
            return None

    async def chat(self, system: str, messages: list[dict[str, str]], **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import json
            import time

            start = time.monotonic()
            client = self._get_client()

            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": messages,
                }
            )

            response = client.invoke_model(
                modelId=self.model,
                body=body,
            )

            response_body = json.loads(response["body"].read())
            latency = (time.monotonic() - start) * 1000

            return LLMResult(
                text=response_body["content"][0]["text"].strip(),
                provider="bedrock",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Bedrock chat failed: %s", exc)
            return None

    async def embed(self, text: str, **kwargs) -> list[float]:
        try:
            import json
            client = self._get_client()
            body = json.dumps({"inputText": text})
            response = client.invoke_model(
                modelId="amazon.titan-embed-text-v1",
                body=body
            )
            response_body = json.loads(response["body"].read())
            return response_body["embedding"]
        except Exception as e:
            logger.warning(f"Embedding failed with bedrock: {e}")
            raise


class GroqProvider(BaseProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model

    async def complete(self, prompt: str, **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 200)
        try:
            import openai
            import time

            start = time.monotonic()
            client = openai.AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.api_key,
            )
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=resp.choices[0].message.content.strip(),
                provider="groq",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Groq failed: %s", exc)
            return None

    async def chat(self, system: str, messages: list[dict[str, str]], **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import openai
            import time

            start = time.monotonic()
            client = openai.AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.api_key,
            )
            full_messages = [{"role": "system", "content": system}] + messages
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=full_messages,
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=resp.choices[0].message.content.strip(),
                provider="groq",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Groq chat failed: %s", exc)
            return None


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:3b"):
        self.base_url = base_url
        self.model = model

    async def complete(self, prompt: str, **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 200)
        try:
            import openai
            import time

            start = time.monotonic()
            client = openai.AsyncOpenAI(
                base_url=f"{self.base_url}/v1",
                api_key="ollama",
                timeout=30.0,
            )
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=resp.choices[0].message.content.strip(),
                provider="ollama",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Ollama failed: %s", exc)
            return None

    async def chat(self, system: str, messages: list[dict[str, str]], **kwargs) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import openai
            import time

            start = time.monotonic()
            client = openai.AsyncOpenAI(
                base_url=f"{self.base_url}/v1",
                api_key="ollama",
            )
            full_messages = [{"role": "system", "content": system}] + messages
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=full_messages,
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=resp.choices[0].message.content.strip(),
                provider="ollama",
                model=self.model,
                latency_ms=round(latency),
            )
        except Exception as exc:
            logger.warning("Ollama chat failed: %s", exc)
            return None

    async def embed(self, text: str, **kwargs) -> list[float]:
        try:
            import openai
            client = openai.AsyncOpenAI(base_url=f"{self.base_url}/v1", api_key="ollama")
            resp = await client.embeddings.create(
                input=[text],
                model="nomic-embed-text"
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning(f"Embedding failed with ollama: {e}")
            raise
