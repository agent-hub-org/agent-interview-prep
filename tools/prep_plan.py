"""Generate a structured 30-day interview preparation plan as a PDF or markdown."""
import logging
import os
import uuid
from datetime import datetime, timezone
from langchain_core.tools import tool
from agent_sdk.utils.pdf import MarkdownPDFRenderer, slugify

logger = logging.getLogger("agent_interview_prep.tools.prep_plan")

_BASE_URL = (os.getenv("BACKEND_URL") or os.getenv("PUBLIC_URL") or "").rstrip("/")
_pdf_renderer = MarkdownPDFRenderer()


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
    slug = slugify(f"{target_company or 'interview'}-{role or 'prep'}-{days}day")

    filename = f"{timestamp}_{slug}.{'pdf' if format == 'pdf' else 'md'}"

    try:
        if format == "pdf":
            file_bytes = _pdf_renderer.render(content, title)
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
