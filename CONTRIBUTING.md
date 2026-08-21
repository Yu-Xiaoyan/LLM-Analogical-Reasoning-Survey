# Contributing

Thanks for helping keep this list current. The most valuable contribution is a
paper we have missed — including your own.

## The important rule

`README.md` and everything under `docs/` are **generated**. Editing them by hand
does nothing; the next build overwrites your change. The source of truth is
`data/`.

```
data/taxonomy.yaml        the category tree (rarely changes)
data/papers/*.yaml        one file per survey pillar — this is where papers live
data/benchmarks.yaml      evaluation resources
```

## Adding a paper

### Option A — open an issue (easiest)

Use the [**Add a paper**](../../issues/new?template=add-paper.yml) form. Fill in
the fields and a maintainer will convert it. Good if you do not want to install
anything.

### Option B — pull request

1. **Pick the file.** The one matching the paper's primary pillar. If the paper
   is an evaluation of model ability, it goes in
   `01-capability-evaluation.yaml`, even if it also proposes a method.

2. **Pick one subsection.** See [`docs/taxonomy.md`](docs/taxonomy.md) for what
   each key means. A paper lives in exactly one subsection — its *primary*
   contribution. Everything else it touches is expressed with `tags`.

3. **Write the entry.** Fields are documented in
   [`data/schema.md`](data/schema.md). Minimum:

   ```yaml
   - id: lastname2026keyword
     title: The Full Title, Capitalised As Published
     authors: First Author et al.
     venue: ACL
     year: 2026
     date: 2026-03          # required when in_survey is false
     subsection: structural
     tags: [benchmark]
     links:
       paper: https://arxiv.org/abs/2603.xxxxx
     in_survey: false       # true only for papers cited in the survey itself
   ```

   You can leave `authors` and `links.paper` out and run
   `python scripts/fetch_meta.py` to fill them in from arXiv/Semantic Scholar.

4. **Rebuild and validate.**

   ```bash
   pip install -r requirements.txt
   python scripts/build.py       # regenerates README.md + docs/
   python scripts/validate.py    # must exit 0
   ```

5. **Commit both** the YAML change and the regenerated files. CI re-runs the
   build and fails the PR if they are out of sync.

## What gets a ⭐ and a `tldr`

`must-read` is reserved for papers we would hand to someone entering the field —
roughly one or two per subsection. The validator requires every `must-read`
entry to carry a `tldr`, because a star without a reason is not useful.

A good `tldr` states what the paper **shows**, not what it is about:

- ✅ "Humans stay flat under counterfactual variants while GPT models degrade
  sharply — the strongest evidence that the ability is non-robust."
- ❌ "This paper studies the robustness of analogical reasoning in LLMs."

Non-`must-read` entries do not need a `tldr`. Add one only if you have something
sharper than the title already says.

## Scope

**In:** work where analogy or relational mapping is the object of study, or is
the mechanism behind a proposed method or application.

**Out:** general reasoning work that merely mentions analogy in passing; the
broad ARC-AGI leaderboard/agent-harness literature, unless the paper says
something about *abstraction and analogy as a capability* rather than about
search or program synthesis. This boundary is a judgement call — open an issue
if you think we have drawn it wrong.

We index papers regardless of venue, including preprints. Peer review status is
visible through the `venue` field, not through exclusion.

## Reporting problems

Broken links, wrong venues, misfiled papers, a `tldr` that misrepresents a
result — all worth an issue. If it is your paper and we have described it badly,
please tell us; we will fix it quickly.
