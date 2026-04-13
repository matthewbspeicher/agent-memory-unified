import { test, expect } from '@playwright/test';

test.describe('Real-time WebSocket Feed', () => {
  test.beforeEach(async ({ page }) => {
    // Setup authentication token in localStorage
    await page.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'test-token');
    });

    // Mock initial memories endpoint
    await page.route('**/api/v1/memories', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [
          { id: 'initial-1', agent_id: 'a1', value: 'Initial Memory', visibility: 'public', created_at: new Date().toISOString() }
        ]}),
      });
    });

    // Mock agent endpoint
    await page.route('**/api/v1/agents/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'a1', name: 'Test Agent' } }),
      });
    });
  });

  test('should connect to websocket and receive real-time memories', async ({ page }) => {
    // We can intercept the websocket creation in Playwright and mock it
    await page.routeWebSocket('**/engine/v1/ws/public', ws => {
      // Accept the connection
      ws.onMessage(message => {
        // Handle incoming messages if needed
      });
      
      // Send a mock message after 1 second
      setTimeout(() => {
        ws.send(JSON.stringify({
          type: 'MemoryCreated',
          payload: {
            memory: {
              id: 'ws-mock-1',
              agent_id: 'a1',
              value: 'Real-time Neural Sync Initialized',
              visibility: 'public',
              created_at: new Date().toISOString(),
              agent: { name: 'Nexus.Void' }
            }
          }
        }));
      }, 1000);
    });

    // Load the dashboard which initializes the WS connection
    await page.goto('/dashboard');
    
    // The initial memory should be visible
    await expect(page.locator('text=Initial Memory')).toBeVisible();
    
    // Check that the UI indicates connected status
    await expect(page.locator('text=System Operational')).toBeVisible();
    await expect(page.locator('text=Live Sync')).toBeVisible();

    // After 1 second, the mocked WS message will be sent. 
    // The new memory should appear in the feed automatically.
    await expect(page.locator('text=Real-time Neural Sync Initialized')).toBeVisible({ timeout: 5000 });
  });

  test('should handle websocket disconnection gracefully', async ({ page }) => {
    // Intercept and close immediately to simulate failure
    await page.routeWebSocket('**/engine/v1/ws/public', ws => {
      ws.close();
    });

    await page.goto('/dashboard');
    
    // UI should indicate offline status
    await expect(page.locator('text=Offline / Reconnecting')).toBeVisible();
  });
});
