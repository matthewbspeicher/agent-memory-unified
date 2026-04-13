# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: fleet_gamification.spec.ts >> Fleet Gamification & Roster Journey >> should load the Agent Roster and display gamified Agent Cards
- Location: tests/e2e/fleet_gamification.spec.ts:84:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.cursor-pointer').filter({ hasText: 'AlphaScout' }).first().locator('text=Lv.25')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('.cursor-pointer').filter({ hasText: 'AlphaScout' }).first().locator('text=Lv.25')

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
      - generic [ref=e117]:
        - generic [ref=e118] [cursor=pointer]:
          - generic [ref=e119]: Legendary Card
          - generic [ref=e120]:
            - generic [ref=e121]:
              - generic "Level 25" [ref=e122]: "25"
              - generic "diamond" [ref=e123]:
                - generic [ref=e124]: ◆
                - text: DIA
            - generic [ref=e125]:
              - generic [ref=e126]: AlphaScout
              - generic [ref=e127]:
                - generic [ref=e128]: "1850"
                - generic [ref=e129]: ELO
            - generic [ref=e131]:
              - generic [ref=e132]: Level 25
              - generic [ref=e133]: 62500 XP
            - generic [ref=e136]:
              - generic [ref=e137]:
                - generic [ref=e138]: "150"
                - generic [ref=e139]: Matches
              - generic [ref=e140]:
                - generic [ref=e141]: 0.66%
                - generic [ref=e142]: Win Rate
              - generic [ref=e143]:
                - generic [ref=e144]: "12"
                - generic [ref=e145]: Best Streak
            - generic [ref=e146]:
              - generic [ref=e147]: Traits
              - generic [ref=e148]:
                - generic "🧠" [ref=e149]
                - generic "🛡️" [ref=e150]
                - generic "⚡" [ref=e151]
            - generic [ref=e152]:
              - generic [ref=e153]: Recent Achievements
              - generic "On Fire" [ref=e155]: stre
          - generic [ref=e156]:
            - generic [ref=e157]: v1.0.0
            - generic [ref=e158]: 14 achievements
        - generic [ref=e159] [cursor=pointer]:
          - generic [ref=e160]: Rare Card
          - generic [ref=e161]:
            - generic [ref=e162]:
              - generic "Level 25" [ref=e163]: "25"
              - generic "silver" [ref=e164]:
                - generic [ref=e165]: ◆
                - text: SLV
            - generic [ref=e166]:
              - generic [ref=e167]: OmegaGrid
              - generic [ref=e168]:
                - generic [ref=e169]: "1200"
                - generic [ref=e170]: ELO
            - generic [ref=e172]:
              - generic [ref=e173]: Level 25
              - generic [ref=e174]: 62500 XP
            - generic [ref=e177]:
              - generic [ref=e178]:
                - generic [ref=e179]: "150"
                - generic [ref=e180]: Matches
              - generic [ref=e181]:
                - generic [ref=e182]: 0.66%
                - generic [ref=e183]: Win Rate
              - generic [ref=e184]:
                - generic [ref=e185]: "12"
                - generic [ref=e186]: Best Streak
            - generic [ref=e187]:
              - generic [ref=e188]: Traits
              - generic [ref=e189]:
                - generic "🧠" [ref=e190]
                - generic "🛡️" [ref=e191]
                - generic "⚡" [ref=e192]
            - generic [ref=e193]:
              - generic [ref=e194]: Recent Achievements
              - generic "On Fire" [ref=e196]: stre
          - generic [ref=e197]:
            - generic [ref=e198]: v1.0.0
            - generic [ref=e199]: 14 achievements
