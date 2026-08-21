#!/usr/bin/env python3
"""Find candidates by citation graph rather than by keyword.

    python scripts/cited_by.py                    # anchors from data/anchors.yaml
    python scripts/cited_by.py --min-anchors 2    # only papers citing 2+ anchors
    python scripts/cited_by.py --since 2025

Keyword sweeps have a recall ceiling that is invisible from the inside. Three
separate blind spots turned up only because a reader named a missing paper:

  - a title facet truncated by pagination (arXiv:2606.13680)
  - applied work using domain vocabulary — precedent, TRIZ, case-based —
    instead of the analogy root
  - mechanism work calling the same object "abstract reasoning" or "symbolic
    mechanisms" and never writing "analogy" at all (arXiv:2502.20332)

All three cite at least one anchor of this literature. Citation traversal fails
differently from keyword search — it misses work that cites nothing central,
where keyword search misses work that words things unusually — so running both
covers far more than either. Neither alone is complete.

Papers citing several anchors at once are the strongest candidates, which is
what --min-anchors ranks on.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

import yaml

from common import DATA, load_papers, ssl_context

S2 = "https://api.semanticscholar.org/graph/v1/paper"
UA = {"User-Agent": "llm-analogical-reasoning-survey/1.0 (citation traversal)"}


def get(url: str, tries: int = 5) -> dict | None:
    """GET with backoff. The public S2 endpoint 429s freely; be patient."""
    headers = dict(UA)
    if os_key := __import__("os").environ.get("S2_API_KEY"):
        headers["x-api-key"] = os_key
    delay = 4.0
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < tries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            print(f"  HTTP {exc.code}", file=sys.stderr)
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"  {type(exc).__name__}", file=sys.stderr)
            return None
    return None


def citations(anchor: str, cap: int, sleep: float) -> list[dict]:
    """Every paper citing `anchor`, paged. `anchor` is an S2-resolvable id."""
    out: list[dict] = []
    offset = 0
    page = 100
    while offset < cap:
        params = urllib.parse.urlencode(
            {
                "fields": "title,year,abstract,externalIds,venue",
                "limit": min(page, cap - offset),
                "offset": offset,
            }
        )
        data = get(f"{S2}/{anchor}/citations?{params}")
        if not data:
            break
        batch = [c["citingPaper"] for c in data.get("data", []) if c.get("citingPaper")]
        out.extend(batch)
        if len(batch) < page or "next" not in data:
            break
        offset = data["next"]
        time.sleep(sleep)
    return out


def known() -> tuple[set[str], set[str]]:
    ids, titles = set(), set()
    for paper in load_papers():
        url = (paper.get("links") or {}).get("paper") or ""
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", url)
        if match:
            ids.add(match.group(1))
        titles.add(re.sub(r"\W+", "", paper["title"].lower()))
    return ids, titles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchors", default=str(DATA / "anchors.yaml"))
    parser.add_argument("--since", type=int, default=2024)
    parser.add_argument("--min-anchors", type=int, default=1)
    parser.add_argument("--cap", type=int, default=500, help="max citing papers per anchor")
    parser.add_argument("--sleep", type=float, default=3.0)
    parser.add_argument("--out", default="citation-candidates.yaml")
    args = parser.parse_args()

    with open(args.anchors, encoding="utf-8") as fh:
        anchors = yaml.safe_load(fh) or []

    seen_ids, seen_titles = known()
    hits: dict[str, dict] = {}
    cited_by_anchor: dict[str, set[str]] = defaultdict(set)

    for anchor in anchors:
        key = anchor["s2_id"]
        print(f"[{anchor['name']}] …", file=sys.stderr, end=" ")
        found = citations(key, args.cap, args.sleep)
        print(f"{len(found)} citing", file=sys.stderr)
        for paper in found:
            if not paper.get("title") or (paper.get("year") or 0) < args.since:
                continue
            norm = re.sub(r"\W+", "", paper["title"].lower())
            arxiv = (paper.get("externalIds") or {}).get("ArXiv")
            if norm in seen_titles or (arxiv and arxiv in seen_ids):
                continue
            hits[norm] = paper
            cited_by_anchor[norm].add(anchor["name"])
        time.sleep(args.sleep)

    ranked = sorted(
        (h for norm, h in hits.items() if len(cited_by_anchor[norm]) >= args.min_anchors),
        key=lambda p: (
            -len(cited_by_anchor[re.sub(r"\W+", "", p["title"].lower())]),
            -(p.get("year") or 0),
        ),
    )
    print(f"\n{len(ranked)} candidates not already listed", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"# citation-graph candidates, {len(anchors)} anchors, year >= {args.since}\n")
        fh.write("# Ranked by how many anchors each cites. Triage by hand.\n\n")
        for paper in ranked:
            norm = re.sub(r"\W+", "", paper["title"].lower())
            anchor_names = ", ".join(sorted(cited_by_anchor[norm]))
            ext = paper.get("externalIds") or {}
            url = (
                f"https://arxiv.org/abs/{ext['ArXiv']}"
                if ext.get("ArXiv")
                else f"https://doi.org/{ext['DOI']}"
                if ext.get("DOI")
                else ""
            )
            fh.write(f"# cites: {anchor_names}\n")
            fh.write(f"# {(paper.get('abstract') or '')[:240]}…\n")
            fh.write(f"- title: {paper['title']!r}\n")
            fh.write(f"  venue: {paper.get('venue') or 'arXiv'}\n")
            fh.write(f"  year: {paper.get('year')}\n")
            fh.write(f"  links:\n    paper: {url}\n\n")

    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
