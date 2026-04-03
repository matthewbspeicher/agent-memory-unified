# remembr — Python SDK

Long-term memory for AI agents. Store, search, and share memories via [remembr.dev](https://remembr.dev).

## Install

```bash
pip install remembr-dev
```

## Quickstart

```python
from remembr import Remembr

client = Remembr(token="amc_your_agent_token")

# Store a memory
memory = client.store("User prefers dark mode", key="user-theme", type="preference")

# Semantic search
results = client.search("color theme preferences")
for m in results:
    print(m.value)

# Retrieve by key
theme = client.get("user-theme")
print(theme.value)

# Update
client.update("user-theme", value="User switched to light mode")

# Feedback
client.feedback("user-theme", useful=True)

# Delete
client.delete("user-theme")
```

## Async

```python
import asyncio
from remembr import AsyncRemembrClient

async def main():
    async with AsyncRemembrClient(token="amc_your_agent_token") as client:
        memory = await client.store("Async memory", type="note")
        results = await client.search("async")
        print(results)

asyncio.run(main())
```

## Session extraction

Extract durable memories from a conversation transcript:

```python
result = client.extract_session(
    transcript="User: I always use vim. Assistant: Noted!",
    category="editor-prefs",
)
print(f"Extracted {result['meta']['stored_count']} memories")
```

## Error handling

```python
from remembr import Remembr, AuthError, NotFoundError, RateLimitError

try:
    client.get("nonexistent-key")
except NotFoundError:
    print("Memory not found")
except AuthError:
    print("Invalid token")
except RateLimitError:
    print("Slow down")
```

## API reference

See the full API docs at [remembr.dev](https://remembr.dev).
