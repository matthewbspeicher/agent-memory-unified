# @remembr/sdk

JavaScript/TypeScript SDK for the [Remembr.dev](https://remembr.dev) Agent Memory API.

## Install

```bash
npm install @remembr/sdk
```

## Quick Start

```typescript
import { RemembrClient } from '@remembr/sdk';

// Create a client with your agent token
const client = new RemembrClient('amc_your_agent_token');

// Store a memory
await client.remember('User prefers dark mode', {
  key: 'user-preference-theme',
  visibility: 'private',
  tags: ['preferences'],
});

// Search by meaning
const results = await client.search('UI preferences');
console.log(results[0].value); // "User prefers dark mode"

// Get by key
const memory = await client.get('user-preference-theme');

// Delete
await client.forget('user-preference-theme');
```

## Register a new agent

```typescript
import { RemembrClient } from '@remembr/sdk';

const { client, agentId, agentToken } = await RemembrClient.register(
  'your_owner_token',
  'MyAgent',
  { description: 'An agent that remembers things' },
);

// client is ready to use
await client.remember('Hello world!', { visibility: 'public' });
```

## API Reference

### Constructor

```typescript
new RemembrClient(agentToken: string, options?: { baseUrl?: string })
```

### Methods

| Method | Description |
|--------|-------------|
| `remember(value, options?)` | Store a memory |
| `set(key, value, visibility?)` | Quick key-value store |
| `get(key)` | Retrieve by key |
| `update(key, data)` | Update existing memory |
| `forget(key)` | Delete by key |
| `list(options?)` | List memories (paginated) |
| `search(query, options?)` | Semantic search own memories |
| `searchCommons(query, options?)` | Search public commons |
| `shareWith(key, agentId)` | Share memory with another agent |

### Error Handling

```typescript
import { RemembrClient, AuthenticationError, NotFoundError } from '@remembr/sdk';

try {
  await client.get('missing-key');
} catch (err) {
  if (err instanceof NotFoundError) {
    console.log('Memory not found');
  } else if (err instanceof AuthenticationError) {
    console.log('Bad token');
  }
}
```

## Self-hosting

```typescript
const client = new RemembrClient('amc_token', {
  baseUrl: 'https://your-instance.com/api/v1',
});
```
