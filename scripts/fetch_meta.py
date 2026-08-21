#!/usr/bin/env python3
"""Resolve and verify paper metadata against public bibliographic APIs.

Fills in `authors`, `venue`, `year` and `links.paper` where they are missing,
and — with --verify — checks that the links we already have point at the paper
we claim they do.

    python scripts/fetch_meta.py --dry-run        # show what would change
    python scripts/fetch_meta.py                  # write back to data/papers/
    python scripts/fetch_meta.py --verify         # title-check existing links
    python scripts/fetch_meta.py --only anon2026adage

Rules:
  - An entry whose `links.paper` is already an arXiv URL is resolved by ID.
  - Everything else is looked up by title through `resolve_by_title`, which
    tries Crossref, then arXiv, then OpenAlex, then Semantic Scholar.
  - **A match is only ever accepted when the normalised titles are identical.**
    That is what keeps a near-miss from silently pointing an entry at the wrong
    paper — the failure mode that link checking cannot catch, because a wrong
    identifier still returns HTTP 200.
  - Existing non-empty values are never overwritten unless --force is given.
    Authors are only filled in when absent, since a hand-written author list is
    usually better than the abbreviation this would generate.

Environment:
  OPENALEX_MAILTO   identifies you to OpenAlex/Crossref for their faster,
                    more permissive "polite pool". Recommended.
  S2_API_KEY        optional; the public Semantic Scholar endpoint 429s readily.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from common import load_papers, patch_entry, ssl_context

ARXIV_API = "http://export.arxiv.org/api/query"
OPENALEX_API = "https://api.openalex.org/works"
CROSSREF_API = "https://api.crossref.org/works"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
UA = {"User-Agent": "llm-analogical-reasoning-survey/1.0 (paper list maintenance)"}
# OpenAlex gives you the faster "polite pool" if you identify yourself.
MAILTO = os.environ.get("OPENALEX_MAILTO", "")


def normalise(title: str) -> str:
    return re.sub(r"\W+", "", str(title).lower())


def get(url: str, headers: dict | None = None, retries: int = 3) -> bytes | None:
    """GET with exponential backoff on rate limiting.

    The unauthenticated Semantic Scholar endpoint 429s readily, so a bare
    request fails often enough to make a bulk resolve useless without this.
    """
    request = urllib.request.Request(url, headers={**UA, **(headers or {})})
    delay = 5.0
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=45, context=ssl_context()) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < retries - 1:
                print(f"  HTTP {exc.code}, retrying in {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            print(f"  HTTP {exc.code} for {url}", file=sys.stderr)
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"  {type(exc).__name__} for {url}", file=sys.stderr)
            return None
    return None


def canonical_url(doi: str | None, arxiv_id: str | None, fallback: str | None) -> str | None:
    """Prefer a stable, human-readable landing page over a DOI redirect."""
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    if doi:
        doi = doi.replace("https://doi.org/", "")
        if doi.startswith("10.18653/v1/"):  # ACL Anthology
            return f"https://aclanthology.org/{doi[len('10.18653/v1/'):]}/"
        match = re.match(r"10\.48550/arxiv\.(\S+)", doi, re.IGNORECASE)  # arXiv's own DOIs
        if match:
            return f"https://arxiv.org/abs/{match.group(1)}"
        return f"https://doi.org/{doi}"
    return fallback


def from_crossref(title: str) -> dict | None:
    """Resolve by title against Crossref — authoritative for anything with a DOI."""
    query = {"query.bibliographic": title, "rows": "5", "select": "title,author,DOI,issued,container-title"}
    if MAILTO:
        query["mailto"] = MAILTO
    raw = get(f"{CROSSREF_API}?{urllib.parse.urlencode(query)}")
    if not raw:
        return None
    for hit in (json.loads(raw).get("message", {}).get("items") or []):
        found = (hit.get("title") or [""])[0]
        if normalise(found) != normalise(title):
            continue  # only ever accept an exact title match
        authors = [
            " ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "")
            for a in (hit.get("author") or [])
        ]
        parts = (hit.get("issued") or {}).get("date-parts") or [[None]]
        container = (hit.get("container-title") or [None])[0]
        return {
            "title": found,
            "authors": [a for a in authors if a],
            "year": parts[0][0],
            "venue": container,
            "url": canonical_url(hit.get("DOI"), None, None),
        }
    return None


def from_arxiv_title(title: str) -> dict | None:
    """Resolve a preprint by exact title against the arXiv API."""
    escaped = re.sub(r'["\\]', " ", title)
    params = urllib.parse.urlencode(
        {"search_query": f'ti:"{escaped}"', "max_results": 5}
    )
    raw = get(f"{ARXIV_API}?{params}")
    if not raw:
        return None
    for entry in ET.fromstring(raw).findall("a:entry", ATOM):
        found = " ".join((entry.findtext("a:title", default="", namespaces=ATOM)).split())
        if normalise(found) != normalise(title):
            continue
        url = entry.findtext("a:id", default="", namespaces=ATOM)
        arxiv_id = url.split("/abs/")[-1].split("v")[0]
        published = entry.findtext("a:published", default="", namespaces=ATOM)
        return {
            "title": found,
            "authors": [
                a.findtext("a:name", default="", namespaces=ATOM)
                for a in entry.findall("a:author", ATOM)
            ],
            "year": int(published[:4]) if published else None,
            "date": published[:7] if published else None,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
        }
    return None


def resolve_by_title(title: str) -> dict | None:
    """Try each source in turn. Order is by reliability, not by speed.

    Crossref first because a DOI is the canonical published record; arXiv next
    for preprints that never got one; OpenAlex and Semantic Scholar last, both
    because their coverage overlaps the first two and because their public
    endpoints rate-limit hard.
    """
    for source in (from_crossref, from_arxiv_title, from_openalex, from_s2):
        meta = source(title)
        if meta and meta.get("url"):
            return meta
    return None


def from_openalex(title: str) -> dict | None:
    """Resolve by title against OpenAlex — best coverage, no API key needed."""
    query = {"filter": f"title.search:{title}", "per-page": "5"}
    if MAILTO:
        query["mailto"] = MAILTO
    raw = get(f"{OPENALEX_API}?{urllib.parse.urlencode(query)}")
    if not raw:
        return None
    for hit in (json.loads(raw).get("results") or []):
        if normalise(hit.get("display_name") or "") != normalise(title):
            continue  # only ever accept an exact title match
        arxiv_id = None
        for location in hit.get("locations") or []:
            landing = (location.get("landing_page_url") or "")
            match = re.search(r"arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5})", landing)
            if match:
                arxiv_id = match.group(1)
                break
        source = ((hit.get("primary_location") or {}).get("source") or {})
        venue = source.get("display_name")
        return {
            "title": hit.get("display_name"),
            "authors": [
                (a.get("author") or {}).get("display_name", "")
                for a in (hit.get("authorships") or [])
            ],
            "year": hit.get("publication_year"),
            "venue": None if venue in (None, "arXiv (Cornell University)") else venue,
            "url": canonical_url(hit.get("doi"), arxiv_id, hit.get("id")),
        }
    return None


def arxiv_id_of(paper: dict) -> str | None:
    url = (paper.get("links") or {}).get("paper") or ""
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", url)
    return match.group(1) if match else None


def from_arxiv(arxiv_id: str) -> dict | None:
    raw = get(f"{ARXIV_API}?id_list={arxiv_id}&max_results=1")
    if not raw:
        return None
    entry = ET.fromstring(raw).find("a:entry", ATOM)
    if entry is None:
        return None
    title = entry.find("a:title", ATOM)
    if title is None or title.text is None:
        return None
    authors = [
        a.findtext("a:name", default="", namespaces=ATOM)
        for a in entry.findall("a:author", ATOM)
    ]
    published = entry.findtext("a:published", default="", namespaces=ATOM)
    return {
        "title": " ".join(title.text.split()),
        "authors": authors,
        "year": int(published[:4]) if published else None,
        "date": published[:7] if published else None,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def from_s2(title: str) -> dict | None:
    params = urllib.parse.urlencode(
        {"query": title, "limit": 5, "fields": "title,year,authors,venue,externalIds,url"}
    )
    headers = {}
    if os.environ.get("S2_API_KEY"):
        headers["x-api-key"] = os.environ["S2_API_KEY"]
    raw = get(f"{S2_API}?{params}", headers)
    if not raw:
        return None
    for hit in (json.loads(raw).get("data") or []):
        if normalise(hit.get("title", "")) != normalise(title):
            continue  # only accept an exact title match
        ext = hit.get("externalIds") or {}
        if ext.get("ArXiv"):
            url = f"https://arxiv.org/abs/{ext['ArXiv']}"
        elif ext.get("ACL"):
            url = f"https://aclanthology.org/{ext['ACL']}/"
        elif ext.get("DOI"):
            url = f"https://doi.org/{ext['DOI']}"
        else:
            url = hit.get("url")
        return {
            "title": hit.get("title"),
            "authors": [a["name"] for a in (hit.get("authors") or [])],
            "year": hit.get("year"),
            "venue": hit.get("venue") or None,
            "url": url,
        }
    return None


def short_authors(names: list[str]) -> str:
    if not names:
        return "unknown"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    if len(names) == 3:
        return f"{names[0]}, {names[1]} and {names[2]}"
    return f"{names[0]} et al."


def authors_missing(paper: dict) -> bool:
    return not paper.get("authors") or str(paper["authors"]).startswith("TBD")


def needs_work(paper: dict) -> bool:
    return (
        not (paper.get("links") or {}).get("paper")
        or str(paper.get("authors", "")).startswith("TBD")
        or not paper.get("authors")
    )


def verify(papers: list[dict], sleep: float) -> int:
    """Check that every arXiv link actually points at the paper we claim.

    A wrong-but-existing identifier returns HTTP 200, so link checking cannot
    catch it — only comparing titles can. Non-arXiv links (ACL Anthology, DOI)
    are checked the other way round: we resolve the title on Semantic Scholar
    and compare the URL it reports.
    """
    checked = mismatched = unchecked = 0
    for paper in papers:
        url = (paper.get("links") or {}).get("paper")
        if not url:
            continue
        arxiv_id = arxiv_id_of(paper)
        if arxiv_id:
            meta = from_arxiv(arxiv_id)
            time.sleep(sleep)
            if not meta:
                print(f"?  {paper['id']}: arXiv {arxiv_id} did not resolve")
                unchecked += 1
                continue
            checked += 1
            if normalise(meta["title"]) != normalise(paper["title"]):
                mismatched += 1
                print(f"!! {paper['id']}: {url}")
                print(f"     listed:   {paper['title']}")
                print(f"     arXiv is: {meta['title']}")
        else:
            meta = resolve_by_title(paper["title"])
            time.sleep(sleep)
            if not meta or not meta.get("url"):
                unchecked += 1
                continue
            checked += 1
            if meta["url"].rstrip("/") != url.rstrip("/"):
                mismatched += 1
                print(f"?? {paper['id']}: URL disagrees with Semantic Scholar")
                print(f"     listed: {url}")
                print(f"     S2 has: {meta['url']}")

    print(f"\nverified {checked}, {mismatched} mismatched, {unchecked} unresolvable")
    return 1 if mismatched else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify",
        action="store_true",
        help="title-check existing links instead of filling in missing ones",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="overwrite existing values")
    parser.add_argument("--only", help="resolve a single paper id")
    parser.add_argument("--sleep", type=float, default=1.2, help="seconds between requests")
    args = parser.parse_args()

    papers = load_papers()
    if args.verify:
        return verify(
            [p for p in papers if not args.only or p["id"] == args.only], args.sleep
        )

    targets = [
        p
        for p in papers
        if (args.only and p["id"] == args.only) or (not args.only and needs_work(p))
    ]
    print(f"{len(targets)} entr{'y' if len(targets) == 1 else 'ies'} to resolve\n")

    changed = 0
    for paper in targets:
        print(f"{paper['id']}: {paper['title'][:70]}")
        arxiv_id = arxiv_id_of(paper)
        meta = (
            from_arxiv(arxiv_id)
            if arxiv_id
            else resolve_by_title(paper["title"])
        )
        time.sleep(args.sleep)
        if not meta:
            print("  no match\n")
            continue

        updates: dict[str, object] = {}
        # Only touch authors when we have none. A hand-written "A, B and C" is
        # better than what a re-resolve would collapse it to.
        if meta.get("authors") and (args.force or authors_missing(paper)):
            updates["authors"] = short_authors(meta["authors"])
        for field in ("year", "venue", "date"):
            if meta.get(field) and (args.force or not paper.get(field)):
                updates[field] = meta[field]
        if meta.get("url") and (args.force or not (paper.get("links") or {}).get("paper")):
            updates["links.paper"] = meta["url"]

        if normalise(meta["title"]) != normalise(paper["title"]):
            print(f"  ! title differs upstream: {meta['title']}")

        for key, value in updates.items():
            was = paper.get(key) if "." not in key else (paper.get("links") or {}).get("paper")
            print(f"  {key}: {was!r} -> {value!r}")
        if updates and not args.dry_run:
            patch_entry(paper["_file"], paper["id"], updates)
        changed += bool(updates)
        print()

    if args.dry_run:
        print(f"dry run — {changed} entries would change")
    else:
        print(f"wrote {changed} updated entries. Now run: python scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
