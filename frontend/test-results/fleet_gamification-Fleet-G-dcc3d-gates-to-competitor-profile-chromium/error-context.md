# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: fleet_gamification.spec.ts >> Fleet Gamification & Roster Journey >> clicking an Agent Card navigates to competitor profile
- Location: tests/e2e/fleet_gamification.spec.ts:100:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.group').filter({ hasText: 'AlphaScout' }).first()
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('.group').filter({ hasText: 'AlphaScout' }).first()

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
        - heading "Ops" [level=3] [ref=e33]
        - generic [ref=e34]:
          - link "Mission Control" [ref=e35] [cursor=pointer]:
            - /url: /mission-control
            - img [ref=e36]
            - generic [ref=e41]: Mission Control
          - link "Dashboard" [ref=e42] [cursor=pointer]:
            - /url: /dashboard
            - img [ref=e43]
            - generic [ref=e45]: Dashboard
          - link "Agent Roster" [ref=e46] [cursor=pointer]:
            - /url: /roster
            - img [ref=e47]
            - generic [ref=e52]: Agent Roster
          - link "Bittensor Node" [ref=e53] [cursor=pointer]:
            - /url: /bittensor
            - img [ref=e54]
            - generic [ref=e57]: Bittensor Node
      - generic [ref=e58]:
        - heading "Community" [level=3] [ref=e59]
        - generic [ref=e60]:
          - link "Arena" [ref=e61] [cursor=pointer]:
            - /url: /arena
            - img [ref=e62]
            - generic [ref=e71]: Arena
          - link "Commons" [ref=e72] [cursor=pointer]:
            - /url: /commons
            - img [ref=e73]
            - generic [ref=e76]: Commons
          - link "Leaderboard" [ref=e77] [cursor=pointer]:
            - /url: /leaderboard
            - img [ref=e78]
            - generic [ref=e84]: Leaderboard
      - generic [ref=e85]:
        - heading "System" [level=3] [ref=e86]
        - generic [ref=e87]:
          - link "Explorer" [ref=e88] [cursor=pointer]:
            - /url: /explorer
            - img [ref=e89]
            - generic [ref=e92]: Explorer
          - link "Webhooks" [ref=e93] [cursor=pointer]:
            - /url: /webhooks
            - img [ref=e94]
            - generic [ref=e96]: Webhooks
          - link "Workspaces" [ref=e97] [cursor=pointer]:
            - /url: /workspaces
            - img [ref=e98]
            - generic [ref=e100]: Workspaces
    - button "Exit System" [ref=e103] [cursor=pointer]:
      - img [ref=e104]
      - generic [ref=e107]: Exit System
  - main [ref=e108]:
    - generic [ref=e110]:
      - generic [ref=e112]:
        - heading "Agent Roster" [level=1] [ref=e113]
        - paragraph [ref=e114]: Manage your fleet of autonomous trading agents. Equip traits and monitor achievements.
      - generic [ref=e117]: No agents registered in the fleet.
