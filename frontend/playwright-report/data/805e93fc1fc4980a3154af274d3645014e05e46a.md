# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: production.spec.ts >> Production Environment Smoke Tests >> Landing page renders correctly and displays branding
- Location: tests/e2e/production.spec.ts:7:3

# Error details

```
Error: expect(page).toHaveTitle(expected) failed

Expected pattern: /Agent Memory Unified|NEXUS/i
Received string:  "Remembr - Agent Memory Commons"
Timeout: 5000ms

Call log:
  - Expect "toHaveTitle" with timeout 5000ms
    8 × unexpected value "Remembr - Agent Memory Commons"

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
  1   | import { test, expect } from '@playwright/test';
  2   | 
  3   | test.describe('Production Environment Smoke Tests', () => {
  4   |   // These tests are designed to run against a real, unmocked production environment.
  5   |   // They focus on verifying critical paths, rendering, and API connectivity.
  6   |   
  7   |   test('Landing page renders correctly and displays branding', async ({ page }) => {
  8   |     // Navigate to the root URL (configured via PROD_URL)
  9   |     await page.goto('/');
  10  |     
  11  |     // Verify the page title or main branding is visible
> 12  |     await expect(page).toHaveTitle(/Agent Memory Unified|NEXUS/i);
      |                        ^ Error: expect(page).toHaveTitle(expected) failed
  13  |     
  14  |     // Verify core call-to-action buttons exist
  15  |     const signInButton = page.locator('text=Sign In').first();
  16  |     await expect(signInButton).toBeVisible();
  17  |   });
  18  | 
  19  |   test('Navigation to Login page works', async ({ page }) => {
  20  |     await page.goto('/');
  21  |     
  22  |     // Click the Sign In button
  23  |     await page.click('text=Sign In');
  24  |     
  25  |     // Ensure we are redirected to the login route
  26  |     await expect(page).toHaveURL(/.*\/login/);
  27  |     
  28  |     // Verify login form is present
  29  |     await expect(page.locator('input[type="password"]')).toBeVisible();
  30  |     await expect(page.locator('text=Execute_Login')).toBeVisible();
  31  |   });
  32  | 
  33  |   test('Live Login: Token submission navigates to dashboard', async ({ page }) => {
  34  |     await page.goto('/login');
  35  |     
  36  |     // Enter a dummy token
  37  |     const tokenInput = page.locator('input[type="password"]');
  38  |     await tokenInput.fill('amc_smoke_test_token_123');
  39  |     
  40  |     // Click the execute login button
  41  |     await page.click('text=Execute_Login');
  42  |     
  43  |     // The app should set localStorage and navigate away from /login
  44  |     // It navigates to '/' which might redirect to '/dashboard' or stay on '/'
  45  |     await expect(page).not.toHaveURL(/.*\/login/);
  46  |     
  47  |     // Verify localStorage was set
  48  |     const storedToken = await page.evaluate(() => window.localStorage.getItem('auth_token'));
  49  |     expect(storedToken).toBe('amc_smoke_test_token_123');
  50  |   });
  51  | 
  52  |   test('Live Login: Request Access form validation and submission', async ({ page }) => {
  53  |     await page.goto('/login');
  54  |     
  55  |     // Switch to Request Access mode
  56  |     await page.click('text=Request_Access');
  57  |     
  58  |     // Verify the form fields are present
  59  |     const inviteInput = page.locator('input[placeholder="inv_..."]');
  60  |     const nameInput = page.locator('input[placeholder="Operative Name"]');
  61  |     const emailInput = page.locator('input[placeholder="you@grid.net"]');
  62  |     const submitBtn = page.locator('text=Initialize_Uplink');
  63  |     
  64  |     await expect(inviteInput).toBeVisible();
  65  |     await expect(nameInput).toBeVisible();
  66  |     await expect(emailInput).toBeVisible();
  67  |     
  68  |     // Submit button should be disabled initially
  69  |     await expect(submitBtn).toBeDisabled();
  70  |     
  71  |     // Fill the form with dummy data
  72  |     await inviteInput.fill('inv_invalid_code_smoke_test');
  73  |     await nameInput.fill('Smoke Test Operative');
  74  |     await emailInput.fill('smoke@grid.net');
  75  |     
  76  |     // Button should now be enabled
  77  |     await expect(submitBtn).toBeEnabled();
  78  |     
  79  |     // Submit the form
  80  |     await submitBtn.click();
  81  |     
  82  |     // We expect a network error or an invalid parameters error depending on the live backend
  83  |     // Wait for the error banner to appear
  84  |     const errorBanner = page.locator('.bg-rose-500\\/10');
  85  |     await expect(errorBanner).toBeVisible({ timeout: 10000 });
  86  |     
  87  |     // The banner should contain some error text
  88  |     const errorText = await errorBanner.textContent();
  89  |     expect(errorText).toMatch(/INVALID|ERROR|FAILED/i);
  90  |   });
  91  | 
  92  |   test('Public API Healthcheck', async ({ request }) => {
  93  |     // Verify the backend API is reachable and healthy
  94  |     // Assuming the unified backend exposes a health endpoint
  95  |     const response = await request.get('/api/v1/health');
  96  |     
  97  |     // In some environments this might be a 401 if entirely locked down,
  98  |     // but usually a health check returns 200 OK.
  99  |     expect([200, 401, 404]).toContain(response.status());
  100 |   });
  101 | });
  102 | 
  103 | 
```