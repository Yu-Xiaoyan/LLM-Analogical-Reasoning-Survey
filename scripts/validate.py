#!/usr/bin/env python3
"""Validate the paper database. Run in CI on every PR.

    python scripts/validate.py                # structural checks only
    python scripts/validate.py --check-links  # also HEAD every URL (slow, network)

Structural checks are cheap and always run. Link checking is opt-in because it
hits the network and third-party sites rate-limit.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import re
import sys
import urllib.error
import urllib.request

from common import load_benchmarks, load_papers, load_taxonomy, section_index

REQUIRED = ("id", "title", "year", "subsection")
ID_RE = re.compile(r"^[a-z][a-z0-9]*\d{4}[a-z0-9]+$")
UA = {"User-Agent": "awesome-analogical-reasoning-linkcheck/1.0"}


def check_structure(papers, benchmarks, taxonomy) -> list[str]:
    errors: list[str] = []
    valid_subs = set(section_index(taxonomy))
    valid_tags = set(taxonomy.get("tags") or {})

    seen: dict[str, str] = {}
    titles: dict[str, str] = collections.defaultdict(str)

    for paper in papers:
        where = paper.get("_file", "?")
        pid = paper.get("id", "<no id>")

        for field in REQUIRED:
            if not paper.get(field):
                errors.append(f"{where}: `{pid}` is missing required field `{field}`")

        if "id" in paper:
            if paper["id"] in seen:
                errors.append(
                    f"{where}: duplicate id `{paper['id']}` "
                    f"(also in {seen[paper['id']]})"
                )
            seen[paper["id"]] = where
            if not ID_RE.match(paper["id"]):
                errors.append(
                    f"{where}: id `{paper['id']}` should look like "
                    "`<author><year><word>`, lowercase alphanumeric"
                )

        norm = re.sub(r"\W+", "", str(paper.get("title", "")).lower())
        if norm and norm in titles:
            errors.append(
                f"{where}: `{pid}` looks like a duplicate of `{titles[norm]}` "
                "(identical title)"
            )
        titles[norm] = pid

        sub = paper.get("subsection")
        if sub and sub not in valid_subs:
            errors.append(
                f"{where}: `{pid}` has unknown subsection `{sub}`. "
                f"Valid: {sorted(valid_subs)}"
            )

        for tag in paper.get("tags") or []:
            if tag not in valid_tags:
                errors.append(
                    f"{where}: `{pid}` uses undeclared tag `{tag}` — "
                    "add it to data/taxonomy.yaml first"
                )

        if "must-read" in (paper.get("tags") or []) and not paper.get("tldr"):
            errors.append(f"{where}: `{pid}` is tagged must-read but has no tldr")

        if paper.get("date") and not re.match(r"^\d{4}-\d{2}$", str(paper["date"])):
            errors.append(f"{where}: `{pid}` has date `{paper['date']}`, expected YYYY-MM")

        if paper.get("in_survey") is False and not paper.get("date"):
            errors.append(
                f"{where}: `{pid}` is new since the survey and needs a `date` "
                "so it sorts correctly in the feed"
            )

    ids = set(seen)
    for bench in benchmarks:
        ref = bench.get("paper_id")
        if ref and ref not in ids:
            errors.append(
                f"benchmarks.yaml: `{bench['name']}` references unknown paper_id `{ref}`"
            )

    return errors


def collect_urls(papers, benchmarks) -> list[tuple[str, str]]:
    urls = []
    for paper in papers:
        for label, url in (paper.get("links") or {}).items():
            if url:
                urls.append((f"{paper['id']}.{label}", url))
    for bench in benchmarks:
        for label, url in (bench.get("links") or {}).items():
            if url:
                urls.append((f"{bench['name']}.{label}", url))
    return urls


def head(item: tuple[str, str]) -> str | None:
    name, url = item
    request = urllib.request.Request(url, method="HEAD", headers=UA)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 400:
                return f"{name}: HTTP {response.status} — {url}"
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 429):  # bot-blocked or method not allowed
            return None
        return f"{name}: HTTP {exc.code} — {url}"
    except Exception as exc:  # noqa: BLE001 - report anything else as a warning
        return f"{name}: {type(exc).__name__} — {url}"
    return None


def check_links(papers, benchmarks) -> list[str]:
    urls = collect_urls(papers, benchmarks)
    print(f"checking {len(urls)} URLs…", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return [r for r in pool.map(head, urls) if r]


def report_coverage(papers) -> None:
    missing = [p for p in papers if not (p.get("links") or {}).get("paper")]
    tbd = [p for p in papers if str(p.get("authors", "")).startswith("TBD")]
    total = len(papers)
    print(f"\n{total} papers")
    print(f"  {total - len(missing)}/{total} have a resolved paper URL")
    if missing:
        print(f"  missing URL: {', '.join(sorted(p['id'] for p in missing))}")
    if tbd:
        print(f"  placeholder authors ({len(tbd)}): run scripts/fetch_meta.py")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-links", action="store_true")
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    papers = load_papers()
    benchmarks = load_benchmarks()

    errors = check_structure(papers, benchmarks, taxonomy)
    warnings = check_links(papers, benchmarks) if args.check_links else []

    for error in errors:
        print(f"ERROR  {error}")
    for warning in warnings:
        print(f"WARN   {warning}")

    report_coverage(papers)

    if errors:
        print(f"\n{len(errors)} error(s).")
        return 1
    print("\nstructure OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
