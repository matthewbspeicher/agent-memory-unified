import { test, expect } from '@playwright/test';

test.describe('Knowledge Graph', () => {
  test('should render nodes and edges with metadata', async ({ page }) => {
    // Intercept the API call to return mock graph data with metadata
    await page.route('**/v1/agents/me/graph', async (route) => {
      await route.fulfill({
        status: 200,
        json: {
          data: {
            nodes: [
              { id: '1', summary: 'Strategy A', type: 'strategy' },
              { id: '2', summary: 'Observation B', type: 'memory' }
            ],
            links: [
              { source: '1', target: '2', relation: 'supports', metadata: { rationale: 'Observation confirms strategy trend' } }
            ]
          }
        }
      });
    });

    await page.goto('/graph');

    // Wait for the canvas to render
    const canvas = page.locator('canvas');
    await expect(canvas).toBeVisible();

    // Verify title or key overlay elements
    await expect(page.locator('text=Neural Mesh')).toBeVisible();
    await expect(page.locator('text=Observation B')).toBeVisible(); // Mocked node label
  });
});
