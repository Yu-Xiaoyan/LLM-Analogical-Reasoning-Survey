#!/usr/bin/env python3
"""Surface new arXiv papers that are candidates for this list.

Queries arXiv across the keyword facets that match the survey's taxonomy,
drops anything already in data/papers/, filters obvious noise (the word
"analog" matches analog circuits, planetary analogs, quantum analogs …), and
writes a triage file you can edit down and paste into the YAML.

    python scripts/watch_arxiv.py --since 2026-01                # default: last 90 days
    python scripts/watch_arxiv.py --since 2026-01 --until 2026-09
    python scripts/watch_arxiv.py --out candidates.yaml

The output is deliberately *not* merged automatically. Recall matters more
than precision here — expect to reject most of what it finds.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from common import load_papers, ssl_context

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
UA = {"User-Agent": "awesome-analogical-reasoning/1.0 (paper list maintenance)"}

# Facet -> arXiv query. Keys are only used to label the triage output.
FACETS = {
    "core": 'all:"analogical reasoning"',
    "analogy-llm": 'abs:"analogy" AND (abs:"language model" OR abs:"LLM")',
    "structure-mapping": 'abs:"structure mapping" OR abs:"structure-mapping"',
    "relational": 'abs:"relational reasoning" AND abs:"abstraction"',
    "visual-analogy": 'abs:"visual analogy" OR abs:"abstract visual reasoning"',
    "rpm-bongard": 'abs:"Raven\'s progressive matrices" OR abs:"Bongard"',
    "arc": 'abs:"ARC-AGI" AND (abs:"abstraction" OR abs:"analogy")',
    "metaphor": 'abs:"metaphor" AND (abs:"language model" OR abs:"LLM")',
    "proportional": 'abs:"proportional analogy" OR abs:"analogical proportion"',
}

# Categories we care about. Everything else is almost always a false positive
# from the physics/EE senses of "analog"/"analogue".
KEEP_CATEGORIES = {"cs.CL", "cs.AI", "cs.LG", "cs.CV", "cs.NE", "cs.HC", "q-bio.NC"}

# Title patterns that are reliably the wrong sense of the word.
NOISE = re.compile(
    r"\b(analog(?:ue)?\s+(?:circuit|comput|front-end|layout|gauge|quantum|"
    r"in-memory|design|signal)|planetary analog|jupiter analog|"
    r"analog-to-digital|analog error)",
    re.IGNORECASE,
)


def query(search: str, start_date: str, end_date: str, limit: int = 100) -> list[dict]:
    window = f"submittedDate:[{start_date}0000 TO {end_date}0000]"
    params = urllib.parse.urlencode(
        {
            "search_query": f"({search}) AND {window}",
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(f"{ARXIV_API}?{params}", headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
                raw = response.read()
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  retry {attempt + 1}/3: {type(exc).__name__}", file=sys.stderr)
            time.sleep(5)
    else:
        return []

    out = []
    for entry in ET.fromstring(raw).findall("a:entry", ATOM):
        title = entry.findtext("a:title", default="", namespaces=ATOM)
        categories = [c.get("term") for c in entry.findall("a:category", ATOM)]
        primary = entry.find("{http://arxiv.org/schemas/atom}primary_category")
        out.append(
            {
                "id": entry.findtext("a:id", default="", namespaces=ATOM)
                .split("/abs/")[-1]
                .split("v")[0],
                "title": " ".join(title.split()),
                "date": entry.findtext("a:published", default="", namespaces=ATOM)[:10],
                "primary": primary.get("term") if primary is not None else "",
                "categories": categories,
                "authors": [
                    a.findtext("a:name", default="", namespaces=ATOM)
                    for a in entry.findall("a:author", ATOM)
                ],
                "abstract": " ".join(
                    entry.findtext("a:summary", default="", namespaces=ATOM).split()
                ),
            }
        )
    return out


def known_arxiv_ids() -> set[str]:
    ids = set()
    for paper in load_papers():
        url = (paper.get("links") or {}).get("paper") or ""
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", url)
        if match:
            ids.add(match.group(1))
    return ids


def known_titles() -> set[str]:
    return {re.sub(r"\W+", "", p["title"].lower()) for p in load_papers()}


def main() -> int:
    today = dt.date.today()
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=(today - dt.timedelta(days=90)).strftime("%Y-%m"))
    parser.add_argument("--until", default=(today + dt.timedelta(days=1)).strftime("%Y-%m"))
    parser.add_argument("--out", default="candidates.yaml")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=3.0)
    args = parser.parse_args()

    start = args.since.replace("-", "") + "01"
    end = args.until.replace("-", "") + "01"

    seen_ids, seen_titles = known_arxiv_ids(), known_titles()
    found: dict[str, dict] = {}

    for facet, search in FACETS.items():
        print(f"[{facet}] querying…", file=sys.stderr)
        for hit in query(search, start, end, args.limit):
            if hit["id"] in seen_ids:
                continue
            if re.sub(r"\W+", "", hit["title"].lower()) in seen_titles:
                continue
            if not KEEP_CATEGORIES.intersection(hit["categories"]):
                continue
            if NOISE.search(hit["title"]):
                continue
            found.setdefault(hit["id"], {**hit, "facets": []})["facets"].append(facet)
        time.sleep(args.sleep)

    ordered = sorted(found.values(), key=lambda h: h["date"], reverse=True)
    print(f"\n{len(ordered)} candidates in {args.since}..{args.until}", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(f"# arXiv candidates {args.since}..{args.until}\n")
        fh.write(f"# generated {today.isoformat()} by scripts/watch_arxiv.py\n")
        fh.write("# Triage by hand: delete what does not belong, fill in\n")
        fh.write("# `subsection`, `tags` and `tldr`, then move into data/papers/.\n\n")
        for hit in ordered:
            author = (hit["authors"] or ["unknown"])[0].split()[-1].lower()
            slug = re.sub(r"[^a-z]", "", hit["title"].split()[0].lower()) or "paper"
            fh.write(f"# facets: {', '.join(hit['facets'])} | {hit['primary']}\n")
            fh.write(f"# {hit['abstract'][:300]}…\n")
            fh.write(f"- id: {author}{hit['date'][:4]}{slug}\n")
            fh.write(f"  title: {hit['title']!r}\n")
            fh.write(f"  authors: {hit['authors'][0]}")
            fh.write(" et al.\n" if len(hit["authors"]) > 2 else "\n")
            fh.write("  venue: arXiv\n")
            fh.write(f"  year: {hit['date'][:4]}\n")
            fh.write(f"  date: {hit['date'][:7]}\n")
            fh.write("  subsection: TODO\n")
            fh.write("  links:\n")
            fh.write(f"    paper: https://arxiv.org/abs/{hit['id']}\n")
            fh.write("  in_survey: false\n\n")

    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
