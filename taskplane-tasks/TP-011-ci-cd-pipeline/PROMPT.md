# Task: TP-011 - CI/CD Pipeline

**Created:** 2026-04-07
**Size:** M

## Review Level: 1 (Plan Only)

**Assessment:** Infrastructure config, no production code changes. Existing ci.yml to extend.
**Score:** 2/8 — Blast radius: 1, Pattern novelty: 1, Security: 0, Reversibility: 0

## Canonical Task Folder

```
taskplane-tasks/TP-011-ci-cd-pipeline/
```

## Mission

Set up a comprehensive GitHub Actions CI/CD pipeline. There's already a `.github/workflows/ci.yml` — audit it and extend to cover: Python linting (ruff), Python tests, frontend build check, Docker image build, and optional deploy-on-merge.

## Dependencies

- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `.github/workflows/ci.yml` — existing CI config
- `CLAUDE.md` — dev environment details

## Environment

- **Workspace:** root
- **Services required:** None (GitHub Actions)

## File Scope

- `.github/workflows/ci.yml` (modified)
- `.github/workflows/deploy.yml` (new, optional)
- `trading/pyproject.toml` or `trading/ruff.toml` (linting config)

## Steps

### Step 0: Preflight
- [ ] Read existing ci.yml
- [ ] Check if ruff/linting config exists
- [ ] Identify test dependencies and Docker build requirements

### Step 1: Enhance CI Pipeline
- [ ] Add Python linting job (ruff)
- [ ] Add Python test job with PostgreSQL service container
- [ ] Add frontend build check job
- [ ] Add Docker image build job (build only, no push)
- [ ] Configure caching for pip and npm

### Step 2: Add Linting Config
- [ ] Create or update ruff config for trading/
- [ ] Fix any critical linting errors that block CI

### Step 3: Testing & Verification
- [ ] CI pipeline runs successfully on a test branch
- [ ] All jobs pass or have clear skip conditions

### Step 4: Documentation & Delivery
- [ ] Document CI pipeline in CLAUDE.md
- [ ] Discoveries logged

## Completion Criteria
- [ ] CI runs on every PR
- [ ] Lint, test, build jobs all configured
- [ ] Pipeline is green (or has tracked skip reasons)

## Git Commit Convention
- `feat(TP-011): complete Step N — description`

## Do NOT
- Add deploy-to-production without explicit approval
- Expose secrets in CI logs
- Make CI mandatory without green tests first

---

## Amendments (Added During Execution)
