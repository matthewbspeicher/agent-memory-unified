"""
Lint the knowledge base for structural and semantic health.

Runs 7 checks: broken links, orphan pages, orphan sources, stale articles,
contradictions (LLM), missing backlinks, and sparse articles.

Usage:
    uv run python lint.py                    # all checks
    uv run python lint.py --structural-only  # skip LLM checks (faster, cheaper)
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from datetime import date, datetime

from config import CONTRADICTIONS_DIR, KNOWLEDGE_DIR, REPORTS_DIR, now_iso, today_iso
from utils import (
    count_inbound_links,
    extract_wikilinks,
    file_hash,
    get_article_word_count,
    list_raw_files,
    list_wiki_articles,
    load_state,
    parse_frontmatter,
    read_all_wiki_content,
    save_state,
    wiki_article_exists,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def check_broken_links() -> list[dict]:
    """Check for [[wikilinks]] that point to non-existent articles."""
    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(KNOWLEDGE_DIR)
        for link in extract_wikilinks(content):
            if link.startswith("daily/"):
                continue  # daily log references are valid
            if not wiki_article_exists(link):
                issues.append({
                    "severity": "error",
                    "check": "broken_link",
                    "file": str(rel),
                    "detail": f"Broken link: [[{link}]] - target does not exist",
                })
    return issues


def check_orphan_pages() -> list[dict]:
    """Check for articles with zero inbound links."""
    issues = []
    for article in list_wiki_articles():
        rel = article.relative_to(KNOWLEDGE_DIR)
        link_target = str(rel).replace(".md", "").replace("\\", "/")
        inbound = count_inbound_links(link_target)
        if inbound == 0:
            issues.append({
                "severity": "warning",
                "check": "orphan_page",
                "file": str(rel),
                "detail": f"Orphan page: no other articles link to [[{link_target}]]",
            })
    return issues


def check_orphan_sources() -> list[dict]:
    """Check for daily logs that haven't been compiled yet."""
    state = load_state()
    ingested = state.get("ingested", {})
    issues = []
    for log_path in list_raw_files():
        if log_path.name not in ingested:
            issues.append({
                "severity": "warning",
                "check": "orphan_source",
                "file": f"daily/{log_path.name}",
                "detail": f"Uncompiled daily log: {log_path.name} has not been ingested",
            })
    return issues


def check_stale_articles() -> list[dict]:
    """Check if source daily logs have changed since compilation."""
    state = load_state()
    ingested = state.get("ingested", {})
    issues = []
    for log_path in list_raw_files():
        rel = log_path.name
        if rel in ingested:
            stored_hash = ingested[rel].get("hash", "")
            current_hash = file_hash(log_path)
            if stored_hash != current_hash:
                issues.append({
                    "severity": "warning",
                    "check": "stale_article",
                    "file": f"daily/{rel}",
                    "detail": f"Stale: {rel} has changed since last compilation",
                })
    return issues


def check_missing_backlinks() -> list[dict]:
    """Check for asymmetric links: A links to B but B doesn't link to A."""
    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(KNOWLEDGE_DIR)
        source_link = str(rel).replace(".md", "").replace("\\", "/")

        for link in extract_wikilinks(content):
            if link.startswith("daily/"):
                continue
            target_path = KNOWLEDGE_DIR / f"{link}.md"
            if target_path.exists():
                target_content = target_path.read_text(encoding="utf-8")
                if f"[[{source_link}]]" not in target_content:
                    issues.append({
                        "severity": "suggestion",
                        "check": "missing_backlink",
                        "file": str(rel),
                        "detail": f"[[{source_link}]] links to [[{link}]] but not vice versa",
                        "auto_fixable": True,
                    })
    return issues


def check_sparse_articles() -> list[dict]:
    """Check for articles with fewer than 200 words."""
    issues = []
    for article in list_wiki_articles():
        word_count = get_article_word_count(article)
        if word_count < 200:
            rel = article.relative_to(KNOWLEDGE_DIR)
            issues.append({
                "severity": "suggestion",
                "check": "sparse_article",
                "file": str(rel),
                "detail": f"Sparse article: {word_count} words (minimum recommended: 200)",
            })
    return issues


def check_unresolved_contradictions() -> list[dict]:
    """Check for unresolved contradiction entries."""
    import json as _json

    issues = []
    if not CONTRADICTIONS_DIR.exists():
        return issues
    for f in sorted(CONTRADICTIONS_DIR.glob("*.json")):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            issues.append({
                "severity": "error",
                "check": "contradiction_parse",
                "file": f"contradictions/{f.name}",
                "detail": f"Failed to parse contradiction file: {f.name}",
            })
            continue
        if data.get("resolution", "pending") == "pending":
            old = data.get("old_claim", "?")[:80]
            new = data.get("new_claim", "?")[:80]
            article = data.get("article", "?")
            issues.append({
                "severity": "warning",
                "check": "unresolved_contradiction",
                "file": f"contradictions/{f.name}",
                "detail": (
                    f"Unresolved contradiction in [[{article}]]: "
                    f'"{old}" vs "{new}"'
                ),
            })
    return issues


