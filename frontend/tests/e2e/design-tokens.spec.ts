import { test, expect } from '@playwright/test';

/**
 * Visual regression baselines for the DESIGN.md token pipeline rollout.
 *
 * Commit 1 captures these baselines against the CURRENT (pre-refactor) main.
 * Commit 2 regenerates baselines for pages containing primary/danger buttons
 * (the accepted 1-shade shift documented in
 * docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md §6.5).
 * Future brand swaps regenerate all baselines wholesale and review visually.
 */

const ROUTES = [
  { name: 'dashboard',       path: '/' },
  { name: 'leaderboard',     path: '/leaderboard' },
  { name: 'arena',           path: '/arena' },
  { name: 'bittensor',       path: '/bittensor' },
  { name: 'knowledge-graph', path: '/knowledge-graph' },
];

for (const { name, path } of ROUTES) {
  test(`design-tokens baseline: ${name}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    // Wait a touch longer for glow animations to settle into a stable frame
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot(`${name}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.001,
    });
  });
}
