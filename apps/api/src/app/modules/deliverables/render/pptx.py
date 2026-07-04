"""PPTX renderer via python-pptx.

Deterministic layout on blank slides: designed once, rendered every time.
Speaker notes carry the slide's citations — the deck itself stays clean
while every claim remains traceable in presenter view.
"""

import io

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

INK = RGBColor(0x1A, 0x1F, 0x26)
ACCENT = RGBColor(0x5A, 0x56, 0xC9)
MUTED = RGBColor(0x5C, 0x65, 0x70)
DANGER = RGBColor(0xB1, 0x3A, 0x5E)

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.6)


def _slide(deck):
    return deck.slides.add_slide(deck.slide_layouts[6])  # blank


def _text(slide, x, y, w, h, text, size, *, bold=False, color=INK, align_notes=None):
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def _heading(slide, text):
    _text(slide, MARGIN, Inches(0.35), SLIDE_W - 2 * MARGIN, Inches(0.7),
          text, 26, bold=True, color=INK)
    bar = slide.shapes.add_textbox(MARGIN, Inches(0.95), Inches(1.2), Inches(0.06))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()


def _notes(slide, spec, citation_numbers):
    if not citation_numbers:
        return
    lookup = {c["n"]: c for c in spec["citations"]}
    lines = []
    for n in sorted(set(citation_numbers)):
        citation = lookup.get(n)
        if citation:
            quote = f' — "{citation["quote"]}"' if citation.get("quote") else ""
            lines.append(f"[{n}] {citation['filename']}{quote}")
    slide.notes_slide.notes_text_frame.text = "Sources:\n" + "\n".join(lines)


def _marks(item: dict) -> str:
    marks = "".join(f"[{n}]" for n in item.get("citations", []))
    if item.get("unreviewed"):
        marks += "*"
    return f" {marks}" if marks else ""


