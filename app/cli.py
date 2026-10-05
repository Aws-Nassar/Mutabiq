"""Minimal CLI for a quick sanity check of the pipeline.

Usage: python -m app.cli "your question"
"""

from __future__ import annotations

import sys

from app.pipeline import Pipeline


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print('Usage: python -m app.cli "your question"', file=sys.stderr)
        return 1
    q = " ".join(argv)
    p = Pipeline()
    res = p.run(q, top_k=3)

    print(f"status : {res.status}")
    if res.notice:
        print(f"notice : {res.notice}")
    if res.sensitive_group:
        print(f"sensitive: {res.sensitive_group}")
    if res.query_restated and res.query_restated != res.query_original:
        print(f"restated: {res.query_restated}")
    if res.comparison:
        for s in res.comparison.get("similarities", []):
            print(f"  ~ {s['statement']}")
        for d in res.comparison.get("differences", []):
            print(f"  ! {d['statement']}")
    if not res.candidates:
        print("no candidates")
        return 0
    for c in res.candidates:
        print(f"[{c.match_score:.3f}] {c.id} {c.title}")
        print(f"    {c.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
