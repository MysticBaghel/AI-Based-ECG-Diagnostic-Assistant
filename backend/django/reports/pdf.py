"""A tiny, dependency-free PDF writer for ECG reports.

The project deliberately does not depend on ReportLab or a headless browser:
the report is text, a few rules and one vector waveform, all of which PDF 1.4
supports directly. Keeping the writer here means `pip install` stays small and a
report can be regenerated on any machine that can run Django.

Only the standard 14 fonts (Helvetica, Helvetica-Bold, Courier) are used, so no
font file is embedded and the PDF stays small and portable. The waveform is a
polyline, not a raster image, so it remains sharp at any zoom.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 44.0
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
BOTTOM_LIMIT = 58.0

INK = (0.09, 0.12, 0.18)
MUTED = (0.38, 0.43, 0.52)
ACCENT = (0.05, 0.55, 0.52)
RULE = (0.82, 0.85, 0.89)
LIGHT = (0.95, 0.97, 0.98)
DANGER = (0.72, 0.18, 0.22)
WARN = (0.72, 0.45, 0.05)


def _escape(text: str) -> str:
    """Escape a PDF literal string; non-Latin characters become '?'."""
    cleaned = text.encode("latin-1", errors="replace").decode("latin-1")
    return (
        cleaned.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _color(rgb: tuple[float, float, float]) -> str:
    return " ".join(_num(channel) for channel in rgb)


@dataclass
class _Page:
    content: list[str] = field(default_factory=list)


class _PDF:
    def __init__(self) -> None:
        self.pages: list[_Page] = []
        self._page = _Page()
        self.pages.append(self._page)

    # -- graphics primitives ------------------------------------------------

    def _add(self, command: str) -> None:
        self._page.content.append(command)

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        size: float = 9.5,
        font: str = "F1",
        color: tuple[float, float, float] = INK,
    ) -> None:
        self._add(
            f"BT /{font} {_num(size)} Tf {_color(color)} rg "
            f"1 0 0 1 {_num(x)} {_num(y)} Tm ({_escape(value)}) Tj ET"
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        color: tuple[float, float, float] = RULE,
        width: float = 0.7,
    ) -> None:
        self._add(
            f"q {_color(color)} RG {_num(width)} w "
            f"{_num(x1)} {_num(y1)} m {_num(x2)} {_num(y2)} l S Q"
        )

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: tuple[float, float, float] | None = None,
        stroke: tuple[float, float, float] | None = None,
        line_width: float = 0.7,
    ) -> None:
        commands = ["q"]
        if fill is not None:
            commands.append(f"{_color(fill)} rg")
        if stroke is not None:
            commands.append(f"{_color(stroke)} RG {_num(line_width)} w")
        commands.append(f"{_num(x)} {_num(y)} {_num(width)} {_num(height)} re")
        commands.append("B" if fill is not None and stroke is not None else ("f" if fill is not None else "S"))
        commands.append("Q")
        self._add(" ".join(commands))

    def circle(
        self,
        x: float,
        y: float,
        radius: float,
        *,
        fill: tuple[float, float, float] = DANGER,
    ) -> None:
        k = 0.5523 * radius
        self._add(
            f"q {_color(fill)} rg {_num(x + radius)} {_num(y)} m "
            f"{_num(x + radius)} {_num(y + k)} {_num(x + k)} {_num(y + radius)} "
            f"{_num(x)} {_num(y + radius)} c "
            f"{_num(x - k)} {_num(y + radius)} {_num(x - radius)} {_num(y + k)} "
            f"{_num(x - radius)} {_num(y)} c "
            f"{_num(x - radius)} {_num(y - k)} {_num(x - k)} {_num(y - radius)} "
            f"{_num(x)} {_num(y - radius)} c "
            f"{_num(x + k)} {_num(y - radius)} {_num(x + radius)} {_num(y - k)} "
            f"{_num(x + radius)} {_num(y)} c f Q"
        )

    def polyline(
        self,
        points: Iterable[tuple[float, float]],
        *,
        color: tuple[float, float, float] = ACCENT,
        width: float = 0.9,
    ) -> None:
        items = list(points)
        if len(items) < 2:
            return
        x0, y0 = items[0]
        commands = [
            "q",
            f"{_color(color)} RG",
            f"{_num(width)} w",
            "1 j 1 J",
            f"{_num(x0)} {_num(y0)} m",
        ]
        for x, y in items[1:]:
            commands.append(f"{_num(x)} {_num(y)} l")
        commands.append("S Q")
        self._add(" ".join(commands))

    # -- output -------------------------------------------------------------

    def new_page(self) -> None:
        self._page = _Page()
        self.pages.append(self._page)

    def build(self, *, title: str, author: str) -> bytes:
        objects: dict[int, bytes] = {}

        def add(object_id: int, body: bytes) -> None:
            objects[object_id] = body

        # Fixed ids: 1 catalog, 2 pages, 3-5 fonts, 6 info, then 2 per page.
        add(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        add(2, b"")
        add(3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        add(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        add(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

        page_ids: list[int] = []
        for index, page in enumerate(self.pages):
            content_id = 7 + index * 2
            page_id = content_id + 1
            page_ids.append(page_id)
            stream = "\n".join(page.content).encode("latin-1", errors="replace")
            add(
                content_id,
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
                + stream
                + b"\nendstream",
            )
            add(
                page_id,
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_num(PAGE_WIDTH)} {_num(PAGE_HEIGHT)}] "
                    f"/Contents {content_id} 0 R "
                    "/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> >>"
                ).encode("ascii"),
            )

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        add(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii"))

        info = (
            f"<< /Title ({_escape(title)}) /Author ({_escape(author)}) "
            f"/Creator ({_escape(author)}) /Producer ({_escape(author)}) "
            f"/CreationDate (D:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}Z) >>"
        ).encode("latin-1")
        add(6, info)

        ordered = [objects[key] for key in sorted(objects)]
        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for number, body in enumerate(ordered, start=1):
            offsets.append(len(output))
            output += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

        xref_offset = len(output)
        output += f"xref\n0 {len(ordered) + 1}\n".encode("ascii")
        output += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            output += f"{offset:010d} 00000 n \n".encode("ascii")
        output += (
            f"trailer\n<< /Size {len(ordered) + 1} /Root 1 0 R /Info 6 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
        return bytes(output)


def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


class ReportBuilder:
    """Lays out one screening report on A4 pages."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.pdf = _PDF()
        self.y = PAGE_HEIGHT - MARGIN
        self._draw_header()

    # -- layout -------------------------------------------------------------

    def _draw_header(self) -> None:
        self.pdf.text(MARGIN, PAGE_HEIGHT - 30, "AI-Based ECG Diagnostic Assistant", size=10, font="F2", color=ACCENT)
        self.pdf.text(
            PAGE_WIDTH - MARGIN - 140,
            PAGE_HEIGHT - 30,
            "ECG SCREENING REPORT",
            size=8,
            font="F2",
            color=MUTED,
        )
        self.pdf.line(MARGIN, PAGE_HEIGHT - 38, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 38)
        self.y = PAGE_HEIGHT - 56

    def _new_page(self) -> None:
        self.pdf.new_page()
        self._draw_header()

    def _ensure(self, space: float) -> None:
        if self.y - space < BOTTOM_LIMIT:
            self._new_page()

    def section(self, title: str) -> None:
        self._ensure(30)
        self.y -= 8
        self.pdf.text(MARGIN, self.y, title.upper(), size=8.5, font="F2", color=ACCENT)
        self.y -= 5
        self.pdf.line(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y, color=RULE)
        self.y -= 14

    def key_values(self, pairs: list[tuple[str, str]], *, columns: int = 2) -> None:
        if not pairs:
            return
        col_width = CONTENT_WIDTH / columns
        row_height = 17
        for index in range(0, len(pairs), columns):
            self._ensure(row_height)
            for column, (label, value) in enumerate(pairs[index : index + columns]):
                x = MARGIN + column * col_width
                self.pdf.text(x, self.y, label, size=7.5, color=MUTED)
                self.pdf.text(x, self.y - 10, value, size=9.2, font="F2")
            self.y -= row_height
        self.y -= 4

    def paragraph(self, text: str, *, size: float = 9.2, leading: float = 12.5, color=INK, font="F1") -> None:
        max_chars = max(20, int(CONTENT_WIDTH / (size * 0.51)))
        for line in _wrap(text, max_chars):
            self._ensure(leading)
            self.pdf.text(MARGIN, self.y, line, size=size, font=font, color=color)
            self.y -= leading
        self.y -= 4

    def bullet(self, text: str) -> None:
        max_chars = max(20, int((CONTENT_WIDTH - 14) / (9.2 * 0.51)))
        lines = _wrap(text, max_chars)
        for index, line in enumerate(lines):
            self._ensure(12.5)
            if index == 0:
                self.pdf.circle(MARGIN + 3, self.y + 3, 1.6, fill=ACCENT)
            self.pdf.text(MARGIN + 12, self.y, line, size=9.2)
            self.y -= 12.5
        self.y -= 2

    def banner(self, text: str, *, tone: tuple[float, float, float] = DANGER) -> None:
        max_chars = max(20, int((CONTENT_WIDTH - 18) / (9.4 * 0.51)))
        lines = _wrap(text, max_chars)
        height = len(lines) * 13 + 12
        self._ensure(height + 8)
        top = self.y + 4
        self.pdf.rect(MARGIN, top - height, CONTENT_WIDTH, height, fill=(0.99, 0.96, 0.93), stroke=tone)
        self.pdf.rect(MARGIN, top - height, 4, height, fill=tone)
        line_y = top - 14
        for line in lines:
            self.pdf.text(MARGIN + 14, line_y, line, size=9.4, color=tone, font="F2")
            line_y -= 13
        self.y = top - height - 12

    def waveform(self, *, samples: list[float], sample_rate_hz: int | None, duration: float, peaks: list[float]) -> None:
        box_height = 150
        self._ensure(box_height + 34)
        x0, width = MARGIN, CONTENT_WIDTH
        y_bottom = self.y - box_height
        self.pdf.rect(x0, y_bottom, width, box_height, fill=(0.98, 0.99, 0.99), stroke=RULE)

        for step in range(1, 10):
            x = x0 + width * step / 10
            self.pdf.line(x, y_bottom, x, y_bottom + box_height, color=(0.91, 0.93, 0.95), width=0.4)
        for step in range(1, 4):
            y = y_bottom + box_height * step / 4
            self.pdf.line(x0, y, x0 + width, y, color=(0.91, 0.93, 0.95), width=0.4)

        if samples and sample_rate_hz:
            # Decimate to at most 1100 points: more than a page can resolve.
            stride = max(1, math.ceil(len(samples) / 1100))
            values = samples[::stride]
            low = min(values)
            high = max(values)
            span = max(0.2, high - low)
            mid = (high + low) / 2
            points = []
            for index, value in enumerate(values):
                x = x0 + (index / max(1, len(values) - 1)) * width
                y = y_bottom + box_height / 2 + ((value - mid) / span) * (box_height * 0.78)
                points.append((x, y))
            self.pdf.polyline(points, color=ACCENT, width=0.75)

            for second in peaks:
                if duration <= 0 or second < 0 or second > duration:
                    continue
                x = x0 + (second / duration) * width
                self.pdf.line(x, y_bottom + box_height - 2, x, y_bottom + box_height - 9, color=DANGER, width=0.8)

            self.pdf.text(x0 + 6, y_bottom + 6, "time (s)", size=6.8, color=MUTED)
            self.pdf.text(x0 + width - 58, y_bottom + 6, f"scale {span:.2f} mV", size=6.8, color=MUTED)
            self.pdf.text(x0 + 6, y_bottom + box_height - 11, "ECG (filtered)", size=7, font="F2", color=ACCENT)
        else:
            self.pdf.text(x0 + 12, y_bottom + box_height / 2, "No stored ECG waveform is available for this session.", size=9, color=MUTED)

        self.y = y_bottom - 16

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        def row(values: list[str], *, bold: bool = False, color=INK) -> None:
            self._ensure(18)
            x = MARGIN
            for value, width in zip(values, widths):
                self.pdf.text(x, self.y, value, size=8.6, font="F2" if bold else "F1", color=color)
                x += width
            self.y -= 14

        self._ensure(24)
        row(headers, bold=True, color=MUTED)
        self.pdf.line(MARGIN, self.y + 6, PAGE_WIDTH - MARGIN, self.y + 6, color=RULE)
        for values in rows:
            row(values)
        self.y -= 6

    def footer(self) -> None:
        total = len(self.pdf.pages)
        for index, page in enumerate(self.pdf.pages):
            page.content.append(
                f"q {_color(RULE)} RG 0.6 w {_num(MARGIN)} 46 m {_num(PAGE_WIDTH - MARGIN)} 46 l S Q"
            )
            page.content.append(
                f"BT /F1 7 Tf {_color(MUTED)} rg 1 0 0 1 {_num(MARGIN)} 34 Tm "
                f"(Screening aid, not a medical diagnosis. Page {index + 1} of {total}.) Tj ET"
            )

    def build(self) -> bytes:
        self.footer()
        return self.pdf.build(
            title=f"ECG screening report {self.payload.get('report_id', '')}",
            author="AI-Based ECG Diagnostic Assistant",
        )


