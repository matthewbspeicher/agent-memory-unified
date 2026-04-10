import { test, expect } from '@playwright/test';

test.describe('Arena Match & Betting Journey', () => {
  test.beforeEach(async ({ page }) => {
    // Setup authentication token in localStorage
    await page.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'test-token');
    });

    // Mock the user profile
    await page.route('**/api/v1/agents/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { id: 'admin1', name: 'Admin Coach' } }),
      });
    });

    // Mock Arena Leaderboard
    await page.route('**/engine/v1/leaderboard*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          leaderboard: [
            { id: '1', name: 'AlphaScout', elo: 1850, tier: 'diamond', type: 'agent', matches_count: 150 },
            { id: '2', name: 'OmegaGrid', elo: 1200, tier: 'silver', type: 'agent', matches_count: 50 }
          ],
          competitor_count: 2
        }),
      });
    });

    // Mock Match Details
    await page.route('**/engine/v1/matches/match-123', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'match-123',
          status: 'in_progress',
          agent_1_id: '1',
          agent_2_id: '2',
          winner_id: null,
          score_1: null,
          score_2: null,
          judge_feedback: null,
          challenge: {
            id: 'c1',
            gym_id: 'g1',
            title: 'Escape Room Protocol',
            prompt: 'Solve the simulated cyber breach',
            difficulty_level: 'expert',
            xp_reward: 1000,
            max_turns: 50
          },
          agent1: { id: '1', name: 'AlphaScout' },
          agent2: { id: '2', name: 'OmegaGrid' },
          sessions: [
            {
              id: 's1',
              agent_id: '1',
              status: 'in_progress',
              turns: [
                {
                  id: 't1',
                  turn_number: 1,
                  input: '{"tool_call": "run_sql_query", "args": {"query": "SELECT * FROM logs"}}',
                  output: '3 rows returned',
                  score: 85,
                  feedback: 'Good initial exploration.'
                }
              ]
            }
          ],
          created_at: new Date().toISOString()
        }),
      });
    });

    // Mock Betting Pool
    await page.route('**/engine/v1/matches/match-123/pool', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          match_id: 'match-123',
          total_pool: 24500,
          competitor_a_pool: 15925,
          competitor_b_pool: 8575,
          competitor_a_bettors: 14,
          competitor_b_bettors: 8,
          competitor_a_odds: 0.65,
          competitor_b_odds: 0.35,
          status: 'open'
        }),
      });
    });

    // Mock place bet mutation
    await page.route('**/engine/v1/matches/match-123/bet', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, bet_id: 'bet-123' })
      });
    });
  });

  test('should load Arena Leaderboard', async ({ page }) => {
    await page.goto('/arena');
    await expect(page.locator('h1')).toContainText('Arena Leaderboard');
    
    // Check leaderboard rows
    await expect(page.locator('text=AlphaScout').first()).toBeVisible();
    await expect(page.locator('text=1850').first()).toBeVisible();
  });

  test('Arena Match visualizes terminal execution and betting pool', async ({ page }) => {
    await page.goto('/arena/matches/match-123');

    // Wait for challenge info to render
    await expect(page.locator('text=Escape Room Protocol')).toBeVisible();

    // Verify Betting Pool Widget renders
    await expect(page.locator('text=Arena Betting Pool')).toBeVisible();
    await expect(page.locator('text=POOL: 24,500 XP')).toBeVisible();
    await expect(page.locator('text=65% implied')).toBeVisible();

    // Interact with betting UI
    const wagerInput = page.locator('input[type="number"]');
    await expect(wagerInput).toBeVisible();
    await wagerInput.fill('500');

    // Place a bet and listen for the mocked alert (since our mock component uses alert)
    page.on('dialog', async dialog => {
      expect(dialog.message()).toContain('Bet of 500 XP placed successfully!');
      await dialog.accept();
    });

    const betButton = page.locator('text=Bet AlphaScout');
    await betButton.click();

    // Verify Terminal Output Rendering for Escape Rooms
    await expect(page.locator('text=Terminal execution')).toBeVisible();
    await expect(page.locator('text=> run_sql_query')).toBeVisible();
    await expect(page.locator('text=3 rows returned')).toBeVisible();
  });
});
