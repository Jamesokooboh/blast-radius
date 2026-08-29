#!/usr/bin/env python3
"""Build the recording pack: directions plus the voiceover script, as one PDF.

Two documents in one file, because they are used at two different moments:
pages 1-2 while recording the terminal, the rest while laying the voice over the
footage in an editor. Narration is set larger than everything else -- it is the
only part that gets read aloud.

    python tools/make_video_pdf.py
"""

import pathlib

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "report" / "video-recording-pack.pdf"

INK = colors.HexColor("#161A20")
MUTED = colors.HexColor("#69737F")
ACCENT = colors.HexColor("#2A4E7C")
RULE = colors.HexColor("#D5DBE4")
CODEBG = colors.HexColor("#EFF1F5")
WARN = colors.HexColor("#A83A31")

ss = getSampleStyleSheet()


def style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK,
                alignment=TA_LEFT, spaceAfter=6)
    base.update(kw)
    return ParagraphStyle(name, **base)


H1 = style("H1", fontName="Helvetica-Bold", fontSize=19, leading=23,
           spaceAfter=3, spaceBefore=0)
SUB = style("SUB", fontSize=10, textColor=MUTED, spaceAfter=16)
H2 = style("H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
           spaceBefore=15, spaceAfter=7, textColor=ACCENT)
BODY = style("BODY")
SMALL = style("SMALL", fontSize=8.5, leading=12, textColor=MUTED)
CODE = style("CODE", fontName="Courier-Bold", fontSize=9.5, leading=13.5,
             textColor=INK, spaceAfter=0)
# Narration is the only thing read aloud, so it is the only thing set large.
SAY = style("SAY", fontSize=12, leading=17.5, spaceAfter=9)
CUE = style("CUE", fontName="Helvetica-Bold", fontSize=10, leading=13,
            textColor=colors.white, spaceAfter=0)


def code(text):
    t = Table([[Paragraph(line.replace(" ", "&nbsp;"), CODE)] for line in text.split("\n")],
              colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODEBG),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
    ]))
    return [Spacer(1, 4), t, Spacer(1, 9)]


