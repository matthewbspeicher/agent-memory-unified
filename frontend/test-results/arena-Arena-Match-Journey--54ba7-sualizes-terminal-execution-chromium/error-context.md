# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: arena.spec.ts >> Arena Match Journey >> Arena Match visualizes terminal execution
- Location: tests/e2e/arena.spec.ts:45:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('text=85.0')
Expected: visible
Error: strict mode violation: locator('text=85.0') resolved to 2 elements:
    1) <div class="text-3xl font-black font-mono text-emerald-400">85.0</div> aka getByText('85.0', { exact: true })
    2) <span class="font-black tracking-tighter text-emerald-400">+85.0</span> aka getByText('+')

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('text=85.0')

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
    - generic [ref=e66]:
      - link "← Back to Arena" [ref=e67] [cursor=pointer]:
        - /url: /arena
      - generic [ref=e68]:
        - generic [ref=e69]:
          - heading "Session Details" [level=1] [ref=e70]
          - generic [ref=e71]: in_progress
        - generic [ref=e72]:
          - generic [ref=e73]:
            - text: Score
            - generic [ref=e74]: "85.0"
          - generic [ref=e75]:
            - text: Turns
            - generic [ref=e76]: "1"
          - generic [ref=e77]:
            - text: Agent
            - generic [ref=e78]: AlphaScout
          - generic [ref=e79]:
            - text: Inventory
            - generic [ref=e80]: 1 items
      - heading "Turn History" [level=2] [ref=e81]
      - generic [ref=e82]:
        - generic [ref=e83]:
          - generic [ref=e84]:
            - generic [ref=e85]: Turn 1
            - generic [ref=e86]: "+85.0"
          - generic [ref=e87]: run_sql_query
          - generic [ref=e88]: "{ \"query\": \"SELECT * FROM logs\" }"
          - generic [ref=e89]: 3 rows returned
        - generic [ref=e90]: Session in progress...
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Arena Match Journey', () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     await page.addInitScript(() => {
  6  |       window.localStorage.setItem('auth_token', 'test-token');
  7  |     });
  8  | 
  9  |     // Mock Arena Sessions/Match Details
  10 |     await page.route('**/engine/v1/arena/sessions/match-123', async route => {
  11 |       await route.fulfill({
  12 |         status: 200,
  13 |         contentType: 'application/json',
  14 |         headers: { 
  15 |           'Access-Control-Allow-Origin': '*',
  16 |           'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  17 |           'Access-Control-Allow-Headers': '*'
  18 |         },
  19 |         body: JSON.stringify({
  20 |           id: 'match-123',
  21 |           challenge_id: 'c1',
  22 |           agent_id: 'AlphaScout',
  23 |           current_state: 'room1',
  24 |           inventory: ['key'],
  25 |           turn_count: 1,
  26 |           score: 85,
  27 |           status: 'in_progress',
  28 |           created_at: new Date().toISOString(),
  29 |           turns: [
  30 |             {
  31 |               id: 't1',
  32 |               turn_number: 1,
  33 |               tool_name: 'run_sql_query',
  34 |               tool_input: { query: 'SELECT * FROM logs' },
  35 |               tool_output: '3 rows returned',
  36 |               score_delta: 85,
  37 |               created_at: new Date().toISOString()
  38 |             }
  39 |           ]
  40 |         }),
  41 |       });
  42 |     });
  43 |   });
  44 | 
  45 |   test('Arena Match visualizes terminal execution', async ({ page }) => {
  46 |     await page.goto('/arena/matches/match-123');
  47 | 
  48 |     // Wait for Session Details header to render
  49 |     await expect(page.locator('text=Session Details')).toBeVisible();
  50 | 
  51 |     // Check stats
  52 |     await expect(page.locator('text=AlphaScout')).toBeVisible();
> 53 |     await expect(page.locator('text=85.0')).toBeVisible();
     |                                             ^ Error: expect(locator).toBeVisible() failed
  54 |     await expect(page.locator('text=1 items')).toBeVisible();
  55 | 
  56 |     // Verify Turn rendering
  57 |     await expect(page.locator('text=Turn History')).toBeVisible();
  58 |     await expect(page.locator('text=run_sql_query')).toBeVisible();
  59 |     await expect(page.locator('text=3 rows returned')).toBeVisible();
  60 |   });
  61 | });
  62 | 
```