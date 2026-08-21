# Maintenance

Notes for whoever keeps this list alive. Contributors want
[CONTRIBUTING.md](CONTRIBUTING.md) instead.

## Before the first publish

The repository ships with paper metadata transcribed from the survey. Titles,
authors, venues and years are from the survey's own bibliography and are
reliable. **URLs are not all resolved yet** — entries without one render as a
Semantic Scholar search link rather than a possibly-wrong direct link.

Run once, with network access:

```bash
pip install -r requirements.txt
make bootstrap
```

That resolves the missing URLs from arXiv and Semantic Scholar, title-checks
every link, and rebuilds `README.md`. Review the diff before committing —
`fetch_meta.py` only accepts exact title matches, but a review is cheap.

Then fill in the placeholders in:

- `templates/README.head.md` — `PLACEHOLDER` (arXiv ID) and `OWNER` (GitHub org/user)
- `CITATION.cff` — the arXiv ID

and run `make build` again.

## Why link-checking is not enough

`make links` only asks whether a URL returns HTTP 200. A wrong-but-real
identifier — say an ACL Anthology number that belongs to a different paper —
passes that check happily. `make verify` is the one that matters: it pulls the
title at the far end and compares it against what we claim. Run it after any
bulk edit.

## Adding new papers

```bash
make watch                      # last 90 days -> candidates.yaml
make watch --since 2026-01      # or a specific window
```

`watch_arxiv.py` queries nine keyword facets matching the taxonomy, drops
anything already listed, filters the physics/EE senses of "analog", and writes
a triage file of YAML stubs. Expect to reject most of it — the queries are
tuned for recall, not precision.

For each keeper: set `subsection`, add `tags`, write a `tldr` if it earns a
star, and move the block into the right `data/papers/*.yaml`. Then
`make build && make check`.

Facets live in `FACETS` at the top of `scripts/watch_arxiv.py`. arXiv is not
the whole field — sweep the ACL Anthology, and check citing papers of the
anchor works (Webb 2023, Lewis & Mitchell 2024, Yasunaga 2023, Sourati 2024,
Opiełka 2025), which is where the non-arXiv work usually surfaces.

## Keeping the survey and the list in sync

`in_survey: false` marks everything published after the survey was finalised.
That flag is what drives the "New since the survey" feed, and it doubles as the
working set for the next revision:

```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
from common import load_papers
new = [p for p in load_papers() if not p.get('in_survey', True)]
for p in sorted(new, key=lambda p: p.get('date','')):
    print(p.get('date'), p['subsection'], '-', p['title'])
"
```

When a revision ships, flip those entries to `in_survey: true` and the feed
empties itself.

## Release checklist

- [ ] `make bootstrap` passes
- [ ] `make links` has no unexplained failures
- [ ] `PLACEHOLDER` / `OWNER` replaced everywhere (`grep -rn 'PLACEHOLDER\|OWNER' --exclude-dir=.git .`)
- [ ] Figures render on github.com (relative paths, not local ones)
- [ ] `README.md` and `docs/` committed in the same commit as the YAML change
