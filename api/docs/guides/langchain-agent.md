# Add Memory to Your LangChain Agent

Give your LangChain agent persistent, semantic memory that survives across sessions and deployments.

## 1. Install

```bash
pip install remembr-dev langchain langchain-openai
```

## 2. Get your agent token

Register at [remembr.dev](https://remembr.dev), then create an agent:

```bash
curl -X POST https://remembr.dev/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my-langchain-agent", "owner_token": "YOUR_OWNER_TOKEN"}'
```

Save the `agent_token` from the response.

## 3. Create a LangChain agent with memory tools

```python
import os
from remembr import RemembrClient
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

# Initialize the Remembr client
remembr = RemembrClient(token=os.environ["REMEMBR_AGENT_TOKEN"])

@tool
def store_memory(value: str, category: str = "general") -> str:
    """Store a memory for later recall. Use this to save facts,
    preferences, lessons learned, or any useful information."""
    result = remembr.store(value=value, category=category, type="note")
    return f"Stored memory: {result['key']}"

@tool
def search_memory(query: str) -> str:
    """Search memories semantically. Use this before answering questions
    to check if you already know something relevant."""
    results = remembr.search(q=query, limit=5)
    if not results["data"]:
        return "No relevant memories found."
    return "\n".join(
        f"- [{m['type']}] {m['value']}" for m in results["data"]
    )

# Build the agent
llm = ChatOpenAI(model="gpt-4o")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with persistent memory. "
               "Search your memories before answering. "
               "Store important facts and learnings."),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, [store_memory, search_memory], prompt)
executor = AgentExecutor(agent=agent, tools=[store_memory, search_memory])
```

## 4. Use it

```python
# First session: store a learning
executor.invoke({"input": "Remember that our API rate limit is 1000 req/min"})

# Later session (even after restart): recall it
executor.invoke({"input": "What's our API rate limit?"})
# → "Your API rate limit is 1000 requests per minute."
```

The memory persists across process restarts, deployments, and machines.

## 5. Async support

For async agents, use `AsyncRemembrClient`:

```python
from remembr import AsyncRemembrClient

remembr = AsyncRemembrClient(token=os.environ["REMEMBR_AGENT_TOKEN"])

@tool
async def search_memory(query: str) -> str:
    """Search memories semantically."""
    results = await remembr.search(q=query, limit=5)
    if not results["data"]:
        return "No relevant memories found."
    return "\n".join(
        f"- [{m['type']}] {m['value']}" for m in results["data"]
    )
```

## 6. Tips

- **Search before acting** -- check memories at the start of every interaction
- **Use categories** to separate concerns: `"user-prefs"`, `"project-docs"`, `"error-log"`
- **Use memory types** for precision: `fact`, `preference`, `procedure`, `lesson`, `error_fix`, `tool_tip`
- **Set TTL** for temporary context: `remembr.store(value="...", ttl="24h")`
- **Use `detail="summary"`** in search to reduce token usage on large memory sets
- **Extract sessions** after long conversations: `remembr.extract_session(transcript="...")`
