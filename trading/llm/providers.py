import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

logger = logging.getLogger(__name__)

ProviderName = Literal["anthropic", "bedrock", "groq", "ollama", "rule-based"]

if TYPE_CHECKING:
    from anthropic.types import MessageParam
    from openai.types.chat import ChatCompletionMessageParam


def _anthropic_messages(messages: list[dict[str, str]]) -> list["MessageParam"]:
    typed_messages: list["MessageParam"] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "assistant":
            typed_messages.append({"role": "assistant", "content": content})
        else:
            typed_messages.append({"role": "user", "content": content})
    return typed_messages


def _anthropic_message_text(message: Any) -> str:
    from anthropic.types import TextBlock

    parts: list[str] = []
    for block in getattr(message, "content", []):
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "".join(parts).strip()


def _openai_messages(
    system: str, messages: list[dict[str, str]]
) -> list["ChatCompletionMessageParam"]:
    full_messages: list["ChatCompletionMessageParam"] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "assistant":
            full_messages.append({"role": "assistant", "content": content})
        elif role == "developer":
            full_messages.append({"role": "developer", "content": content})
        elif role == "system":
            full_messages.append({"role": "system", "content": content})
        else:
            full_messages.append({"role": "user", "content": content})
    return full_messages


def _openai_message_text(response: Any) -> str:
    content = response.choices[0].message.content
    return content.strip() if content else ""


@dataclass
class LLMResult:
    """Structured result from any LLM provider."""

    text: str
    provider: ProviderName
    model: str
    latency_ms: float = 0.0
    # Token tracking for cost monitoring
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        """Total tokens used (input + output)."""
        if self.input_tokens is not None and self.output_tokens is not None:
            return self.input_tokens + self.output_tokens
        return None


class BaseProvider(ABC):
    name: ProviderName

    @abstractmethod
    async def chat(
        self, system: str, messages: list[dict[str, str]], **kwargs
    ) -> LLMResult | None:
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
            anthropic_messages = _anthropic_messages(
                [{"role": "user", "content": prompt}]
            )
            msg = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=anthropic_messages,
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=_anthropic_message_text(msg),
                provider="anthropic",
                model=self.model,
                latency_ms=round(latency),
                input_tokens=getattr(msg.usage, "input_tokens", None),
                output_tokens=getattr(msg.usage, "output_tokens", None),
            )
        except Exception as exc:
            logger.warning("Anthropic failed: %s", exc)
            return None

    async def chat(
        self, system: str, messages: list[dict[str, str]], **kwargs
    ) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import anthropic
            import time

            start = time.monotonic()
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            anthropic_messages = _anthropic_messages(messages)
            msg = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=anthropic_messages,
            )
            latency = (time.monotonic() - start) * 1000
            return LLMResult(
                text=_anthropic_message_text(msg),
                provider="anthropic",
                model=self.model,
                latency_ms=round(latency),
                input_tokens=getattr(msg.usage, "input_tokens", None),
                output_tokens=getattr(msg.usage, "output_tokens", None),
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
        import importlib

        boto3 = importlib.import_module("boto3")

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

    async def chat(
        self, system: str, messages: list[dict[str, str]], **kwargs
    ) -> LLMResult | None:
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
                modelId="amazon.titan-embed-text-v1", body=body
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
            full_messages = _openai_messages("", [{"role": "user", "content": prompt}])
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=full_messages,
            )
            latency = (time.monotonic() - start) * 1000
            usage = getattr(resp, "usage", None)
            return LLMResult(
                text=_openai_message_text(resp),
                provider="groq",
                model=self.model,
                latency_ms=round(latency),
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None)
                if usage
                else None,
            )
        except Exception as exc:
            logger.warning("Groq failed: %s", exc)
            return None

    async def chat(
        self, system: str, messages: list[dict[str, str]], **kwargs
    ) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import openai
            import time

            start = time.monotonic()
            client = openai.AsyncOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.api_key,
            )
            full_messages = _openai_messages(system, messages)
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=full_messages,
            )
            latency = (time.monotonic() - start) * 1000
            usage = getattr(resp, "usage", None)
            return LLMResult(
                text=_openai_message_text(resp),
                provider="groq",
                model=self.model,
                latency_ms=round(latency),
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None)
                if usage
                else None,
            )
        except Exception as exc:
            logger.warning("Groq chat failed: %s", exc)
            return None


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "llama3.2:3b"
    ):
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
            full_messages = _openai_messages("", [{"role": "user", "content": prompt}])
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=full_messages,
            )
            latency = (time.monotonic() - start) * 1000
            usage = getattr(resp, "usage", None)
            return LLMResult(
                text=_openai_message_text(resp),
                provider="ollama",
                model=self.model,
                latency_ms=round(latency),
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None)
                if usage
                else None,
            )
        except Exception as exc:
            logger.warning("Ollama failed: %s", exc)
            return None

    async def chat(
        self, system: str, messages: list[dict[str, str]], **kwargs
    ) -> LLMResult | None:
        max_tokens = kwargs.get("max_tokens", 500)
        try:
            import openai
            import time

            start = time.monotonic()
            client = openai.AsyncOpenAI(
                base_url=f"{self.base_url}/v1",
                api_key="ollama",
            )
            full_messages = _openai_messages(system, messages)
            resp = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=full_messages,
            )
            latency = (time.monotonic() - start) * 1000
            usage = getattr(resp, "usage", None)
            return LLMResult(
                text=_openai_message_text(resp),
                provider="ollama",
                model=self.model,
                latency_ms=round(latency),
                input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                output_tokens=getattr(usage, "completion_tokens", None)
                if usage
                else None,
            )
        except Exception as exc:
            logger.warning("Ollama chat failed: %s", exc)
            return None

    async def embed(self, text: str, **kwargs) -> list[float]:
        try:
            import openai

            client = openai.AsyncOpenAI(
                base_url=f"{self.base_url}/v1", api_key="ollama"
            )
            resp = await client.embeddings.create(
                input=[text], model="nomic-embed-text"
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.warning(f"Embedding failed with ollama: {e}")
            raise
