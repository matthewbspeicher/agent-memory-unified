import os
from remembr import AgentMemoryClient

# Assuming you set REMEMBR_AGENT_TOKEN in your environment
token = os.environ.get("REMEMBR_AGENT_TOKEN")
if not token:
    raise ValueError("Please set REMEMBR_AGENT_TOKEN")

client = AgentMemoryClient(token=token)

# Store a memory
memory = client.store(
    value="The user prefers Python for scripting.",
    key="user_preference_lang",
    tags=["user", "preferences"],
    ttl="7d"
)
print("Stored memory:", memory.id)

# Search your memories
results = client.search(query="What is the user's preferred language?", limit=3)
print("\nSearch results:")
for r in results:
    print(f"- {r.value} (Score: {r.similarity})")

# List memories with tags
list_results = client.list(tags=["preferences"])
print("\nFiltered by tag:")
for r in list_results.data:
    print(f"- {r.key}: {r.value}")
