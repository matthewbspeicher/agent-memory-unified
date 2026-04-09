"""
Entity-relation graph for the knowledge base.

Parses wikilinks from all articles to build an adjacency graph, tracks
which code files are referenced by which articles, and enables graph
traversal queries.

Usage:
    uv run python scripts/graph.py related "bittensor"    # articles related to a topic
    uv run python scripts/graph.py orphans                # disconnected articles
    uv run python scripts/graph.py code-map               # code file -> article mapping
    uv run python scripts/graph.py code-stale             # articles referencing changed code
    uv run python scripts/graph.py stats                  # graph statistics
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from config import KNOWLEDGE_DIR, SCRIPTS_DIR
from utils import extract_wikilinks, list_wiki_articles, parse_frontmatter

DB_PATH = SCRIPTS_DIR / "graph.db"
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent  # repo root (/opt/agent-memory-unified)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create graph tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            path TEXT PRIMARY KEY,
            title TEXT,
            type TEXT,
            tags TEXT
        );
        CREATE TABLE IF NOT EXISTS edges (
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            type TEXT DEFAULT 'wikilink',
            PRIMARY KEY (source, target, type),
            FOREIGN KEY (source) REFERENCES nodes(path),
            FOREIGN KEY (target) REFERENCES nodes(path)
        );
        CREATE TABLE IF NOT EXISTS code_refs (
            article_path TEXT NOT NULL,
            code_path TEXT NOT NULL,
            PRIMARY KEY (article_path, code_path)
        );
    """)
    conn.commit()


# Regex to find code file references in article text
_CODE_REF_PATTERNS = [
    re.compile(r'`((?:trading|frontend|api|shared|taoshi-vanta)/[^\s`]+\.\w+)`'),
    re.compile(r'`([\w/]+\.(?:py|ts|tsx|js|jsx|yaml|yml|json|toml|sql|sh))`'),
]


def _extract_code_refs(content: str) -> set[str]:
    """Extract referenced code file paths from article content."""
    refs = set()
    for pattern in _CODE_REF_PATTERNS:
        for match in pattern.finditer(content):
            ref = match.group(1)
            if not ref.startswith("daily/") and not ref.startswith("knowledge/"):
                refs.add(ref)
    return refs


def rebuild_graph(conn: sqlite3.Connection) -> dict:
    """Rebuild the entire graph from article files. Returns stats."""
    init_db(conn)
    conn.execute("DELETE FROM nodes")
    conn.execute("DELETE FROM edges")
    conn.execute("DELETE FROM code_refs")

    articles = list_wiki_articles()
    node_count = 0
    edge_count = 0
    code_ref_count = 0

    for article_path in articles:
        content = article_path.read_text(encoding="utf-8")
        rel = str(article_path.relative_to(KNOWLEDGE_DIR)).replace("\\", "/")
        fm = parse_frontmatter(content)

        # Determine type from path (rel is like "concepts/foo.md" from KNOWLEDGE_DIR)
        if rel.startswith("concepts/"):
            node_type = "concept"
        elif rel.startswith("connections/"):
            node_type = "connection"
        elif rel.startswith("qa/"):
            node_type = "qa"
        else:
            node_type = "other"

        title = fm.get("title", rel)
        tags = json.dumps(fm.get("tags", []))

        conn.execute(
            "INSERT OR REPLACE INTO nodes(path, title, type, tags) VALUES (?, ?, ?, ?)",
            (rel, str(title), node_type, tags),
        )
        node_count += 1

        # Extract wikilinks as edges
        for link in extract_wikilinks(content):
            if link.startswith("daily/"):
                continue
            target = link if link.endswith(".md") else f"{link}.md"
            # Normalize path separators
            target = target.replace("\\", "/")
            conn.execute(
                "INSERT OR IGNORE INTO edges(source, target, type) VALUES (?, ?, 'wikilink')",
                (rel, target),
            )
            edge_count += 1

        # Extract code file references
        code_refs = _extract_code_refs(content)
        for code_ref in code_refs:
            conn.execute(
                "INSERT OR IGNORE INTO code_refs(article_path, code_path) VALUES (?, ?)",
                (rel, code_ref),
            )
            code_ref_count += 1

    conn.commit()
    return {"nodes": node_count, "edges": edge_count, "code_refs": code_ref_count}


def find_related(conn: sqlite3.Connection, query: str, depth: int = 2) -> list[dict]:
    """Find articles related to a query term via graph traversal."""
    init_db(conn)
    query_lower = query.lower()

    # Find seed nodes (title/tags/path match)
    seeds = set()
    for row in conn.execute("SELECT path, title, tags FROM nodes"):
        path, title, tags = row
        if (query_lower in (title or "").lower()
                or query_lower in path.lower()
                or query_lower in (tags or "").lower()):
            seeds.add(path)

    if not seeds:
        return []

    # BFS traversal to find connected nodes
    visited = set(seeds)
    frontier = set(seeds)
    results = []

    for d in range(depth):
        next_frontier = set()
        for node in frontier:
            # Outgoing edges
            for row in conn.execute("SELECT target FROM edges WHERE source = ?", (node,)):
                if row[0] not in visited:
                    next_frontier.add(row[0])
            # Incoming edges
            for row in conn.execute("SELECT source FROM edges WHERE target = ?", (node,)):
                if row[0] not in visited:
                    next_frontier.add(row[0])
        visited.update(next_frontier)
        frontier = next_frontier

    # Build result list with metadata
    for path in visited:
        row = conn.execute("SELECT title, type, tags FROM nodes WHERE path = ?", (path,)).fetchone()
        if row:
            results.append({
                "path": path,
                "title": row[0],
                "type": row[1],
                "tags": row[2],
                "is_seed": path in seeds,
            })

    # Sort: seeds first, then by type
    results.sort(key=lambda r: (not r["is_seed"], r["type"], r["path"]))
    return results


