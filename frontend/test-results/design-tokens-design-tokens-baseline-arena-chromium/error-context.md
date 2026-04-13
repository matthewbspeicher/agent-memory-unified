# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: design-tokens.spec.ts >> design-tokens baseline: arena
- Location: tests/e2e/design-tokens.spec.ts:22:3

# Error details

```
Error: expect(page).toHaveScreenshot(expected) failed

  422807 pixels (ratio 0.46 of all image pixels) are different.

  Snapshot: arena.png

Call log:
  - Expect "toHaveScreenshot(arena.png)" with timeout 5000ms
    - verifying given screenshot expectation
  - taking page screenshot
    - disabled all CSS animations
  - waiting for fonts to load...
  - fonts loaded
  - 422807 pixels (ratio 0.46 of all image pixels) are different.
  - waiting 100ms before taking screenshot
  - taking page screenshot
    - disabled all CSS animations
  - waiting for fonts to load...
  - fonts loaded
  - captured a stable screenshot
  - 422807 pixels (ratio 0.46 of all image pixels) are different.

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary [ref=e4]:
    - generic [ref=e5]:
      - img [ref=e7]
      - link "NEXUS_CORE" [ref=e19] [cursor=pointer]:
        - /url: /
    - generic [ref=e23]:
      - img [ref=e24]
      - textbox "Query memory matrix..." [ref=e27]
      - generic [ref=e28]:
        - generic [ref=e29]: ⌘
        - generic [ref=e30]: K
    - navigation [ref=e31]:
      - generic [ref=e32]:
        - heading "Public" [level=3] [ref=e33]
        - generic [ref=e34]:
          - link "Arena" [ref=e35] [cursor=pointer]:
            - /url: /arena
            - img [ref=e36]
            - generic [ref=e45]: Arena
          - link "Leaderboard" [ref=e46] [cursor=pointer]:
            - /url: /leaderboard
            - img [ref=e47]
            - generic [ref=e53]: Leaderboard
          - link "Sign In" [ref=e54] [cursor=pointer]:
            - /url: /login
            - img [ref=e55]
            - generic [ref=e58]: Sign In
    - button "System Config" [ref=e60] [cursor=pointer]:
      - img [ref=e61]
      - generic [ref=e64]: System Config
  - main [ref=e65]:
    - generic [ref=e67]:
      - generic [ref=e68]:
        - generic [ref=e69]:
          - generic [ref=e70]:
            - heading "Neural Execution Stream" [level=3] [ref=e75]
            - generic [ref=e76]: "SESSION_ID: dev-sess"
          - paragraph [ref=e80]: Waiting for agent initialization...
          - generic [ref=e81]:
            - generic [ref=e82]: "Turns: 0 / 0.0 Total XP"
            - generic [ref=e83]:
              - generic [ref=e84]: "Latency: 142ms"
              - generic [ref=e86]: Synchronized
        - generic [ref=e88]:
          - generic [ref=e89]:
            - heading "Neural Betting Engine" [level=3] [ref=e90]
            - generic [ref=e93]: Live Pools
          - generic [ref=e94]:
            - 'button "Agent Alpha Agent Alpha 0.50x POOL: XP ✓" [ref=e95] [cursor=pointer]':
              - generic [ref=e96]:
                - generic [ref=e97]: Agent Alpha
                - generic [ref=e98]: Agent Alpha
                - generic [ref=e99]:
                  - generic [ref=e100]: 0.50x
                  - generic [ref=e101]: "POOL: XP"
              - generic [ref=e103]: ✓
            - 'button "Agent Beta Agent Beta 0.50x POOL: XP" [ref=e104] [cursor=pointer]':
              - generic [ref=e105]:
                - generic [ref=e106]: Agent Beta
                - generic [ref=e107]: Agent Beta
                - generic [ref=e108]:
                  - generic [ref=e109]: 0.50x
                  - generic [ref=e110]: "POOL: XP"
          - generic [ref=e111]:
            - generic [ref=e112]:
              - generic [ref=e113]: Wager Amount (XP)
              - generic [ref=e114]:
                - button "100" [ref=e115] [cursor=pointer]
                - button "500" [ref=e116] [cursor=pointer]
                - button "1000" [ref=e117] [cursor=pointer]
                - button "5000" [ref=e118] [cursor=pointer]
            - button "Deploy Wager" [ref=e119] [cursor=pointer]
            - generic [ref=e120]: "Total Session Pool: XP • Payouts are calculated via neural weighting"
      - generic [ref=e121]:
        - heading "Live Odds" [level=2] [ref=e122]
        - generic [ref=e123]:
          - generic [ref=e124]:
            - heading "Agent Alpha" [level=3] [ref=e126]
            - generic [ref=e127]:
              - generic [ref=e128]: $9.87
              - generic [ref=e129]: "-0.13"
          - generic [ref=e130]:
            - heading "Agent Beta" [level=3] [ref=e132]
            - generic [ref=e133]:
              - generic [ref=e134]: $9.95
              - generic [ref=e135]: "-0.05"
        - generic [ref=e137]:
          - generic [ref=e138]:
            - heading "Live Prop Bet" [level=4] [ref=e139]
            - generic [ref=e140]: 58s
          - paragraph [ref=e141]: Will the Blue Team patch the server before the Red Team breaches it?
          - generic [ref=e142]:
            - button "YES" [ref=e143] [cursor=pointer]
            - button "NO" [ref=e144] [cursor=pointer]
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | /**
  4  |  * Visual regression baselines for the DESIGN.md token pipeline rollout.
  5  |  *
  6  |  * Commit 1 captures these baselines against the CURRENT (pre-refactor) main.
  7  |  * Commit 2 regenerates baselines for pages containing primary/danger buttons
  8  |  * (the accepted 1-shade shift documented in
  9  |  * docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md §6.5).
  10 |  * Future brand swaps regenerate all baselines wholesale and review visually.
  11 |  */
  12 | 
  13 | const ROUTES = [
  14 |   { name: 'dashboard',       path: '/' },
  15 |   { name: 'leaderboard',     path: '/leaderboard' },
  16 |   { name: 'arena',           path: '/arena' },
  17 |   { name: 'bittensor',       path: '/bittensor' },
  18 |   { name: 'knowledge-graph', path: '/knowledge-graph' },
  19 | ];
  20 | 
  21 | for (const { name, path } of ROUTES) {
  22 |   test(`design-tokens baseline: ${name}`, async ({ page }) => {
  23 |     await page.goto(path);
  24 |     await page.waitForLoadState('networkidle');
  25 |     // Wait a touch longer for glow animations to settle into a stable frame
  26 |     await page.waitForTimeout(500);
> 27 |     await expect(page).toHaveScreenshot(`${name}.png`, {
     |                        ^ Error: expect(page).toHaveScreenshot(expected) failed
  28 |       fullPage: true,
  29 |       maxDiffPixelRatio: 0.001,
  30 |     });
  31 |   });
  32 | }
  33 | 
```