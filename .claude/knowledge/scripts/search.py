"""
SQLite FTS5 full-text search over knowledge base articles.

Builds/updates an FTS5 index from all markdown articles and provides
ranked search with snippet extraction. No external dependencies — uses
Python's built-in sqlite3 module.

Usage:
    uv run python scripts/search.py "bittensor weight setting"
    uv run python scripts/search.py "VWAP" --rebuild
    uv run python scripts/search.py "agent arena" --limit 5
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from pathlib import Path

from config import KNOWLEDGE_DIR, SCRIPTS_DIR
from utils import list_wiki_articles, parse_frontmatter

DB_PATH = SCRIPTS_DIR / "search.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create FTS5 table and metadata table if they don't exist."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            path,
            title,
            tags,
            body
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS article_meta (
            path TEXT PRIMARY KEY,
            hash TEXT NOT NULL,
            confidence REAL,
            decay_rate TEXT,
            updated TEXT
        )
    """)
    conn.commit()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def rebuild_index(conn: sqlite3.Connection, force: bool = False) -> int:
    """Rebuild the FTS5 index from article files. Returns count of articles indexed."""
    init_db(conn)

    # Get current state
    existing = {}
    try:
        for row in conn.execute("SELECT path, hash FROM article_meta"):
            existing[row[0]] = row[1]
    except sqlite3.OperationalError:
        pass

    articles = list_wiki_articles()
    indexed = 0

    # Track which paths still exist
    current_paths = set()

    for article_path in articles:
        rel = str(article_path.relative_to(KNOWLEDGE_DIR))
        current_paths.add(rel)
        h = _file_hash(article_path)

        if not force and existing.get(rel) == h:
            continue  # unchanged

        content = article_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        body = _strip_frontmatter(content)
        title = fm.get("title", "")
        tags = " ".join(fm.get("tags", [])) if isinstance(fm.get("tags"), list) else str(fm.get("tags", ""))
        confidence = fm.get("confidence")
        decay_rate = fm.get("decay_rate")
        updated = fm.get("updated")

        # Remove old entry if exists
        if rel in existing:
            # Get the rowid for deletion
            row = conn.execute(
                "SELECT rowid FROM articles_fts WHERE path = ?", (rel,)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM articles_fts WHERE rowid = ?", (row[0],))

        # Insert new
        conn.execute(
            "INSERT INTO articles_fts(path, title, tags, body) VALUES (?, ?, ?, ?)",
            (rel, str(title), tags, body),
        )
        conn.execute(
            "INSERT OR REPLACE INTO article_meta(path, hash, confidence, decay_rate, updated) VALUES (?, ?, ?, ?, ?)",
            (rel, h, confidence, decay_rate, updated),
        )
        indexed += 1

    # Remove entries for deleted articles
    for old_path in set(existing.keys()) - current_paths:
        row = conn.execute(
            "SELECT rowid FROM articles_fts WHERE path = ?", (old_path,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM articles_fts WHERE rowid = ?", (row[0],))
        conn.execute("DELETE FROM article_meta WHERE path = ?", (old_path,))

    conn.commit()
    return indexed


def search(
    conn: sqlite3.Connection,
    query_text: str,
    limit: int = 10,
) -> list[dict]:
    """Search articles using FTS5. Returns ranked results with snippets."""
    init_db(conn)

    # FTS5 MATCH query — escape special chars
    safe_query = query_text.replace('"', '""')

    results = []
    try:
        rows = conn.execute(
            """
            SELECT
                path,
                title,
                snippet(articles_fts, 3, '>>>', '<<<', '...', 40) as snippet,
                rank
            FROM articles_fts
            WHERE articles_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (safe_query, limit),
        ).fetchall()

        for path, title, snippet, rank in rows:
            meta = conn.execute(
                "SELECT confidence, decay_rate, updated FROM article_meta WHERE path = ?",
                (path,),
            ).fetchone()

            result = {
                "path": path,
                "title": title,
                "snippet": snippet,
                "rank": rank,
            }
            if meta:
                result["confidence"] = meta[0]
                result["decay_rate"] = meta[1]
                result["updated"] = meta[2]
            results.append(result)

    except sqlite3.OperationalError:
        # Empty index or bad query — try prefix match
        try:
            prefix_query = " ".join(f'"{w}"*' for w in query_text.split())
            rows = conn.execute(
                """
                SELECT path, title,
                    snippet(articles_fts, 3, '>>>', '<<<', '...', 40) as snippet,
                    rank
                FROM articles_fts
                WHERE articles_fts MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (prefix_query, limit),
            ).fetchall()
            for path, title, snippet, rank in rows:
                results.append({
                    "path": path,
                    "title": title,
                    "snippet": snippet,
                    "rank": rank,
                })
        except sqlite3.OperationalError:
            pass

    return results


def main():
    parser = argparse.ArgumentParser(description="Full-text search over knowledge articles")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild the FTS5 index")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    args = parser.parse_args()

    conn = _connect()

    if args.rebuild or not DB_PATH.exists():
        count = rebuild_index(conn, force=args.rebuild)
        print(f"Indexed {count} article(s)")
        if not args.query:
            conn.close()
            return

    if not args.query:
        parser.print_help()
        conn.close()
        return

    # Ensure index exists
    try:
        conn.execute("SELECT count(*) FROM articles_fts").fetchone()
    except sqlite3.OperationalError:
        count = rebuild_index(conn)
        print(f"Built index: {count} article(s)")

    results = search(conn, args.query, limit=args.limit)

    if not results:
        print(f"No results for: {args.query}")
        conn.close()
        return

    print(f"Results for: {args.query}")
    print("-" * 60)
    for i, r in enumerate(results, 1):
        conf_str = ""
        if r.get("confidence"):
            conf_str = f" [conf={r['confidence']:.1f}, decay={r.get('decay_rate', '?')}]"
        path_str = (r.get('path') or '?').replace('.md', '')
        title_str = r.get('title') or '(untitled)'
        print(f"\n{i}. [[{path_str}]] — {title_str}{conf_str}")
        print(f"   {r['snippet']}")

    conn.close()


if __name__ == "__main__":
    main()
