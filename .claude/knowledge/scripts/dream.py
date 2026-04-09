"""
Dream cycle — periodic knowledge consolidation and active learning.

Scores articles by access patterns, cross-references, and freshness.
Archives decayed articles, identifies topic gaps, and proposes
procedural memory rules for CLAUDE.md.

Usage:
    uv run python scripts/dream.py                  # full consolidation report
    uv run python scripts/dream.py --archive        # also archive decayed articles
    uv run python scripts/dream.py --procedural     # extract procedural memory rules
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from config import (
    CONTRADICTIONS_DIR,
    KNOWLEDGE_DIR,
    REPORTS_DIR,
    SCRIPTS_DIR,
    now_iso,
    today_iso,
)
from utils import (
    compute_effective_confidence,
    count_inbound_links,
    extract_wikilinks,
    get_article_word_count,
    list_raw_files,
    list_wiki_articles,
    parse_frontmatter,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = KNOWLEDGE_DIR / "_archived"


def score_article(article_path: Path) -> dict:
    """Score an article on multiple dimensions. Returns a score dict."""
    content = article_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    rel = str(article_path.relative_to(KNOWLEDGE_DIR)).replace("\\", "/")
    link_target = rel.replace(".md", "")

    # Cross-reference score: inbound + outbound links
    outbound = len([l for l in extract_wikilinks(content) if not l.startswith("daily/")])
    inbound = count_inbound_links(link_target)
    cross_ref_score = min((inbound + outbound) / 10.0, 1.0)

    # Source count score: how many daily logs contributed
    sources = fm.get("sources", [])
    source_count = len(sources) if isinstance(sources, list) else 0
    source_score = min(source_count / 5.0, 1.0)

    # Word count score: penalize very sparse or very bloated articles
    word_count = get_article_word_count(article_path)
    if word_count < 100:
        depth_score = 0.3
    elif word_count < 200:
        depth_score = 0.6
    elif word_count < 800:
        depth_score = 1.0
    else:
        depth_score = 0.8  # slightly penalize very long articles

    # Effective confidence (temporal decay)
    confidence = fm.get("confidence", 0.7)
    decay_rate = fm.get("decay_rate", "slow")
    updated = fm.get("updated", fm.get("created", "2026-01-01"))
    try:
        eff_confidence = compute_effective_confidence(
            float(confidence), str(decay_rate), str(updated)
        )
    except (ValueError, TypeError):
        eff_confidence = 0.5

    # Composite score (weighted)
    composite = (
        eff_confidence * 0.35
        + cross_ref_score * 0.25
        + source_score * 0.20
        + depth_score * 0.20
    )

    return {
        "path": rel,
        "title": fm.get("title", rel),
        "composite": round(composite, 3),
        "eff_confidence": round(eff_confidence, 3),
        "cross_ref_score": round(cross_ref_score, 3),
        "source_score": round(source_score, 3),
        "depth_score": round(depth_score, 3),
        "word_count": word_count,
        "inbound_links": inbound,
        "outbound_links": outbound,
        "source_count": source_count,
        "decay_rate": str(decay_rate),
        "updated": str(updated),
    }


def find_topic_gaps() -> list[str]:
    """Find concepts referenced in wikilinks that don't have their own article."""
    existing_articles = set()
    all_links = set()

    for article in list_wiki_articles():
        rel = str(article.relative_to(KNOWLEDGE_DIR)).replace("\\", "/").replace(".md", "")
        existing_articles.add(rel)
        content = article.read_text(encoding="utf-8")
        for link in extract_wikilinks(content):
            if not link.startswith("daily/"):
                all_links.add(link)

    gaps = sorted(all_links - existing_articles)
    return gaps


def find_uncompiled_logs() -> list[str]:
    """Find daily logs that haven't been compiled yet."""
    state_file = SCRIPTS_DIR / "state.json"
    ingested = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            ingested = state.get("ingested", {})
        except (json.JSONDecodeError, OSError):
            pass

    uncompiled = []
    for log_path in list_raw_files():
        if log_path.name not in ingested:
            uncompiled.append(log_path.name)
    return uncompiled


