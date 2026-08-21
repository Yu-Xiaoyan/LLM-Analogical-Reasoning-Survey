---

## Contributing

Contributions are very welcome — especially papers we have missed.

**The fastest path:** open an issue with the
[Add a paper](../../issues/new?template=add-paper.yml) template. It is a
structured form; a maintainer converts it to a YAML entry.

**By pull request:**

1. Add an entry to the right file under `data/papers/` — see
   [`data/schema.md`](data/schema.md) for the fields and
   [`docs/taxonomy.md`](docs/taxonomy.md) for choosing a subsection.
2. Run `python scripts/build.py` to regenerate `README.md` and `docs/`.
3. Run `python scripts/validate.py` and make sure it passes.
4. Commit both the YAML and the generated files.

Never edit `README.md` or anything under `docs/` by hand — those changes are
overwritten on the next build. Full guidance in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Scope

In scope: work that treats analogy or relational mapping as the object of
study, or that uses it as the mechanism behind a method or application.

Deliberately at the edge: the ARC-AGI program-synthesis and agent-search
literature. We index the papers that speak to *abstraction and analogy* as a
capability, not every system that improves an ARC leaderboard score. See
[docs/taxonomy.md](docs/taxonomy.md) for the boundary.

## Acknowledgements

Structure and tooling inspired by the many excellent `awesome-*` survey
companions in the LLM community. Paper metadata is resolved through the
[Semantic Scholar](https://www.semanticscholar.org/product/api) and
[arXiv](https://info.arxiv.org/help/api/index.html) APIs.

## License

[CC0-1.0](LICENSE) for the list itself. Individual papers remain under their
own licenses.
