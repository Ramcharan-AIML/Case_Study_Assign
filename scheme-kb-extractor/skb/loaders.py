"""Turns each source file into a flat list of located lines.

Whatever the format (text PDF, scanned PDF, HTML page, plain text, MyScheme
listing), the extractors only ever see `Line` objects, each of which knows
where it came from. That is what lets every value carry a page/section.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import pymupdf

from .schema import Source


@dataclass
class Line:
    text: str
    location: str  # human readable, e.g. "page 2, line 7"
    tag: str = "p"  # h1 / h2 / li / p ; used for sectioning HTML
    section_hint: str | None = None  # set directly for structured sources (MyScheme)


@dataclass
class Document:
    source: Source
    lines: list[Line]
    needs_ocr: bool = False
    raw_bytes: bytes | None = field(default=None, repr=False)

    @property
    def full_text(self) -> str:
        return "\n".join(l.text for l in self.lines)


def load(source: Source, data_dir: Path) -> Document:
    path = data_dir / source.path
    loader = {"pdf": _load_pdf, "html": _load_html, "text": _load_text, "myscheme": _load_myscheme}[source.kind]
    return loader(source, path)


def _load_pdf(source: Source, path: Path) -> Document:
    raw = path.read_bytes()
    lines: list[Line] = []
    with pymupdf.open(path) as pdf:
        for pno, page in enumerate(pdf, start=1):
            for i, text in enumerate(page.get_text("text").splitlines(), start=1):
                if text.strip():
                    lines.append(Line(text.strip(), f"page {pno}, line {i}"))
    # No text layer at all = a scanned image. We do not guess; we flag it.
    return Document(source, lines, needs_ocr=not lines, raw_bytes=raw)


class _BlockParser(HTMLParser):
    BLOCKS = {"h1", "h2", "h3", "p", "li", "td"}

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str]] = []
        self._tag: str | None = None
        self._buf: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "title"):
            self._skip += 1
        elif tag in self.BLOCKS:
            self._flush()
            self._tag = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title"):
            self._skip -= 1
        elif tag in self.BLOCKS:
            self._flush()

    def handle_data(self, data):
        if not self._skip and self._tag:
            self._buf.append(data)

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if self._tag and text:
            self.blocks.append((self._tag, text))
        self._buf, self._tag = [], None


def _load_html(source: Source, path: Path) -> Document:
    parser = _BlockParser()
    parser.feed(path.read_text(encoding="utf-8"))
    lines, heading, n = [], "top", 0
    for tag, text in parser.blocks:
        if tag in ("h1", "h2", "h3"):
            heading, n = text, 0
            lines.append(Line(text, f"heading <{tag}> '{text}'", tag=tag))
        else:
            n += 1
            lines.append(Line(text, f"section '{heading}', item {n}", tag=tag))
    return Document(source, lines)


def _load_text(source: Source, path: Path) -> Document:
    lines, after_blank = [], True
    for i, t in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not t.strip():
            after_blank = True
            continue
        # In plain-text notes a blank line ends a section, so mark paragraph starts.
        lines.append(Line(t.strip(), f"line {i}", tag="para" if after_blank else "p"))
        after_blank = False
    return Document(source, lines)


# MyScheme page sections -> our field sections
_MYSCHEME_SECTIONS = {
    "scheme_name": ("scheme_name", "Scheme name"),
    "department": ("department", "Ministry / Department"),
    "benefits": ("benefit", "Benefits"),
    "eligibility": ("eligibility", "Eligibility"),
    "documents_required": ("documents_required", "Documents Required"),
    "application_process": ("how_to_apply", "Application Process"),
    "deadline": ("deadline", "Deadline"),
    "official_link": ("official_link", "Official link"),
}


def _load_myscheme(source: Source, path: Path) -> Document:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for key, (section, label) in _MYSCHEME_SECTIONS.items():
        if key not in data:
            continue
        values = data[key] if isinstance(data[key], list) else [data[key]]
        for i, v in enumerate(values, start=1):
            loc = f"MyScheme listing, section '{label}'" + (f", item {i}" if len(values) > 1 else "")
            lines.append(Line(v, loc, tag="li" if len(values) > 1 else "p", section_hint=section))
    return Document(source, lines)
