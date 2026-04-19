"""Generate a structured 30-day interview preparation plan as a PDF or markdown."""
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool

logger = logging.getLogger("agent_interview_prep.tools.prep_plan")

_BASE_URL = (os.getenv("BACKEND_URL") or os.getenv("PUBLIC_URL") or "").rstrip("/")

_UNICODE_TO_ASCII = str.maketrans({
    "≤": "<=", "≥": ">=", "≠": "!=", "→": "->", "•": "*",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2014": "--", "\u2013": "-",
})


def _sanitize(text: str) -> str:
    return text.translate(_UNICODE_TO_ASCII)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60]


def _create_pdf_bytes(title: str, content: str) -> bytes:
    from fpdf import FPDF

    title = _sanitize(title)
    content = _sanitize(content)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_fill_color(20, 80, 160)
    pdf.rect(0, 0, 210, 18, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_xy(10, 4)
    pdf.cell(0, 10, "Interview Prep Plan — Agent Hub")

    # Title
    pdf.set_text_color(20, 20, 20)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_xy(10, 24)
    pdf.multi_cell(190, 10, title, align="C")
    pdf.ln(4)

    pdf.set_draw_color(20, 80, 160)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    pdf.set_font("Helvetica", size=11)
    pdf.set_text_color(20, 20, 20)

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.ln(4)
            pdf.multi_cell(0, 10, stripped[2:])
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.ln(3)
            pdf.multi_cell(0, 9, stripped[3:])
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(2)
            pdf.multi_cell(0, 8, stripped[4:])
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("**Day ") or stripped.startswith("- Day "):
            pdf.set_font("Helvetica", "B", 11)
            plain = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped.lstrip("- "))
            pdf.multi_cell(0, 7, plain)
            pdf.set_font("Helvetica", size=11)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            bullet = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped[2:])
            pdf.set_x(14)
            pdf.multi_cell(0, 6, f"• {bullet}")
        elif stripped.startswith("> "):
            quote = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped[2:])
            pdf.set_fill_color(230, 245, 255)
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_x(14)
            pdf.multi_cell(180, 6, quote, fill=True)
            pdf.set_font("Helvetica", size=11)
            pdf.ln(1)
        elif stripped:
            plain = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)
            plain = re.sub(r"\*(.*?)\*", r"\1", plain)
            pdf.multi_cell(0, 6, plain)
        else:
            pdf.ln(3)

    return pdf.output()


@tool
async def generate_prep_plan(
    title: str,
    content: str,
    target_company: str = "",
    role: str = "",
    days: int = 30,
    format: str = "pdf",
) -> str:
    """Generate a downloadable structured interview preparation plan.

    Args:
        title: Plan title, e.g. "30-Day Google L5 SWE Prep Plan".
        content: Full markdown content of the plan, organized by week/day.
                 Include daily topics, resources, practice exercises, and milestones.
        target_company: Company being prepared for (e.g. "Google", "Amazon").
        role: Target role (e.g. "Senior Software Engineer", "Data Scientist").
        days: Total preparation days (e.g. 30, 60, 90).
        format: "pdf" or "markdown". Defaults to "pdf".
    """
    from database.mongo import MongoDB

    file_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = _slugify(f"{target_company or 'interview'}-{role or 'prep'}-{days}day")

    filename = f"{timestamp}_{slug}.{'pdf' if format == 'pdf' else 'md'}"

    try:
        if format == "pdf":
            file_bytes = _create_pdf_bytes(title, content)
        else:
            meta_header = ""
            if target_company or role:
                meta_header = f"**Company:** {target_company or 'General'}  |  **Role:** {role or 'General'}  |  **Duration:** {days} days\n\n"
            file_bytes = (f"# {title}\n\n{meta_header}{content}").encode("utf-8")

        await MongoDB.store_file(
            file_id=file_id,
            filename=filename,
            data=file_bytes,
            file_type="prep_plan",
        )

        logger.info("Generated prep plan: file_id='%s', days=%d, format='%s'", file_id, days, format)

        return (
            f"Prep plan generated!\n\n"
            f"**Title:** {title}\n"
            f"**Duration:** {days} days\n"
            f"**Format:** {format.upper()}\n"
            f"**Download:** [Download Plan: {title}]({_BASE_URL}/download/{file_id})"
        )

    except Exception as e:
        logger.error("Failed to generate prep plan: %s", e)
        return f"Error generating prep plan: {e}. Retry with format='markdown'."
