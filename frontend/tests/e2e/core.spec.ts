import { test, expect } from '@playwright/test';

test.describe('Core Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Setup authentication token in localStorage
    await page.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'test-token');
    });

    // Mock common endpoints
    await page.route('**/api/v1/agents/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'a1', name: 'Test Agent' } }),
      });
    });

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
          { id: '1', agent_id: 'a1', agent_name: 'Test Agent', symbol: 'AAPL', side: 'long', entry_price: '150', entry_quantity: 10, status: 'open', entry_time: new Date().toISOString() }
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
    // Mock the arena profile endpoint so it doesn't hang
    await page.route('**/api/v1/arena/profile', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { agent_id: 'a1', elo: 1200 } }),
      });
    });

    await page.goto('/dashboard');
    // Ensure dashboard loaded first
    await expect(page.locator('h2').first()).toContainText('Dashboard');
    
    // Use force true to bypass any potential overlay issues
    await page.click('nav a:has-text("Arena")', { force: true });
    await expect(page).toHaveURL(/.*\/arena/);
    await expect(page.locator('h1')).toContainText('Agent Battle Arena');
    
    await page.click('nav a:has-text("Commons")', { force: true });
    await expect(page).toHaveURL(/.*\/commons/);
    await expect(page.locator('h1')).toContainText('The Semantic Commons');
  });
});
