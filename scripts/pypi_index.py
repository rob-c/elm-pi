#!/usr/bin/env python3
"""An offline search index of PyPI, for the agent (bootstrap.sh --with-pypi-index).

PyPI has no search API any more - `pip search` fails, and pypi.org/search is a
JavaScript challenge - so finding "a package that does X" needs the web, which a
normal session does not have. This builds agent/pypi-index.db, an SQLite FTS5
table over each package's name, summary, keywords and trove classifiers, from a
published snapshot of PyPI's metadata (pypiIndex in config/elm-pi.json), and
searches it.

  build PARQUET_DIR DB --dataset D --revision R   write DB from the snapshot's Parquet files
  search TERMS... [--all] [-n N]                  print the best matches

The build needs pyarrow, so it runs on the agent's Python (agent/python). The
search needs only the standard library. bootstrap.sh downloads and checksums
the files; nothing here touches the network.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
import sys
from pathlib import Path

COLUMNS = ["name", "version", "summary", "keywords", "classifiers", "requires_python", "recent_7d_downloads", "upload_time"]
# Name matches matter most, then the one-line summary, then keywords, then classifiers.
WEIGHTS = (10.0, 4.0, 3.0, 1.0)
# How far a package's use (log10 of weekly downloads) moves it up the text ranking.
# Tried on physics and data queries: at 1.5-2 near-unused packages named after
# the query buried camelot-py, h5py and lmfit; at 3 an elliptic-curve crypto
# library ranked fourth for "curve fitting".
POPULARITY = 2.5
DEFAULT_DB = Path(__file__).resolve().parents[1] / "agent" / "pypi-index.db"


def build(parquet_dir: Path, db: Path, dataset: str, revision: str) -> int:
    import pyarrow.parquet as pq

    rows = (row for path in sorted(parquet_dir.glob("*.parquet")) for row in pq.read_table(path, columns=COLUMNS).to_pylist())
    return write(rows, db, dataset, revision)


def write(rows, db: Path, dataset: str, revision: str) -> int:
    """Write DB from snapshot rows (dicts with COLUMNS), replacing it only once complete."""
    # One row per release file in the snapshot: keep each package's latest upload.
    latest: dict[str, tuple] = {}
    for row in rows:
        name = (row["name"] or "").strip()
        if not name:
            continue
        key = re.sub(r"[-_.]+", "-", name).lower()
        uploaded = str(row["upload_time"] or "")
        if key in latest and latest[key][-1] >= uploaded:
            continue
        classifiers = row["classifiers"]
        if isinstance(classifiers, (list, tuple)):
            classifiers = "; ".join(classifiers)
        latest[key] = (
            name, row["summary"] or "", row["keywords"] or "", classifiers or "",
            row["version"] or "", row["requires_python"] or "", int(row["recent_7d_downloads"] or 0), uploaded,
        )

    tmp = db.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(
        """
        CREATE VIRTUAL TABLE pkg USING fts5(
            name, summary, keywords, classifiers,
            version UNINDEXED, requires_python UNINDEXED, downloads UNINDEXED, uploaded UNINDEXED,
            tokenize = 'porter unicode61'
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    con.executemany("INSERT INTO pkg VALUES (?, ?, ?, ?, ?, ?, ?, ?)", latest.values())
    snapshot = max((row[-1] for row in latest.values()), default="")[:10]
    con.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [("dataset", dataset), ("revision", revision), ("packages", str(len(latest))), ("snapshot", snapshot)],
    )
    con.commit()
    con.execute("INSERT INTO pkg(pkg) VALUES ('optimize')")
    con.commit()
    con.close()
    os.replace(tmp, db)
    print(f"    {len(latest):,} packages, newest upload {snapshot}, {db.stat().st_size // 10**6} MB")
    return 0


def search(terms: list[str], all_terms: bool, limit: int, db: Path) -> int:
    if not db.exists():
        print(f"pypi-search: no index at {db}. It is built by bootstrap.sh --with-pypi-index.", file=sys.stderr)
        return 1
    words = [w for w in re.findall(r"\w+", " ".join(terms).lower()) if w]
    if not words:
        print("pypi-search: give some words to search for, e.g. pypi-search spectral line fitting", file=sys.stderr)
        return 2
    # Each word quoted, so FTS5 operators and punctuation in a request are text, not
    # syntax. Any word by default: a summary is one line, and requiring every word
    # of "spectral line fitting" found nothing; bm25 still ranks fuller matches first.
    query = (" " if all_terms else " OR ").join(f'"{w}"' for w in words)
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT name, version, summary, downloads, requires_python, bm25(pkg, ?, ?, ?, ?) AS score "
            "FROM pkg WHERE pkg MATCH ? ORDER BY score LIMIT 500",
            (*WEIGHTS, query),
        ).fetchall()
        meta = dict(con.execute("SELECT key, value FROM meta"))
    except sqlite3.DatabaseError as error:
        print(f"pypi-search: {db} is not a usable index ({error}). Re-run bootstrap.sh --with-pypi-index.", file=sys.stderr)
        return 1
    # bm25 is lower-is-better; a package people actually use breaks near-ties.
    rows.sort(key=lambda r: r[5] - POPULARITY * math.log10(1 + int(r[3] or 0)))
    for name, version, summary, downloads, requires_python, _ in rows[:limit]:
        py = f", Python {requires_python}" if requires_python else ""
        print(f"{name} {version} ({int(downloads or 0):,} downloads/7d{py})\n    {summary.strip()[:200]}")
    if not rows:
        print(f"no match for {query}" + (" - try without --all" if all_terms else ""))
    print(
        f"\n[snapshot of {meta.get('packages', '?')} packages, uploads up to {meta.get('snapshot', '?')}: "
        "newer packages are missing and versions may be stale. Check one with: pip index versions NAME]"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pypi-search", description="Search an offline index of PyPI packages.")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("parquet_dir", type=Path)
    b.add_argument("db", type=Path)
    b.add_argument("--dataset", required=True)
    b.add_argument("--revision", required=True)
    s = sub.add_parser("search")
    s.add_argument("terms", nargs="+")
    s.add_argument("--all", action="store_true", help="only packages that match every word")
    s.add_argument("-n", type=int, default=20, help="how many results (default 20)")
    s.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if args.command == "build":
        return build(args.parquet_dir, args.db, args.dataset, args.revision)
    return search(args.terms, args.all, args.n, args.db)


if __name__ == "__main__":
    raise SystemExit(main())
