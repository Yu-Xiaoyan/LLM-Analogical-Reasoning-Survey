.PHONY: help build check links verify meta watch bootstrap

help:
	@grep -E '^[a-z]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t—/'

build:      ## regenerate README.md and docs/ from data/
	python3 scripts/build.py

check:      ## structural validation, no network (this is what CI runs)
	python3 scripts/validate.py

meta:       ## fill in missing authors/venues/links from arXiv + Semantic Scholar
	python3 scripts/fetch_meta.py

verify:     ## title-check every existing link (catches links to the WRONG paper)
	python3 scripts/fetch_meta.py --verify

links:      ## check every URL resolves (catches dead links, not wrong ones)
	python3 scripts/validate.py --check-links

watch:      ## keyword sweep of arXiv -> candidates.yaml
	python3 scripts/watch_arxiv.py

cited:      ## citation-graph sweep from data/anchors.yaml -> citation-candidates.yaml
	python3 scripts/cited_by.py

sweep: watch cited   ## both recall paths; neither alone is complete

trends:     ## re-measure arXiv publication trends and redraw figures/trends.*
	python3 scripts/trends.py --from 2014
	python3 scripts/plot_trends.py

bootstrap:  ## first run: resolve everything, verify it, rebuild
	python3 scripts/fetch_meta.py
	python3 scripts/fetch_meta.py --verify
	python3 scripts/build.py
	python3 scripts/validate.py
