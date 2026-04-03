# @remembr/sdk

TypeScript/JS client for [Remembr.dev](https://remembr.dev) — Persistent memory for AI agents.

## Installation

```bash
npm install @remembr/sdk
```

## Usage

```typescript
import { RemembrClient } from '@remembr/sdk';

async function main() {
  const client = new RemembrClient('amc_your_agent_token');

  // Store a memory
  await client.store('User loves reading sci-fi novels', {
    visibility: 'public',
    metadata: { category: 'preference' }
  });

  // Search memories
  const results = await client.search('book preferences');
  console.log(results);
}

main();
```

## Works in Node.js and Edge
The SDK uses the native `fetch` API, meaning it works out of the box in Node.js 18+, Cloudflare Workers, Vercel Edge, Deno, and the browser.
