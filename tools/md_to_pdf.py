#!/usr/bin/env python3
"""Render this project's markdown documents to PDF.

Handles the subset those documents actually use -- headings, paragraphs, bullets,
fenced code, tables, blockquotes, and inline bold/italic/code/links -- in the same
visual language as the video recording pack, so the submission reads as one set
of documents rather than three.

    python tools/md_to_pdf.py README.md REPRODUCE.md report/changelog.md
    python tools/md_to_pdf.py --all
    python tools/md_to_pdf.py --selfcheck
"""

import argparse
import html
import pathlib
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ["README.md", "REPRODUCE.md", "report/changelog.md"]

INK = colors.HexColor("#161A20")
MUTED = colors.HexColor("#69737F")
ACCENT = colors.HexColor("#2A4E7C")
RULE = colors.HexColor("#D5DBE4")
CODEBG = colors.HexColor("#EFF1F5")
QUOTEBG = colors.HexColor("#F4F7FB")

FRAME_W = 166 * mm


def st(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK,
                spaceAfter=6)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "h1": st("h1", fontName="Helvetica-Bold", fontSize=18, leading=22,
             spaceBefore=0, spaceAfter=10),
    "h2": st("h2", fontName="Helvetica-Bold", fontSize=13, leading=17,
             spaceBefore=16, spaceAfter=7, textColor=ACCENT),
    "h3": st("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
             spaceBefore=12, spaceAfter=5),
    "h4": st("h4", fontName="Helvetica-BoldOblique", fontSize=9.5, leading=13,
             spaceBefore=10, spaceAfter=4),
    "p": st("p"),
    "li": st("li", leftIndent=11, bulletIndent=1, spaceAfter=3),
    "code": st("code", fontName="Courier", fontSize=8, leading=11, spaceAfter=0),
    "th": st("th", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
             textColor=MUTED, spaceAfter=0),
    "td": st("td", fontSize=7.5, leading=10, spaceAfter=0),
    "quote": st("quote", fontSize=9.5, leading=13.5, spaceAfter=0),
}

INLINE = [
    (re.compile(r"`([^`]+)`"), r'<font face="Courier" size="8.5">\1</font>'),
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])"), r"<i>\1</i>"),
    (re.compile(r"~~(.+?)~~"), r"<strike>\1</strike>"),
]
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
REPO = "https://github.com/Jamesokooboh/blast-radius/blob/main/"


def href(target):
    """A PDF has no in-document anchors and no working relative paths.

    Absolute URLs stay links; repo-relative paths become GitHub links so they
    still work from a downloaded file; in-page anchors become plain text.
    """
    if target.startswith(("http://", "https://", "mailto:")):
        return target
    if target.startswith("#"):
        return None
    return REPO + target.lstrip("./")


def inline(text):
    """Markdown inline formatting to reportlab markup."""
    out = html.escape(text, quote=False)
    def _link(m):
        target, label = href(m.group(2)), m.group(1)
        if target is None:
            return f'<font color="#2A4E7C">{label}</font>'
        return (f'<link href="{html.escape(target, quote=True)}">'
                f'<font color="#2A4E7C">{label}</font></link>')

    out = LINK.sub(_link, out)
    for pat, rep in INLINE:
        out = pat.sub(rep, out)
    return out


def code_block(lines):
    rows = [[Paragraph(html.escape(ln).replace(" ", "&nbsp;") or "&nbsp;", S["code"])]
            for ln in lines]
    t = Table(rows, colWidths=[FRAME_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODEBG),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
    ]))
    return [Spacer(1, 3), t, Spacer(1, 8)]


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_block(rows):
    header, body = rows[0], rows[1:]
    ncol = len(header)
    # Width by content, so a wide prose column gets the room it needs.
    weights = [max(len(r[i]) if i < len(r) else 0 for r in rows) or 1
               for i in range(ncol)]
    total = sum(weights)
    # 19mm is about the width of the longest single word likely in a cell at
    # 7.5pt; below that reportlab splits words mid-way ("improvemen t on cost").
    widths = [max(19 * mm, FRAME_W * w / total) for w in weights]
    scale = FRAME_W / sum(widths)
    widths = [w * scale for w in widths]

    data = [[Paragraph(inline(c), S["th"]) for c in header]]
    for r in body:
        r = (r + [""] * ncol)[:ncol]
        data.append([Paragraph(inline(c), S["td"]) for c in r])

    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [Spacer(1, 3), t, Spacer(1, 9)]


