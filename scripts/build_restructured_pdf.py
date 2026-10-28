#!/usr/bin/env python3
"""Render docs/restructured.md to docs/Restructured.pdf.

Uses the same dependency-free PDF primitives as the ECG report writer, so the
documentation and the product share one small PDF implementation.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "django"))

from reports.pdf import (  # noqa: E402
    ACCENT,
    CONTENT_WIDTH,
    INK,
    MARGIN,
    MUTED,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    RULE,
    WARN,
    _PDF,
    _num,
    _wrap,
)

SOURCE = REPO_ROOT / "docs" / "restructured.md"
TARGET = REPO_ROOT / "docs" / "Restructured.pdf"

BODY_SIZE = 9.2
BODY_LEADING = 12.6
BOTTOM = 58.0


def clean(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    text = text.replace("—", "-").replace("–", "-").replace("→", "->")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = text.replace("…", "...")
    return text.strip()


class DocPDF:
    def __init__(self) -> None:
        self.pdf = _PDF()
        self.y = PAGE_HEIGHT - MARGIN
        self._header()

    def _header(self) -> None:
        self.pdf.text(MARGIN, PAGE_HEIGHT - 30, "AI-Based ECG Diagnostic Assistant", size=9.5, font="F2", color=ACCENT)
        self.pdf.text(PAGE_WIDTH - MARGIN - 95, PAGE_HEIGHT - 30, "RESTRUCTURED", size=8, font="F2", color=MUTED)
        self.pdf.line(MARGIN, PAGE_HEIGHT - 38, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 38, color=RULE)
        self.y = PAGE_HEIGHT - 56

    def new_page(self) -> None:
        self.pdf.new_page()
        self._header()

    def ensure(self, space: float) -> None:
        if self.y - space < BOTTOM:
            self.new_page()

    def title(self, text: str, subtitle: str) -> None:
        self.ensure(110)
        self.pdf.rect(MARGIN, self.y - 82, CONTENT_WIDTH, 82, fill=(0.94, 0.98, 0.97), stroke=ACCENT)
        self.pdf.text(MARGIN + 16, self.y - 30, clean(text), size=24, font="F2", color=INK)
        for index, line in enumerate(_wrap(clean(subtitle), 74)):
            self.pdf.text(MARGIN + 16, self.y - 52 - index * 13, line, size=10, color=MUTED)
        self.y -= 100

    def section(self, text: str) -> None:
        self.ensure(70)
        self.y -= 6
        self.pdf.rect(MARGIN, self.y - 13, 3, 13, fill=ACCENT)
        self.pdf.text(MARGIN + 10, self.y - 11, clean(text), size=13.5, font="F2", color=INK)
        self.y -= 24

    def subsection(self, text: str) -> None:
        self.ensure(28)
        self.y -= 2
        self.pdf.text(MARGIN, self.y, clean(text), size=10.6, font="F2", color=ACCENT)
        self.y -= 16

    def paragraph(self, text: str) -> None:
        for line in _wrap(clean(text), max(24, int(CONTENT_WIDTH / (BODY_SIZE * 0.5)))):
            self.ensure(BODY_LEADING)
            self.pdf.text(MARGIN, self.y, line, size=BODY_SIZE, color=INK)
            self.y -= BODY_LEADING
        self.y -= 4

    def bullet(self, text: str) -> None:
        lines = _wrap(clean(text), max(24, int((CONTENT_WIDTH - 14) / (BODY_SIZE * 0.5))))
        for index, line in enumerate(lines):
            self.ensure(BODY_LEADING)
            if index == 0:
                self.pdf.circle(MARGIN + 3, self.y + 3, 1.5, fill=ACCENT)
            self.pdf.text(MARGIN + 11, self.y, line, size=BODY_SIZE, color=INK)
            self.y -= BODY_LEADING
        self.y -= 2

    def code(self, lines: list[str]) -> None:
        line_height = 10.5
        height = len(lines) * line_height + 12
        self.ensure(height + 6)
        top = self.y + 2
        self.pdf.rect(MARGIN, top - height, CONTENT_WIDTH, height, fill=(0.96, 0.97, 0.99), stroke=RULE)
        y = top - 12
        for line in lines:
            self.pdf.text(MARGIN + 8, y, line[:110], size=7.4, font="F3", color=INK)
            y -= line_height
        self.y = top - height - 10

    def table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        columns = max(len(row) for row in rows)
        rows = [row + [""] * (columns - len(row)) for row in rows]
        cleaned = [[clean(cell) for cell in row] for row in rows]

        # Column widths from the longest content, with a floor so a narrow
        # "Action" column stays readable.
        weights = []
        for index in range(columns):
            longest = max(len(row[index]) for row in cleaned)
            weights.append(max(6, min(60, longest)))
        total = sum(weights)
        widths = [CONTENT_WIDTH * weight / total for weight in weights]

        def draw_header() -> None:
            self.ensure(20)
            x = MARGIN
            for text, width in zip(cleaned[0], widths):
                self.pdf.text(x, self.y, text, size=7.6, font="F2", color=MUTED)
                x += width
            self.y -= 5
            self.pdf.line(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y, color=RULE)
            self.y -= 10

        draw_header()
        for row in cleaned[1:]:
            wrapped = [
                _wrap(cell, max(8, int(width / (7.4 * 0.5)))) for cell, width in zip(row, widths)
            ]
            height = max(len(lines) for lines in wrapped) * 9.5 + 4
            if self.y - height < BOTTOM:
                self.new_page()
                draw_header()
            x = MARGIN
            for lines, width in zip(wrapped, widths):
                line_y = self.y
                for line in lines:
                    self.pdf.text(x, line_y, line, size=7.4, color=INK)
                    line_y -= 9.5
                x += width
            self.y -= height
            self.pdf.line(MARGIN, self.y + 2, PAGE_WIDTH - MARGIN, self.y + 2, color=(0.92, 0.94, 0.97), width=0.4)
        self.y -= 8

    def footer(self) -> None:
        total = len(self.pdf.pages)
        for index, page in enumerate(self.pdf.pages):
            page.content.append(
                f"q {_num(0.82)} {_num(0.85)} {_num(0.89)} RG 0.6 w {_num(MARGIN)} 46 m {_num(PAGE_WIDTH - MARGIN)} 46 l S Q"
            )
            page.content.append(
                f"BT /F1 7 Tf 0.44 0.48 0.55 rg 1 0 0 1 {_num(MARGIN)} 34 Tm "
                f"(AI-Based ECG Diagnostic Assistant - Restructured - page {index + 1} of {total}) Tj ET"
            )

    def build(self) -> bytes:
        self.footer()
        return self.pdf.build(
            title="Restructured - AI-Based ECG Diagnostic Assistant",
            author="AI-Based ECG Diagnostic Assistant",
        )


def render(markdown: str) -> bytes:
    doc = DocPDF()
    lines = markdown.splitlines()
    index = 0
    in_code = False
    code_lines: list[str] = []
    saw_title = False

    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()

        if stripped.startswith("```"):
            if in_code:
                doc.code(code_lines)
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(raw)
            index += 1
            continue

        if not stripped:
            index += 1
            continue

        if stripped.startswith("# ") and not saw_title:
            title = stripped[2:]
            subtitle = ""
            cursor = index + 1
            while cursor < len(lines):
                candidate = lines[cursor].strip()
                if candidate and not candidate.startswith("#"):
                    subtitle = candidate
                    cursor += 1
                    break
                if candidate.startswith("#"):
                    break
                cursor += 1
            doc.title(title, subtitle)
            saw_title = True
            index = cursor
            continue

        if stripped.startswith("## "):
            doc.section(stripped[3:])
            index += 1
            continue
        if stripped.startswith("### "):
            doc.subsection(stripped[4:])
            index += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                candidate = lines[index].strip()
                if not re.match(r"^\|[\s:\-|]+\|$", candidate):
                    rows.append([cell.strip() for cell in candidate.strip("|").split("|")])
                index += 1
            doc.table(rows)
            continue

        if stripped.startswith("- "):
            doc.bullet(stripped[2:])
            index += 1
            continue

        if re.match(r"^\d+\.\s", stripped):
            doc.bullet(re.sub(r"^\d+\.\s", "", stripped))
            index += 1
            continue

        # Join adjacent non-empty paragraph lines.
        paragraph = [stripped]
        index += 1
        while index < len(lines):
            nxt = lines[index].strip()
            if not nxt or nxt.startswith(("#", "- ", "|", "```")) or re.match(r"^\d+\.\s", nxt):
                break
            paragraph.append(nxt)
            index += 1
        doc.paragraph(" ".join(paragraph))

    if code_lines:
        doc.code(code_lines)
    return doc.build()


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    pdf = render(markdown)
    TARGET.write_bytes(pdf)
    print(f"wrote {TARGET} ({len(pdf)} bytes) at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
