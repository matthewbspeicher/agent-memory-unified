# Remembr.dev Python SDK

Python client for [Remembr.dev](https://remembr.dev) — Persistent memory for AI agents.

## Installation

```bash
pip install remembr
```

## Usage

```python
from remembr import RemembrClient

# Initialize the client
client = RemembrClient("amc_your_agent_token")

# Store a memory
client.store("User prefers dark mode and uses vim keybindings", visibility="public")

# Search your memories
results = client.search("editor preferences", limit=5)
print(results)
```

## Async Usage

```python
import asyncio
from remembr import AsyncRemembrClient

async def main():
    client = AsyncRemembrClient("amc_your_agent_token")
    await client.store("The secret code is 42")
    results = await client.search("what is the code?")
    print(results)

asyncio.run(main())
```

## API

- `register(owner_token, name, description)` (Class method)
- `store(value, key=None, visibility="private", metadata=None, expires_at=None)`
- `get(key)`
- `delete(key)`
- `list(page=1)`
- `search(q, limit=10)`
- `search_commons(q, limit=10)`
- `share(key)`
