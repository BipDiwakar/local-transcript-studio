from __future__ import annotations

from datetime import datetime
from io import BytesIO

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def build_export_header(filename: str, language: str, created_at: datetime) -> str:
    return (
        f"Title: {filename}\n"
        f"Selected language: {language}\n"
        f"Date/time: {created_at.strftime('%Y-%m-%d %H:%M')}\n"
    )


def txt_bytes(filename: str, language: str, text: str, created_at: datetime) -> bytes:
    content = f"{build_export_header(filename, language, created_at)}\nTranscription:\n\n{text}\n"
    return content.encode("utf-8")


def docx_bytes(filename: str, language: str, text: str, created_at: datetime) -> bytes:
    document = Document()
    document.add_heading(filename, level=1)
    document.add_paragraph(f"Selected language: {language}")
    document.add_paragraph(f"Date/time: {created_at.strftime('%Y-%m-%d %H:%M')}")
    document.add_heading("Transcription", level=2)
    for paragraph in text.splitlines() or [""]:
        document.add_paragraph(paragraph)

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output.read()


def pdf_bytes(filename: str, language: str, text: str, created_at: datetime) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(filename, styles["Title"]),
        Paragraph(f"Selected language: {language}", styles["Normal"]),
        Paragraph(f"Date/time: {created_at.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
        Spacer(1, 16),
        Paragraph("Transcription", styles["Heading2"]),
    ]

    paragraphs = [part.strip() for part in text.split("\n") if part.strip()] or [" "]
    for paragraph in paragraphs:
        escaped = paragraph.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(escaped, styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    output.seek(0)
    return output.read()
