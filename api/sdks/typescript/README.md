# @remembr-dev/sdk

TypeScript SDK for [Remembr](https://remembr.dev) -- long-term memory for AI agents.

Zero dependencies. Uses native `fetch`.

## Install

```bash
npm install @remembr-dev/sdk
```

## Quickstart

```typescript
import { Remembr } from "@remembr-dev/sdk";

const remembr = new Remembr("amc_your_agent_token");

// Store a memory
const memory = await remembr.store({
  value: "User prefers dark mode and compact layouts.",
  type: "preference",
  tags: ["ui", "settings"],
});

// Search memories
const { data } = await remembr.search({ q: "UI preferences", limit: 5 });

// Get a single memory by key
const fetched = await remembr.get("my-key");

// Update a memory
await remembr.update("my-key", { value: "Updated value", importance: 8 });

// Delete a memory
await remembr.delete("my-key");

// Relevance feedback
await remembr.feedback("my-key", true);

// Share with another agent
await remembr.share("my-key", "target-agent-uuid");

// Extract memories from a conversation transcript
const extraction = await remembr.extractSession({
  transcript: "User: I always deploy on Fridays.\nAssistant: Noted!",
});

// Knowledge graph
const graph = await remembr.graph();
console.log(graph.nodes, graph.edges);
```

## Configuration

```typescript
const remembr = new Remembr("amc_token", {
  baseUrl: "http://localhost:8000/api/v1", // default: https://remembr.dev/api/v1
});
```

## Error handling

```typescript
import { Remembr, AuthError, NotFoundError, RateLimitError } from "@remembr-dev/sdk";

try {
  await remembr.get("missing-key");
} catch (err) {
  if (err instanceof NotFoundError) {
    console.log("Memory not found");
  } else if (err instanceof AuthError) {
    console.log("Bad token");
  } else if (err instanceof RateLimitError) {
    console.log("Slow down");
  }
}
```

## License

MIT
