# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: knowledge_graph.spec.ts >> Knowledge Graph >> should render nodes and edges with metadata
- Location: tests/e2e/knowledge_graph.spec.ts:4:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('canvas')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('canvas')

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - heading "Unexpected Application Error!" [level=2] [ref=e3]
  - heading "404 Not Found" [level=3] [ref=e4]
  - paragraph [ref=e5]: 💿 Hey developer 👋
  - paragraph [ref=e6]:
    - text: You can provide a way better UX than this when your app throws errors by providing your own
    - code [ref=e7]: ErrorBoundary
    - text: or
    - code [ref=e8]: errorElement
    - text: prop on your route.
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Knowledge Graph', () => {
  4  |   test('should render nodes and edges with metadata', async ({ page }) => {
  5  |     // Intercept the API call to return mock graph data with metadata
  6  |     await page.route('**/v1/agents/me/graph', async (route) => {
  7  |       await route.fulfill({
  8  |         status: 200,
  9  |         json: {
  10 |           data: {
  11 |             nodes: [
  12 |               { id: '1', summary: 'Strategy A', type: 'strategy' },
  13 |               { id: '2', summary: 'Observation B', type: 'memory' }
  14 |             ],
  15 |             links: [
  16 |               { source: '1', target: '2', relation: 'supports', metadata: { rationale: 'Observation confirms strategy trend' } }
  17 |             ]
  18 |           }
  19 |         }
  20 |       });
  21 |     });
  22 | 
  23 |     await page.goto('/graph');
  24 | 
  25 |     // Wait for the canvas to render
  26 |     const canvas = page.locator('canvas');
> 27 |     await expect(canvas).toBeVisible();
     |                          ^ Error: expect(locator).toBeVisible() failed
  28 | 
  29 |     // Verify title or key overlay elements
  30 |     await expect(page.locator('text=Neural Mesh')).toBeVisible();
  31 |     await expect(page.locator('text=Observation B')).toBeVisible(); // Mocked node label
  32 |   });
  33 | });
  34 | 
```