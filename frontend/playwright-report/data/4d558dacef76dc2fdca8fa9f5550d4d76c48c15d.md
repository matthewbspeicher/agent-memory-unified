# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core.spec.ts >> Core Functionality >> should load the memories list
- Location: tests/e2e/core.spec.ts:46:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('h1')
Expected substring: "Memories"
Received string:    "WORKSPACE_MEMORIES"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('h1')
    9 × locator resolved to <h1 class="text-4xl font-black tracking-tighter mb-2 bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500">WORKSPACE_MEMORIES</h1>
      - unexpected value "WORKSPACE_MEMORIES"

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
        - heading "Ops" [level=3] [ref=e33]
        - generic [ref=e34]:
          - link "Mission Control" [ref=e35] [cursor=pointer]:
            - /url: /mission-control
            - img [ref=e36]
            - generic [ref=e41]: Mission Control
          - link "Dashboard" [ref=e42] [cursor=pointer]:
            - /url: /dashboard
            - img [ref=e43]
            - generic [ref=e45]: Dashboard
          - link "Agent Roster" [ref=e46] [cursor=pointer]:
            - /url: /roster
            - img [ref=e47]
            - generic [ref=e52]: Agent Roster
          - link "Bittensor Node" [ref=e53] [cursor=pointer]:
            - /url: /bittensor
            - img [ref=e54]
            - generic [ref=e57]: Bittensor Node
      - generic [ref=e58]:
        - heading "Community" [level=3] [ref=e59]
        - generic [ref=e60]:
          - link "Arena" [ref=e61] [cursor=pointer]:
            - /url: /arena
            - img [ref=e62]
            - generic [ref=e71]: Arena
          - link "Commons" [ref=e72] [cursor=pointer]:
            - /url: /commons
            - img [ref=e73]
            - generic [ref=e76]: Commons
          - link "Leaderboard" [ref=e77] [cursor=pointer]:
            - /url: /leaderboard
            - img [ref=e78]
            - generic [ref=e84]: Leaderboard
      - generic [ref=e85]:
        - heading "System" [level=3] [ref=e86]
        - generic [ref=e87]:
          - link "Explorer" [ref=e88] [cursor=pointer]:
            - /url: /explorer
            - img [ref=e89]
            - generic [ref=e92]: Explorer
          - link "Webhooks" [ref=e93] [cursor=pointer]:
            - /url: /webhooks
            - img [ref=e94]
            - generic [ref=e96]: Webhooks
          - link "Workspaces" [ref=e97] [cursor=pointer]:
            - /url: /workspaces
            - img [ref=e98]
            - generic [ref=e100]: Workspaces
    - button "Exit System" [ref=e103] [cursor=pointer]:
      - img [ref=e104]
      - generic [ref=e107]: Exit System
  - main [ref=e108]:
    - generic [ref=e109]:
      - generic [ref=e110]:
        - heading "WORKSPACE_MEMORIES" [level=1] [ref=e111]
        - paragraph [ref=e112]: // Private Datastore _
      - generic [ref=e114]:
        - textbox "What do you want to remember?" [ref=e115]
        - generic [ref=e116]:
          - generic [ref=e117]:
            - generic [ref=e118]:
              - radio "Private" [checked] [ref=e119]
              - text: Private
            - generic [ref=e120]:
              - radio "Public" [ref=e121]
              - text: Public
          - button "Save Memory" [disabled] [ref=e122]
      - generic [ref=e125]:
        - generic [ref=e126]: ">"
        - textbox "Query memory fragments..." [ref=e127]
      - generic [ref=e130]:
        - paragraph [ref=e131]: Test Memory
        - generic [ref=e132]:
          - generic [ref=e133]: 4/13/2026
          - generic [ref=e134]: public
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Core Functionality', () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     // Setup authentication token in localStorage
  6  |     await page.addInitScript(() => {
  7  |       window.localStorage.setItem('auth_token', 'test-token');
  8  |     });
  9  | 
  10 |     // Mock common endpoints
  11 |     await page.route('**/api/v1/agents/me', async route => {
  12 |       await route.fulfill({
  13 |         status: 200,
  14 |         contentType: 'application/json',
  15 |         body: JSON.stringify({ data: { id: 'a1', name: 'Test Agent' } }),
  16 |       });
  17 |     });
  18 | 
  19 |     await page.route('**/api/v1/memories', async route => {
  20 |       await route.fulfill({
  21 |         status: 200,
  22 |         contentType: 'application/json',
  23 |         body: JSON.stringify({ data: [
  24 |           { id: '1', agent_id: 'a1', value: 'Test Memory', visibility: 'public', created_at: new Date().toISOString() }
  25 |         ]}),
  26 |       });
  27 |     });
  28 | 
  29 |     await page.route('**/api/v1/trades', async route => {
  30 |       await route.fulfill({
  31 |         status: 200,
  32 |         contentType: 'application/json',
  33 |         body: JSON.stringify({ data: [
  34 |           { id: '1', agent_id: 'a1', agent_name: 'Test Agent', symbol: 'AAPL', side: 'long', entry_price: '150', entry_quantity: 10, status: 'open', entry_time: new Date().toISOString() }
  35 |         ]}),
  36 |       });
  37 |     });
  38 |   });
  39 | 
  40 |   test('should load the dashboard', async ({ page }) => {
  41 |     await page.goto('/dashboard');
  42 |     await expect(page.locator('h2')).toContainText('Dashboard');
  43 |     await expect(page.locator('text=Total Memories')).toBeVisible();
  44 |   });
  45 | 
  46 |   test('should load the memories list', async ({ page }) => {
  47 |     await page.goto('/memories');
> 48 |     await expect(page.locator('h1')).toContainText('Memories');
     |                                      ^ Error: expect(locator).toContainText(expected) failed
  49 |     await expect(page.locator('text=Test Memory')).toBeVisible();
  50 |   });
  51 | 
  52 |   test('should load the trade history', async ({ page }) => {
  53 |     await page.goto('/trades');
  54 |     await expect(page.locator('h2')).toContainText('Trade History');
  55 |     await expect(page.locator('text=AAPL')).toBeVisible();
  56 |   });
  57 | 
  58 |   test('should navigate between pages via layout', async ({ page }) => {
  59 |     // Mock the arena profile endpoint so it doesn't hang
  60 |     await page.route('**/api/v1/arena/profile', async route => {
  61 |       await route.fulfill({
  62 |         status: 200,
  63 |         contentType: 'application/json',
  64 |         body: JSON.stringify({ data: { agent_id: 'a1', elo: 1200 } }),
  65 |       });
  66 |     });
  67 | 
  68 |     await page.goto('/dashboard');
  69 |     // Ensure dashboard loaded first
  70 |     await expect(page.locator('h2').first()).toContainText('Dashboard');
  71 |     
  72 |     // Use force true to bypass any potential overlay issues
  73 |     await page.click('nav a:has-text("Arena")', { force: true });
  74 |     await expect(page).toHaveURL(/.*\/arena/);
  75 |     await expect(page.locator('h1')).toContainText('Agent Battle Arena');
  76 |     
  77 |     await page.click('nav a:has-text("Commons")', { force: true });
  78 |     await expect(page).toHaveURL(/.*\/commons/);
  79 |     await expect(page.locator('h1')).toContainText('The Semantic Commons');
  80 |   });
  81 | });
  82 | 
```