# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: arena.spec.ts >> Arena Match & Betting Journey >> Arena Match visualizes terminal execution and betting pool
- Location: tests/e2e/arena.spec.ts:119:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('text=Escape Room Protocol')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('text=Escape Room Protocol')

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
    - generic [ref=e110]: Failed to synchronize match log.
```

# Test source

```ts
  23  |         contentType: 'application/json',
  24  |         body: JSON.stringify({
  25  |           leaderboard: [
  26  |             { id: '1', name: 'AlphaScout', elo: 1850, tier: 'diamond', type: 'agent', matches_count: 150 },
  27  |             { id: '2', name: 'OmegaGrid', elo: 1200, tier: 'silver', type: 'agent', matches_count: 50 }
  28  |           ],
  29  |           competitor_count: 2
  30  |         }),
  31  |       });
  32  |     });
  33  | 
  34  |     // Mock Match Details
  35  |     await page.route('**/engine/v1/matches/match-123', async route => {
  36  |       await route.fulfill({
  37  |         status: 200,
  38  |         contentType: 'application/json',
  39  |         body: JSON.stringify({
  40  |           id: 'match-123',
  41  |           status: 'in_progress',
  42  |           agent_1_id: '1',
  43  |           agent_2_id: '2',
  44  |           winner_id: null,
  45  |           score_1: null,
  46  |           score_2: null,
  47  |           judge_feedback: null,
  48  |           challenge: {
  49  |             id: 'c1',
  50  |             gym_id: 'g1',
  51  |             title: 'Escape Room Protocol',
  52  |             prompt: 'Solve the simulated cyber breach',
  53  |             difficulty_level: 'expert',
  54  |             xp_reward: 1000,
  55  |             max_turns: 50
  56  |           },
  57  |           agent1: { id: '1', name: 'AlphaScout' },
  58  |           agent2: { id: '2', name: 'OmegaGrid' },
  59  |           sessions: [
  60  |             {
  61  |               id: 's1',
  62  |               agent_id: '1',
  63  |               status: 'in_progress',
  64  |               turns: [
  65  |                 {
  66  |                   id: 't1',
  67  |                   turn_number: 1,
  68  |                   input: '{"tool_call": "run_sql_query", "args": {"query": "SELECT * FROM logs"}}',
  69  |                   output: '3 rows returned',
  70  |                   score: 85,
  71  |                   feedback: 'Good initial exploration.'
  72  |                 }
  73  |               ]
  74  |             }
  75  |           ],
  76  |           created_at: new Date().toISOString()
  77  |         }),
  78  |       });
  79  |     });
  80  | 
  81  |     // Mock Betting Pool
  82  |     await page.route('**/engine/v1/matches/match-123/pool', async route => {
  83  |       await route.fulfill({
  84  |         status: 200,
  85  |         contentType: 'application/json',
  86  |         body: JSON.stringify({
  87  |           match_id: 'match-123',
  88  |           total_pool: 24500,
  89  |           competitor_a_pool: 15925,
  90  |           competitor_b_pool: 8575,
  91  |           competitor_a_bettors: 14,
  92  |           competitor_b_bettors: 8,
  93  |           competitor_a_odds: 0.65,
  94  |           competitor_b_odds: 0.35,
  95  |           status: 'open'
  96  |         }),
  97  |       });
  98  |     });
  99  | 
  100 |     // Mock place bet mutation
  101 |     await page.route('**/engine/v1/matches/match-123/bet', async route => {
  102 |       await route.fulfill({
  103 |         status: 200,
  104 |         contentType: 'application/json',
  105 |         body: JSON.stringify({ success: true, bet_id: 'bet-123' })
  106 |       });
  107 |     });
  108 |   });
  109 | 
  110 |   test('should load Arena Leaderboard', async ({ page }) => {
  111 |     await page.goto('/arena');
  112 |     await expect(page.locator('h1')).toContainText('Arena Leaderboard');
  113 |     
  114 |     // Check leaderboard rows
  115 |     await expect(page.locator('text=AlphaScout').first()).toBeVisible();
  116 |     await expect(page.locator('text=1850').first()).toBeVisible();
  117 |   });
  118 | 
  119 |   test('Arena Match visualizes terminal execution and betting pool', async ({ page }) => {
  120 |     await page.goto('/arena/matches/match-123');
  121 | 
  122 |     // Wait for challenge info to render
> 123 |     await expect(page.locator('text=Escape Room Protocol')).toBeVisible();
      |                                                             ^ Error: expect(locator).toBeVisible() failed
  124 | 
  125 |     // Verify Betting Pool Widget renders
  126 |     await expect(page.locator('text=Arena Betting Pool')).toBeVisible();
  127 |     await expect(page.locator('text=POOL: 24,500 XP')).toBeVisible();
  128 |     await expect(page.locator('text=65% implied')).toBeVisible();
  129 | 
  130 |     // Interact with betting UI
  131 |     const wagerInput = page.locator('input[type="number"]');
  132 |     await expect(wagerInput).toBeVisible();
  133 |     await wagerInput.fill('500');
  134 | 
  135 |     // Place a bet and listen for the mocked alert (since our mock component uses alert)
  136 |     page.on('dialog', async dialog => {
  137 |       expect(dialog.message()).toContain('Bet of 500 XP placed successfully!');
  138 |       await dialog.accept();
  139 |     });
  140 | 
  141 |     const betButton = page.locator('text=Bet AlphaScout');
  142 |     await betButton.click();
  143 | 
  144 |     // Verify Terminal Output Rendering for Escape Rooms
  145 |     await expect(page.locator('text=Terminal execution')).toBeVisible();
  146 |     await expect(page.locator('text=> run_sql_query')).toBeVisible();
  147 |     await expect(page.locator('text=3 rows returned')).toBeVisible();
  148 |   });
  149 | });
  150 | 
```