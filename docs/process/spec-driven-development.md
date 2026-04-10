# Spec-Driven Development

> Adapted from [addyosmani/agent-skills/skills/spec-driven-development](https://github.com/addyosmani/agent-skills/blob/main/skills/spec-driven-development/SKILL.md) (MIT). Workflow structure preserved; the spec/plan/task locations and templates are reconciled with this repo's existing `docs/superpowers/specs/`, `docs/superpowers/plans/`, `docs/features/`, and `docs/adr/` conventions so we don't introduce a competing parallel system.

## Overview

Write a structured specification before writing any code. The spec is the shared source of truth between you and the human engineer — it defines what we're building, why, and how we'll know it's done. Code without a spec is guessing.

In this repo, "spec" is not a generic word. It maps to a specific directory and file naming convention that already exists:

- **Design specs** → `docs/superpowers/specs/YYYY-MM-DD-<name>-design.md`
- **Implementation plans** → `docs/superpowers/plans/YYYY-MM-DD-<name>.md`
- **Architecture decisions** → `docs/adr/NNNN-<name>.md` (see `reference_adr_convention` in user memory)
- **Feature state docs** → `docs/features/<feature>.md` (template at `docs/features/TEMPLATE.md`)

This skill explains *when* to use which artifact, *what* each one must contain, and *how* the existing `superpowers:brainstorming` → `superpowers:writing-plans` → `superpowers:executing-plans` skills hand off between them. **Do not invent a new top-level `SPEC.md` in the repo root** — that's the upstream addyosmani convention but it would collide with our existing layout.

## When to Use

- Starting a new feature, integration, or significant refactor
- Requirements are ambiguous, incomplete, or only exist as a vague chat message
- The change touches more than one of: `trading/`, `frontend/`, `taoshi-vanta/`, `shared/`, `scripts/`, `docker-compose.yml`
- About to make an architectural decision that would warrant an ADR
- The task is going to take more than ~30 minutes and ~3 files
- A new external integration (broker, exchange, data feed, LLM provider, MCP server)
- The user describes a feature in terms of *outcomes* without specifying the *mechanism* ("make the dashboard faster", "get the validator scoring properly", "add a new strategy")

**When NOT to use:**

- Single-line fixes, typo corrections
- Renaming a variable
- Updating a docstring or comment
- Bumping a dependency without behavior change
- Cleanup tasks scoped to one file

## The Gated Workflow

Spec-driven development has four phases. Do not advance to the next phase until the current one is validated by the user.

```
SPECIFY ──→ PLAN ──→ TASKS ──→ IMPLEMENT
   │          │        │           │
   ▼          ▼        ▼           ▼
 Human      Human    Human      Human
 reviews    reviews  reviews    reviews
```

These phases map cleanly onto the skills already installed:

| Phase | Existing skill that owns it | Output artifact in this repo |
|---|---|---|
| **SPECIFY** | `superpowers:brainstorming` → this skill | `docs/superpowers/specs/YYYY-MM-DD-<name>-design.md` |
| **PLAN** | `superpowers:writing-plans` | `docs/superpowers/plans/YYYY-MM-DD-<name>.md` |
| **TASKS** | `superpowers:writing-plans` (the plan IS the task list, broken down) | Same plan file, with `## Tasks` section using checkboxes |
| **IMPLEMENT** | `superpowers:executing-plans`, `superpowers:subagent-driven-development`, `superpowers:test-driven-development` | Code + commits + the plan file's checkbox progress |

The four phases are gated. **Each phase produces a reviewable artifact, and the human approves it before the next phase begins.** No skipping ahead.

### Phase 1: Specify

Start with a high-level vision. Ask the human clarifying questions until requirements are concrete.

**Surface assumptions immediately.** Before writing any spec content, list what you're assuming in a fenced block:

```
ASSUMPTIONS I'M MAKING:
1. The new strategy runs inside the existing agent framework, not as a sidecar service
2. Signals flow through the SignalBus, not directly to the broker
3. Configuration uses STA_* env vars per the project convention
4. Paper mode by default; live mode requires the existing TradingConfig invariants
5. New tables (if any) get added to scripts/init-trading-tables.sql
→ Correct me now or I'll proceed with these.
```

**Don't silently fill in ambiguous requirements.** The spec's entire purpose is to surface misunderstandings *before* code gets written. Assumptions are the most dangerous form of misunderstanding because they look like facts.

**The spec document covers six core areas.** This is the template for `docs/superpowers/specs/YYYY-MM-DD-<name>-design.md`:

```markdown
# <Feature Name> — Design

**Date:** YYYY-MM-DD
**Status:** draft | in-review | accepted | implemented | superseded
**Author:** Claude / human pair

---

## 1. Objective
What are we building and why? Who benefits? What does success look like?

User stories or acceptance criteria as bullet points. Include the *measurable* form of any
soft requirement ("dashboard is faster" → "dashboard p95 LCP < 2.5s on a 4G profile").

## 2. Tech Stack & Surface Area
Which parts of the repo this touches:
- `trading/<modules>` — describe
- `frontend/<modules>` — describe
- `taoshi-vanta/` — read-only, no changes (or call out if changes needed)
- New external integrations: <list with versions>
- New env vars (STA_*): <list>
- Database changes: <yes/no, link to migration>

## 3. Commands
Full executable commands an operator would run to use, test, or verify this feature.
Match the existing patterns in CLAUDE.md "Common Tasks" and "Testing" sections.

## 4. Project Layout
Where new files live, where new tests go, where new docs belong.
Reference CLAUDE.md "Architecture" as the canonical layout.

## 5. Code Style & Patterns
Concrete examples, not prose. One real Pydantic model > three paragraphs about validation.
Include:
- Pydantic v2 model for any new request body
- Structured logging via `log_event()` with the event types from ADR-0008
  (or a justification for adding a new event type)
- Type hints everywhere; no `Any` at module boundaries

## 6. Testing Strategy
- Which test directory (`trading/tests/unit/`, `trading/tests/integration/`, `frontend/tests/e2e/`)
- Which markers (`@pytest.mark.integration`, `@pytest.mark.live_paper`)
- What needs a real DB / Redis / IBKR vs what can be mocked
- What the verification step looks like for each task

## 7. Boundaries
Reference CLAUDE.md "Working Boundaries" as the source of truth. Add feature-specific items only:
- **Always do (for this feature):** ...
- **Ask first (for this feature):** ...
- **Never do (for this feature):** ...

## 8. Success Criteria
Specific, testable conditions that mean "done."
- [ ] All listed unit tests pass
- [ ] Integration test against real Postgres + Redis passes
- [ ] Manual check: <specific human verification>
- [ ] Documentation updated: <which files>
- [ ] If applicable: ADR written and added to docs/adr/

## 9. Open Questions
Anything unresolved that needs human input. Track here until answered, then promote to a decision in the relevant section.

## 10. Out of Scope
What this feature explicitly does NOT include. Saves arguments later.
```

**Reframe vague instructions as measurable success criteria.** This is one of the highest-value habits from the upstream skill:

```
REQUIREMENT: "Make the bittensor dashboard faster"

REFRAMED SUCCESS CRITERIA:
- /engine/v1/bittensor/status response time p95 < 200ms (currently ~800ms)
- Frontend dashboard initial render < 1.5s on local dev
- TaoshiBridge poll loop adds < 100ms per cycle to status response
- No regressions in existing pytest suite
→ Are these the right targets? Note: the 30s bridge poll interval is intentional
  per ADR-0007, so we're optimizing rendering and aggregation, not polling cadence.
```

The reframing also lets you cite ADRs and existing constraints, which catches the user's attention if you've misunderstood the constraint.

### Phase 2: Plan

With the validated spec, generate a technical implementation plan. The plan is a separate file at `docs/superpowers/plans/YYYY-MM-DD-<name>.md`. This is where `superpowers:writing-plans` takes over.

The plan should:

1. Identify the major components and their dependencies
2. Determine the implementation order — what must be built first
3. Note risks and mitigation strategies (especially around irreversible operations: weight setter, broker live mode, schema migrations)
4. Identify what can be parallelized via `superpowers:dispatching-parallel-agents` vs what must be sequential
5. Define verification checkpoints between phases (run the test suite, hit a real endpoint, check a log line)
6. Reference the `docs/process/source-driven-development.md` skill for any phase that touches an external library — this is where citations get added

The plan should be reviewable: the human should be able to read it and say "yes, that's the right approach" or "no, change X before implementation starts."

### Phase 3: Tasks

Break the plan into discrete, implementable tasks. In this repo, tasks live as a `## Tasks` section *inside* the plan file (not in a separate task tracker), using markdown checkboxes:

```markdown
## Tasks

- [ ] **T1: Add Pydantic model for the new strategy config**
  - Acceptance: `trading/strategies/<name>/config.py` defines `<Name>Config(BaseModel)` with all STA_* fields and validators
  - Verify: `pytest trading/tests/unit/strategies/test_<name>_config.py -v`
  - Files: `trading/strategies/<name>/config.py`, `trading/tests/unit/strategies/test_<name>_config.py`
  - Depends on: nothing
  - Process docs: source-driven-development (Pydantic v2 patterns)

- [ ] **T2: Wire the strategy into the agent framework**
  - Acceptance: New strategy appears in `trading/agents/agents.yaml`; runner picks it up
  - Verify: `make test-unit` plus a manual `docker compose restart trading` and check the status endpoint
  - Files: `trading/strategies/<name>/strategy.py`, `trading/agents/agents.yaml`
  - Depends on: T1
  - Process docs: source-driven-development (FastAPI/agent framework conventions)

- [ ] **T3: Add the integration test**
  - Acceptance: Integration test exercises real Postgres + Redis path
  - Verify: `pytest trading/tests/integration/strategies/test_<name>_integration.py -m integration -v`
  - Files: `trading/tests/integration/strategies/test_<name>_integration.py`
  - Depends on: T2
  - Process docs: test-driven-development (superpowers skill)
```

Rules for tasks:
- Each task should be completable in a single focused session
- Each task has explicit acceptance criteria — no hand-waving
- Each task has a concrete `Verify:` command (a `pytest` invocation, a `make` target, a `curl`, or a manual check)
- No task should require changing more than ~5 files; if it does, split it
- Tasks are ordered by dependency, not by perceived importance
- If a task touches anything in `trading/integrations/bittensor/weight_setter.py` or live broker mode, **mark it explicitly as "Requires user approval before execution"** (CLAUDE.md "Ask first")

### Phase 4: Implement

Hand the plan to `superpowers:executing-plans` (or `superpowers:subagent-driven-development` if tasks are independent and you want to parallelize). Each task follows `superpowers:test-driven-development` and `superpowers:incremental-implementation`-style discipline:

1. Read the task's acceptance criteria
2. Load just the spec sections and source files relevant to this task (don't flood the context)
3. Write a failing test for the expected behavior (RED)
4. Implement the minimum code to pass (GREEN)
5. Run the verify command from the task
6. Commit with a descriptive message
7. Tick the checkbox in the plan file
8. Move to the next task

If anything fails, follow `superpowers:systematic-debugging`. If you get stuck for more than ~3 attempts, escalate to the user — don't thrash.

## Keeping the Spec Alive

The spec is a living document, not a one-time artifact:

- **Update when decisions change.** If you discover the data model needs to change, update the spec first, *then* implement. The git history of the spec file is itself a record of how the design evolved.
- **Update when scope changes.** Features added or cut should be reflected in the spec's "Out of Scope" section.
- **Commit the spec.** It belongs in version control alongside the code, in `docs/superpowers/specs/`.
- **Reference the spec in commit messages and PRs.** "Implements section 4.2 of `docs/superpowers/specs/2026-04-12-new-strategy-design.md`"
- **Promote stable decisions to ADRs.** Once a decision is implemented and won't change, lift it from the spec into a numbered ADR under `docs/adr/`. The spec records "we considered options A/B/C and chose B"; the ADR records "we use B because [stable reasons]." Both are useful; they have different lifecycles.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "This is simple, I don't need a spec" | Simple tasks don't need *long* specs. They still need acceptance criteria. A 10-line spec is fine; an unwritten one is not. |
| "I'll write the spec after I code it" | That's documentation, not specification. The spec's value is in forcing clarity *before* code, while changes are still cheap. |
| "The spec will slow us down" | A 15-minute spec prevents hours of rework. Look at any of the existing `docs/superpowers/specs/*-design.md` files — they paid for themselves by catching ambiguities before code shipped. |
| "Requirements will change anyway" | That's why the spec is a living document under version control. An outdated spec is still better than no spec, and the diff history is itself documentation. |
| "The user knows what they want" | Even clear requests have implicit assumptions about the existing system. The spec surfaces them. The "Make the dashboard faster" example above is real — it could mean ten different things. |
| "There's already a related spec, I'll just code from that" | If the related spec is more than a week old, re-read it and ask "is this still the plan?" before assuming. Specs drift. |
| "I have a brainstorming summary, that's enough" | Brainstorming output is the *input* to the spec, not a substitute for it. The spec's six sections force decisions that brainstorming leaves open. |
| "Adding all these sections is busywork" | The sections that feel like busywork *for this feature* are the ones you can keep brief. The discipline is filling them in deliberately, not at length. |

## Red Flags

Stop and write a spec if you catch yourself doing any of these:

- Starting to write code without any written requirements
- Asking "should I just start building?" before clarifying what "done" means
- Implementing features not mentioned in any spec or task list
- Making architectural decisions without an ADR or a spec section
- Skipping the spec because "it's obvious what to build"
- About to touch more than 3 files with no plan in `docs/superpowers/plans/`
- About to add a new STA_* env var without listing it in a spec
- About to add a new external integration without a spec section listing the credential and rotation procedure (cross-check with `docs/process/security-and-hardening.md` rotation cheatsheet)
- About to write a new ADR without a spec that motivated the decision
- About to refactor `trading/api/app.py` (the 1700-line god file) without a spec for what the smaller pieces look like

## Verification

Before proceeding from Specify to Plan, confirm:

- [ ] Spec covers all 10 sections from the template above
- [ ] Assumptions block was surfaced at the start and the human responded
- [ ] Vague instructions were reframed as measurable success criteria
- [ ] The spec lives under `docs/superpowers/specs/` with the `YYYY-MM-DD-<name>-design.md` naming convention
- [ ] The "Boundaries" section references CLAUDE.md "Working Boundaries" and adds only feature-specific items
- [ ] "Out of Scope" is filled in (even if it's "nothing currently excluded")
- [ ] The human has read and approved the spec

Before proceeding from Plan to Tasks:

- [ ] Plan lives under `docs/superpowers/plans/` with matching `YYYY-MM-DD-<name>.md` naming
- [ ] Plan references the spec it implements
- [ ] Risks and mitigations are listed (especially for irreversible ops)
- [ ] Verification checkpoints are concrete commands, not "check that it works"
- [ ] Human has reviewed and approved the plan

Before proceeding from Tasks to Implement:

- [ ] Each task has acceptance + verify + files + depends-on
- [ ] No task touches more than ~5 files
- [ ] Tasks involving the weight setter, live broker mode, or schema changes are flagged for approval
- [ ] Human has reviewed and approved the task list

Before declaring Implement done:

- [ ] All task checkboxes ticked
- [ ] The verify command of every task passes
- [ ] CLAUDE.md "Working Boundaries" still hold across the diff
- [ ] If applicable, ADR written and indexed in CLAUDE.md
- [ ] Spec status updated to `implemented`

---

*Adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/spec-driven-development/SKILL.md) under MIT license. The four-phase gated workflow and the six-section spec template are preserved; the file locations, naming conventions, hand-offs to `superpowers:*` skills, and references to ADRs / process docs / `CLAUDE.md` Working Boundaries are specific to this repository.*