def find_orphans(conn: sqlite3.Connection) -> list[dict]:
    """Find articles with no inbound or outbound wikilinks (excluding daily/ refs)."""
    init_db(conn)
    orphans = []
    for row in conn.execute("SELECT path, title, type FROM nodes"):
        path, title, node_type = row
        outbound = conn.execute("SELECT COUNT(*) FROM edges WHERE source = ?", (path,)).fetchone()[0]
        inbound = conn.execute("SELECT COUNT(*) FROM edges WHERE target = ?", (path,)).fetchone()[0]
        if outbound == 0 and inbound == 0:
            orphans.append({"path": path, "title": title, "type": node_type})
    return orphans


def get_code_map(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Get mapping of code files to articles that reference them."""
    init_db(conn)
    code_map: dict[str, list[str]] = {}
    for row in conn.execute("SELECT code_path, article_path FROM code_refs ORDER BY code_path"):
        code_path, article_path = row
        code_map.setdefault(code_path, []).append(article_path)
    return code_map


def find_stale_code_refs(conn: sqlite3.Connection) -> list[dict]:
    """Find articles that reference code files which may have changed."""
    init_db(conn)
    stale = []
    for row in conn.execute("SELECT DISTINCT code_path, article_path FROM code_refs"):
        code_path, article_path = row
        full_path = ROOT_DIR / code_path
        if not full_path.exists():
            stale.append({
                "article": article_path,
                "code_file": code_path,
                "reason": "file_not_found",
            })
    return stale


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get graph statistics."""
    init_db(conn)
    nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    code_refs = conn.execute("SELECT COUNT(*) FROM code_refs").fetchone()[0]
    concepts = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'concept'").fetchone()[0]
    connections = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'connection'").fetchone()[0]
    qa = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'qa'").fetchone()[0]

    # Density
    density = (2 * edges) / (nodes * (nodes - 1)) if nodes > 1 else 0

    return {
        "nodes": nodes,
        "edges": edges,
        "code_refs": code_refs,
        "concepts": concepts,
        "connections": connections,
        "qa": qa,
        "density": density,
    }


def main():
    parser = argparse.ArgumentParser(description="Knowledge base entity-relation graph")
    sub = parser.add_subparsers(dest="command")

    rel_parser = sub.add_parser("related", help="Find related articles")
    rel_parser.add_argument("query", help="Search term")
    rel_parser.add_argument("--depth", type=int, default=2, help="Traversal depth (default: 2)")

    sub.add_parser("orphans", help="Find disconnected articles")
    sub.add_parser("code-map", help="Show code file -> article mapping")
    sub.add_parser("code-stale", help="Find articles referencing missing/changed code")
    sub.add_parser("stats", help="Show graph statistics")
    sub.add_parser("rebuild", help="Force rebuild the graph")

    args = parser.parse_args()

    conn = _connect()

    # Always rebuild on first run or if DB doesn't exist
    if not DB_PATH.exists() or args.command == "rebuild":
        stats = rebuild_graph(conn)
        print(f"Graph built: {stats['nodes']} nodes, {stats['edges']} edges, {stats['code_refs']} code refs")
        if args.command == "rebuild":
            conn.close()
            return
    else:
        # Ensure tables exist
        init_db(conn)
        # Quick check if graph is populated
        count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        if count == 0:
            stats = rebuild_graph(conn)
            print(f"Graph built: {stats['nodes']} nodes, {stats['edges']} edges, {stats['code_refs']} code refs")

    if args.command == "related":
        results = find_related(conn, args.query, depth=args.depth)
        if not results:
            print(f"No articles found related to: {args.query}")
        else:
            print(f"Articles related to '{args.query}' ({len(results)} found):")
            print("-" * 60)
            for r in results:
                marker = "*" if r["is_seed"] else " "
                print(f"  {marker} [{r['type']}] [[{r['path'].replace('.md', '')}]] — {r['title']}")

    elif args.command == "orphans":
        orphans = find_orphans(conn)
        if not orphans:
            print("No orphan articles found — all articles are connected.")
        else:
            print(f"Orphan articles ({len(orphans)}):")
            for o in orphans:
                print(f"  [{o['type']}] [[{o['path'].replace('.md', '')}]] — {o['title']}")

    elif args.command == "code-map":
        code_map = get_code_map(conn)
        if not code_map:
            print("No code file references found in articles.")
        else:
            print(f"Code files referenced by articles ({len(code_map)} files):")
            print("-" * 60)
            for code_path, articles in sorted(code_map.items()):
                print(f"\n  {code_path}")
                for a in articles:
                    print(f"    <- [[{a.replace('.md', '')}]]")

    elif args.command == "code-stale":
        stale = find_stale_code_refs(conn)
        if not stale:
            print("All code references are valid.")
        else:
            print(f"Stale code references ({len(stale)}):")
            for s in stale:
                print(f"  {s['code_file']} (referenced in [[{s['article'].replace('.md', '')}]]) — {s['reason']}")

    elif args.command == "stats":
        stats = get_stats(conn)
        print("Knowledge Graph Statistics:")
        print(f"  Nodes:       {stats['nodes']}")
        print(f"    Concepts:    {stats['concepts']}")
        print(f"    Connections: {stats['connections']}")
        print(f"    Q&A:         {stats['qa']}")
        print(f"  Edges:       {stats['edges']}")
        print(f"  Code refs:   {stats['code_refs']}")
        print(f"  Density:     {stats['density']:.3f}")

    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
