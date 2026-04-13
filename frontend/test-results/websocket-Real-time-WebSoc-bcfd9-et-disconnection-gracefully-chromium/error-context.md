# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: websocket.spec.ts >> Real-time WebSocket Feed >> should handle websocket disconnection gracefully
- Location: tests/e2e/websocket.spec.ts:72:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('text=Offline / Reconnecting')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('text=Offline / Reconnecting')

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
  3  | test.describe('Real-time WebSocket Feed', () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     // Setup authentication token in localStorage
  6  |     await page.addInitScript(() => {
  7  |       window.localStorage.setItem('auth_token', 'test-token');
  8  |     });
  9  | 
  10 |     // Mock initial memories endpoint
  11 |     await page.route('**/api/v1/memories', async route => {
  12 |       await route.fulfill({
  13 |         status: 200,
  14 |         contentType: 'application/json',
  15 |         body: JSON.stringify({ data: [
  16 |           { id: 'initial-1', agent_id: 'a1', value: 'Initial Memory', visibility: 'public', created_at: new Date().toISOString() }
  17 |         ]}),
  18 |       });
  19 |     });
  20 | 
  21 |     // Mock agent endpoint
  22 |     await page.route('**/api/v1/agents/me', async route => {
  23 |       await route.fulfill({
  24 |         status: 200,
  25 |         contentType: 'application/json',
  26 |         body: JSON.stringify({ data: { id: 'a1', name: 'Test Agent' } }),
  27 |       });
  28 |     });
  29 |   });
  30 | 
  31 |   test('should connect to websocket and receive real-time memories', async ({ page }) => {
  32 |     // We can intercept the websocket creation in Playwright and mock it
  33 |     await page.routeWebSocket('**/api/trading-direct/ws/public', ws => {
  34 |       // Accept the connection
  35 |       ws.onMessage(message => {
  36 |         // Handle incoming messages if needed
  37 |       });
  38 |       
  39 |       // Send a mock message after 1 second
  40 |       setTimeout(() => {
  41 |         ws.send(JSON.stringify({
  42 |           type: 'MemoryCreated',
  43 |           payload: {
  44 |             memory: {
  45 |               id: 'ws-mock-1',
  46 |               agent_id: 'a1',
  47 |               value: 'Real-time Neural Sync Initialized',
  48 |               visibility: 'public',
  49 |               created_at: new Date().toISOString(),
  50 |               agent: { name: 'Nexus.Void' }
  51 |             }
  52 |           }
  53 |         }));
  54 |       }, 1000);
  55 |     });
  56 | 
  57 |     // Load the dashboard which initializes the WS connection
  58 |     await page.goto('/dashboard');
  59 |     
  60 |     // The initial memory should be visible
  61 |     await expect(page.locator('text=Initial Memory')).toBeVisible();
  62 |     
  63 |     // Check that the UI indicates connected status
  64 |     await expect(page.locator('text=System Operational')).toBeVisible();
  65 |     await expect(page.locator('text=Live Sync')).toBeVisible();
  66 | 
  67 |     // After 1 second, the mocked WS message will be sent. 
  68 |     // The new memory should appear in the feed automatically.
  69 |     await expect(page.locator('text=Real-time Neural Sync Initialized')).toBeVisible({ timeout: 5000 });
  70 |   });
  71 | 
  72 |   test('should handle websocket disconnection gracefully', async ({ page }) => {
  73 |     // Intercept and close immediately to simulate failure
  74 |     await page.routeWebSocket('**/api/trading-direct/ws/public', ws => {
  75 |       ws.close();
  76 |     });
  77 | 
  78 |     await page.goto('/dashboard');
  79 |     
  80 |     // UI should indicate offline status
> 81 |     await expect(page.locator('text=Offline / Reconnecting')).toBeVisible();
     |                                                               ^ Error: expect(locator).toBeVisible() failed
  82 |   });
  83 | });
  84 | 
```