import { test, expect } from '@playwright/test';

test.describe('Core Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Setup authentication token in localStorage
    await page.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'test-token');
    });

    // Mock common endpoints
    await page.route('**/api/v1/memories', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [
          { id: '1', agent_id: 'a1', value: 'Test Memory', visibility: 'public', created_at: new Date().toISOString() }
        ]}),
      });
    });

    await page.route('**/api/v1/trades', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [
          { id: '1', agent_id: 'a1', ticker: 'AAPL', direction: 'long', entry_price: '150', quantity: '10', status: 'open', entry_at: new Date().toISOString() }
        ]}),
      });
    });
  });

  test('should load the dashboard', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('h2')).toContainText('Dashboard');
    await expect(page.locator('text=Total Memories')).toBeVisible();
  });

  test('should load the memories list', async ({ page }) => {
    await page.goto('/memories');
    await expect(page.locator('h1')).toContainText('Memories');
    await expect(page.locator('text=Test Memory')).toBeVisible();
  });

  test('should load the trade history', async ({ page }) => {
    await page.goto('/trades');
    await expect(page.locator('h2')).toContainText('Trade History');
    await expect(page.locator('text=AAPL')).toBeVisible();
  });

  test('should navigate between pages via layout', async ({ page }) => {
    await page.goto('/dashboard');
    await page.click('nav >> text=Arena');
    await expect(page).toHaveURL('/arena');
    await expect(page.locator('h1')).toContainText('Agent Battle Arena');
    
    await page.click('nav >> text=Commons');
    await expect(page).toHaveURL('/commons');
    await expect(page.locator('h1')).toContainText('The Semantic Commons');
  });
});
