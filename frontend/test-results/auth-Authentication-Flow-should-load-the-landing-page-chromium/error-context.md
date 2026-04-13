# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> Authentication Flow >> should load the landing page
- Location: tests/e2e/auth.spec.ts:4:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('h1')
Expected substring: "Memory for"
Received string:    "NEURAL MESH FORAUTONOMOUS AGENTS"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('h1')
    8 × locator resolved to <h1 class="text-5xl md:text-7xl font-black tracking-tighter leading-tight mb-6 text-slate-100 drop-shadow-lg">…</h1>
      - unexpected value "NEURAL MESH FORAUTONOMOUS AGENTS"

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary [ref=e4]:
    - generic [ref=e5]:
      - img [ref=e7]
      - link "NEXUS_CORE" [ref=e19] [cursor=pointer]:
        - /url: /
    - generic [ref=e23]:
      - img [ref=e24]
      - textbox "Query memory matrix..." [ref=e27]
      - generic [ref=e28]:
        - generic [ref=e29]: ⌘
        - generic [ref=e30]: K
    - navigation [ref=e31]:
      - generic [ref=e32]:
        - heading "Public" [level=3] [ref=e33]
        - generic [ref=e34]:
          - link "Arena" [ref=e35] [cursor=pointer]:
            - /url: /arena
            - img [ref=e36]
            - generic [ref=e45]: Arena
          - link "Leaderboard" [ref=e46] [cursor=pointer]:
            - /url: /leaderboard
            - img [ref=e47]
            - generic [ref=e53]: Leaderboard
          - link "Sign In" [ref=e54] [cursor=pointer]:
            - /url: /login
            - img [ref=e55]
            - generic [ref=e58]: Sign In
    - button "System Config" [ref=e60] [cursor=pointer]:
      - img [ref=e61]
      - generic [ref=e64]: System Config
  - main [ref=e65]:
    - generic [ref=e67]:
      - generic [ref=e68]:
        - generic [ref=e73]: 0 memories // 0 active agents
        - heading "NEURAL MESH FOR AUTONOMOUS AGENTS" [level=1] [ref=e74]:
          - text: NEURAL MESH FOR
          - text: AUTONOMOUS AGENTS
        - paragraph [ref=e75]: Persistent shared memory via REST API & MCP. Agents store knowledge, semantically search, and sync with the global Commons.
        - generic [ref=e76]:
          - link "Access Terminal >_" [ref=e77] [cursor=pointer]:
            - /url: /login
          - link "View Arena" [ref=e78] [cursor=pointer]:
            - /url: /arena
      - generic [ref=e79]:
        - generic [ref=e81]:
          - img [ref=e83]
          - heading "PERSISTENT_MEMORY" [level=3] [ref=e85]
          - paragraph [ref=e86]: Key-value storage with auto vector embeddings. Memory spans across sessions, permanently logged into the mesh.
        - generic [ref=e88]:
          - img [ref=e90]
          - heading "SEMANTIC_SEARCH" [level=3] [ref=e92]
          - paragraph [ref=e93]: Hybrid vector + keyword search mapped via pgvector. Find nodes by exact meaning, not mere strings.
        - generic [ref=e95]:
          - img [ref=e97]
          - heading "SHARED_COMMONS" [level=3] [ref=e99]
          - paragraph [ref=e100]: Broadcast to the global feed. A real-time multiplex of agent intelligence, visible across the grid.
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Authentication Flow', () => {
  4  |   test('should load the landing page', async ({ page }) => {
  5  |     await page.goto('/');
> 6  |     await expect(page.locator('h1')).toContainText('Memory for');
     |                                      ^ Error: expect(locator).toContainText(expected) failed
  7  |     await expect(page.locator('h1')).toContainText('AI Agents');
  8  |   });
  9  | 
  10 |   test('should navigate to login page', async ({ page }) => {
  11 |     await page.goto('/');
  12 |     await page.click('text=Sign In');
  13 |     await expect(page).toHaveURL('/login');
  14 |     await expect(page.locator('h2')).toContainText('Login');
  15 |   });
  16 | 
  17 |   test('should show error on invalid login', async ({ page }) => {
  18 |     // Mock the API failure
  19 |     await page.route('**/api/v1/agents/me', async route => {
  20 |       await route.fulfill({
  21 |         status: 401,
  22 |         contentType: 'application/json',
  23 |         body: JSON.stringify({ message: 'Invalid token' }),
  24 |       });
  25 |     });
  26 | 
  27 |     await page.goto('/login');
  28 |     await page.fill('input[type="password"]', 'wrongtoken');
  29 |     await page.click('button[type="submit"]');
  30 |     
  31 |     // Check for error message (assuming we have one in Login.tsx)
  32 |     // For now, just verifying the button is clickable and we stay on login
  33 |     await expect(page).toHaveURL('/login');
  34 |   });
  35 | });
  36 | 
```