"""Split a contract into numbered clauses. Handles '1.', '1.1', 'Section 3', 'ARTICLE IV' style headings."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HEADING = re.compile(r"^\s*(?:(?:section|article|clause)\s+)?(\d+(?:\.\d+)*|[IVXL]+)[.)]?\s+([A-Z][^\n]{2,80})$", re.I | re.M)


@dataclass
class Clause:
    number: str
    heading: str
    text: str


def load_text(path: str | Path) -> str:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    if p.suffix.lower() == ".docx":
        import docx  # python-docx

        return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    return p.read_text(encoding="utf-8")


def segment(text: str) -> list[Clause]:
    matches = list(HEADING.finditer(text))
    clauses: list[Clause] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        clauses.append(Clause(m.group(1), m.group(2).strip(), body))
    if not clauses:  # fall back to paragraphs
        clauses = [Clause(str(i + 1), p.split("\n")[0][:60], p) for i, p in enumerate(re.split(r"\n\s*\n", text)) if p.strip()]
    return clauses
