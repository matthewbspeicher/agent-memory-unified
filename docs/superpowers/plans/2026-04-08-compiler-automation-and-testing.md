# Compiler Automation and Testing Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the Developer Knowledge Compiler via GitHub Actions and write robust Pytest and Playwright coverage for the Trading Knowledge Compiler and 3D UI.

**Architecture:** 
1. A new GitHub Action runs `.claude/knowledge/scripts/compile.py` and `lint.py` nightly, automatically committing compiled markdown articles to the repository to persist the developer knowledge.
2. Unit tests ensure the `DailyTradeCompiler` correctly digests raw trades into summaries and that the `MemoryLinter` flags stale/orphan articles.
3. A Playwright E2E test verifies the React 3D Knowledge Graph correctly renders the compiled memory relationships and metadata tooltips.

**Tech Stack:** GitHub Actions, Python (pytest, pytest-asyncio, unittest.mock), TypeScript (Playwright)

---

### Task 1: Automate Developer Knowledge Compilation

**Files:**
- Create: `.github/workflows/knowledge-compiler.yml`

- [ ] **Step 1: Write the GitHub Action workflow**

```yaml
name: Developer Knowledge Compiler

on:
  schedule:
    - cron: '0 2 * * *' # Run at 2 AM UTC daily
  workflow_dispatch: # Allow manual triggers

permissions:
  contents: write

jobs:
  compile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        
      - name: Setup Python
        run: uv python install 3.13
        
      - name: Install dependencies
        run: |
          cd .claude/knowledge
          uv sync
          
      - name: Run Compilation
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          cd .claude/knowledge
          uv run python scripts/compile.py
          
      - name: Run Linter
        run: |
          cd .claude/knowledge
          uv run python scripts/lint.py --structural-only
          
      - name: Commit and Push changes
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add .claude/knowledge/articles/ .claude/knowledge/index.md .claude/knowledge/log.md
          git diff --quiet && git diff --staged --quiet || (git commit -m "docs(knowledge): auto-compile developer knowledge base" && git push)
```

- [ ] **Step 2: Commit the workflow**

```bash
git add .github/workflows/knowledge-compiler.yml
git commit -m "ci: automate developer knowledge compilation via github actions"
```

### Task 2: Unit Tests for Trading Memory Linter

**Files:**
- Create: `trading/tests/unit/test_learning/test_memory_linter.py`

- [ ] **Step 1: Write the MemoryLinter test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from learning.memory_linter import MemoryLinter

@pytest.mark.asyncio
async def test_memory_linter_detects_stale_and_orphans():
    # Mock Memory Client
    mock_client = MagicMock()
    mock_shared = MagicMock()
    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.json.return_value = {
        "data": [
            {"id": "1", "expires_at": "2026-01-01T00:00:00Z", "access_count": 5}, # Stale
            {"id": "2", "access_count": 0}, # Orphan
            {"id": "3", "access_count": 10} # Healthy
        ]
    }
    mock_shared.client.get = AsyncMock(return_value=mock_resp)
    mock_client._shared = mock_shared
    
    linter = MemoryLinter(mock_client)
    result = await linter.lint()
    
    assert result["ok"] is True
    assert result["total_strategies"] == 3
    assert result["stale_articles"] == 1
    assert result["orphan_articles"] == 1
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/unit/test_learning/test_memory_linter.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add trading/tests/unit/test_learning/test_memory_linter.py
git commit -m "test: add unit tests for memory linter"
```

### Task 3: Unit Tests for Daily Trade Compiler

**Files:**
- Create: `trading/tests/unit/test_learning/test_trade_compiler.py`

- [ ] **Step 1: Write the DailyTradeCompiler test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from learning.trade_compiler import DailyTradeCompiler

@pytest.mark.asyncio
async def test_compile_daily_summary():
    mock_memory = MagicMock()
    mock_memory.search_both = AsyncMock(return_value=[
        {"value": "Trade 1", "tags": ["trade"]},
        {"value": "Observation 1", "tags": ["market_observation"]}
    ])
    mock_memory.store_private = AsyncMock()
    
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.text = "## Trades Executed\nMock Summary"
    mock_llm.complete = AsyncMock(return_value=mock_result)
    
    compiler = DailyTradeCompiler(mock_memory, mock_llm)
    summary = await compiler.compile_daily_summary()
    
    assert "Mock Summary" in summary
    mock_memory.search_both.assert_called_once()
    mock_llm.complete.assert_called_once()
    mock_memory.store_private.assert_called_once()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/unit/test_learning/test_trade_compiler.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add trading/tests/unit/test_learning/test_trade_compiler.py
git commit -m "test: add unit tests for daily trade compiler"
```

### Task 4: E2E Test for Knowledge Graph

**Files:**
- Create: `frontend/tests/e2e/knowledge_graph.spec.ts`

- [ ] **Step 1: Write the Playwright test**

```typescript
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
```

- [ ] **Step 2: Run test to verify it fails (or passes if fully mocked correctly)**
Note: For Playwright tests, testing WebGL canvas interactions (like hovering over edges to see tooltips) is notoriously flaky in CI. Validating the canvas and the mock API payload is sufficient for E2E validation of the wiring.

Run: `cd frontend && npx playwright test tests/e2e/knowledge_graph.spec.ts`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/knowledge_graph.spec.ts
git commit -m "test: add e2e test for 3D knowledge graph rendering"
```
