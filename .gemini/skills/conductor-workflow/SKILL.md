---
name: conductor-workflow
description: Enforce the project's standard Conductor Task Workflow (TDD, Quality Gates, and Checkpoints). Use when starting, working on, or completing any task from plan.md.
---

# Conductor Workflow Skill

Expert guidance for executing tasks within the `conductor` ecosystem with high rigor and TDD discipline.

## Core Capabilities

1. **TDD Enforcement**: Strict adherence to the Red -> Green -> Refactor cycle.
2. **Quality Gates**: Mandatory validation of code coverage, types, and mobile/UI standards.
3. **Phase Checkpointing**: Atomic verification and manual verification plans for the user.
4. **Git Note Documentation**: Automated "Why" and "What" summaries attached via Git Notes.

## Anti-Rationalization Table

| Thought | Reality |
|---------|---------|
| "I'll just write the code first and the test later; it's faster." | **STOP.** You must write a failing test first. The "Red" phase is non-negotiable for task integrity. |
| "This change is too small for a unit test." | **STOP.** Every logic change needs a corresponding test to prevent regressions. |
| "I'll skip the manual verification plan since it's just a backend fix." | **STOP.** The user must always have a clear path to verify your work, even for internal APIs. |
| "The plan says Phase X is done, so I'll just move on." | **STOP.** You must execute the Phase Completion Verification protocol, including coverage audits. |

## Standard Workflow

### 1. Task Activation (Pre-Work)
- Read `plan.md` and mark the task as `[~]`.
- Identify the specific files that will be impacted.
- **GATE**: Verify that the tech stack (`conductor/tech-stack.md`) supports the approach.

### 2. The TDD Cycle
- **Red Phase**: Create a test file (or add to an existing one). Write a test that *fails* against the current codebase. Run it to confirm failure.
- **Green Phase**: Write the *minimal* code to make the test pass. Run tests to confirm success.
- **Refactor Phase**: Clean up the code. Ensure it follows `conductor/code_styleguides/`. Confirm tests still pass.

### 3. Quality & Coverage
- Run coverage reports (e.g., `pytest --cov` or `vitest run --coverage`).
- **GATE**: New code must achieve >80% coverage.
- **GATE**: Verify type safety (e.g., `mypy` or `tsc`).

### 4. Completion & Git Notes
- Stage changes and commit with the specified `<type>(<scope>): <description>` format.
- **CRITICAL**: Attach a Git Note to the commit hash with the "What" and "Why" of the change.
- Update `plan.md` with the first 7 characters of the SHA and mark as `[x]`.

## Phase Completion Protocol
When a task finishes a phase:
1. **Announce** the start of the verification protocol.
2. **Audit** coverage for all files changed since the last checkpoint.
3. **Propose** a clear, step-by-step Manual Verification Plan for the user.
4. **Create** a `conductor(checkpoint)` commit and attach the full report via Git Notes.
5. **Update** the Phase heading in `plan.md` with the checkpoint SHA.
