# project-feed

Source of truth for this project's **agent-readable milestone feed**. Every substantive
milestone we ship lands here as a structured markdown file, regardless of whether it's
ever published to an external platform.

## Why this exists

Three reasons, in order of importance:

1. **Cheap session context for our own agents.** Any AI agent (Claude Code, opencode,
   Gemini, future subagents) opening a fresh session on this repo can `ls project-feed/`
   and get a dense summary of what's shipped recently without doing 20 `git log` +
   `grep` calls to reconstruct state.
2. **Publication sink for Moltbook** (and any other agent-facing platform). The
   `scripts/publish-to-moltbook.py` publisher reads unposted entries here and POSTs
   them to the agent social network, writing the post UUID back to the frontmatter.
   See `reference_moltbook.md` in user memory for the three-layer integration plan.
3. **Accountability.** Writing a post forces us to be able to articulate what we built,
   why it matters, and what's non-obvious about it. If we can't write a post, we
   probably didn't build a milestone.

## Frontmatter schema

Every file under `project-feed/` **must** start with YAML frontmatter matching this schema:

```yaml
---
title: "Short title under ~70 chars"
summary: "One-sentence hook — what's the non-obvious thing about this work"
tags: [design-systems, tokens, frontend]   # free-form, 1-6 tags
submolt_targets: [m/designsystems, m/claudecode]   # which Moltbook submolts to post into
status: draft   # draft | ready | posted
posted_to_moltbook: false   # set true after publisher succeeds
posted_at: null             # ISO timestamp, populated by publisher
post_uuid: null             # Moltbook post UUID, populated by publisher
source_links:
  - type: spec     # spec | plan | commits | docs | memory | adr
    url: docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md
  - type: commits
    range: e2e9543..8a0b6ec
---
```

Fields:

| Field | Purpose | Who writes it |
|---|---|---|
| `title` | The post headline. Keep it under ~70 chars; Moltbook shows truncated titles in feeds. | Author |
| `summary` | A single sentence capturing the most interesting thing. If you can't write this, the post isn't ready. | Author |
| `tags` | Freeform tags for search. | Author |
| `submolt_targets` | Which Moltbook submolts to post into. Can be empty for internal-only. | Author |
| `status` | `draft` = incomplete, `ready` = publisher can pick up, `posted` = done. | Author → Publisher |
| `posted_to_moltbook` | Set to `true` after the publisher successfully posts. | Publisher |
| `posted_at` | ISO timestamp of successful post. | Publisher |
| `post_uuid` | Moltbook post UUID for back-reference. | Publisher |
| `source_links` | Pointers to the underlying work (specs, plans, commits, ADRs). | Author |

## Body conventions

After the frontmatter, the body is plain markdown. Conventions:

- **Lead with the non-obvious insight.** Not "we built X" but "we learned that X requires Y
  because Z, which surprised us." Moltbook's content quality is disputed (critics call a lot
  of it "AI slop" — see `reference_moltbook.md`). Engineering posts that stand out need to
  *say something worth reading*.
- **Keep it under ~600 words** for the first post in a series. Longer posts can come later
  once you have an audience.
- **Show, don't tell.** If the work is in git, link to the commits or the spec. Anything
  citable should be cited.
- **End with an invitation.** An open question, a known unknown, or "would love to hear
  how other agents solved this." Drives engagement and signals good faith.
- **No secrets.** Ever. Moltbook has a documented breach history (two breaches in the first
  two months of 2026, per `reference_moltbook.md`). Assume anything you write here may leak.
  Never include API keys, internal URLs, wallet details, IBKR credentials, or
  environment-variable values.

## File naming

Format: `YYYY-MM-DD-short-kebab-slug.md`

- `2026-04-10-design-md-token-pipeline.md` ✓
- `2026-04-11-temporal-knowledge-graph.md` ✓
- `2026_04_10_design.md` ✗ (use dashes)
- `design-pipeline.md` ✗ (needs date prefix)

## Directory layout

```
project-feed/
├── README.md                              # this file
├── 2026-04-10-<slug>.md                   # published/ready milestones
├── ...
└── drafts/                                # work-in-progress posts, not picked up by publisher
    ├── 2026-04-??-<slug>.md
    └── ...
```

Files in `drafts/` are **ignored** by the publisher regardless of `status` field. Move to
the parent directory when ready.

## Publisher workflow

The `scripts/publish-to-moltbook.py` script (**not yet implemented** as of 2026-04-10):

1. Scans `project-feed/*.md` (top level only, skipping `drafts/`)
2. For each file where `posted_to_moltbook == false` and `status == ready`, prompt the
   operator for confirmation (human-in-the-loop, no silent posts)
3. On confirmation, POST to `https://www.moltbook.com/api/v1/posts` with the submolt targets
4. On success, update frontmatter with `posted_to_moltbook: true`, `posted_at: <iso>`,
   `post_uuid: <uuid>`, `status: posted`
5. Respect the 1-post-per-30-minute rate limit (see Moltbook API docs)
6. Commit the frontmatter update automatically

See `reference_moltbook.md` in user memory for the full three-layer Moltbook integration plan.

## Hard gate reminder

**Do NOT run the publisher until all of these are in place** (per the agent-readiness audit
at `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`):

1. Audit Phase A (rate limiting + audit decorator + kill-switch protection) landed — track at
   `conductor/tracks/defensive_perimeter/`
2. Audit Phase B (real per-agent identity) or explicit acceptance of attribution-only identity
3. A `FOR_AGENTS.md` at repo root + `/.well-known/agents.json` for arriving external agents
4. An abuse contact + incident response playbook
5. Moltbook agent registration + Twitter verification (human-in-the-loop, one-time)

Building content here *before* those gates is fine — the content just sits in the repo
waiting. But **publishing** is gated on all six.
