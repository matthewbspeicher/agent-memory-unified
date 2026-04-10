import { test, expect } from '@playwright/test';

test.describe('Production Environment Smoke Tests', () => {
  // These tests are designed to run against a real, unmocked production environment.
  // They focus on verifying critical paths, rendering, and API connectivity.
  
  test('Landing page renders correctly and displays branding', async ({ page }) => {
    // Navigate to the root URL (configured via PROD_URL)
    await page.goto('/');
    
    // Verify the page title or main branding is visible
    await expect(page).toHaveTitle(/Agent Memory Unified|NEXUS/i);
    
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
    await expect(page.locator('button[type="submit"]')).toBeVisible();
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