def render_report(payload: dict) -> bytes:
    """Render the report payload to a valid PDF byte string."""
    builder = ReportBuilder(payload)

    builder.section("Report")
    generated = payload.get("generated_at") or "—"
    builder.key_values(
        [
            ("Report ID", payload.get("report_id", "—")),
            ("Version", str(payload.get("version", 1))),
            ("Generated", generated),
            ("Application", payload.get("application", "AI-Based ECG Diagnostic Assistant")),
        ]
    )

    patient = payload.get("patient") or {}
    builder.section("Patient")
    demographics = []
    if patient.get("date_of_birth"):
        demographics.append(f"DOB {patient['date_of_birth']}")
    if patient.get("age") is not None:
        demographics.append(f"Age {patient['age']}")
    if patient.get("sex") and patient["sex"] != "unknown":
        demographics.append(str(patient["sex"]).capitalize())
    pairs = [
        ("Name", patient.get("full_name", "—")),
        ("Patient ID", patient.get("patient_id", "—")),
        ("Phone", patient.get("phone") or "Not recorded"),
        ("Demographics", " · ".join(demographics) or "Not recorded"),
    ]
    builder.key_values(pairs)

    session = payload.get("session") or {}
    builder.section("Recording")
    builder.key_values(
        [
            ("Session ID", session.get("id", "—")),
            ("Device", session.get("device_name", "—")),
            ("Recording date", session.get("start_time", "—")),
            ("Started", session.get("start_time", "—")),
            ("Ended", session.get("end_time") or "—"),
            ("Duration", f"{float(session.get('duration_seconds') or 0):.1f} s"),
            ("Sampling frequency", (f"{session['sample_rate_hz']} Hz" if session.get("sample_rate_hz") else "Not recorded")),
        ]
    )

    signal = payload.get("signal") or {}
    quality = signal.get("quality") or {}
    builder.section("Signal and quality")
    quality_rows = [
        ("Quality score", (f"{quality.get('score')} / 100" if quality.get("score") is not None else "Not available")),
        ("Level", str(quality.get("level", "unknown")).capitalize()),
        ("Usable for measurement", "Yes" if quality.get("usable") else "No"),
        ("Samples analysed", str(signal.get("sample_count", "—"))),
        ("Analysed duration", (f"{float(signal.get('duration_seconds') or 0):.1f} s" if signal.get("duration_seconds") else "—")),
    ]
    builder.key_values(quality_rows)
    builder.paragraph(
        "Filtering: "
        + (
            signal.get("filtering_note")
            or "Baseline-wander and power-line reduction applied where possible."
        ),
        size=8.6,
        color=MUTED,
    )
    reasons = quality.get("reasons") or []
    if reasons:
        builder.paragraph("Quality notes: " + "; ".join(str(reason) for reason in reasons), color=WARN)

    measurements = payload.get("measurements") or {}
    builder.section("Signal-processing measurements")
    if measurements:
        def number(key: str, digits: int = 1) -> str:
            value = measurements.get(key)
            return "—" if value is None else f"{float(value):.{digits}f}"

        builder.table(
            ["Measurement", "Value", "Measurement", "Value"],
            [
                ["Heart rate", f"{number('heart_rate_bpm', 1)} bpm", "Beats detected", str(measurements.get("beats_detected", "—"))],
                ["Mean RR", f"{number('rr_mean_ms', 0)} ms", "RR std. dev.", f"{number('rr_std_ms', 0)} ms"],
                ["RMSSD", f"{number('rmssd_ms', 0)} ms", "pNN50", f"{number('pnn50_percent', 1)} %"],
            ],
            [130, 120, 130, 120],
        )
        intervals = measurements.get("rr_intervals_ms") or []
        if intervals:
            shown = ", ".join(f"{float(value):.0f}" for value in intervals[:30])
            more = "" if len(intervals) <= 30 else f" … ({len(intervals) - 30} more)"
            builder.paragraph("RR intervals (ms): " + shown + more, size=8.2, color=MUTED)
    else:
        builder.paragraph(
            "No validated heart-rate or RR measurement could be produced from this recording.",
            color=WARN,
        )

    builder.section("ECG waveform")
    builder.waveform(
        samples=payload.get("waveform_samples") or [],
        sample_rate_hz=signal.get("sample_rate_hz") or session.get("sample_rate_hz"),
        duration=float(signal.get("duration_seconds") or session.get("duration_seconds") or 0),
        peaks=measurements.get("r_peak_seconds") or [],
    )

    ml = payload.get("ml") or payload.get("ai") or {}
    builder.section("ML classification")
    if ml.get("available"):
        probabilities = ml.get("probabilities") or {}
        labels = ml.get("class_labels") or {}
        confidence = ml.get("confidence")
        if confidence is None:
            confidence = probabilities.get(ml.get("predicted_class"))
        builder.key_values(
            [
                (
                    "Predicted class",
                    f"{ml.get('predicted_class') or '—'} — {ml.get('predicted_label') or ''}".strip(),
                ),
                ("Model", str(ml.get("model_name") or "—")),
                ("Model version", str(ml.get("model_version") or "—")),
                ("Architecture", str(ml.get("architecture") or "—")),
                (
                    "Model confidence",
                    f"{float(confidence) * 100:.1f}%" if confidence is not None else "—",
                ),
                ("Windows scored", str(ml.get("window_count") or "—")),
                ("Analysed at", str(ml.get("analyzed_at") or "—")),
                ("Model checksum", str(ml.get("model_sha256") or "—")[:24]),
            ]
        )
        if probabilities:
            builder.table(
                ["Class", "Label", "Probability"],
                [
                    [
                        str(name),
                        str(labels.get(name) or name),
                        f"{float(value) * 100:.1f}%",
                    ]
                    for name, value in probabilities.items()
                ],
                [45, 300, 105],
            )
        builder.banner(
            "The classification above is an experimental 1-D CNN screening aid. "
            "It is not a diagnosis and must be interpreted by a qualified clinician.",
            tone=WARN,
        )
    else:
        reason = ml.get("reason") or (
            "No trained ECG classification model is configured on this deployment."
        )
        builder.banner(
            "ML classification is unavailable. " + str(reason) + " No prediction has been fabricated.",
            tone=WARN,
        )

    advice = payload.get("advice") or {}
    builder.section("AI advisory")
    if advice.get("available"):
        builder.key_values(
            [
                ("Risk level", str(advice.get("risk_level") or "unknown").capitalize()),
                ("Provider", str(advice.get("provider") or "—")),
                ("Prompt version", str(advice.get("prompt_version") or "—")),
                ("Generated at", str(advice.get("generated_at") or "—")),
            ]
        )
        builder.paragraph(
            str(advice.get("headline") or "Automated advisory"),
            size=11,
            color=ACCENT,
            font="F2",
        )
        if advice.get("summary"):
            builder.paragraph(str(advice["summary"]))
        recommendations = advice.get("recommendations") or []
        if recommendations:
            builder.paragraph("Cautious next steps", size=8.8, font="F2", color=MUTED)
            for item in recommendations:
                builder.bullet(str(item))
        red_flags = advice.get("red_flags") or []
        if red_flags:
            builder.paragraph("Seek urgent care for", size=8.8, font="F2", color=WARN)
            for item in red_flags:
                builder.bullet(str(item))
        if advice.get("confidence_note"):
            builder.paragraph(str(advice["confidence_note"]), size=8.4, color=MUTED)
        builder.banner(
            str(advice.get("disclaimer") or "Automated screening aid, not a medical diagnosis."),
            tone=WARN,
        )
    else:
        reason = advice.get("reason") or (
            "No AI advisory provider is configured on this deployment."
        )
        builder.banner(
            "AI advice is unavailable. " + str(reason) + " The measurements and any "
            "classifier output above are still reported.",
            tone=WARN,
        )

    builder.section("Findings and cautious guidance")
    findings = payload.get("findings") or []
    if findings:
        for finding in findings:
            builder.bullet(str(finding))
    else:
        builder.paragraph(
            "No analysis findings are stored for this recording. The waveform and any "
            "measurements above should be interpreted by a qualified clinician."
        )

    builder.section("Limitations")
    for limitation in payload.get("limitations") or []:
        builder.bullet(str(limitation))

    builder.banner(
        "SCREENING AID, NOT A STANDALONE MEDICAL DIAGNOSIS. This report is generated "
        "from a single-lead ECG recording and must not be used alone to diagnose, "
        "rule out, or treat any condition. A qualified clinician must review the "
        "recording in the appropriate clinical context.",
        tone=DANGER,
    )

    return builder.build()