def render_pptx(spec: dict) -> bytes:
    deck = Presentation()
    deck.slide_width, deck.slide_height = SLIDE_W, SLIDE_H

    # Title slide
    slide = _slide(deck)
    _text(slide, MARGIN, Inches(2.6), SLIDE_W - 2 * MARGIN, Inches(1.2),
          spec["title"], 36, bold=True)
    _text(slide, MARGIN, Inches(3.7), SLIDE_W - 2 * MARGIN, Inches(0.5),
          f"Generated {spec['generated_at'][:10]} · knowledge model "
          f"{spec['review_coverage']} analyst-reviewed", 14, color=MUTED)
    _text(slide, MARGIN, Inches(6.6), SLIDE_W - 2 * MARGIN, Inches(0.4),
          "Every claim in this deck cites its source; every figure derives "
          "from an assumption sheet.", 11, color=MUTED)

    for section in spec["sections"]:
        kind = section["kind"]
        if kind == "overview":
            slide = _slide(deck)
            _heading(slide, section["heading"])
            _text(slide, MARGIN, Inches(1.25), SLIDE_W - 2 * MARGIN, Inches(0.6),
                  section["body"], 13, color=MUTED)
            columns = 3
            box_w = (SLIDE_W - 2 * MARGIN - Inches(0.4)) / columns
            for i, stat in enumerate(section["stats"][:6]):
                x = MARGIN + (i % columns) * (box_w + Inches(0.2))
                y = Inches(2.2) + (i // columns) * Inches(1.7)
                _text(slide, x, y, box_w, Inches(0.8),
                      stat["value"], 30, bold=True, color=ACCENT)
                _text(slide, x, y + Inches(0.85), box_w, Inches(0.5),
                      stat["label"], 12, color=MUTED)
        elif kind == "findings":
            slide = _slide(deck)
            _heading(slide, section["heading"])
            numbers = []
            box = slide.shapes.add_textbox(
                MARGIN, Inches(1.3), SLIDE_W - 2 * MARGIN, SLIDE_H - Inches(1.8)
            )
            frame = box.text_frame
            frame.word_wrap = True
            for i, item in enumerate(section["items"][:7]):
                paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
                run = paragraph.add_run()
                run.text = f"•  {item['text']}{_marks(item)}"
                run.font.size = Pt(15)
                run.font.color.rgb = INK
                paragraph.space_after = Pt(12)
                if item.get("taxonomy"):
                    tag = paragraph.add_run()
                    tag.text = f"   [{item['taxonomy']}]"
                    tag.font.size = Pt(11)
                    tag.font.color.rgb = DANGER
                numbers += item.get("citations", [])
            _notes(slide, spec, numbers)
        elif kind == "opportunities":
            slide = _slide(deck)
            _heading(slide, section["heading"])
            rows = section["rows"][:6]
            table_shape = slide.shapes.add_table(
                len(rows) + 1, 5, MARGIN, Inches(1.3),
                SLIDE_W - 2 * MARGIN, Inches(0.5) * (len(rows) + 1),
            )
            table = table_shape.table
            numbers = []
            for i, header in enumerate(
                ["Opportunity", "Type", "I / C / R", "Net annual", "Payback"]
            ):
                cell = table.cell(0, i)
                cell.text = header
                cell.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
                cell.text_frame.paragraphs[0].runs[0].font.bold = True
            for r, row in enumerate(rows, start=1):
                net = (
                    f"${row['net_annual_savings']:,.0f}"
                    if row.get("net_annual_savings") is not None else "—"
                )
                payback = (
                    f"{row['payback_months']} mo" if row.get("payback_months") else "—"
                )
                values = [
                    row["title"][:60] + _marks(row),
                    row["taxonomy"].replace("_", " "),
                    f"{row['impact']} / {row['complexity']} / {row['risk']}",
                    net,
                    payback,
                ]
                for c, value in enumerate(values):
                    cell = table.cell(r, c)
                    cell.text = str(value)
                    cell.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
                numbers += row.get("citations", [])
            _notes(slide, spec, numbers)
        elif kind == "roadmap":
            slide = _slide(deck)
            _heading(slide, section["heading"])
            column_w = (SLIDE_W - 2 * MARGIN - Inches(0.6)) / 4
            for i, (horizon, label) in enumerate(
                (("30", "First 30 days"), ("90", "90 days"),
                 ("180", "6 months"), ("365", "12 months"))
            ):
                x = MARGIN + i * (column_w + Inches(0.2))
                _text(slide, x, Inches(1.3), column_w, Inches(0.4),
                      label, 14, bold=True, color=ACCENT)
                items = section["horizons"].get(horizon, [])[:6]
                box = slide.shapes.add_textbox(
                    x, Inches(1.8), column_w, SLIDE_H - Inches(2.3)
                )
                frame = box.text_frame
                frame.word_wrap = True
                for j, item in enumerate(items):
                    paragraph = (
                        frame.paragraphs[0] if j == 0 else frame.add_paragraph()
                    )
                    run = paragraph.add_run()
                    prefix = "⚡ " if item.get("quick_win") else "•  "
                    run.text = prefix + item["title"][:70]
                    run.font.size = Pt(11)
                    run.font.color.rgb = INK
                    paragraph.space_after = Pt(8)
                if not items:
                    frame.paragraphs[0].add_run().text = "—"

    # Sources appendix
    citations = spec["citations"]
    for start in range(0, len(citations), 12):
        slide = _slide(deck)
        _heading(slide, "Sources")
        box = slide.shapes.add_textbox(
            MARGIN, Inches(1.3), SLIDE_W - 2 * MARGIN, SLIDE_H - Inches(1.8)
        )
        frame = box.text_frame
        frame.word_wrap = True
        for i, citation in enumerate(citations[start : start + 12]):
            paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            run = paragraph.add_run()
            quote = f' — "{(citation.get("quote") or "")[:120]}"'
            run.text = f"[{citation['n']}] {citation['filename']}{quote}"
            run.font.size = Pt(10)
            run.font.color.rgb = MUTED

    buffer = io.BytesIO()
    deck.save(buffer)
    return buffer.getvalue()