def extract_patterns(min_occurrences: int = 3) -> list[dict]:
    """Find recurring patterns across articles that could become CLAUDE.md rules.

    Looks for:
    - Same debugging workflow mentioned 3+ times
    - Same architectural pattern repeated
    - Same gotcha/lesson appearing in multiple articles
    """
    articles = list_wiki_articles()
    # Collect all "Key Points" and "Lessons Learned" bullet items
    bullet_items: list[tuple[str, str]] = []  # (item_text, article_path)

    for article in articles:
        content = article.read_text(encoding="utf-8")
        rel = str(article.relative_to(KNOWLEDGE_DIR))

        in_key_section = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("## Key Points") or stripped.startswith("## Lessons"):
                in_key_section = True
                continue
            if stripped.startswith("## ") and in_key_section:
                in_key_section = False
                continue
            if in_key_section and stripped.startswith("- "):
                bullet_items.append((stripped[2:].strip(), rel))

    # Group similar bullets (simple: by shared 4+ word n-grams)
    from collections import Counter

    word_groups: dict[str, list[tuple[str, str]]] = {}
    for text, path in bullet_items:
        words = text.lower().split()
        # Generate 4-word sliding windows as grouping keys
        for i in range(len(words) - 3):
            key = " ".join(words[i : i + 4])
            word_groups.setdefault(key, []).append((text, path))

    # Find groups with items from different articles
    patterns = []
    seen_keys = set()
    for key, items in sorted(word_groups.items(), key=lambda x: -len(x[1])):
        unique_articles = set(path for _, path in items)
        if len(unique_articles) >= min_occurrences and key not in seen_keys:
            seen_keys.add(key)
            patterns.append({
                "pattern_key": key,
                "occurrences": len(unique_articles),
                "articles": sorted(unique_articles),
                "examples": [text for text, _ in items[:3]],
            })

    return patterns[:10]  # top 10


def generate_dream_report(
    scores: list[dict],
    gaps: list[str],
    uncompiled: list[str],
    patterns: list[dict],
) -> str:
    """Generate the dream consolidation report."""
    lines = [
        f"# Dream Consolidation Report — {today_iso()}",
        "",
        f"Generated: {now_iso()}",
        "",
    ]

    # Summary
    total = len(scores)
    avg_score = sum(s["composite"] for s in scores) / total if total else 0
    decayed = [s for s in scores if s["eff_confidence"] < 0.5]
    strong = [s for s in scores if s["composite"] >= 0.7]

    lines.extend([
        "## Summary",
        "",
        f"- **Total articles:** {total}",
        f"- **Average composite score:** {avg_score:.3f}",
        f"- **Strong articles (score >= 0.7):** {len(strong)}",
        f"- **Decayed articles (eff_confidence < 0.5):** {len(decayed)}",
        f"- **Topic gaps:** {len(gaps)}",
        f"- **Uncompiled daily logs:** {len(uncompiled)}",
        f"- **Recurring patterns found:** {len(patterns)}",
        "",
    ])

    # Article rankings
    lines.extend(["## Article Rankings", ""])
    lines.append("| Rank | Score | Conf | Article | Words |")
    lines.append("|------|-------|------|---------|-------|")
    for i, s in enumerate(scores, 1):
        lines.append(
            f"| {i} | {s['composite']:.3f} | {s['eff_confidence']:.2f} | "
            f"[[{s['path'].replace('.md', '')}]] | {s['word_count']} |"
        )
    lines.append("")

    # Decayed articles (candidates for archive)
    if decayed:
        lines.extend(["## Decayed Articles (Archive Candidates)", ""])
        for s in decayed:
            lines.append(
                f"- [[{s['path'].replace('.md', '')}]] — "
                f"eff_conf={s['eff_confidence']:.2f}, "
                f"decay={s['decay_rate']}, updated={s['updated']}"
            )
        lines.append("")

    # Topic gaps
    if gaps:
        lines.extend(["## Topic Gaps (Referenced but No Article)", ""])
        for gap in gaps:
            lines.append(f"- [[{gap}]]")
        lines.append("")

    # Uncompiled logs
    if uncompiled:
        lines.extend(["## Uncompiled Daily Logs", ""])
        for log_name in uncompiled:
            lines.append(f"- daily/{log_name}")
        lines.append("")

    # Procedural memory candidates
    if patterns:
        lines.extend(["## Procedural Memory Candidates", ""])
        lines.append(
            "Patterns appearing in 3+ articles — candidates for CLAUDE.md rules:"
        )
        lines.append("")
        for p in patterns:
            lines.append(f"### Pattern: \"{p['pattern_key']}\" ({p['occurrences']} articles)")
            lines.append("")
            for ex in p["examples"]:
                lines.append(f"- {ex}")
            lines.append(f"- *Found in:* {', '.join(p['articles'])}")
            lines.append("")

    # Suggested actions
    lines.extend(["## Suggested Actions", ""])
    if uncompiled:
        lines.append(f"1. Compile {len(uncompiled)} uncompiled daily log(s)")
    if decayed:
        lines.append(
            f"2. Review {len(decayed)} decayed article(s) — refresh or archive"
        )
    if gaps:
        lines.append(f"3. Create articles for {len(gaps)} topic gap(s)")
    if patterns:
        lines.append(
            f"4. Consider adding {len(patterns)} recurring pattern(s) to CLAUDE.md"
        )
    if not any([uncompiled, decayed, gaps, patterns]):
        lines.append("Knowledge base is healthy — no immediate actions needed.")
    lines.append("")

    return "\n".join(lines)