def callout(text, color=WARN):
    t = Table([[Paragraph(text, style("W", fontSize=9.5, leading=13.5))]],
              colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF0EF")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [Spacer(1, 3), t, Spacer(1, 10)]


def cue(banner, seconds):
    """The on-screen banner the narration is read against."""
    t = Table([[Paragraph(banner, CUE),
                Paragraph(f"{seconds}s", ParagraphStyle(
                    "d", parent=CUE, alignment=2))]],
              colWidths=[143 * mm, 22 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def beat(banner, seconds, lines):
    """One narration beat: the banner, then what to say against it."""
    flow = [cue(banner, seconds), Spacer(1, 7)]
    for ln in lines:
        flow.append(Paragraph(ln, SAY))
    flow.append(Spacer(1, 8))
    return KeepTogether(flow)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(22 * mm, 12 * mm, "Blast Radius — video recording pack")
    canvas.drawRightString(188 * mm, 12 * mm, f"{doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
    canvas.restoreState()


def build():
    doc = BaseDocTemplate(str(OUT), pagesize=A4,
                          leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=20 * mm, bottomMargin=22 * mm,
                          title="Blast Radius — video recording pack",
                          author="Blast Radius")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=footer)])

    s = []

    # ── Part 1: directions ──────────────────────────────────────────────────
    s.append(Paragraph("Video recording pack", H1))
    s.append(Paragraph("Blast Radius — micro1 Agentic Workflows Hackathon, "
                       "deliverable 3", SUB))

    s.append(Paragraph("The workflow", H2))
    s.append(Paragraph(
        "Record the terminal silently, then add the voice afterwards in CapCut. "
        "Decoupling the two means you never have to talk at the speed the "
        "terminal runs, and you can re-do a line without re-recording the "
        "footage. No webcam is needed: the whole video is one terminal window.",
        BODY))

    s.append(Paragraph("Step 1 — record the terminal", H2))
    s.append(Paragraph(
        "Open <b>Git Bash</b> (not PowerShell), maximised. Change into the "
        "repository first -- a bare <font face='Courier-Bold'>./demo.sh</font> "
        "from your home directory just reports 'No such file or directory'. "
        "Start your screen "
        "recorder, run the command below, and stop recording when the GitHub URL "
        "appears. That is about <b>4 minutes 50 seconds</b> of footage.", BODY))
    s += code("cd ~/Documents/projects/Hackerthon   # wherever you cloned it\n"
              "./demo.sh")
    s.append(Paragraph(
        "<b>Windows Game Bar</b> (Win+G) is enough and needs no install. OBS gives "
        "you a tighter crop if you want one.", BODY))
    s.append(Paragraph(
        "Legibility matters more than anything else here: dark theme, font size "
        "around 16–18pt so the text survives 1080p compression.", BODY))

    s += callout(
        "<b>Do not run the demo commands by hand.</b> <font face='Courier-Bold'>"
        "demo.sh</font> writes only to <font face='Courier-Bold'>--mode demo</font> "
        "and deletes it afterwards. Running "
        "<font face='Courier-Bold'>run_oneshot.py --case 08</font> without "
        "<font face='Courier-Bold'>--mode</font> overwrites the committed baseline "
        "result and silently changes the numbers in your own changelog. That "
        "happened once already while this script was being checked.")

    s.append(Paragraph("Rehearse it first", H2))
    s.append(Paragraph(
        "Run the whole thing in about fifteen seconds to check every beat renders "
        "on your machine before you start recording:", BODY))
    s += code("SPEED=20 ./demo.sh")   # from inside the repo

    s.append(Paragraph("Step 2 — lay the voice over it", H2))
    s.append(Paragraph(
        "Drop the footage into CapCut and record the narration against it. Each "
        "beat overleaf names the blue banner you will see on screen, and its "
        "duration. Read the lines while that banner is up — every hold is sized "
        "for its narration with slack, so you are trimming rather than rushing. "
        "Word counts assume roughly 150 words per minute.", BODY))


    s.append(PageBreak())

    # ── Part 2: the script ──────────────────────────────────────────────────
    s.append(Paragraph("The voiceover script", H1))
    s.append(Paragraph("Read each block against the blue banner named above it. "
                       "Durations are how long that banner stays on screen.", SUB))

    s.append(beat("A pull request against production infrastructure", 20, [
        "This is a pull request against production infrastructure. It says: "
        "enable encryption at rest on the production database, to close a SOC 2 "
        "finding.",
        "It's a security improvement. It's correct. And it's one line.",
    ]))

    s.append(beat("The entire change", 20, [
        "That's the whole change. <font face='Courier-Bold'>storage_encrypted"
        "</font>, false to true.",
        "Merging it destroys the database. That attribute is immutable on RDS, so "
        "Terraform satisfies the line by deleting the instance and creating a new "
        "empty one. Nothing in the diff says so.",
        "Whoever approves this is the last checkpoint before production. This is "
        "exactly what they're there to catch.",
    ]))

    s.append(beat("The baseline: a static scanner, scored generously", 16, [
        "The tool most teams already have is a static scanner. Here's Checkov "
        "across fifteen labelled pull requests — scored generously, restricted to "
        "the resources each change actually touches, which is better than it does "
        "in CI.",
        "F1 of 0.32.",
    ]))

    s.append(beat("What the scanner says about case 08", 18, [
        "It does flag the database. For missing log exports.",
        "The right resource, an entirely unrelated reason, and nothing at all "
        "about the deletion. Unscoped in real CI it reports nine point six "
        "findings on every pull request whatever changed, which is why nobody "
        "reads it.",
    ]))

    s.append(beat("The agent: one prompt, the diff, Haiku 4.5 on Bedrock", 12, [
        "So here's the agent. One prompt — the diff, the pull request "
        "description, and instructions to report at most five findings and stay "
        "quiet about things that don't matter. Claude Haiku 4.5 through Bedrock. "
        "No plan, no tools, no retries.",
    ]))

    s.append(beat("The finding", 30, [
        "Verdict: block. One finding, on the database, categorised "
        "<b>data-loss</b>.",
        "<i>“AWS does not support modifying storage_encrypted in place on an "
        "existing RDS instance. Terraform will destroy the current database and "
        "create a new one, resulting in data loss unless migrated via snapshot "
        "first. The PR description misrepresents this as a one-line configuration "
        "fix.”</i>",
        "Ten seconds, six tenths of a cent. And it got there from the diff alone "
        "— it knew that attribute is immutable without ever being shown the plan.",
    ]))

    s.append(beat("Iteration 1: add the terraform plan. Same case.", 40, [
        "Which brings me to the thing this project was built around, and cut.",
        "The premise was that a reviewer needs the plan, because the diff doesn't "
        "say what will happen. So iteration one adds it — same model, same prompt, "
        "same code path, one flag.",
        "Same case. Still blocked. Still the right resource. Look at the category.",
        "Without the plan: <b>data-loss</b> — it will destroy the database.",
        "With the plan: <b>reliability</b> — the application will lose "
        "connectivity for ten to thirty minutes.",
        "Downtime. Not data loss. Shown a plan that says <i>delete</i> then "
        "<i>create</i>, it reasoned about the resource lifecycle and stopped "
        "reasoning about what was inside it.",
    ]))

    s.append(beat("Across all fifteen cases", 14, [
        "Across all fifteen cases: 0.78 without the plan, 0.67 with it. The plan "
        "is strictly more accurate than the diff, and it made the review worse. We "
        "removed it.",
    ]))

    s.append(beat("The same configuration, run four times, unchanged", 40, [
        "The change that contributed most to this project didn't improve the "
        "agent at all. It's this.",
        "Same configuration. Run four times. Unchanged.",
        "0.90. 0.74. 0.76. 0.74.",
        "For most of this project I reported 0.90 — and 0.90 was the best of four. "
        "I had already written up four separate iterations as regressions against "
        "it, each with a plausible mechanism, each committed.",
        "Three of those four evaporated. They were inside the noise. My best story "
        "— that giving the agent a cost table made it stop reporting cost — died "
        "right here: one baseline run dropped that finding too, with no cost table "
        "anywhere.",
        "Twelve minutes and thirty-three cents. It should have been the second "
        "measurement in this project, not the twenty-second.",
    ]))

    s.append(beat("Everything measured", 46, [
        "So here's everything, with the three regressions re-run four times each "
        "so they're compared distribution against distribution.",
        "Nothing beat one prompt. Three additions made it measurably worse; the "
        "other three couldn't be distinguished from doing nothing.",
        "The worst was the most capable thing I built — an agent with tools, the "
        "plan, the scanner, unlimited steps. Nineteen times the cost, and it "
        "wandered: reviewing a load balancer change, it reported a finding about "
        "the database, because it could read the whole directory and did.",
        "Two things I'd take forward.",
        "Every context you add to fix a blind spot also tells the model that blind "
        "spot is someone else's job now. The plan made the review about resource "
        "lifecycles. The scanner made it about security. The cost table made the "
        "money look already accounted for.",
        "And a single run is not a measurement. Structured outputs, fixed prompts, "
        "deterministic scoring — everything downstream of the model was "
        "reproducible, which quietly convinced me the model was too. Measure your "
        "noise floor first, and refuse to interpret any difference smaller than it.",
    ]))

    s.append(beat("github.com/Jamesokooboh/blast-radius", 8, [
        "Fifteen labelled cases, twenty-four configurations, about ten dollars end "
        "to end. The four-minute version is in the README.",
    ]))

    s.append(Paragraph("Notes for the edit", H2))
    for note in [
        "The strongest shot is the two case 08 findings on screen together, with "
        "<b>DATA-LOSS</b> and <b>RELIABILITY</b> both visible. It holds for forty "
        "seconds; use them.",
        "The four variance numbers print one at a time, three seconds apart. The "
        "beat lands on the fourth.",
        "Do not smooth over the retraction. A project that withdrew four of its "
        "own findings is more credible than one that reported eight.",
        "Model output is not deterministic. The live run in the footage will not "
        "match the committed file word for word, and may return a different number "
        "of findings — which is why the narration reads the committed result while "
        "the live run is only shown executing. If a take contradicts the committed "
        "result, say so rather than re-shooting until it agrees. That is the whole "
        "point of the variance section.",
        "If it runs long, cut the scanner section to one sentence over the 0.32. "
        "It is the only compressible part.",
    ]:
        s.append(Paragraph(f"•&nbsp;&nbsp;{note}", BODY))

    s.append(Spacer(1, 6))
    s.append(Paragraph("What the video has to cover", H2))  # keep with its table
    req = Table([
        [Paragraph("<b>The brief asks for</b>", SMALL),
         Paragraph("<b>Where it happens</b>", SMALL)],
        [Paragraph("The problem and simple baseline", BODY),
         Paragraph("Beats 1–4", BODY)],
        [Paragraph("One realistic execution, start to finish", BODY),
         Paragraph("Beats 5–6", BODY)],
        [Paragraph("One experiment you removed", BODY),
         Paragraph("Beats 7–8 — the terraform plan", BODY)],
        [Paragraph("The change that contributed most", BODY),
         Paragraph("Beat 9 — the variance check", BODY)],
        [Paragraph("The final comparison and changelog", BODY),
         Paragraph("Beat 10", BODY)],
    ], colWidths=[85 * mm, 80 * mm])
    req.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    s.append(KeepTogether([req]))

    doc.build(s)
    print(f"  wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    build()