def quote_block(lines):
    inner = to_flow("\n".join(lines), quote=True)
    t = Table([[inner]], colWidths=[FRAME_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), QUOTEBG),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [Spacer(1, 3), t, Spacer(1, 9)]


def to_flow(md, quote=False):
    """Markdown text -> list of platypus flowables."""
    flow, lines, i = [], md.split("\n"), 0
    para, bullets = [], []

    def flush_para():
        if para:
            flow.append(Paragraph(inline(" ".join(para)), S["quote" if quote else "p"]))
            para.clear()

    def flush_bullets():
        for b in bullets:
            flow.append(Paragraph(inline(b), S["li"], bulletText="•"))
        if bullets:
            flow.append(Spacer(1, 4))
        bullets.clear()

    while i < len(lines):
        ln = lines[i]

        if ln.startswith("```"):
            flush_para(); flush_bullets()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            flow += code_block(buf); i += 1; continue

        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?$", lines[i + 1]):
            flush_para(); flush_bullets()
            rows = [split_row(ln)]; i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i])); i += 1
            flow += table_block(rows); continue

        if ln.startswith(">") and not quote:
            flush_para(); flush_bullets()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").lstrip()); i += 1
            flow += quote_block(buf); continue

        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            flush_para(); flush_bullets()
            flow.append(Paragraph(inline(m.group(2)), S[f"h{len(m.group(1))}"]))
            i += 1; continue

        if re.match(r"^\s*[-*]\s+", ln):
            flush_para()
            bullets.append(re.sub(r"^\s*[-*]\s+", "", ln)); i += 1
            while i < len(lines) and re.match(r"^\s{2,}\S", lines[i]) and lines[i].strip():
                bullets[-1] += " " + lines[i].strip(); i += 1
            continue

        if re.match(r"^---+\s*$", ln):
            flush_para(); flush_bullets(); flow.append(Spacer(1, 6)); i += 1; continue

        if not ln.strip():
            flush_para(); flush_bullets(); i += 1; continue

        para.append(ln.strip()); i += 1

    flush_para(); flush_bullets()
    return flow


def convert(src):
    src = pathlib.Path(src)
    out = src.with_suffix(".pdf")
    md = src.read_text(encoding="utf-8")
    name = src.name

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 12 * mm, f"Blast Radius — {name}")
        canvas.drawRightString(190 * mm, 12 * mm, str(doc.page))
        canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5)
        canvas.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)
        canvas.restoreState()

    doc = BaseDocTemplate(str(out), pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=22 * mm,
                          title=f"Blast Radius — {src.stem}", author="Blast Radius")
    doc.addPageTemplates([PageTemplate(id="all", onPage=footer, frames=[
        Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")])])
    doc.build(to_flow(md))
    return out


def selfcheck():
    f = to_flow("# T\n\nA **bold** and `code` and [link](http://x).\n\n"
                "- one\n- two\n\n```\nx = 1\n```\n\n"
                "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n> quoted\n")
    kinds = [type(x).__name__ for x in f]
    assert kinds.count("Paragraph") >= 4, kinds
    assert kinds.count("Table") >= 3, kinds     # code, table, quote
    assert "<b>bold</b>" in inline("**bold**")
    assert 'face="Courier"' in inline("`code`")
    assert "<link" in inline("[t](https://x)")
    assert "<link" not in inline("[t](#anchor)")          # anchors have no target
    assert REPO in inline("[c](report/changelog.md)")     # relative -> GitHub
    assert "&lt;script&gt;" in inline("<script>")   # escaped, not injected
    print("md_to_pdf selfcheck ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    targets = DOCS if a.all or not a.files else a.files
    for t in targets:
        p = convert(ROOT / t)
        print(f"  {t:<24} -> {p.relative_to(ROOT)}  ({p.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