def archive_decayed(scores: list[dict]) -> int:
    """Move decayed articles to _archived/ directory. Returns count archived."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archived = 0

    for s in scores:
        if s["eff_confidence"] >= 0.5:
            continue
        src = KNOWLEDGE_DIR / s["path"]
        if not src.exists():
            continue
        dst = ARCHIVE_DIR / s["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        archived += 1

    return archived


def main():
    parser = argparse.ArgumentParser(description="Dream cycle — knowledge consolidation")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Archive articles with effective confidence below 0.5",
    )
    parser.add_argument(
        "--procedural",
        action="store_true",
        help="Only run procedural memory extraction",
    )
    args = parser.parse_args()

    print("Running dream consolidation cycle...")

    # Score all articles
    articles = list_wiki_articles()
    scores = [score_article(a) for a in articles]
    scores.sort(key=lambda s: -s["composite"])

    # Find gaps and uncompiled logs
    gaps = find_topic_gaps()
    uncompiled = find_uncompiled_logs()

    # Extract recurring patterns
    patterns = extract_patterns(min_occurrences=2)  # lower threshold while KB is small

    if args.procedural:
        if patterns:
            print(f"\nProcedural memory candidates ({len(patterns)}):")
            for p in patterns:
                print(f"\n  Pattern: \"{p['pattern_key']}\" ({p['occurrences']} articles)")
                for ex in p["examples"]:
                    print(f"    - {ex}")
        else:
            print("No recurring patterns found yet (need more articles).")
        return

    # Generate report
    report = generate_dream_report(scores, gaps, uncompiled, patterns)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"dream-{today_iso()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {report_path}")

    # Archive if requested
    if args.archive:
        decayed = [s for s in scores if s["eff_confidence"] < 0.5]
        if decayed:
            archived = archive_decayed(scores)
            print(f"Archived {archived} decayed article(s)")
        else:
            print("No articles to archive (all above confidence threshold)")

    # Print summary
    total = len(scores)
    avg = sum(s["composite"] for s in scores) / total if total else 0
    decayed_count = sum(1 for s in scores if s["eff_confidence"] < 0.5)
    print(f"\nSummary: {total} articles, avg score {avg:.3f}, {decayed_count} decayed, {len(gaps)} gaps")


if __name__ == "__main__":
    main()