```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test';
  2   | 
  3   | test.describe('Fleet Gamification & Roster Journey', () => {
  4   |   test.beforeEach(async ({ page }) => {
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
  15  |         headers: { 
  16  |           'Access-Control-Allow-Origin': '*',
  17  |           'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  18  |           'Access-Control-Allow-Headers': '*'
  19  |         },
  20  |         body: JSON.stringify({ data: { id: 'admin1', name: 'Admin Coach' } }),
  21  |       });
  22  |     });
  23  | 
  24  |     // Mock the fleet/agents list
  25  |     await page.route('**/api/v1/agents/directory', async route => {
  26  |       await route.fulfill({
  27  |         status: 200,
  28  |         contentType: 'application/json',
  29  |         headers: { 
  30  |           'Access-Control-Allow-Origin': '*',
  31  |           'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  32  |           'Access-Control-Allow-Headers': '*'
  33  |         },
  34  |         body: JSON.stringify({ data: [
  35  |           { name: 'AlphaScout', status: 'active' },
  36  |           { name: 'OmegaGrid', status: 'active' }
  37  |         ]}),
  38  |       });
  39  |     });
  40  | 
  41  |     // Mock individual Agent Cards
  42  |     await page.route('**/engine/v1/competitors/*/card*', async route => {
  43  |       const url = route.request().url();
  44  |       const name = url.includes('AlphaScout') ? 'AlphaScout' : 'OmegaGrid';
  45  |       const rarity = url.includes('AlphaScout') ? 'legendary' : 'rare';
  46  |       const elo = url.includes('AlphaScout') ? 1850 : 1200;
  47  |       const tier = url.includes('AlphaScout') ? 'diamond' : 'silver';
  48  | 
  49  |       await route.fulfill({
  50  |         status: 200,
  51  |         contentType: 'application/json',
  52  |         headers: { 
  53  |           'Access-Control-Allow-Origin': '*',
  54  |           'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  55  |           'Access-Control-Allow-Headers': '*'
  56  |         },
  57  |         body: JSON.stringify({
  58  |           competitor_id: `${name}-id`,
  59  |           name: name,
  60  |           level: 25,
  61  |           tier: tier,
  62  |           elo: elo,
  63  |           rarity: rarity,
  64  |           stats: {
  65  |             matches: 150,
  66  |             wins: 100,
  67  |             losses: 50,
  68  |             win_rate: 0.66,
  69  |             current_streak: 5,
  70  |             best_streak: 12,
  71  |             total_xp: 62500,
  72  |             achievement_count: 14,
  73  |             traits_unlocked: 3,
  74  |             calibration_score: 0.92
  75  |           },
  76  |           trait_icons: ['🧠', '🛡️', '⚡'],
  77  |           achievement_badges: [{ type: 'streak_5', name: 'On Fire', tier: 'gold' }],
  78  |           card_version: '1.0.0'
  79  |         }),
  80  |       });
  81  |     });
  82  |   });
  83  | 
  84  |   test('should load the Agent Roster and display gamified Agent Cards', async ({ page }) => {
  85  |     await page.goto('/roster');
  86  | 
  87  |     // Verify page header
  88  |     await expect(page.locator('h1')).toContainText('Agent Roster');
  89  |     await expect(page.locator('text=Manage your fleet')).toBeVisible();
  90  | 
  91  |     // Verify AlphaScout card renders with specific gamified elements
  92  |     const alphaCard = page.locator('.cursor-pointer', { hasText: 'AlphaScout' }).first();
  93  |     await expect(alphaCard).toBeVisible();
  94  |     
  95  |     // Check level badge and XP
> 96  |     await expect(alphaCard.locator('text=Lv.25')).toBeVisible();
      |                                                   ^ Error: expect(locator).toBeVisible() failed
  97  |     
  98  |     // Check ELO and Tier
  99  |     await expect(alphaCard.locator('text=1850 ELO')).toBeVisible();
  100 |     await expect(alphaCard.locator('text=DIAMOND')).toBeVisible();
  101 |     
  102 |     // Check Rarity banner
  103 |     await expect(alphaCard.locator('text=LEGENDARY')).toBeVisible();
  104 |     
  105 |     // Check Trait Icons
  106 |     await expect(alphaCard.locator('text=🧠')).toBeVisible();
  107 | 
  108 |     // Verify OmegaGrid card renders
  109 |     const omegaCard = page.locator('.group', { hasText: 'OmegaGrid' }).first();
  110 |     await expect(omegaCard).toBeVisible();
  111 |     await expect(omegaCard.locator('text=1200 ELO')).toBeVisible();
  112 |     await expect(omegaCard.locator('text=RARE')).toBeVisible();
  113 |   });
  114 | 
  115 |   test('clicking an Agent Card navigates to competitor profile', async ({ page }) => {
  116 |     await page.goto('/roster');
  117 | 
  118 |     // Wait for the card to be visible
  119 |     const alphaCard = page.locator('.cursor-pointer', { hasText: 'AlphaScout' }).first();
  120 |     await expect(alphaCard).toBeVisible();
  121 | 
  122 |     // Click the card
  123 |     await alphaCard.click();
  124 | 
  125 |     // Verify navigation
  126 |     await expect(page).toHaveURL(/.*\/arena\/competitors\/AlphaScout/);
  127 |   });
  128 | });
  129 | 
```