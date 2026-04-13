# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: chaos.spec.ts >> Chaos Engineering tests - Resilience against backend failures >> Latency test on Bittensor /api/bittensor/status shows loading state
- Location: tests/e2e/chaos.spec.ts:22:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.loading-spinner, [aria-busy="true"], .skeleton-loader').first()
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('.loading-spinner, [aria-busy="true"], .skeleton-loader').first()

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
      - heading "Bittensor Validator Node" [level=1] [ref=e69]
      - paragraph [ref=e72]: Bittensor integration is not enabled. Set STA_BITTENSOR_ENABLED=true to activate.
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Chaos Engineering tests - Resilience against backend failures', () => {
  4  |     
  5  |     test('API 500 Error test on Memory Load gracefully shows error state', async ({ page }) => {
  6  |         // Intercept memories API and force a 500 status
  7  |         await page.route('**/api/memories*', async route => {
  8  |             await route.fulfill({
  9  |                 status: 500,
  10 |                 contentType: 'application/json',
  11 |                 body: JSON.stringify({ error: 'Internal Server Error' })
  12 |             });
  13 |         });
  14 | 
  15 |         await page.goto('/memories');
  16 |         
  17 |         // Assert resilient frontend parsing of error handling
  18 |         const errorAlert = page.locator('.error-message, [role="alert"]').first();
  19 |         await expect(errorAlert).toBeVisible();
  20 |     });
  21 | 
  22 |     test('Latency test on Bittensor /api/bittensor/status shows loading state', async ({ page }) => {
  23 |         // Simulate 3 seconds of latency
  24 |         await page.route('**/api/bittensor/status', async route => {
  25 |             await new Promise(resolve => setTimeout(resolve, 3000));
  26 |             const response = await route.fetch();
  27 |             await route.fulfill({
  28 |                 response,
  29 |             });
  30 |         });
  31 | 
  32 |         // Use a test that doesn't strictly freeze
  33 |         await page.goto('/bittensor');
  34 |         
  35 |         // Assert that loading indicator is shown
  36 |         const loader = page.locator('.loading-spinner, [aria-busy="true"], .skeleton-loader').first();
> 37 |         await expect(loader).toBeVisible();
     |                              ^ Error: expect(locator).toBeVisible() failed
  38 |     });
  39 | 
  40 |     test('Malformed JSON response test on Trade processing handles exception gracefully', async ({ page }) => {
  41 |         // Intercept trades API and return malformed JSON
  42 |         await page.route('**/api/trades*', async route => {
  43 |             await route.fulfill({
  44 |                 status: 200,
  45 |                 contentType: 'application/json',
  46 |                 body: '{"data": [{"id": 1, "ticker": "AAPL" ' // Malformed JSON
  47 |             });
  48 |         });
  49 | 
  50 |         await page.goto('/trades');
  51 | 
  52 |         // Assert frontend doesn't crash completely, error or empty state
  53 |         const errorBoundary = page.locator('.error-message, [role="alert"]').first();
  54 |         await expect(errorBoundary).toBeVisible();
  55 |     });
  56 | });
  57 | 
```