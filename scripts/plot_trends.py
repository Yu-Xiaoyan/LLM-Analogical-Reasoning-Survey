#!/usr/bin/env python3
"""Render data/trends.csv as a publication figure.

    python scripts/plot_trends.py                 # -> figures/trends.pdf + .png

Three panels, because these are different measures and a dual-axis chart would
be a lie about their comparability:

  A  Volume — raw arXiv submissions matching "analogical reasoning". Up ~8x.
  B  Share  — the same query per 10,000 cs.CL+cs.AI submissions. Essentially
              FLAT. cs.CL+cs.AI itself grew ~8x over the same span, so the
              growth in A is the field's growth, not extra attention. Panel B
              exists to stop A from being over-read; do not drop it.
  C  Growth by facet, indexed to the first year — the real finding. Elicitation
              and prompting breaks away from the pack, meaning the field
              shifted from studying the capability to exploiting it.

Windowed from 2018 because the earlier years have single-digit counts, where
the share estimate is dominated by sampling noise (2014 has n=3).

Series identity is carried by direct end-labels rather than a legend: the
validated categorical palette has three slots below 3:1 contrast on a light
surface, and visible labels are the required relief.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

HEADLINE = "Analogical reasoning (all)"
FACET_ORDER = [
    "Capability evaluation",
    "Perceptual / visual analogy",
    "Elicitation / prompting",
    "Mechanism / interpretability",
    "Applications",
]
# Validated categorical slots 1-5 (light mode). Fixed order, never cycled.
FACET_COLOR = {
    "Capability evaluation": "#2a78d6",
    "Perceptual / visual analogy": "#eb6834",
    "Elicitation / prompting": "#1baf7a",
    "Mechanism / interpretability": "#eda100",
    "Applications": "#e87ba4",
}
SHORT = {
    "Capability evaluation": "Evaluation",
    "Perceptual / visual analogy": "Perceptual",
    "Elicitation / prompting": "Elicitation",
    "Mechanism / interpretability": "Mechanism",
    "Applications": "Applications",
}

INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#e3e3e1"
ACCENT = "#2a78d6"


def load(path: pathlib.Path):
    series = defaultdict(dict)
    partial = set()
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            year = int(row["year"])
            if row["partial_year"] == "yes":
                partial.add(year)
            if row["hits"] == "":
                continue
            series[row["facet"]][year] = {
                "hits": int(row["hits"]),
                "share": float(row["share_per_10k"]) if row["share_per_10k"] else None,
            }
    return series, partial


def style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "Times New Roman", "Georgia"],
            "font.size": 8,
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "axes.titlesize": 8.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlepad": 7,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def dress(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))


def split_partial(years: list[int], values: list[float], partial: set[int]):
    """Separate complete years from the still-accruing one.

    Returns (complete_years, complete_values, tail_years, tail_values) where the
    tail repeats the last complete point so the dashed segment joins up.

    A partial year plotted as another point on the same solid line reads as a
    decline — the eye takes the downward slope before it takes any shading or
    footnote. Counts for a partial year are not comparable to full ones, so
    they get a visually different mark instead.
    """
    complete = [y for y in years if y not in partial]
    tail = [y for y in years if y in partial]
    if not tail:
        return years, values, [], []
    index = {y: v for y, v in zip(years, values)}
    cvals = [index[y] for y in complete]
    join = [complete[-1]] + tail if complete else tail
    return complete, cvals, join, [index[y] for y in join]


def draw_partial_tail(ax, tail_years, tail_values, color) -> None:
    """Dashed connector plus a hollow marker — 'measured differently', not 'lower'."""
    if len(tail_years) < 2:
        return
    ax.plot(
        tail_years, tail_values,
        color=color, linewidth=1.4, linestyle=(0, (2.5, 2)), zorder=3,
    )
    ax.plot(
        tail_years[-1], tail_values[-1],
        marker="o", markersize=4.5, markerfacecolor="white",
        markeredgecolor=color, markeredgewidth=1.5, zorder=4,
    )


def note_partial(ax, partial, years, label="Jan–Aug only") -> None:
    for year in sorted(partial):
        if year in years:
            ax.annotate(
                label,
                (year, ax.get_ylim()[1]),
                textcoords="offset points", xytext=(2, -2),
                ha="right", va="top", fontsize=5.8, color=MUTED, rotation=90,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(ROOT / "data" / "trends.csv"))
    parser.add_argument("--start", type=int, default=2018, help="first year to plot")
    parser.add_argument("--out", default=str(ROOT / "figures" / "trends"))
    args = parser.parse_args()

    path = pathlib.Path(args.csv)
    if not path.exists():
        sys.exit(f"{path} not found — run scripts/trends.py first")

    series, partial = load(path)
    if HEADLINE not in series:
        sys.exit(f"'{HEADLINE}' missing from {path}")

    style()
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.45))
    fig.subplots_adjust(left=0.055, right=0.995, top=0.80, bottom=0.16, wspace=0.42)

    head = {y: v for y, v in series[HEADLINE].items() if y >= args.start}
    years = sorted(head)

    # -- A. volume -----------------------------------------------------------
    ax = axes[0]
    counts = [head[y]["hits"] for y in years]
    cy, cv, ty, tv = split_partial(years, counts, partial)
    ax.fill_between(cy, cv, color=ACCENT, alpha=0.13, linewidth=0, zorder=2)
    ax.plot(cy, cv, color=ACCENT, linewidth=2, zorder=3, solid_capstyle="round")
    ax.plot(cy[-1], cv[-1], "o", color=ACCENT, markersize=4.5, zorder=4)
    draw_partial_tail(ax, ty, tv, ACCENT)
    ax.set_ylim(0, max(counts) * 1.3)
    dress(ax)
    ax.set_title("A   Volume", color=INK)
    ax.set_ylabel("submissions", color=MUTED, fontsize=7)
    peak = max(range(len(cy)), key=lambda i: cv[i])
    ax.annotate(
        f"{cv[peak]}",
        (cy[peak], cv[peak]),
        textcoords="offset points", xytext=(0, 6),
        ha="center", fontsize=7, color=INK, fontweight="bold",
    )
    note_partial(ax, partial, years)

    # -- B. share ------------------------------------------------------------
    # The corrective panel. Reviewers will read A as "the field is booming";
    # B is what stops that reading from being wrong.
    ax = axes[1]
    shares = [head[y]["share"] for y in years]
    ax.plot(years, shares, color=ACCENT, linewidth=2, zorder=3, solid_capstyle="round")
    ax.plot(years[-1], shares[-1], "o", color=ACCENT, markersize=4.5, zorder=4)
    mean = sum(shares) / len(shares)
    ax.axhline(mean, color=ACCENT, linewidth=0.9, linestyle=(0, (4, 3)), zorder=2)
    ax.set_ylim(0, max(shares) * 1.62)
    dress(ax)
    ax.set_title("B   Share of cs.CL + cs.AI", color=INK)
    ax.set_ylabel("per 10,000", color=MUTED, fontsize=7)
    ax.annotate(
        f"mean {mean:.1f}",
        (years[-1], mean), textcoords="offset points", xytext=(-1, 6),
        ha="right", va="bottom", fontsize=6.2, color=ACCENT,
    )
    ax.annotate(
        "no trend — the topic grows\nwith its field, not faster",
        (years[len(years) // 2], max(shares) * 1.58),
        ha="center", va="top", fontsize=6.4, color=MUTED, style="italic",
    )
    # No partial-year treatment here on purpose: numerator and denominator
    # cover the same window, so the ratio stays comparable across years.

    # -- C. growth by facet, indexed ----------------------------------------
    # Absolute counts all rise together, so indexing to the base year is what
    # separates a facet that actually accelerated from one that merely grew.
    ax = axes[2]
    ends = []
    base_year = years[0]
    for facet in FACET_ORDER:
        if facet not in series:
            continue
        fyears = [y for y in sorted(series[facet]) if y >= base_year]
        base = series[facet].get(base_year, {}).get("hits")
        if not base:
            continue
        vals = [100.0 * series[facet][y]["hits"] / base for y in fyears]
        cy, cv, ty, tv = split_partial(fyears, vals, partial)
        ax.plot(
            cy, cv,
            color=FACET_COLOR[facet], linewidth=1.7, zorder=3, solid_capstyle="round",
        )
        draw_partial_tail(ax, ty, tv, FACET_COLOR[facet])
        last_x = ty[-1] if ty else cy[-1]
        last_y = tv[-1] if tv else cv[-1]
        ends.append((last_y, last_x, facet))
    ax.axhline(100, color=GRID, linewidth=0.8, zorder=1)
    dress(ax)
    ax.set_title("C   Growth by facet", color=INK)
    ax.set_ylabel(f"indexed, {base_year} = 100", color=MUTED, fontsize=7)

    # Direct end-labels, nudged apart so they never collide. This is the
    # required relief for the low-contrast slots, so it must stay legible.
    top = ax.get_ylim()[1]
    ends.sort(reverse=True)
    minimum_gap = top * 0.115
    placed: list[float] = []
    for value, year, facet in ends:
        target = value
        for prior in placed:
            if abs(target - prior) < minimum_gap:
                target = prior - minimum_gap
        placed.append(target)
        # Anchor at the nudged position, not the raw one — otherwise the
        # de-collision is computed and then thrown away.
        ax.annotate(
            SHORT[facet],
            (year, target), xycoords="data",
            xytext=(6, 0), textcoords="offset points",
            va="center", ha="left", fontsize=6.4,
            color=FACET_COLOR[facet], fontweight="bold",
            annotation_clip=False,
        )
    # Room inside the axes for the end-labels, with ticks pinned to real years
    # so the locator does not invent a 2028 to fill the gutter.
    ax.set_xlim(min(years) - 0.3, max(years) + 2.5)
    ax.set_xticks([y for y in years if y % 2 == 0])

    out = pathlib.Path(args.out)
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=300, bbox_inches="tight")
    print(f"wrote {out.with_suffix('.pdf')} and {out.with_suffix('.png')}")

    first, last = years[0], years[-1]
    print(f"\n{HEADLINE}: {head[first]['hits']} ({first}) -> {head[last]['hits']} ({last})")
    print(f"share per 10k: {head[first]['share']} -> {head[last]['share']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
