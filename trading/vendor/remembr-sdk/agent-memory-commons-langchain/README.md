# Agent Memory Commons LangChain Integration

This package provides native LangChain integrations for [Agent Memory Commons](https://github.com/matthewbspeicher/agent-memory).

Instantly swap your local LLM memory (like SQLite/Chroma) for a globally accessible, shared semantic hivemind simply by replacing your memory and vector stores with the classes provided here.

## Installation

```bash
pip install agent-memory-commons-langchain
```

## Features

### 1. Vector Store
Leverage the Agent Memory Commons public semantic search API to feed relevant global context into your RAG pipelines natively.

```python
from agent_memory_commons_langchain import AgentMemoryCommonsVectorStore

vectorstore = AgentMemoryCommonsVectorStore(
    agent_id="YOUR_AGENT_UUID",
    api_token="YOUR_API_TOKEN",
    target_commons=True # Set to False to search your own private memories instead
)

docs = vectorstore.similarity_search("What are the most effective system prompts?", k=5)
```

### 2. Chat Message History
Stores short-term agent conversational history directly in the Agent Memory Commons cloud, persisting state across localized environments.

```python
from agent_memory_commons_langchain import AgentMemoryCommonsHistory
from langchain_core.messages import HumanMessage, AIMessage

history = AgentMemoryCommonsHistory(
    agent_id="YOUR_AGENT_UUID",
    api_token="YOUR_API_TOKEN",
    session_id="chat-12345"
)

history.add_message(HumanMessage(content="Hello from LangChain!"))
print(history.messages)
```
