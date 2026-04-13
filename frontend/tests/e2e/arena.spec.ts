import { test, expect } from '@playwright/test';

test.describe('Arena Match Journey', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'test-token');
    });

    // Mock Arena Sessions/Match Details
    await page.route('**/engine/v1/arena/sessions/match-123', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': '*'
        },
        body: JSON.stringify({
          id: 'match-123',
          challenge_id: 'c1',
          agent_id: 'AlphaScout',
          current_state: 'room1',
          inventory: ['key'],
          turn_count: 1,
          score: 85,
          status: 'in_progress',
          created_at: new Date().toISOString(),
          turns: [
            {
              id: 't1',
              turn_number: 1,
              tool_name: 'run_sql_query',
              tool_input: { query: 'SELECT * FROM logs' },
              tool_output: '3 rows returned',
              score_delta: 85,
              created_at: new Date().toISOString()
            }
          ]
        }),
      });
    });
  });

  test('Arena Match visualizes terminal execution', async ({ page }) => {
    await page.goto('/arena/matches/match-123');

    // Wait for Session Details header to render
    await expect(page.locator('text=Session Details')).toBeVisible();

    // Check stats
    await expect(page.locator('text=AlphaScout')).toBeVisible();
    await expect(page.locator('text=85.0')).toBeVisible();
    await expect(page.locator('text=1 items')).toBeVisible();

    // Verify Turn rendering
    await expect(page.locator('text=Turn History')).toBeVisible();
    await expect(page.locator('text=run_sql_query')).toBeVisible();
    await expect(page.locator('text=3 rows returned')).toBeVisible();
  });
});
