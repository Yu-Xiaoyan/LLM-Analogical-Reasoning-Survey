# Paper entry schema

Every file under `data/papers/*.yaml` is a list of paper entries. One file per
survey pillar — this keeps concurrent PRs from colliding.

```yaml
- id: webb2023emergent          # required, unique. <firstauthor><year><first-title-word>
  title: Emergent Analogical Reasoning in Large Language Models
  authors: Webb et al.          # short form; fetch_meta.py can expand to the full list
  venue: Nature Human Behaviour # conference/journal acronym, or "arXiv" for preprints
  year: 2023                    # required
  date: 2023-07                 # optional YYYY-MM; used to sort the "New since the survey" feed
  subsection: symbolic          # required; must be one of the keys in data/taxonomy.yaml
  tags: [must-read, evaluation] # optional; free-form, see docs/taxonomy.md
  links:
    paper: https://...          # leave empty and run scripts/fetch_meta.py to resolve
    code: https://...           # optional
    data: https://...           # optional
    project: https://...        # optional
  in_survey: true               # true = cited in the survey (v1); false = added afterwards
  tldr: One sentence on what the paper actually shows.   # required for `must-read`
```

## Papers proposed for the next revision

Two extra fields mark work that the survey *should* cite but does not yet. They
came out of the coverage audit, and they are what the next revision works from.

```yaml
  proposed_addition: true       # survey does not cite this, and should
  priority: P1                  # P1 must add · P2 should add · P3 optional
  gap_reason: >                 # required when proposed_addition is true —
    Why it belongs, in one sentence, phrased as what it changes about the
    survey rather than what the paper is about.
```

`proposed_addition` is orthogonal to `in_survey`. A paper from 2019 that the
survey missed is `in_survey: false, proposed_addition: true`; a 2026 paper that
simply postdates the survey is `in_survey: false` with no proposal flag. Once a
revision cites something, flip it to `in_survey: true` and drop both fields.

## Rules

- `id` must be globally unique across all files. `scripts/validate.py` enforces it.
- `subsection` must exist in `data/taxonomy.yaml`. A paper lives in exactly one
  subsection (its primary home); everything else it touches goes in `tags`.
- `in_survey: false` puts the entry in the **New since the survey** feed on the
  README, sorted by `date`.
- Never hand-edit `README.md` or anything in `docs/` — they are generated.
  Edit YAML, then run `python scripts/build.py`.
