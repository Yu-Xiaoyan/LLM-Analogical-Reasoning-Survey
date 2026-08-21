"""Shared loading/validation helpers for the paper database."""

from __future__ import annotations

import pathlib
import re
import ssl
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PAPERS_DIR = DATA / "papers"


def ssl_context() -> ssl.SSLContext:
    """TLS context that works on a stock macOS python.org install.

    That build ships without root certificates, so every HTTPS call fails with
    CERTIFICATE_VERIFY_FAILED until you run `Install Certificates.command`.
    Falling back to certifi's bundle means the scripts just work; on Linux and
    in CI the system store is already fine and this is a no-op.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def load_taxonomy() -> dict:
    with (DATA / "taxonomy.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_benchmarks() -> list[dict]:
    with (DATA / "benchmarks.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def load_difficulty() -> dict:
    path = DATA / "difficulty.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_results() -> list[dict]:
    path = DATA / "results.yaml"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def load_papers() -> list[dict]:
    """Load every paper entry, tagging each with the file it came from."""
    papers: list[dict] = []
    for path in sorted(PAPERS_DIR.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            entries = yaml.safe_load(fh) or []
        if not isinstance(entries, list):
            sys.exit(f"{path.name}: expected a list of entries, got {type(entries).__name__}")
        for entry in entries:
            entry["_file"] = path.name
        papers.extend(entries)
    return papers


def _entry_bounds(lines: list[str], paper_id: str) -> tuple[int, int]:
    """Line range [start, end) of the entry with this id. Raises if not found."""
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^-\s+id:\s*{re.escape(paper_id)}\s*$", line):
            start = i
            break
    if start is None:
        raise KeyError(paper_id)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("- "):
            end = i
            break
    return start, end


def patch_entry(filename: str, paper_id: str, updates: dict[str, str]) -> None:
    """Surgically update fields of one entry, preserving comments and layout.

    Keys are either a top-level field name (`authors`, `venue`, `year`, `date`)
    or `links.<label>` for any link label (`paper`, `code`, `data`, `project`).
    A field that does not exist yet is inserted in place.

    A full yaml.safe_dump round-trip would be shorter, but it strips every
    comment in the file — including the section dividers — so it is not an
    option here.
    """
    path = PAPERS_DIR / filename
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = _entry_bounds(lines, paper_id)

    for key, value in updates.items():
        rendered = _render_scalar(value)
        if key.startswith("links."):
            _patch_link(lines, start, end, key.split(".", 1)[1], rendered)
        else:
            _patch_field(lines, start, end, key, rendered)
        start, end = _entry_bounds(lines, paper_id)  # bounds shift on insert

    path.write_text("".join(lines), encoding="utf-8")


def _render_scalar(value) -> str:
    text = str(value)
    if text != text.strip() or re.search(r"[:#]\s|^[\[{&*!|>%@`\"']|^\s*$", text):
        return yaml.safe_dump(text, default_flow_style=True).strip().rstrip("\n...").strip()
    return text


def _patch_field(lines: list[str], start: int, end: int, key: str, value: str) -> None:
    pattern = re.compile(rf"^(\s+){re.escape(key)}:\s*(.*)$")
    for i in range(start, end):
        match = pattern.match(lines[i])
        if match:
            lines[i] = f"{match.group(1)}{key}: {value}\n"
            return
    lines.insert(start + 1, f"  {key}: {value}\n")


def _patch_link(lines: list[str], start: int, end: int, label: str, value: str) -> None:
    links_at = None
    for i in range(start, end):
        if re.match(r"^\s+links:\s*$", lines[i]):
            links_at = i
            break
        if re.match(r"^\s+links:\s*\S", lines[i]):  # inline mapping — bail out loudly
            raise ValueError(f"inline `links:` mapping at line {i + 1} is not supported")
    if links_at is None:
        lines.insert(end, "  links:\n")
        lines.insert(end + 1, f"    {label}: {value}\n")
        return
    insert_at = links_at + 1
    for i in range(links_at + 1, end):
        if not lines[i].startswith("    "):
            break
        insert_at = i + 1
        match = re.match(rf"^(\s+){re.escape(label)}:\s*(.*)$", lines[i])
        if match:
            lines[i] = f"{match.group(1)}{label}: {value}\n"
            return
    lines.insert(insert_at, f"    {label}: {value}\n")


def section_index(taxonomy: dict) -> dict[str, dict]:
    """subsection key -> {section, subsection} metadata."""
    index = {}
    for section in taxonomy["sections"]:
        for sub in section["subsections"]:
            index[sub["key"]] = {"section": section, "subsection": sub}
    return index


def sort_key(paper: dict) -> tuple:
    """Newest first, must-read floated to the top of its subsection."""
    must_read = "must-read" in (paper.get("tags") or [])
    return (not must_read, -int(paper.get("year", 0)), paper.get("title", ""))
