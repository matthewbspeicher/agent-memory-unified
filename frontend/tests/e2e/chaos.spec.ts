import { test, expect } from '@playwright/test';

test.describe('Chaos Engineering tests - Resilience against backend failures', () => {
    
    test('API 500 Error test on Memory Load gracefully shows error state', async ({ page }) => {
        // Intercept memories API and force a 500 status
        await page.route('**/api/memories*', async route => {
            await route.fulfill({
                status: 500,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'Internal Server Error' })
            });
        });

        await page.goto('/memories');
        
        // Assert resilient frontend parsing of error handling
        const errorAlert = page.locator('.error-message, [role="alert"]').first();
        await expect(errorAlert).toBeVisible();
    });

    test('Latency test on Bittensor /api/bittensor/status shows loading state', async ({ page }) => {
        // Simulate 3 seconds of latency
        await page.route('**/api/bittensor/status', async route => {
            await new Promise(resolve => setTimeout(resolve, 3000));
            const response = await route.fetch();
            await route.fulfill({
                response,
            });
        });

        // Use a test that doesn't strictly freeze
        await page.goto('/bittensor');
        
        // Assert that loading indicator is shown
        const loader = page.locator('.loading-spinner, [aria-busy="true"], .skeleton-loader').first();
        await expect(loader).toBeVisible();
    });

    test('Malformed JSON response test on Trade processing handles exception gracefully', async ({ page }) => {
        // Intercept trades API and return malformed JSON
        await page.route('**/api/trades*', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: '{"data": [{"id": 1, "ticker": "AAPL" ' // Malformed JSON
            });
        });

        await page.goto('/trades');

        // Assert frontend doesn't crash completely, error or empty state
        const errorBoundary = page.locator('.error-message, [role="alert"]').first();
        await expect(errorBoundary).toBeVisible();
    });
});