def check_stale_confidence() -> list[dict]:
    """Check for articles where effective confidence has decayed below 0.5."""
    from utils import compute_effective_confidence, parse_frontmatter

    issues = []
    for article in list_wiki_articles():
        content = article.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        confidence = fm.get("confidence")
        decay_rate = fm.get("decay_rate")
        updated = fm.get("updated")

        if confidence is None or decay_rate is None or updated is None:
            # Skip articles without temporal metadata (pre-Phase 2)
            continue

        try:
            conf_val = float(confidence)
        except (ValueError, TypeError):
            continue

        eff = compute_effective_confidence(conf_val, str(decay_rate), str(updated))
        if eff < 0.5:
            rel = article.relative_to(KNOWLEDGE_DIR)
            issues.append({
                "severity": "warning",
                "check": "stale_confidence",
                "file": str(rel),
                "detail": (
                    f"Stale confidence: initial={conf_val:.2f}, "
                    f"effective={eff:.2f} (decay_rate={decay_rate}, "
                    f"updated={updated})"
                ),
            })
    return issues


async def check_contradictions() -> list[dict]:
    """Use LLM to detect contradictions across articles."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    wiki_content = read_all_wiki_content()

    prompt = f"""Review this knowledge base for contradictions, inconsistencies, or
conflicting claims across articles.

## Knowledge Base

{wiki_content}

## Instructions

Look for:
- Direct contradictions (article A says X, article B says not-X)
- Inconsistent recommendations (different articles recommend conflicting approaches)
- Outdated information that conflicts with newer entries

For each issue found, output EXACTLY one line in this format:
CONTRADICTION: [file1] vs [file2] - description of the conflict
INCONSISTENCY: [file] - description of the inconsistency

If no issues found, output exactly: NO_ISSUES

Do NOT output anything else - no preamble, no explanation, just the formatted lines."""

    response = ""
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                allowed_tools=[],
                max_turns=2,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response += block.text
    except Exception as e:
        return [{"severity": "error", "check": "contradiction", "file": "(system)", "detail": f"LLM check failed: {e}"}]

    issues = []
    if "NO_ISSUES" not in response:
        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("CONTRADICTION:") or line.startswith("INCONSISTENCY:"):
                issues.append({
                    "severity": "warning",
                    "check": "contradiction",
                    "file": "(cross-article)",
                    "detail": line,
                })

    return issues


def generate_report(all_issues: list[dict]) -> str:
    """Generate a markdown lint report."""
    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]
    suggestions = [i for i in all_issues if i["severity"] == "suggestion"]

    lines = [
        f"# Lint Report - {today_iso()}",
        "",
        f"**Total issues:** {len(all_issues)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Suggestions: {len(suggestions)}",
        "",
    ]

    for severity, issues, marker in [
        ("Errors", errors, "x"),
        ("Warnings", warnings, "!"),
        ("Suggestions", suggestions, "?"),
    ]:
        if issues:
            lines.append(f"## {severity}")
            lines.append("")
            for issue in issues:
                fixable = " (auto-fixable)" if issue.get("auto_fixable") else ""
                lines.append(f"- **[{marker}]** `{issue['file']}` - {issue['detail']}{fixable}")
            lines.append("")

    if not all_issues:
        lines.append("All checks passed. Knowledge base is healthy.")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lint the knowledge base")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip LLM-based checks (contradictions) - faster and free",
    )
    args = parser.parse_args()

    print("Running knowledge base lint checks...")
    all_issues: list[dict] = []

    # Structural checks (free, instant)
    checks = [
        ("Broken links", check_broken_links),
        ("Orphan pages", check_orphan_pages),
        ("Orphan sources", check_orphan_sources),
        ("Stale articles", check_stale_articles),
        ("Missing backlinks", check_missing_backlinks),
        ("Sparse articles", check_sparse_articles),
        ("Stale confidence", check_stale_confidence),
        ("Unresolved contradictions", check_unresolved_contradictions),
    ]

    for name, check_fn in checks:
        print(f"  Checking: {name}...")
        issues = check_fn()
        all_issues.extend(issues)
        print(f"    Found {len(issues)} issue(s)")

    # LLM check (costs money)
    if not args.structural_only:
        print("  Checking: Contradictions (LLM)...")
        issues = asyncio.run(check_contradictions())
        all_issues.extend(issues)
        print(f"    Found {len(issues)} issue(s)")
    else:
        print("  Skipping: Contradictions (--structural-only)")

    # Generate and save report
    report = generate_report(all_issues)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"lint-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: {report_path}")

    # Update state
    state = load_state()
    state["last_lint"] = now_iso()
    save_state(state)

    # Summary
    errors = sum(1 for i in all_issues if i["severity"] == "error")
    warnings = sum(1 for i in all_issues if i["severity"] == "warning")
    suggestions = sum(1 for i in all_issues if i["severity"] == "suggestion")
    print(f"\nResults: {errors} errors, {warnings} warnings, {suggestions} suggestions")

    if errors > 0:
        print("\nErrors found - knowledge base needs attention!")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
