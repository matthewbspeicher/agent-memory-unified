# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core.spec.ts >> Core Functionality >> should load the dashboard
- Location: tests/e2e/core.spec.ts:40:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('h2')
Expected substring: "Dashboard"
Received string:    "Unexpected Application Error!"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('h2')
    8 × locator resolved to <h2>Unexpected Application Error!</h2>
      - unexpected value "Unexpected Application Error!"

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - heading "Unexpected Application Error!" [level=2] [ref=e3]
  - heading "CopilotSidebar is not defined" [level=3] [ref=e4]
  - generic [ref=e5]: "ReferenceError: CopilotSidebar is not defined at Rf (http://localhost:3001/assets/index-IZWl2xYa.js:124:72068) at jf (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:47871) at fc (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:70590) at Ry (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:80917) at iv (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:116537) at Wm (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:115614) at Hc (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:115450) at uv (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:112282) at Ev (http://localhost:3001/assets/vendor-react-z46FGGDm.js:40:123953) at MessagePort.At (http://localhost:3001/assets/vendor-react-z46FGGDm.js:17:1634)"
  - paragraph [ref=e6]: 💿 Hey developer 👋
  - paragraph [ref=e7]:
    - text: You can provide a way better UX than this when your app throws errors by providing your own
    - code [ref=e8]: ErrorBoundary
    - text: or
    - code [ref=e9]: errorElement
    - text: prop on your route.
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
> 42 |     await expect(page.locator('h2')).toContainText('Dashboard');
     |                                      ^ Error: expect(locator).toContainText(expected) failed
  43 |     await expect(page.locator('text=Total Memories')).toBeVisible();
  44 |   });
  45 | 
  46 |   test('should load the memories list', async ({ page }) => {
  47 |     await page.goto('/memories');
  48 |     await expect(page.locator('h1')).toContainText('Memories');
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