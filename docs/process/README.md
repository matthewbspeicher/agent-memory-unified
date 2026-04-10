# Process Docs

Manually-referenced engineering process documents adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (MIT) and tailored to this repository's stack and history.

## What these are

Each document encodes a workflow — a sequence of steps with checkpoints, anti-rationalization tables, and verification gates — that an agent (or a human) should follow when working in a specific situation. They are *process*, not reference: they tell you **how** to do something carefully, not **what** to do.

## What these are not

- **Not auto-loaded Claude Code skills.** Skills auto-load via the `Skill` tool and live under `~/.claude/skills/` or plugin directories. These docs are markdown files that an agent or human reads on demand. No installation, no harness wiring.
- **Not a replacement for `superpowers:*` or `oac:*` skills** that this project already has installed. Where there is overlap, the installed skill wins. These docs cover gaps where no equivalent skill exists.
- **Not specs.** Specs go under `docs/superpowers/specs/`. These are timeless workflows; specs describe one-off feature designs.
- **Not ADRs.** ADRs go under `docs/adr/` and document decisions; these document processes.

## How to invoke

Reference one of these docs explicitly when starting work:

> "Follow `docs/process/source-driven-development.md` when implementing the Bittensor weight setter."

The agent should then read the doc and execute its workflow. The doc is the source of truth; the agent should not paraphrase or substitute its own approach.

## Index

| Doc | Use when |
|---|---|
| [source-driven-development.md](source-driven-development.md) | About to write framework-specific code from memory — Bittensor, IBKR, FastAPI, Pydantic, pgvector, React 19, anything where the API changes between versions |
| [security-and-hardening.md](security-and-hardening.md) | Touching FastAPI routes, broker credentials, the Bittensor wallet, the on-chain weight setter, `STA_BROKER_MODE`, secrets, or any external integration that handles money or signs on-chain |
| [spec-driven-development.md](spec-driven-development.md) | Starting any feature or change that touches more than ~3 files or 30 minutes — produces a design spec under `docs/superpowers/specs/` and a plan under `docs/superpowers/plans/`, gated by the existing `superpowers:brainstorming` → `writing-plans` → `executing-plans` flow |

(More may be added. See `project_agent_skills_porting.md` in user memory for the broader porting plan and which upstream skills were intentionally skipped.)

## Source and license

All docs in this directory are derivative works of [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), MIT licensed. Adaptations include:
- Examples drawn from this project's actual stack (Bittensor v10, IBKR, FastAPI, pgvector, React 19 + Vite)
- Cautionary tales from real incidents in this repository (see references to MEMORY.md feedback entries)
- Tooling references for what we actually have available (`gh` CLI, Context7 MCP server)

Attribution preserved in each adapted doc's footer.
