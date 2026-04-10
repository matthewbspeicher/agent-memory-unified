import { test, expect } from '@playwright/test';

test.describe('Fleet Gamification & Roster Journey', () => {
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

    // Mock the fleet/agents list
    await page.route('**/api/v1/agents', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [
          { name: 'AlphaScout', status: 'active' },
          { name: 'OmegaGrid', status: 'active' }
        ]}),
      });
    });

    // Mock individual Agent Cards
    await page.route('**/engine/v1/competitors/*/card*', async route => {
      const url = route.request().url();
      const name = url.includes('AlphaScout') ? 'AlphaScout' : 'OmegaGrid';
      const rarity = url.includes('AlphaScout') ? 'legendary' : 'rare';
      const elo = url.includes('AlphaScout') ? 1850 : 1200;
      const tier = url.includes('AlphaScout') ? 'diamond' : 'silver';

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          competitor_id: `${name}-id`,
          name: name,
          level: 25,
          tier: tier,
          elo: elo,
          rarity: rarity,
          stats: {
            matches: 150,
            wins: 100,
            losses: 50,
            win_rate: 0.66,
            current_streak: 5,
            best_streak: 12,
            total_xp: 62500,
            achievement_count: 14,
            traits_unlocked: 3,
            calibration_score: 0.92
          },
          trait_icons: ['🧠', '🛡️', '⚡'],
          achievement_badges: [{ type: 'streak_5', name: 'On Fire', tier: 'gold' }],
          card_version: '1.0.0'
        }),
      });
    });
  });

  test('should load the Agent Roster and display gamified Agent Cards', async ({ page }) => {
    await page.goto('/roster');

    // Verify page header
    await expect(page.locator('h1')).toContainText('Agent Roster');
    await expect(page.locator('text=Manage your fleet')).toBeVisible();

    // Verify AlphaScout card renders with specific gamified elements
    const alphaCard = page.locator('.group', { hasText: 'AlphaScout' }).first();
    await expect(alphaCard).toBeVisible();
    
    // Check level badge and XP
    await expect(alphaCard.locator('text=Lv.25')).toBeVisible();
    
    // Check ELO and Tier
    await expect(alphaCard.locator('text=1850 ELO')).toBeVisible();
    await expect(alphaCard.locator('text=DIAMOND')).toBeVisible();
    
    // Check Rarity banner
    await expect(alphaCard.locator('text=LEGENDARY')).toBeVisible();
    
    // Check Trait Icons
    await expect(alphaCard.locator('text=🧠')).toBeVisible();

    // Verify OmegaGrid card renders
    const omegaCard = page.locator('.group', { hasText: 'OmegaGrid' }).first();
    await expect(omegaCard).toBeVisible();
    await expect(omegaCard.locator('text=1200 ELO')).toBeVisible();
    await expect(omegaCard.locator('text=RARE')).toBeVisible();
  });

  test('clicking an Agent Card navigates to competitor profile', async ({ page }) => {
    await page.goto('/roster');

    // Wait for the card to be visible
    const alphaCard = page.locator('.group', { hasText: 'AlphaScout' }).first();
    await expect(alphaCard).toBeVisible();

    // Click the card
    await alphaCard.click();

    // Verify navigation
    await expect(page).toHaveURL(/.*\/arena\/competitors\/AlphaScout/);
  });
});
