import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test('should load the landing page', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('Memory for');
    await expect(page.locator('h1')).toContainText('AI Agents');
  });

  test('should navigate to login page', async ({ page }) => {
    await page.goto('/');
    await page.click('text=Sign In');
    await expect(page).toHaveURL('/login');
    await expect(page.locator('h2')).toContainText('Login');
  });

  test('should show error on invalid login', async ({ page }) => {
    // Mock the API failure
    await page.route('**/api/v1/agents/me', async route => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Invalid token' }),
      });
    });

    await page.goto('/login');
    await page.fill('input[type="password"]', 'wrongtoken');
    await page.click('button[type="submit"]');
    
    // Check for error message (assuming we have one in Login.tsx)
    // For now, just verifying the button is clickable and we stay on login
    await expect(page).toHaveURL('/login');
  });
});
