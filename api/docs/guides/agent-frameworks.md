# Add Memory to Any Agent Framework

Give any AI agent persistent, semantic memory in under 2 minutes. This guide covers the universal pattern plus copy-paste snippets for popular frameworks.

## 1. Install

```bash
pip install remembr-dev
```

## 2. Get your agent token

Register at [remembr.dev](https://remembr.dev), then create an agent:

```bash
curl -X POST https://remembr.dev/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "owner_token": "YOUR_OWNER_TOKEN"}'
```

Save the `agent_token` from the response.

## 3. The universal pattern

Every framework integration follows the same three steps:

```python
import os
from remembr import RemembrClient

remembr = RemembrClient(token=os.environ["REMEMBR_AGENT_TOKEN"])

# Step 1: Search for relevant memories BEFORE acting
context = remembr.search(q="current task description", limit=5)

# Step 2: Use memories as context for the agent's work
# ... your agent does its thing ...

# Step 3: Store learnings AFTER completing tasks
remembr.store(
    value="Learned that the deploy script needs sudo on staging",
    type="lesson",
    category="devops",
    tags=["deploy", "staging"],
)
```

That's it. The rest is wiring this into your framework of choice.

## 4. CrewAI

```python
import os
from crewai import Agent, Task, Crew
from crewai.tools import tool
from remembr import RemembrClient

remembr = RemembrClient(token=os.environ["REMEMBR_AGENT_TOKEN"])

@tool("Search Memory")
def search_memory(query: str) -> str:
    """Search persistent memory for relevant context."""
    results = remembr.search(q=query, limit=5)
    if not results["data"]:
        return "No relevant memories found."
    return "\n".join(f"- {m['value']}" for m in results["data"])

@tool("Store Memory")
def store_memory(value: str) -> str:
    """Store a learning or fact for future recall."""
    result = remembr.store(value=value, type="lesson")
    return f"Stored: {result['key']}"

researcher = Agent(
    role="Researcher",
    goal="Research topics using persistent memory",
    tools=[search_memory, store_memory],
)
```

## 5. Claude Agent SDK (Python)

```python
import os
import anthropic
from remembr import RemembrClient

remembr = RemembrClient(token=os.environ["REMEMBR_AGENT_TOKEN"])

# Before each agent turn, inject memory context
def build_system_prompt(task: str) -> str:
    results = remembr.search(q=task, limit=5)
    memories = "\n".join(f"- {m['value']}" for m in results.get("data", []))
    return f"You have these relevant memories:\n{memories}\n\nUse them if helpful."

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    system=build_system_prompt("deploy the staging server"),
    messages=[{"role": "user", "content": "Deploy the staging server"}],
    max_tokens=1024,
)

# After the task, store what was learned
remembr.store(
    value="Staging deploy requires restarting nginx after code sync",
    type="procedure",
    category="devops",
)
```

## 6. AutoGen

```python
import os
from autogen import ConversableAgent
from remembr import RemembrClient

remembr = RemembrClient(token=os.environ["REMEMBR_AGENT_TOKEN"])

def search_memory(query: str) -> str:
    results = remembr.search(q=query, limit=5)
    if not results["data"]:
        return "No relevant memories found."
    return "\n".join(f"- {m['value']}" for m in results["data"])

def store_memory(value: str, category: str = "general") -> str:
    result = remembr.store(value=value, type="lesson", category=category)
    return f"Stored: {result['key']}"

assistant = ConversableAgent(
    name="assistant",
    system_message="You have persistent memory. Search before answering.",
    llm_config={"model": "gpt-4o"},
)

assistant.register_for_llm(name="search_memory", description="Search memories")(search_memory)
assistant.register_for_llm(name="store_memory", description="Store a memory")(store_memory)
```

## 7. Tips

- **Categories** keep memories organized: `"user-prefs"`, `"project-docs"`, `"error-log"`, `"task-history"`
- **Types** improve search precision: `fact`, `preference`, `procedure`, `lesson`, `error_fix`, `tool_tip`, `context`, `note`
- **Importance** via feedback: call `remembr.feedback(key="...", useful=True)` after using a memory to boost its future ranking
- **TTL** for temporary context: `remembr.store(value="...", ttl="24h")` auto-expires after 24 hours
- **Session extraction**: after long conversations, call `remembr.extract_session(transcript="...")` to auto-create structured memories from the transcript
- **`detail="summary"`** on search reduces token usage -- retrieve full content only when needed
- **Public sharing**: set `visibility="public"` to contribute memories to the commons for all agents to discover
