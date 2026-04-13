# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> Authentication Flow >> should navigate to login page
- Location: tests/e2e/auth.spec.ts:10:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('h2')
Expected substring: "Login"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for locator('h2')

```

# Page snapshot

```yaml
- generic [ref=e5]:
  - generic [ref=e9]: AUTH_TERMINAL_V1.0
  - generic [ref=e10]:
    - generic [ref=e11]:
      - button "Agent_Login" [ref=e12] [cursor=pointer]
      - button "Request_Access" [ref=e13] [cursor=pointer]
    - generic [ref=e14]:
      - generic [ref=e15]:
        - generic [ref=e16]: "> API_TOKEN_INPUT"
        - textbox "amc_..." [ref=e17]
      - button "Execute_Login" [disabled] [ref=e18]
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Authentication Flow', () => {
  4  |   test('should load the landing page', async ({ page }) => {
  5  |     await page.goto('/');
  6  |     await expect(page.locator('h1')).toContainText('Memory for');
  7  |     await expect(page.locator('h1')).toContainText('AI Agents');
  8  |   });
  9  | 
  10 |   test('should navigate to login page', async ({ page }) => {
  11 |     await page.goto('/');
  12 |     await page.click('text=Sign In');
  13 |     await expect(page).toHaveURL('/login');
> 14 |     await expect(page.locator('h2')).toContainText('Login');
     |                                      ^ Error: expect(locator).toContainText(expected) failed
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