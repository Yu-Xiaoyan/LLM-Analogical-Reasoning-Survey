#!/usr/bin/env python3
"""Measure how attention to analogical reasoning has grown, per taxonomy facet.

Counts arXiv submissions per facet per year and writes data/trends.csv.

    python scripts/trends.py --from 2015 --to 2026

Why not just count the papers in data/papers/? Because that list is curated,
not sampled. Its shape reflects our reading and the survey's cutoff, so a trend
drawn from it would mostly measure our own selection. This queries arXiv
directly instead.

Two numbers are recorded per facet-year:

  hits      raw submissions matching the facet query
  baseline  all cs.CL + cs.AI submissions that year

`hits` alone proves very little — all of arXiv grows steeply, so any topic's
raw count rises. The share (hits / baseline) is what shows whether the field is
gaining attention *relative to* its parent field, which is the claim a survey
actually wants to make.

Caveats worth stating in any figure caption built from this:
  - arXiv only. Misses ACL-Anthology-only papers and cognitive science
    journals, so the early years are undercounted more than the recent ones.
  - Keyword queries over title+abstract. They approximate a facet; they do not
    define it. "analogy" in particular collides with the physics/EE senses,
    which is why the facets are scoped to cs.* categories.
  - The final year is partial unless it has ended.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from common import ROOT, ssl_context

ARXIV_API = "http://export.arxiv.org/api/query"
UA = {"User-Agent": "llm-analogical-reasoning-survey/1.0 (bibliometrics)"}
ATOM = {"a": "http://www.w3.org/2005/Atom"}
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}totalResults"

CS = "(cat:cs.CL OR cat:cs.AI OR cat:cs.LG OR cat:cs.CV OR cat:cs.NE)"

# Every facet must require an analogy term. An earlier version let the
# mechanism facet match on "relational" alone, which pulled in relational
# databases and relational learning and reported ~125 hits for 2014 — a decade
# before the topic existed in this sense. If you add a facet, keep ANALOGY in
# it unless the terms are themselves analogy-specific (as the visual ones are).
ANALOGY = '(abs:"analogy" OR abs:"analogical" OR abs:"analogies")'

# Facet -> query. Deliberately aligned with the survey's five pillars so the
# figure and the taxonomy tell the same story.
FACETS = {
    "Analogical reasoning (all)": 'abs:"analogical reasoning"',
    "Capability evaluation": f'{ANALOGY} AND (abs:"benchmark" OR abs:"evaluation" OR abs:"evaluating")',
    "Perceptual / visual analogy": '(abs:"visual analogy" OR abs:"visual analogies" OR abs:"abstract visual reasoning" OR abs:"Raven\'s progressive matrices" OR abs:"Bongard" OR abs:"ARC-AGI")',
    "Mechanism / interpretability": f'{ANALOGY} AND (abs:"interpretability" OR abs:"probing" OR abs:"mechanistic" OR abs:"hidden states" OR abs:"circuit")',
    "Elicitation / prompting": f'{ANALOGY} AND (abs:"prompting" OR abs:"in-context" OR abs:"chain-of-thought" OR abs:"retrieval")',
    # Applied work often does analogy without saying "analogy": law says
    # precedent, engineering says TRIZ or bio-inspired, AI-and-design says
    # case-based. Measuring this facet on the analogy root alone made it look
    # like the slowest-growing area when the instrument was simply blindest
    # there. Even so, this remains a LOWER BOUND — much of the applied
    # literature publishes at ICCBR / ICAIL / Design Science, not on arXiv.
    "Applications": (
        f'({ANALOGY} AND (abs:"design" OR abs:"discovery" OR abs:"education" '
        f'OR abs:"knowledge graph" OR abs:"creativity")) '
        f'OR (abs:"case-based reasoning" OR abs:"design-by-analogy" '
        f'OR abs:"design by analogy" OR abs:"TRIZ" OR abs:"biomimicry" '
        f'OR abs:"bio-inspired design" OR abs:"precedent retrieval")'
    ),
}

BASELINE = "(cat:cs.CL OR cat:cs.AI)"


def count(query: str, year: int, sleep: float) -> int | None:
    """Total hits for a query within one calendar year.

    Reads opensearch:totalResults, which is the server's count of everything
    matching — it is NOT capped by max_results, so this is immune to the
    pagination truncation that silently shortened watch_arxiv.py's sweeps.
    `--selftest` proves that property rather than assuming it.
    """
    window = f"submittedDate:[{year}01010000 TO {year}12312359]"
    params = urllib.parse.urlencode(
        {"search_query": f"({query}) AND {window}", "start": 0, "max_results": 1}
    )
    request = urllib.request.Request(f"{ARXIV_API}?{params}", headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
                raw = response.read()
            root = ET.fromstring(raw)
            total = root.findtext(OPENSEARCH)
            if total is None:
                raise ValueError(
                    "arXiv returned no opensearch:totalResults — the response "
                    "shape changed, and every count from this run is untrustworthy"
                )
            time.sleep(sleep)
            return int(total)
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"    retry {attempt + 1}/4 ({type(exc).__name__})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def selftest(sleep: float) -> int:
    """Verify totalResults equals a full paged enumeration.

    The whole figure rests on totalResults being a true total. A sibling script
    was silently truncating its results for exactly this kind of unchecked
    assumption, so it gets tested rather than trusted. Uses a narrow query whose
    result set is small enough to enumerate.
    """
    query = 'abs:"analogical reasoning"'
    year = 2023
    window = f"submittedDate:[{year}01010000 TO {year}12312359]"
    reported = count(query, year, sleep)

    seen, start, page = set(), 0, 100
    while True:
        params = urllib.parse.urlencode(
            {
                "search_query": f"({query}) AND {window}",
                "start": start,
                "max_results": page,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        request = urllib.request.Request(f"{ARXIV_API}?{params}", headers=UA)
        with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
            entries = ET.fromstring(response.read()).findall("a:entry", ATOM)
        seen.update(e.findtext("a:id", default="", namespaces=ATOM) for e in entries)
        if len(entries) < page:
            break
        start += page
        time.sleep(sleep)

    print(f"selftest: totalResults={reported}, enumerated={len(seen)}")
    if reported != len(seen):
        print("FAIL — totalResults disagrees with a full enumeration.", file=sys.stderr)
        return 1
    print("PASS — counts are not truncated by max_results.")
    return 0


def main() -> int:
    today = dt.date.today()
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", type=int, default=2015)
    parser.add_argument("--to", dest="end", type=int, default=today.year)
    parser.add_argument("--sleep", type=float, default=3.0)
    parser.add_argument("--selftest", action="store_true",
                        help="check totalResults against a full enumeration, then exit")
    parser.add_argument("--out", default=str(ROOT / "data" / "trends.csv"))
    args = parser.parse_args()

    if args.selftest:
        return selftest(args.sleep)

    years = list(range(args.start, args.end + 1))
    rows = []

    for year in years:
        partial = year == today.year
        base = count(BASELINE, year, args.sleep)
        print(f"{year}  baseline cs.CL+cs.AI = {base}", file=sys.stderr)
        for facet, query in FACETS.items():
            scoped = f"({query}) AND {CS}" if "cat:" not in query else query
            hits = count(scoped, year, args.sleep)
            print(f"       {facet:32s} {hits}", file=sys.stderr)
            rows.append(
                {
                    "year": year,
                    "facet": facet,
                    "hits": hits if hits is not None else "",
                    "baseline": base if base is not None else "",
                    # `hits is not None`, not `hits` — a genuine zero is data,
                    # and treating it as missing leaves holes in the series.
                    "share_per_10k": (
                        round(10000 * hits / base, 2)
                        if hits is not None and base
                        else ""
                    ),
                    "partial_year": "yes" if partial else "no",
                }
            )

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["year", "facet", "hits", "baseline", "share_per_10k", "partial_year"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {args.out} ({len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
