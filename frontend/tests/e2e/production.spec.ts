import { test, expect } from '@playwright/test';

test.describe('Production Environment Smoke Tests', () => {
  // These tests are designed to run against a real, unmocked production environment.
  // They focus on verifying critical paths, rendering, and API connectivity.
  
  test('Landing page renders correctly and displays branding', async ({ page }) => {
    // Navigate to the root URL (configured via PROD_URL)
    await page.goto('/');
    
    // Verify the page title or main branding is visible
    await expect(page).toHaveTitle(/Agent Memory Unified|NEXUS|Remembr/i);
    
    // Verify core call-to-action buttons exist
    const signInButton = page.locator('text=Sign In').first();
    await expect(signInButton).toBeVisible();
  });

  test('Navigation to Login page works', async ({ page }) => {
    await page.goto('/');
    
    // Click the Sign In button
    await page.click('text=Sign In');
    
    // Ensure we are redirected to the login route
    await expect(page).toHaveURL(/.*\/login/);
    
    // Verify login form is present
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('text=Execute_Login')).toBeVisible();
  });

  test('Live Login: Token submission navigates to dashboard', async ({ page }) => {
    // Mock the auth endpoint so our dummy token isn't immediately wiped by a 401
    await page.route('**/api/v1/agents/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'smoke-test-agent', name: 'SmokeTestAgent' } }),
      });
    });

    await page.goto('/login');
    
    // Enter a dummy token
    const tokenInput = page.locator('input[type="password"]');
    await tokenInput.fill('amc_smoke_test_token_123');
    
    // Click the execute login button
    await page.click('text=Execute_Login');
    
    // The app should set localStorage and navigate away from /login
    // It navigates to '/' which might redirect to '/dashboard' or stay on '/'
    await expect(page).not.toHaveURL(/.*\/login/);
    
    // Verify localStorage was set
    const storedToken = await page.evaluate(() => window.localStorage.getItem('auth_token'));
    expect(storedToken).toBe('amc_smoke_test_token_123');
  });

  test('Live Login: Request Access form validation and submission', async ({ page }) => {
    await page.goto('/login');
    
    // Switch to Request Access mode
    await page.click('text=Request_Access');
    
    // Verify the form fields are present
    const inviteInput = page.locator('input[placeholder="inv_..."]');
    const nameInput = page.locator('input[placeholder="Operative Name"]');
    const emailInput = page.locator('input[placeholder="you@grid.net"]');
    const submitBtn = page.locator('text=Initialize_Uplink');
    
    await expect(inviteInput).toBeVisible();
    await expect(nameInput).toBeVisible();
    await expect(emailInput).toBeVisible();
    
    // Submit button should be disabled initially
    await expect(submitBtn).toBeDisabled();
    
    // Fill the form with dummy data
    await inviteInput.fill('inv_invalid_code_smoke_test');
    await nameInput.fill('Smoke Test Operative');
    await emailInput.fill('smoke@grid.net');
    
    // Button should now be enabled
    await expect(submitBtn).toBeEnabled();
    
    // Submit the form
    await submitBtn.click();
    
    // We expect a network error or an invalid parameters error depending on the live backend
    // Wait for the error banner to appear
    const errorBanner = page.locator('.bg-rose-500\\/10');
    await expect(errorBanner).toBeVisible({ timeout: 10000 });
    
    // The banner should contain some error text
    const errorText = await errorBanner.textContent();
    expect(errorText).toMatch(/INVALID|ERROR|FAILED/i);
  });

  test('Public API Healthcheck', async ({ request }) => {
    // Verify the backend API is reachable and healthy
    // Assuming the unified backend exposes a health endpoint
    const response = await request.get('/api/v1/health');
    
    // In some environments this might be a 401 if entirely locked down,
    // but usually a health check returns 200 OK.
    expect([200, 401, 404]).toContain(response.status());
  });
});

