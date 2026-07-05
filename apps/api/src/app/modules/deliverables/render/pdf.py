"""PDF renderer via PyMuPDF — no system dependencies (the WeasyPrint
alternative rejected in M4 for CI hermeticity). Deterministic paginated
layout: headings, stat grids, tables, bullets, sources appendix."""

import fitz

PAGE_W, PAGE_H = fitz.paper_size("a4")
MARGIN = 54.0
BODY_W = PAGE_W - 2 * MARGIN

INK = (0.10, 0.12, 0.15)
ACCENT = (0.35, 0.34, 0.79)
MUTED = (0.36, 0.40, 0.44)
DANGER = (0.69, 0.23, 0.37)
LINE = (0.85, 0.86, 0.88)


class _Page:
    def __init__(self, doc: "fitz.Document"):
        self.doc = doc
        self.page = doc.new_page(width=PAGE_W, height=PAGE_H)
        self.y = MARGIN

    def ensure(self, height: float) -> None:
        if self.y + height > PAGE_H - MARGIN:
            self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
            self.y = MARGIN

    def text(self, content: str, *, size: float, color=INK, bold=False,
             indent: float = 0.0, gap: float = 6.0) -> None:
        if not content:
            return
        font = "hebo" if bold else "helv"
        width = BODY_W - indent
        # Measure by rendering into a probe rectangle first.
        probe = fitz.Rect(0, 0, width, 10_000)
        needed = 10_000 - self.page.insert_textbox(
            probe, content, fontsize=size, fontname=font, render_mode=3
        )
        self.ensure(needed + gap)
        rect = fitz.Rect(MARGIN + indent, self.y, MARGIN + indent + width,
                         self.y + needed + 2)
        self.page.insert_textbox(rect, content, fontsize=size, fontname=font,
                                 color=color)
        self.y += needed + gap

    def rule(self) -> None:
        self.ensure(10)
        self.page.draw_line(
            fitz.Point(MARGIN, self.y), fitz.Point(MARGIN + 72, self.y),
            color=ACCENT, width=2,
        )
        self.y += 12

    def table(self, columns: list[str], rows: list[list[str]],
              *, size: float = 8.5) -> None:
        if not rows and not columns:
            return
        col_w = BODY_W / max(len(columns), 1)
        row_h = 16.0
        header_and_rows = [columns] + rows
        for row_index, row in enumerate(header_and_rows):
            self.ensure(row_h + 2)
            for col_index, value in enumerate(row[: len(columns)]):
                x = MARGIN + col_index * col_w
                rect = fitz.Rect(x + 2, self.y, x + col_w - 4, self.y + row_h)
                self.page.insert_textbox(
                    rect, str(value)[:120], fontsize=size,
                    fontname="hebo" if row_index == 0 else "helv",
                    color=INK if row_index == 0 else MUTED,
                )
            self.page.draw_line(
                fitz.Point(MARGIN, self.y + row_h),
                fitz.Point(MARGIN + BODY_W, self.y + row_h),
                color=LINE, width=0.5,
            )
            self.y += row_h + 1
        self.y += 8


def _marks(item: dict) -> str:
    marks = "".join(f"[{n}]" for n in item.get("citations", []))
    if item.get("unreviewed"):
        marks += " *"
    return f" {marks}" if marks else ""


def render_pdf(spec: dict) -> bytes:
    doc = fitz.open()
    page = _Page(doc)

    page.text(spec["title"], size=22, bold=True)
    page.text(
        f"Generated {spec['generated_at'][:10]} · model {spec['review_coverage']} "
        "analyst-reviewed · figures derive from the ROI assumption sheets",
        size=8.5, color=MUTED, gap=14,
    )

    for section in spec["sections"]:
        page.text(section["heading"], size=14, bold=True, gap=2)
        page.rule()
        kind = section["kind"]
        if kind == "overview":
            page.text(section["body"], size=9.5, color=MUTED, gap=10)
            page.table(
                ["Metric", "Value"],
                [[s["label"], s["value"]] for s in section["stats"]],
            )
        elif kind == "findings":
            for item in section["items"]:
                taxonomy = f"  [{item['taxonomy']}]" if item.get("taxonomy") else ""
                page.text(
                    f"•  {item['text']}{taxonomy}{_marks(item)}",
                    size=9.5, indent=6, gap=5,
                )
            page.y += 6
        elif kind == "opportunities":
            page.table(
                ["Opportunity", "Type", "I/C/R", "Net annual", "Payback"],
                [
                    [
                        row["title"][:60] + _marks(row),
                        row["taxonomy"].replace("_", " "),
                        f"{row['impact']}/{row['complexity']}/{row['risk']}",
                        (
                            f"${row['net_annual_savings']:,.0f}"
                            if row.get("net_annual_savings") is not None else "—"
                        ),
                        f"{row['payback_months']} mo" if row.get("payback_months") else "—",
                    ]
                    for row in section["rows"]
                ],
            )
        elif kind == "roadmap":
            for horizon, label in (
                ("30", "First 30 days"), ("90", "90 days"),
                ("180", "6 months"), ("365", "12 months"),
            ):
                page.text(label, size=10.5, bold=True, color=ACCENT, gap=3)
                items = section["horizons"].get(horizon, [])
                for item in items:
                    prefix = "⚡ " if item.get("quick_win") else "•  "
                    page.text(prefix + item["title"], size=9.5, indent=6, gap=4)
                if not items:
                    page.text("—", size=9.5, color=MUTED, indent=6, gap=4)
                page.y += 4
        elif kind == "process":
            page.table(
                ["#", "Step", "Type", "Performer"],
                [
                    [str(s["order"]), s["name"][:80] + _marks(s),
                     s["step_type"], s["performer"]]
                    for s in section["steps"]
                ],
            )
            if section["pain_points"]:
                page.text("Pain points", size=10.5, bold=True, color=DANGER, gap=4)
                for pain in section["pain_points"]:
                    taxonomy = f"  [{pain['taxonomy']}]" if pain.get("taxonomy") else ""
                    page.text(
                        f"•  {pain['text']}{taxonomy}{_marks(pain)}",
                        size=9.5, indent=6, gap=4,
                    )
                page.y += 6
        elif kind == "table":
            page.table(section["columns"], [[str(c) for c in r] for r in section["rows"]])

    if spec["citations"]:
        page.text("Sources", size=14, bold=True, gap=2)
        page.rule()
        for citation in spec["citations"]:
            quote = f' — "{(citation.get("quote") or "")[:200]}"'
            page.text(
                f"[{citation['n']}] {citation['filename']}{quote}",
                size=8, color=MUTED, gap=4,
            )
    page.text("* item generated by AI and not yet analyst-reviewed",
              size=7.5, color=MUTED, gap=0)

    data = doc.tobytes()
    doc.close()
    return data