```

# Test source

```ts
  5   |     // Setup authentication token in localStorage
  6   |     await page.addInitScript(() => {
  7   |       window.localStorage.setItem('auth_token', 'test-token');
  8   |     });
  9   | 
  10  |     // Mock the user profile
  11  |     await page.route('**/api/v1/agents/me', async route => {
  12  |       await route.fulfill({
  13  |         status: 200,
  14  |         contentType: 'application/json',
  15  |         body: JSON.stringify({ data: { id: 'admin1', name: 'Admin Coach' } }),
  16  |       });
  17  |     });
  18  | 
  19  |     // Mock the fleet/agents list
  20  |     await page.route('**/api/v1/agents', async route => {
  21  |       await route.fulfill({
  22  |         status: 200,
  23  |         contentType: 'application/json',
  24  |         body: JSON.stringify({ data: [
  25  |           { name: 'AlphaScout', status: 'active' },
  26  |           { name: 'OmegaGrid', status: 'active' }
  27  |         ]}),
  28  |       });
  29  |     });
  30  | 
  31  |     // Mock individual Agent Cards
  32  |     await page.route('**/engine/v1/competitors/*/card*', async route => {
  33  |       const url = route.request().url();
  34  |       const name = url.includes('AlphaScout') ? 'AlphaScout' : 'OmegaGrid';
  35  |       const rarity = url.includes('AlphaScout') ? 'legendary' : 'rare';
  36  |       const elo = url.includes('AlphaScout') ? 1850 : 1200;
  37  |       const tier = url.includes('AlphaScout') ? 'diamond' : 'silver';
  38  | 
  39  |       await route.fulfill({
  40  |         status: 200,
  41  |         contentType: 'application/json',
  42  |         body: JSON.stringify({
  43  |           competitor_id: `${name}-id`,
  44  |           name: name,
  45  |           level: 25,
  46  |           tier: tier,
  47  |           elo: elo,
  48  |           rarity: rarity,
  49  |           stats: {
  50  |             matches: 150,
  51  |             wins: 100,
  52  |             losses: 50,
  53  |             win_rate: 0.66,
  54  |             current_streak: 5,
  55  |             best_streak: 12,
  56  |             total_xp: 62500,
  57  |             achievement_count: 14,
  58  |             traits_unlocked: 3,
  59  |             calibration_score: 0.92
  60  |           },
  61  |           trait_icons: ['🧠', '🛡️', '⚡'],
  62  |           achievement_badges: [{ type: 'streak_5', name: 'On Fire', tier: 'gold' }],
  63  |           card_version: '1.0.0'
  64  |         }),
  65  |       });
  66  |     });
  67  |   });
  68  | 
  69  |   test('should load the Agent Roster and display gamified Agent Cards', async ({ page }) => {
  70  |     await page.goto('/roster');
  71  | 
  72  |     // Verify page header
  73  |     await expect(page.locator('h1')).toContainText('Agent Roster');
  74  |     await expect(page.locator('text=Manage your fleet')).toBeVisible();
  75  | 
  76  |     // Verify AlphaScout card renders with specific gamified elements
  77  |     const alphaCard = page.locator('.group', { hasText: 'AlphaScout' }).first();
  78  |     await expect(alphaCard).toBeVisible();
  79  |     
  80  |     // Check level badge and XP
  81  |     await expect(alphaCard.locator('text=Lv.25')).toBeVisible();
  82  |     
  83  |     // Check ELO and Tier
  84  |     await expect(alphaCard.locator('text=1850 ELO')).toBeVisible();
  85  |     await expect(alphaCard.locator('text=DIAMOND')).toBeVisible();
  86  |     
  87  |     // Check Rarity banner
  88  |     await expect(alphaCard.locator('text=LEGENDARY')).toBeVisible();
  89  |     
  90  |     // Check Trait Icons
  91  |     await expect(alphaCard.locator('text=🧠')).toBeVisible();
  92  | 
  93  |     // Verify OmegaGrid card renders
  94  |     const omegaCard = page.locator('.group', { hasText: 'OmegaGrid' }).first();
  95  |     await expect(omegaCard).toBeVisible();
  96  |     await expect(omegaCard.locator('text=1200 ELO')).toBeVisible();
  97  |     await expect(omegaCard.locator('text=RARE')).toBeVisible();
  98  |   });
  99  | 
  100 |   test('clicking an Agent Card navigates to competitor profile', async ({ page }) => {
  101 |     await page.goto('/roster');
  102 | 
  103 |     // Wait for the card to be visible
  104 |     const alphaCard = page.locator('.group', { hasText: 'AlphaScout' }).first();
> 105 |     await expect(alphaCard).toBeVisible();
      |                             ^ Error: expect(locator).toBeVisible() failed
  106 | 
  107 |     // Click the card
  108 |     await alphaCard.click();
  109 | 
  110 |     // Verify navigation
  111 |     await expect(page).toHaveURL(/.*\/arena\/competitors\/AlphaScout/);
  112 |   });
  113 | });
  114 | 
```